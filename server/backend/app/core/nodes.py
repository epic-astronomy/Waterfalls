"""
Per-node imaging databases and their archive.

Each worker's imager writes the data of the band it images (epic_pixels,
epic_img_metadata2, epic_files_metadata2, epic_daily_digest) to a PostgreSQL
on its own disk. A curator moves the older partitions of these tables to an
archive on the head node, into tables with the same columns (the names are
in the EPIC_ARCHIVE_* settings).

Queries on these tables go to every node, or for one band to the nodes
holding it, in parallel, and to the archive when the requested time range
reaches below the nodes' boundary, the time from which their data are local
(plus an overlap, so that a partition moved after the boundary was read is
still found). The nodes are always asked for the whole range. The rows are
merged here, and a row present in both tiers, as in a partition caught
mid-move, is returned once. A node or archive that does not answer drops out
of the result, which says so (`missing`, `bands_missing`, `archive_missing`),
so a page can show what it lacks instead of failing.

The band held by each node is read from its session table (the distinct
chan0 of epic_img_metadata2) and cached, or fixed by configuration. A band no
node is known to hold is asked of every node.
"""

from __future__ import annotations

import logging
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.visitors import replacement_traverse

log = logging.getLogger(__name__)

MISSING_NODES_HEADER = "X-EPIC-Nodes-Missing"
MISSING_BANDS_HEADER = "X-EPIC-Bands-Missing"
ARCHIVE_MISSING_HEADER = "X-EPIC-Archive-Missing"
# the imager's per-node tables, any of which the curator may archive
NODE_TABLES = ("epic_pixels", "epic_img_metadata2", "epic_files_metadata2", "epic_daily_digest")


@dataclass(frozen=True)
class Node:
    name: str
    host: str
    port: int = 5432
    dbname: str = "epic"
    user: str = ""
    password: str = field(default="", repr=False)
    archive: bool = False  # the head node's archive of older per-node data

    def url(self) -> URL:
        return URL.create("postgresql+psycopg2", username=self.user or None, password=self.password or None,
                          host=self.host, port=self.port, database=self.dbname)


class NodeUnavailable(Exception):
    """Some nodes (or the archive) that may hold the requested data did not answer"""

    def __init__(self, names: Iterable[str]):
        self.names = sorted(names)
        super().__init__(f"Nodes unavailable: {', '.join(self.names)}")


def _hashable(v):
    if isinstance(v, (list, tuple)):
        return tuple(_hashable(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _hashable(x)) for k, x in v.items()))
    return v


def row_key(row) -> tuple:
    """A row's identity when merging the tiers: its values other than binary
    ones (pixel values), which are the same in both copies of a row"""
    return tuple(_hashable(v) for v in row if not isinstance(v, (bytes, bytearray, memoryview)))


def dedupe(rows: Iterable) -> list:
    seen, out = set(), []
    for r in rows:
        k = row_key(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


@dataclass
class FanOut:
    """The answers of the nodes (and the archive) that responded, by name,
    and what did not answer"""
    results: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    bands_missing: list[int] = field(default_factory=list)
    # the archive was needed and did not answer; data older than
    # archive_before (when known) are missing
    archive_missing: bool = False
    archive_before: datetime | None = None
    archive_name: str | None = None  # the archive's key in results, when it was asked

    def ordered(self) -> list[str]:
        """Names of the answers, the nodes first and the archive last"""
        return sorted(n for n in self.results if n != self.archive_name) + (
            [self.archive_name] if self.archive_name in self.results else [])

    def rows(self, key: Callable[[Any], Any] | None = None) -> list:
        """All rows, the nodes' first, each row once: by `key`, or by its
        values other than binary ones (a row copied to the archive is equal)"""
        rows = (r for name in self.ordered() for r in (self.results[name] or []))
        if key is None:
            return dedupe(rows)
        seen, out = set(), []
        for r in rows:
            k = key(r)
            if k not in seen:
                seen.add(k)
                out.append(r)
        return out

    def flags(self) -> dict:
        return dict(nodes_missing=self.missing, bands_missing=self.bands_missing,
                    archive_missing=self.archive_missing, archive_before=self.archive_before)

    def set_headers(self, response) -> None:
        """Name the missing nodes, their bands and a missing archive in the
        response headers, for responses whose body is a plain list"""
        if response is None:
            return
        if self.missing:
            response.headers[MISSING_NODES_HEADER] = ",".join(self.missing)
        if self.bands_missing:
            response.headers[MISSING_BANDS_HEADER] = ",".join(str(b) for b in self.bands_missing)
        if self.archive_missing:
            # the time before which data are missing, or "true" when unknown
            response.headers[ARCHIVE_MISSING_HEADER] = (
                self.archive_before.isoformat() if self.archive_before else "true")


def parse_nodes(entries: Iterable[str], port: int = 5432, dbname: str = "epic", user: str = "",
                password: str = "") -> list[Node]:
    """Nodes from "name=host" or "name=host:port" entries"""
    nodes = []
    for entry in entries:
        name, _, addr = entry.partition("=")
        if not addr:
            name, addr = entry.split(":")[0], entry
        host, _, p = addr.strip().partition(":")
        nodes.append(Node(name=name.strip(), host=host, port=int(p) if p else port, dbname=dbname, user=user,
                          password=password))
    return nodes


def parse_bands(entries: Iterable[str]) -> dict[int, list[str]]:
    """chan0 -> node names from "chan0=node" entries"""
    out: dict[int, list[str]] = {}
    for entry in entries:
        chan0, _, name = entry.partition("=")
        out.setdefault(int(chan0), []).append(name.strip())
    return out


def parse_pairs(entries: Iterable[str]) -> dict[str, str]:
    """name -> value from "name=value" entries, without blank values"""
    return {k.strip(): v.strip() for k, _, v in (e.partition("=") for e in entries) if v.strip()}


class Rows(list):
    """Rows from one or more nodes, read like a SQLAlchemy result"""

    def all(self) -> list:
        return list(self)

    def first(self):
        return self[0] if self else None

    def scalar(self):
        return self[0][0] if self else None


class ArchiveNames:
    """How a per-node query reads the archive: the node tables' names in the
    node schema become the archive tables' names in the archive schema"""

    def __init__(self, node_schema: str, archive_schema: str, tables: dict[str, str]):
        self.node_schema = node_schema
        self.archive_schema = archive_schema
        self.tables = dict(tables)
        self._copies: dict[int, Table] = {}
        self._metadata = MetaData()

    def _pattern(self, name: str) -> str:
        return rf"\b{re.escape(self.node_schema)}\.{re.escape(name)}\b"

    def sql(self, sql: str) -> str | None:
        """SQL text for the archive, or None if it reads a table not archived"""
        names = [t for t in NODE_TABLES if re.search(self._pattern(t), sql)]
        if not names or any(n not in self.tables for n in names):
            return None
        for n in names:
            sql = re.sub(self._pattern(n), f"{self.archive_schema}.{self.tables[n]}", sql)
        return sql

    def statement(self, stmt):
        """A statement (SQLAlchemy, text or a string) for the archive, or None"""
        if isinstance(stmt, str):
            return self.sql(stmt)
        if isinstance(stmt, TextClause):
            sql = self.sql(stmt.text)
            return None if sql is None else text(sql)
        unmapped: list[str] = []
        found: list[str] = []

        def replace(e):
            if isinstance(e, Table):
                return self._copy(e, unmapped, found)
            table = getattr(e, "table", None)
            if isinstance(table, Table) and hasattr(e, "name"):
                copy = self._copy(table, unmapped, found)
                return copy.c[e.name] if copy is not None else None
            return None

        out = replacement_traverse(stmt, {}, replace)
        return None if unmapped or not found else out

    def _copy(self, table: Table, unmapped: list, found: list) -> Table | None:
        if table.schema != self.node_schema or table.name not in NODE_TABLES:
            return None
        if table.name not in self.tables:
            unmapped.append(table.name)
            return None
        found.append(table.name)
        if id(table) not in self._copies:
            self._copies[id(table)] = table.to_metadata(self._metadata, schema=self.archive_schema,
                                                        name=self.tables[table.name])
        return self._copies[id(table)]


def _first_line(e: Exception) -> str:
    return (str(e).splitlines() or [type(e).__name__])[0]


def _is_undefined_table(e: Exception) -> bool:
    return getattr(getattr(e, "orig", e), "pgcode", None) == "42P01"


class NodeSet:
    def __init__(self, nodes: list[Node], *, schema: str = "sevilleta", connect_timeout_s: int = 3,
                 statement_timeout_ms: int = 20000, query_timeout_s: float = 25.0, retry_s: float = 30.0,
                 bands_cache_s: float = 300.0, band_overrides: dict[int, list[str]] | None = None,
                 engine_factory: Callable[..., Engine] | None = None,
                 head: Node | None = None, archive_names: ArchiveNames | None = None,
                 boundary_mode: str = "node_oldest", boundary_column: str = "epic_pixels.img_time",
                 catalogue_sql: str = "", boundary_cache_s: float = 120.0, overlap_s: float = 86400.0):
        self.nodes = list(nodes)
        self.by_name = {n.name: n for n in self.nodes}
        self.schema = schema
        self.connect_timeout_s = connect_timeout_s
        self.statement_timeout_ms = statement_timeout_ms
        self.query_timeout_s = query_timeout_s
        self.retry_s = retry_s
        self.bands_cache_s = bands_cache_s
        self.band_overrides = band_overrides or {}
        self._engine_factory = engine_factory or self._create_engine
        self._engines: dict[tuple[str, int], Engine] = {}
        self._down_until: dict[str, float] = {}
        self._bands: dict[int, list[str]] | None = None
        self._bands_at = 0.0
        self._bands_ttl = bands_cache_s
        # the archive tier
        self.head = head if head is not None and archive_names is not None else None
        self.archive_names = archive_names or ArchiveNames(schema, schema, {})
        self.boundary_mode = boundary_mode
        self.boundary_column = boundary_column
        self.catalogue_sql = catalogue_sql
        self.boundary_cache_s = boundary_cache_s
        self.overlap = timedelta(seconds=overlap_s)
        self._boundaries: dict[str, datetime | None] | None = None
        self._boundaries_at = 0.0
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(8, 4 * (len(self.nodes) + 1)),
                                        thread_name_prefix="epic-node")

    @classmethod
    def from_settings(cls, settings) -> "NodeSet":
        user = settings.EPIC_NODE_USER or settings.POSTGRES_USER
        password = settings.EPIC_NODE_PASSWORD if settings.EPIC_NODE_USER else settings.POSTGRES_PASSWORD
        head = None
        if settings.EPIC_ARCHIVE_ENABLED:
            head = Node(
                name=settings.EPIC_ARCHIVE_NAME,
                host=settings.EPIC_ARCHIVE_HOST or settings.POSTGRES_HOST,
                port=settings.EPIC_ARCHIVE_PORT or settings.POSTGRES_PORT,
                dbname=settings.EPIC_ARCHIVE_DB or settings.POSTGRES_DB,
                user=settings.EPIC_ARCHIVE_USER or settings.POSTGRES_USER,
                password=settings.EPIC_ARCHIVE_PASSWORD if settings.EPIC_ARCHIVE_USER else settings.POSTGRES_PASSWORD,
                archive=True,
            )
        return cls(
            parse_nodes(settings.EPIC_NODES, settings.EPIC_NODE_PORT, settings.EPIC_NODE_DB, user, password),
            schema=settings.EPIC_DATA_SCHEMA,
            connect_timeout_s=settings.EPIC_NODE_CONNECT_TIMEOUT_S,
            statement_timeout_ms=settings.EPIC_NODE_STATEMENT_TIMEOUT_MS,
            query_timeout_s=settings.EPIC_NODE_QUERY_TIMEOUT_S,
            retry_s=settings.EPIC_NODE_RETRY_S,
            bands_cache_s=settings.EPIC_NODE_BANDS_CACHE_S,
            band_overrides=parse_bands(settings.EPIC_NODE_BANDS),
            head=head,
            archive_names=ArchiveNames(settings.EPIC_DATA_SCHEMA, settings.EPIC_ARCHIVE_SCHEMA,
                                       parse_pairs(settings.EPIC_ARCHIVE_TABLES)),
            boundary_mode=settings.EPIC_ARCHIVE_BOUNDARY,
            boundary_column=settings.EPIC_ARCHIVE_BOUNDARY_TABLE,
            catalogue_sql=settings.EPIC_ARCHIVE_CATALOGUE_SQL,
            boundary_cache_s=settings.EPIC_ARCHIVE_BOUNDARY_CACHE_S,
            overlap_s=settings.EPIC_ARCHIVE_OVERLAP_S,
        )

    # connections

    def _create_engine(self, node: Node, statement_timeout_ms: int) -> Engine:
        return create_engine(
            node.url(),
            pool_size=2, max_overflow=6, pool_pre_ping=True, pool_recycle=600, pool_timeout=self.connect_timeout_s,
            connect_args=dict(
                connect_timeout=self.connect_timeout_s,
                application_name="waterfalls",
                # reads only; a statement that runs too long is ended by the server
                options=f"-c statement_timeout={int(statement_timeout_ms)} -c default_transaction_read_only=on",
            ),
        )

    def engine(self, node: Node, statement_timeout_ms: int | None = None) -> Engine:
        key = (node.name, int(statement_timeout_ms or self.statement_timeout_ms))
        with self._lock:
            if key not in self._engines:
                self._engines[key] = self._engine_factory(node, key[1])
            return self._engines[key]

    def is_down(self, node: Node) -> bool:
        return self._down_until.get(node.name, 0.0) > time.monotonic()

    def mark_down(self, node: Node) -> None:
        self._down_until[node.name] = time.monotonic() + self.retry_s

    @contextmanager
    def connect(self, node: Node, statement_timeout_ms: int | None = None):
        """A connection to one node (or the archive); one that cannot be
        reached raises NodeUnavailable and is skipped for EPIC_NODE_RETRY_S"""
        if self.is_down(node):
            raise NodeUnavailable([node.name])
        try:
            conn = self.engine(node, statement_timeout_ms).connect()
        except Exception as e:
            log.warning("Node %s (%s:%s) unreachable: %s", node.name, node.host, node.port, _first_line(e))
            self.mark_down(node)
            raise NodeUnavailable([node.name]) from e
        try:
            yield conn
        finally:
            conn.close()

    # fan-out

    def _call(self, node: Node, fn: Callable, statement_timeout_ms: int | None):
        with self.connect(node, statement_timeout_ms) as conn:
            return fn(conn)

    def run_jobs(self, jobs: list[tuple[Node, Callable[[Any], Any]]], timeout_s: float | None = None,
                 statement_timeout_ms: int | None = None, _discovering: bool = False) -> FanOut:
        """fn(connection) on each job's node in parallel. A failing archive
        sets archive_missing; a table the archive lacks reads as empty (it is
        not archived)."""
        out = FanOut()
        futures = {}
        failed: list[Node] = []
        for node, fn in jobs:
            if self.is_down(node):
                failed.append(node)
            else:
                futures[self._pool.submit(self._call, node, fn, statement_timeout_ms)] = node
        limit = timeout_s or self.query_timeout_s
        done, pending = wait(futures, timeout=limit)
        for f in done:
            node = futures[f]
            try:
                out.results[node.name] = f.result()
            except NodeUnavailable:
                failed.append(node)
            except Exception as e:
                if node.archive and _is_undefined_table(e):
                    log.debug("Archive table missing: %s", _first_line(e))
                    out.results[node.name] = []
                    continue
                log.warning("Query on node %s failed: %s", node.name, _first_line(e))
                failed.append(node)
        for f in pending:
            node = futures[f]
            log.warning("Node %s did not answer in %.1f s", node.name, limit)
            f.cancel()
            failed.append(node)
        for node, _ in jobs:
            if node.archive:
                out.archive_name = node.name
        for node in failed:
            if node.archive:
                out.archive_missing = True
            else:
                out.missing.append(node.name)
        out.missing.sort()
        if not _discovering:
            if out.missing:
                if self._bands is None:
                    self.band_map()  # the bands of the nodes that answer, at least
                out.bands_missing = self.bands_of(out.missing)
            if out.archive_missing:
                out.archive_before = self.archive_before([n for n, _ in jobs if not n.archive])
        return out

    def run(self, fn: Callable[[Any], Any], nodes: Iterable[Node] | None = None, timeout_s: float | None = None,
            statement_timeout_ms: int | None = None, _discovering: bool = False) -> FanOut:
        """fn(connection) on every node (or the given ones) in parallel, without the archive"""
        nodes = list(self.nodes if nodes is None else nodes)
        return self.run_jobs([(n, fn) for n in nodes], timeout_s, statement_timeout_ms, _discovering)

    def query(self, statement, params: dict | None = None, nodes: Iterable[Node] | None = None,
              timeout_s: float | None = None) -> FanOut:
        """Rows of one statement on every node (or the given ones), without the archive"""
        stmt = text(statement) if isinstance(statement, str) else statement
        return self.run(lambda conn: conn.execute(stmt, params or {}).all(), nodes, timeout_s)

    def query_tiers(self, statement, params: dict | None = None, nodes: Iterable[Node] | None = None,
                    since: datetime | None = None, timeout_s: float | None = None) -> FanOut:
        """Rows of one statement on every node (or the given ones) and, when
        it may hold some, on the archive. `since` is the start of the time
        range the statement asks for, if it has one; the archive is read only
        if the range reaches below the nodes' boundary."""
        nodes = list(self.nodes if nodes is None else nodes)
        stmt = text(statement) if isinstance(statement, str) else statement
        jobs = [(n, lambda conn: conn.execute(stmt, params or {}).all()) for n in nodes]
        if self.archive_needed(nodes, since):
            head_stmt = self.archive_names.statement(stmt)
            if head_stmt is not None:
                jobs.append((self.head, lambda conn: conn.execute(head_stmt, params or {}).all()))
        return self.run_jobs(jobs, timeout_s)

    def query_range(self, statement_for: Callable[[datetime, datetime], Any], chan0: int | None,
                    t0: datetime, t1: datetime, timeout_s: float | None = None) -> FanOut:
        """Rows over the time range [t0, t1] of the statement built by
        statement_for(t0, t1): from the nodes holding the band (every node
        without one) over the whole range, and from the archive over the part
        of the range below the nodes' boundary"""
        nodes = self.nodes_for_band(chan0) if chan0 is not None else list(self.nodes)
        stmt = statement_for(t0, t1)
        stmt = text(stmt) if isinstance(stmt, str) else stmt
        jobs = [(n, lambda conn: conn.execute(stmt).all()) for n in nodes]
        if self.archive_needed(nodes, t0):
            until = self.archive_until(nodes)
            head_stmt = self.archive_names.statement(statement_for(t0, t1 if until is None else min(t1, until)))
            if head_stmt is not None:
                head_stmt = text(head_stmt) if isinstance(head_stmt, str) else head_stmt
                jobs.append((self.head, lambda conn: conn.execute(head_stmt).all()))
        return self.run_jobs(jobs, timeout_s)

    # the archive's boundary

    def boundaries(self) -> dict[str, datetime | None]:
        """Per node, the time below which its data may be in the archive: its
        oldest row (node_oldest) or the end of what was archived from it
        (catalogue, datetime.min when nothing was). None where unknown, so the
        archive is read for any time."""
        if self.head is None:
            return {}
        now = time.monotonic()
        if self._boundaries is not None and now - self._boundaries_at < self.boundary_cache_s:
            return self._boundaries
        out: dict[str, datetime | None] = {n.name: None for n in self.nodes}
        if self.boundary_mode == "node_oldest":
            table, _, column = self.boundary_column.partition(".")
            fan = self.run(lambda conn: conn.execute(
                text(f"select min({column}) from {self.schema}.{table}")).scalar(), _discovering=True)
            out.update(fan.results)
        elif self.boundary_mode == "catalogue":
            fan = self.run_jobs([(self.head, lambda conn: conn.execute(
                text(self.catalogue_sql.format(schema=self.archive_names.archive_schema))).all())],
                _discovering=True)
            rows = fan.results.get(self.head.name)
            if rows is not None:
                out = {n.name: datetime.min for n in self.nodes}
                bands = self.band_map()
                for key, until in rows:
                    key = str(key)
                    names = [key] if key in self.by_name else bands.get(int(key), []) if key.isdigit() else []
                    for name in names:
                        if until is not None and until > out[name]:
                            out[name] = until
        # mode "none": every boundary unknown, the archive is read for every request
        self._boundaries, self._boundaries_at = out, now
        return out

    def archive_before(self, nodes: Iterable[Node]) -> datetime | None:
        """The oldest known boundary of these nodes: older data come from the archive"""
        known = [b for n in nodes if (b := self.boundaries().get(n.name)) is not None and b != datetime.min]
        return min(known) if known else None

    def archive_until(self, nodes: Iterable[Node]) -> datetime | None:
        """The end of the time range read from the archive for these nodes:
        their latest boundary plus the overlap; None for no limit"""
        values = [self.boundaries().get(n.name) for n in nodes]
        if not values or any(b is None for b in values):
            return None
        latest = max(values)
        return datetime.min if latest == datetime.min else latest + self.overlap

    def archive_needed(self, nodes: Iterable[Node], since: datetime | None) -> bool:
        if self.head is None:
            return False
        until = self.archive_until(list(nodes))
        if until is None:
            return True
        return until != datetime.min and (since is None or since < until)

    # bands

    def band_map(self) -> dict[int, list[str]]:
        """chan0 -> names of the nodes holding data of that band"""
        now = time.monotonic()
        if self._bands is None or now - self._bands_at > self._bands_ttl:
            fan = self.run(lambda conn: conn.execute(
                text(f"select distinct chan0 from {self.schema}.epic_img_metadata2")).all(), _discovering=True)
            bands: dict[int, list[str]] = {}
            for name, rows in sorted(fan.results.items()):
                for (chan0,) in rows:
                    bands.setdefault(int(chan0), []).append(name)
            # bands of nodes that answered before stay known while they are down
            for chan0, names in (self._bands or {}).items():
                for name in names:
                    if name in fan.missing and name not in bands.setdefault(chan0, []):
                        bands[chan0].append(name)
            self._bands = bands
            self._bands_at = now
            # look again soon while a node is missing
            self._bands_ttl = self.retry_s if fan.missing else self.bands_cache_s
        return {**self._bands, **self.band_overrides}

    def nodes_for_band(self, chan0: int) -> list[Node]:
        """The nodes holding a band, or every node if none is known to"""
        names = self.band_map().get(int(chan0))
        if not names:
            return list(self.nodes)
        return [self.by_name[n] for n in names if n in self.by_name] or list(self.nodes)

    def bands_of(self, names: Iterable[str]) -> list[int]:
        """The bands known to be held by these nodes, from the cached map only"""
        names = set(names)
        bands = {**(self._bands or {}), **self.band_overrides}
        return sorted(c for c, held in bands.items() if names & set(held))

    def local_names(self) -> set[str]:
        """Names of the nodes on this host"""
        host = socket.gethostname().split(".")[0]
        addrs = set()
        try:
            addrs = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None)}
        except OSError:
            pass
        return {n.name for n in self.nodes if n.name == host or n.host in addrs}


class BandReader:
    """Reads one band from the nodes that hold it and from the archive,
    through an object with `execute(statement, params)` like a SQLAlchemy
    connection. A statement with datetime parameters :t0 and :t1 reads the
    archive only over the part of [t0, t1) below the nodes' boundary; one
    without them reads the archive whenever the boundary is unknown. The
    rows are merged, each row once, and ordered by their first column.

    strict: a node or archive that cannot be read raises NodeUnavailable (the
    FRB analysis then tries the band again on its next run). Otherwise it is
    left out and reported by `missing` or `archive_missing`."""

    def __init__(self, nodes: NodeSet, chan0: int, strict: bool = True, node_names: Iterable[str] | None = None,
                 statement_timeout_ms: int | None = None):
        self.nodeset = nodes
        band_nodes = nodes.nodes_for_band(chan0)
        extra = [nodes.by_name[n] for n in (node_names or []) if n in nodes.by_name]
        self.nodes = band_nodes + [n for n in extra if n not in band_nodes]
        self.strict = strict
        self.statement_timeout_ms = statement_timeout_ms
        self.missing: list[str] = []
        self.archive_missing = False
        self._conns: dict[str, Any] = {}
        self._head_conn = None
        self._stack: list = []

    def __enter__(self) -> "BandReader":
        for node in self.nodes:
            cm = self.nodeset.connect(node, self.statement_timeout_ms)
            try:
                self._conns[node.name] = cm.__enter__()
                self._stack.append(cm)
            except NodeUnavailable:
                self.missing.append(node.name)
        if self.missing and self.strict:
            self.__exit__(None, None, None)
            raise NodeUnavailable(self.missing)
        return self

    def __exit__(self, *exc) -> None:
        while self._stack:
            self._stack.pop().__exit__(None, None, None)
        self._conns.clear()
        self._head_conn = None

    def _head(self):
        """The archive's connection, opened on first use"""
        if self._head_conn is None and not self.archive_missing:
            cm = self.nodeset.connect(self.nodeset.head, self.statement_timeout_ms)
            try:
                self._head_conn = cm.__enter__()
                self._stack.append(cm)
            except NodeUnavailable:
                if self.strict:
                    raise
                self.archive_missing = True
        return self._head_conn

    def execute(self, statement, params: dict | None = None) -> Rows:
        stmt = text(statement) if isinstance(statement, str) else statement
        params = dict(params or {})
        parts = []
        for name, conn in list(self._conns.items()):
            try:
                parts.append(conn.execute(stmt, params).all())
            except Exception as e:
                if self.strict:
                    raise NodeUnavailable([name]) from e
                log.warning("Query on node %s failed: %s", name, _first_line(e))
                self.missing.append(name)
                del self._conns[name]
        ns = self.nodeset
        since = params.get("t0") if isinstance(params.get("t0"), datetime) else None
        if ns.archive_needed(self.nodes, since):
            head_stmt = ns.archive_names.statement(stmt)
            if head_stmt is not None:
                head_params = dict(params)
                until = ns.archive_until(self.nodes)
                if until is not None and isinstance(params.get("t1"), datetime):
                    head_params["t1"] = min(params["t1"], until)
                conn = self._head()
                if conn is not None:
                    try:
                        parts.append(conn.execute(head_stmt, head_params).all())
                    except Exception as e:
                        conn.rollback()
                        if not _is_undefined_table(e):
                            log.warning("Query on the archive failed: %s", _first_line(e))
                            if self.strict:
                                raise NodeUnavailable([ns.head.name]) from e
                            self.archive_missing = True
        rows = Rows(dedupe(r for part in parts for r in part))
        if sum(1 for p in parts if p) > 1:
            rows.sort(key=lambda r: r[0])
        return rows

    def fan_out(self) -> FanOut:
        """What was missing, in the form of a fan-out result"""
        missing = sorted(set(self.missing))
        return FanOut(missing=missing, bands_missing=self.nodeset.bands_of(missing) if missing else [],
                      archive_missing=self.archive_missing,
                      archive_before=self.nodeset.archive_before(self.nodes) if self.archive_missing else None)


# merging

def sort_rows(rows: list, keys: list[tuple[Callable[[Any], Any], bool]]) -> list:
    """Order rows by several (key, descending) pairs, the first most
    significant, with NULLs as PostgreSQL orders them: last ascending, first
    descending"""
    out = list(rows)
    for key, desc in reversed(keys):
        out.sort(key=lambda r, k=key: (k(r) is None, k(r)), reverse=desc)
    return out


_nodes: NodeSet | None = None
_nodes_lock = threading.Lock()


def get_nodes() -> NodeSet:
    """The node set of this process, from the settings"""
    global _nodes
    with _nodes_lock:
        if _nodes is None:
            from app.core.config import settings
            _nodes = NodeSet.from_settings(settings)
        return _nodes
