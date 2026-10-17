"""Unit tests of the per-node data access layer and the routes that use it,
with fake nodes (no database). Run from server/backend:

    python -m unittest tests.test_nodes
"""

import os

# settings are read at import; any database here is never connected to
os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
os.environ.setdefault("POSTGRES_DB", "unused")
os.environ.setdefault("PROJECT_NAME", "waterfalls-test")
os.environ.setdefault("ENVIRONMENT", "staging")
os.environ.setdefault("EPIC_DATA_SCHEMA", "sevilleta")
# never the real workers: every test replaces the node set with fake nodes
os.environ["EPIC_NODES"] = "nowhere=127.0.0.1:1"

import time
import unittest
import uuid
from collections import namedtuple
from datetime import datetime, timedelta
from unittest import mock

from app.core.nodes import (
    MISSING_BANDS_HEADER, MISSING_NODES_HEADER, BandReader, Node, NodeSet, NodeUnavailable, parse_bands,
    parse_nodes, sort_rows,
)


class FakeResult(list):
    def all(self):
        return list(self)

    def scalar_one(self):
        return self[0][0]

    def scalar(self):
        return self[0][0] if self else None


class FakeConn:
    def __init__(self, node):
        self.node = node

    def execute(self, stmt, params=None):
        self.node.calls.append(str(stmt))
        if self.node.delay:
            time.sleep(self.node.delay)
        if self.node.error_on_query:
            raise RuntimeError("relation does not exist")
        for needle, rows in self.node.answers:
            if needle in str(stmt):
                return FakeResult(rows(params) if callable(rows) else rows)
        return FakeResult([])

    def close(self):
        pass


class FakeNode:
    """A node's database: answers by a substring of the statement"""

    def __init__(self, answers=(), down=False, delay=0.0, error_on_query=False):
        self.answers = list(answers)
        self.down = down
        self.delay = delay
        self.error_on_query = error_on_query
        self.calls: list[str] = []
        self.connects = 0

    def connect(self):
        self.connects += 1
        if self.down:
            raise ConnectionError("could not connect to server")
        return FakeConn(self)


def make_nodeset(fakes: dict[str, FakeNode], **kw) -> NodeSet:
    nodes = [Node(name=n, host=f"{n}.invalid") for n in fakes]
    return NodeSet(nodes, engine_factory=lambda node, timeout: fakes[node.name], **kw)


def bands(*pairs):
    return [("distinct chan0", [(c,) for c in pairs])]


class ParseTest(unittest.TestCase):
    def test_nodes(self):
        nodes = parse_nodes(["epic1=192.168.40.21", "epic2=192.168.40.22:5433"], port=5432, dbname="epic",
                            user="ro", password="pw")
        self.assertEqual([(n.name, n.host, n.port) for n in nodes],
                         [("epic1", "192.168.40.21", 5432), ("epic2", "192.168.40.22", 5433)])
        self.assertEqual(nodes[1].url().render_as_string(hide_password=False),
                         "postgresql+psycopg2://ro:pw@192.168.40.22:5433/epic")
        self.assertNotIn("pw", repr(nodes[1]))

    def test_bands(self):
        self.assertEqual(parse_bands(["672=epic4", "864=epic1", "672=epic2"]),
                         {672: ["epic4", "epic2"], 864: ["epic1"]})

    def test_settings_default(self):
        from app.core.config import Settings
        with mock.patch.dict(os.environ, {"EPIC_NODES": ""}):
            nodes = NodeSet.from_settings(Settings(_env_file=None)).nodes
        self.assertEqual([(n.name, n.host) for n in nodes], [(f"epic{i}", f"192.168.40.{20 + i}") for i in range(1, 7)])


class FanOutTest(unittest.TestCase):
    def test_missing_and_slow_nodes(self):
        fakes = dict(
            a=FakeNode([("select 1", [(1,)])] + bands(672)),
            b=FakeNode(down=True),
            c=FakeNode([("select 1", [(3,)])], delay=1.0),
            d=FakeNode(error_on_query=True),
        )
        ns = make_nodeset(fakes, query_timeout_s=0.3, retry_s=60)
        t0 = time.monotonic()
        fan = ns.query("select 1")
        self.assertLess(time.monotonic() - t0, 0.9)
        self.assertEqual(fan.results, {"a": [(1,)]})
        self.assertEqual(fan.missing, ["b", "c", "d"])
        # an unreachable node is skipped for retry_s, a slow or failing one is not
        self.assertTrue(ns.is_down(ns.by_name["b"]))
        self.assertFalse(ns.is_down(ns.by_name["c"]))
        self.assertFalse(ns.is_down(ns.by_name["d"]))
        connects = fakes["b"].connects
        ns.query("select 1")
        self.assertEqual(fakes["b"].connects, connects)

    def test_band_map(self):
        fakes = dict(a=FakeNode(bands(672)), b=FakeNode(bands(864, 672)), c=FakeNode(bands(1440)))
        ns = make_nodeset(fakes, band_overrides={2400: ["c"]})
        self.assertEqual(ns.band_map(), {672: ["a", "b"], 864: ["b"], 1440: ["c"], 2400: ["c"]})
        self.assertEqual([n.name for n in ns.nodes_for_band(864)], ["b"])
        # a band no node is known to hold is asked of every node
        self.assertEqual([n.name for n in ns.nodes_for_band(3168)], ["a", "b", "c"])
        self.assertEqual(ns.bands_of(["c"]), [1440, 2400])

    def test_band_map_keeps_bands_of_a_node_gone_down(self):
        fakes = dict(a=FakeNode(bands(672)), b=FakeNode(bands(864)))
        ns = make_nodeset(fakes, bands_cache_s=0.0)
        ns.band_map()
        fakes["b"].down = True
        self.assertEqual(ns.band_map(), {672: ["a"], 864: ["b"]})
        fan = ns.query("select 1")
        self.assertEqual((fan.missing, fan.bands_missing), (["b"], [864]))

    def test_sort_rows(self):
        R = namedtuple("R", "a b")
        rows = [R(1, None), R(2, 5), R(1, 3), R(None, 1), R(2, 4)]
        # PostgreSQL order: NULLs last ascending, first descending
        self.assertEqual(sort_rows(rows, [(lambda r: r.a, False), (lambda r: r.b, True)]),
                         [R(1, None), R(1, 3), R(2, 5), R(2, 4), R(None, 1)])
        self.assertEqual(sort_rows(rows, [(lambda r: r.a, True)])[0], R(None, 1))

    def test_band_reader(self):
        rows_a = [(datetime(2026, 1, 1, 0, 0, 2), "a")]
        rows_b = [(datetime(2026, 1, 1, 0, 0, 1), "b")]
        fakes = dict(a=FakeNode([("epic_pixels", rows_a)] + bands(672)),
                     b=FakeNode([("epic_pixels", rows_b)] + bands(672)),
                     c=FakeNode(bands(864)))
        ns = make_nodeset(fakes)
        with BandReader(ns, 672) as reader:
            rows = reader.execute("select * from epic_pixels")
        self.assertEqual([r[1] for r in rows.all()], ["b", "a"])  # merged in time order
        self.assertEqual(fakes["c"].calls, [fakes["c"].calls[0]])  # only the band map query
        fakes["b"].down = True
        with self.assertRaises(NodeUnavailable) as e:
            with BandReader(ns, 672, strict=True):
                pass
        self.assertEqual(e.exception.names, ["b"])
        with BandReader(ns, 672, strict=False) as reader:
            self.assertEqual(len(reader.execute("select * from epic_pixels")), 1)
        self.assertEqual(reader.fan_out().missing, ["b"])


def session_row(start, chan0, n_pol=4, int_time=0.08):
    return dict(session_id=uuid.uuid4(), chan0=chan0, n_chan=64, n_pol=n_pol, chan_bw_hz=47851, int_time=int_time,
                start_time=start, end_time=start + timedelta(hours=1))


class RouteTest(unittest.TestCase):
    """The routes merge the nodes' rows as a single database would have"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.api.deps import get_db
        from app.core.nodes import get_nodes
        from app.main import app
        cls.app, cls.deps = app, dict(nodes=get_nodes)
        app.dependency_overrides[get_db] = lambda: iter([None])
        cls.client = TestClient(app)

    def use(self, fakes):
        ns = make_nodeset(fakes)
        self.app.dependency_overrides[self.deps["nodes"]] = lambda: ns
        return ns

    def tearDown(self):
        self.app.dependency_overrides.pop(self.deps["nodes"], None)

    def test_sessions_paginated_across_nodes(self):
        t0 = datetime(2026, 10, 1)
        S = namedtuple("S", "session_id chan0 n_chan n_pol chan_bw_hz int_time start_time end_time")
        a = [S(**session_row(t0 + timedelta(hours=h), 672)) for h in (0, 2, 4, 6)]
        b = [S(**session_row(t0 + timedelta(hours=h), 864)) for h in (1, 3, 5)]

        def answers(rows):
            return bands(rows[0].chan0) + [("count(", [(len(rows),)]),
                    ("epic_img_metadata2", lambda p: sorted(rows, key=lambda r: r.start_time, reverse=True))]
        self.use(dict(a=FakeNode(answers(a)), b=FakeNode(answers(b)), c=FakeNode(down=True)))
        q = dict(start_time="2026-10-01T00:00:00", end_time="2026-10-02T00:00:00", source_name="sun", nrows=3)
        pages = [self.client.get("/api/v1/imaging/sessions/", params=q | dict(page=p)) for p in (1, 2, 3)]
        for r in pages:
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["count"], 7)
            self.assertEqual(r.json()["nodes_missing"], ["c"])
            self.assertEqual(r.headers[MISSING_NODES_HEADER], "c")
        starts = [s["start_time"] for r in pages for s in r.json()["data"]]
        self.assertEqual(starts, [(t0 + timedelta(hours=h)).isoformat() for h in (6, 5, 4, 3, 2, 1, 0)])
        # sorted by band ascending, then newest first
        r = self.client.get("/api/v1/imaging/sessions/", params=q | dict(page=1, nrows=10, sort="chan0"))
        self.assertEqual([(s["chan0"], s["start_time"][11:13]) for s in r.json()["data"]],
                         [(672, "06"), (672, "04"), (672, "02"), (672, "00"), (864, "05"), (864, "03"), (864, "01")])

    def test_daily_digest_merged(self):
        D = namedtuple("D", "img_time stokes_i stokes_v cfreq")
        t = datetime(2026, 10, 1, 12)
        self.use(dict(
            a=FakeNode([("count(", [(17e6, 2)]), ("stokes_i", [D(t, [1.0], [0.0], 17e6), D(t + timedelta(minutes=3), [2.0], [0.0], 17e6)])]),
            b=FakeNode([("count(", [(22e6, 1)]), ("stokes_i", [D(t, [3.0], [0.0], 22e6)])]),
        ))
        r = self.client.get("/api/v1/imaging/dailydigest/", params=dict(day="2026-10-01", source_name="sun"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["stats"], [dict(cfreq=22e6, count=1), dict(cfreq=17e6, count=2)])
        self.assertEqual([d["stokes_i"] for d in body["data"]], [[3.0], [1.0], [2.0]])
        self.assertEqual(body["nodes_missing"], [])
        self.assertNotIn(MISSING_NODES_HEADER, r.headers)

    def test_spectrogram_goes_to_the_band_node(self):
        P = namedtuple("P", "img_time pixel_values")
        a = FakeNode(bands(672) + [("epic_pixels", [P(datetime(2026, 10, 1), "AAAAAA==")])])
        b = FakeNode(bands(864) + [("epic_pixels", [P(datetime(2026, 10, 1), "BBBBBB==")])])
        self.use(dict(a=a, b=b))
        r = self.client.get("/api/v1/imaging/spectrogram/", params=dict(
            start_time="2026-10-01T00:00:00", end_time="2026-10-01T00:01:00", source_name="sun", chan0=864,
            pixel_positions="{(0,0)}"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["pixel_values"] for p in r.json()], ["BBBBBB=="])
        self.assertFalse(any("epic_pixels" in c for c in a.calls))

    def test_list_endpoint_flags_missing_band_in_header(self):
        ns = self.use(dict(a=FakeNode(bands(672)), b=FakeNode(bands(864))))
        ns.band_map()
        ns.mark_down(ns.by_name["b"])
        r = self.client.get("/api/v1/imaging/dailyobs/days/", params=dict(start="2026-10-01", end="2026-10-02"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])
        self.assertEqual(r.headers[MISSING_NODES_HEADER], "b")
        self.assertEqual(r.headers[MISSING_BANDS_HEADER], "864")


class PipelineTest(unittest.TestCase):
    def test_band_on_a_missing_node_is_deferred(self):
        from app.frb import pipeline
        ns = make_nodeset(dict(a=FakeNode(bands(672)), b=FakeNode(bands(864))))
        ns.band_map()
        ns.mark_down(ns.by_name["b"])
        event = dict(id=1, source="FRB", t_start=datetime(2026, 10, 1), t_end=datetime(2026, 10, 1, 1), dm=100.0,
                     dm_err=1.0, t_inf=datetime(2026, 10, 1), ra=0.0, dec=0.0)
        session = mock.MagicMock()
        with mock.patch.object(pipeline, "get_nodes", return_value=ns), \
                mock.patch.object(pipeline, "load_event", return_value=event):
            with self.assertRaises(NodeUnavailable):
                pipeline.process_band(session, 1, 864)
            session.commit.assert_not_called()
            # a band held by a node that answered and that has no session there is settled
            self.assertEqual(pipeline.process_band(session, 1, 672), "no_session")


if __name__ == "__main__":
    unittest.main()
