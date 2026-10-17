"""
Per-node imaging databases.

Each worker's imager writes the data of the band it images (epic_pixels,
epic_img_metadata2, epic_files_metadata2, epic_daily_digest) to a PostgreSQL
on its own disk. Queries on these tables go to every node, or for one band
to the nodes holding it, in parallel; the rows are merged and ordered here.
A node that does not answer drops out of the result, which lists it in
`missing`, so a page can show what it lacks instead of failing.

The band held by each node is read from its session table (the distinct
chan0 of epic_img_metadata2) and cached, or fixed by configuration. A band no
node is known to hold is asked of every node.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

log = logging.getLogger(__name__)

MISSING_NODES_HEADER = "X-EPIC-Nodes-Missing"
MISSING_BANDS_HEADER = "X-EPIC-Bands-Missing"


@dataclass(frozen=True)
class Node:
    name: str
    host: str
    port: int = 5432
    dbname: str = "epic"
    user: str = ""
    password: str = field(default="", repr=False)

    def url(self) -> URL:
        return URL.create("postgresql+psycopg2", username=self.user or None, password=self.password or None,
                          host=self.host, port=self.port, database=self.dbname)


class NodeUnavailable(Exception):
    """Some nodes that may hold the requested data did not answer"""

    def __init__(self, names: Iterable[str]):
        self.names = sorted(names)
        super().__init__(f"Nodes unavailable: {', '.join(self.names)}")


@dataclass
class FanOut:
    """The answers of the nodes that responded, by node name, and the names
    of those that did not"""
    results: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    bands_missing: list[int] = field(default_factory=list)

    def rows(self) -> list:
        """All nodes' rows, in node order"""
        return [r for name in sorted(self.results) for r in (self.results[name] or [])]

    def flags(self) -> dict:
        return dict(nodes_missing=self.missing, bands_missing=self.bands_missing)

    def set_headers(self, response) -> None:
        """Name the missing nodes and their bands in the response headers,
        for responses whose body is a plain list"""
        if response is None:
            return
        if self.missing:
            response.headers[MISSING_NODES_HEADER] = ",".join(self.missing)
        if self.bands_missing:
            response.headers[MISSING_BANDS_HEADER] = ",".join(str(b) for b in self.bands_missing)


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


class Rows(list):
    """Rows from one or more nodes, read like a SQLAlchemy result"""

    def all(self) -> list:
        return list(self)

    def first(self):
        return self[0] if self else None

    def scalar(self):
        return self[0][0] if self else None


class NodeSet:
    def __init__(self, nodes: list[Node], *, schema: str = "sevilleta", connect_timeout_s: int = 3,
                 statement_timeout_ms: int = 20000, query_timeout_s: float = 25.0, retry_s: float = 30.0,
                 bands_cache_s: float = 300.0, band_overrides: dict[int, list[str]] | None = None,
                 engine_factory: Callable[..., Engine] | None = None):
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
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(8, 4 * len(self.nodes)), thread_name_prefix="epic-node")

    @classmethod
    def from_settings(cls, settings) -> "NodeSet":
        user = settings.EPIC_NODE_USER or settings.POSTGRES_USER
        password = settings.EPIC_NODE_PASSWORD if settings.EPIC_NODE_USER else settings.POSTGRES_PASSWORD
        return cls(
            parse_nodes(settings.EPIC_NODES, settings.EPIC_NODE_PORT, settings.EPIC_NODE_DB, user, password),
            schema=settings.EPIC_DATA_SCHEMA,
            connect_timeout_s=settings.EPIC_NODE_CONNECT_TIMEOUT_S,
            statement_timeout_ms=settings.EPIC_NODE_STATEMENT_TIMEOUT_MS,
            query_timeout_s=settings.EPIC_NODE_QUERY_TIMEOUT_S,
            retry_s=settings.EPIC_NODE_RETRY_S,
            bands_cache_s=settings.EPIC_NODE_BANDS_CACHE_S,
            band_overrides=parse_bands(settings.EPIC_NODE_BANDS),
        )

    # connections

    def _create_engine(self, node: Node, statement_timeout_ms: int) -> Engine:
        return create_engine(
            node.url(),
            pool_size=2, max_overflow=6, pool_pre_ping=True, pool_recycle=600, pool_timeout=self.connect_timeout_s,
            connect_args=dict(
                connect_timeout=self.connect_timeout_s,
                application_name="waterfalls",
                # reads only; a statement that runs too long is ended by the node
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
        """A connection to one node; a node that cannot be reached raises
        NodeUnavailable and is skipped for EPIC_NODE_RETRY_S"""
        if self.is_down(node):
            raise NodeUnavailable([node.name])
        try:
            conn = self.engine(node, statement_timeout_ms).connect()
        except Exception as e:
            log.warning("Node %s (%s:%s) unreachable: %s", node.name, node.host, node.port, str(e).splitlines()[0])
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

    def run(self, fn: Callable[[Any], Any], nodes: Iterable[Node] | None = None, timeout_s: float | None = None,
            statement_timeout_ms: int | None = None, _discovering: bool = False) -> FanOut:
        """fn(connection) on every node (or the given ones) in parallel"""
        nodes = list(self.nodes if nodes is None else nodes)
        out = FanOut()
        futures = {}
        for node in nodes:
            if self.is_down(node):
                out.missing.append(node.name)
            else:
                futures[self._pool.submit(self._call, node, fn, statement_timeout_ms)] = node
        done, pending = wait(futures, timeout=timeout_s or self.query_timeout_s)
        for f in done:
            node = futures[f]
            try:
                out.results[node.name] = f.result()
            except NodeUnavailable:
                out.missing.append(node.name)
            except Exception as e:
                log.warning("Query on node %s failed: %s", node.name, str(e).splitlines()[0])
                out.missing.append(node.name)
        for f in pending:
            node = futures[f]
            log.warning("Node %s did not answer in %.1f s", node.name, timeout_s or self.query_timeout_s)
            f.cancel()
            out.missing.append(node.name)
        out.missing.sort()
        if out.missing and not _discovering:
            if self._bands is None:
                self.band_map()  # the bands of the nodes that answer, at least
            out.bands_missing = self.bands_of(out.missing)
        return out

    def query(self, statement, params: dict | None = None, nodes: Iterable[Node] | None = None,
              timeout_s: float | None = None) -> FanOut:
        """Rows of one statement on every node (or the given ones)"""
        stmt = text(statement) if isinstance(statement, str) else statement
        return self.run(lambda conn: conn.execute(stmt, params or {}).all(), nodes, timeout_s)

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
    """Reads one band from the nodes that hold it, through an object with
    `execute(statement, params)` like a SQLAlchemy connection. With more than
    one node the rows are merged and ordered by their first column.

    strict: a node that cannot be read raises NodeUnavailable (the FRB
    analysis then tries the band again on its next run). Otherwise it is
    left out and listed in `missing`."""

    def __init__(self, nodes: NodeSet, chan0: int, strict: bool = True, node_names: Iterable[str] | None = None,
                 statement_timeout_ms: int | None = None):
        self.nodeset = nodes
        self.nodes = ([nodes.by_name[n] for n in node_names if n in nodes.by_name] if node_names
                      else nodes.nodes_for_band(chan0))
        self.strict = strict
        self.statement_timeout_ms = statement_timeout_ms
        self.missing: list[str] = []
        self._conns: dict[str, Any] = {}
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

    def execute(self, statement, params: dict | None = None) -> Rows:
        stmt = text(statement) if isinstance(statement, str) else statement
        rows = Rows()
        for name, conn in list(self._conns.items()):
            try:
                rows.extend(conn.execute(stmt, params or {}).all())
            except Exception as e:
                if self.strict:
                    raise NodeUnavailable([name]) from e
                log.warning("Query on node %s failed: %s", name, str(e).splitlines()[0])
                self.missing.append(name)
                del self._conns[name]
        if len(self._conns) > 1:
            rows.sort(key=lambda r: r[0])
        return rows

    def fan_out(self) -> FanOut:
        """The missing nodes, in the form of a fan-out result"""
        missing = sorted(set(self.missing))
        return FanOut(missing=missing, bands_missing=self.nodeset.bands_of(missing) if missing else [])


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
