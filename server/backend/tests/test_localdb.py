"""
Integration test of the per-node databases against throwaway PostgreSQL 16
clusters. Run from server/backend on a worker, not on the head node:

    python -m unittest tests.test_localdb

Two clusters are created with initdb in a temporary directory: cluster A
holds node a's database (band 672) and the global database; cluster B holds
node b's (band 864); node c points at a closed port, as a node that is down.
A third database on A, "ref", holds all the data in one place, as the single
Citus coordinator did. The routes of this branch, reading the nodes, must
answer as the code of the main branch does reading "ref"; the FRB analysis
must give the same products and leave a band on a node that is down pending.

PG_BIN names the directory of initdb and pg_ctl, if they are not on the path.
"""

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest import mock

import numpy as np


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pg_bin() -> str | None:
    for d in [os.environ.get("PG_BIN"), "/usr/lib/postgresql/16/bin"]:
        if d and os.path.exists(os.path.join(d, "initdb")):
            return d
    found = shutil.which("initdb")
    return os.path.dirname(found) if found else None


PG_BIN = _pg_bin()
USER = os.environ.get("USER") or "postgres"
PORT_A, PORT_B, PORT_DEAD = _free_port(), _free_port(), _free_port()
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(BACKEND))

# settings of this branch's code: the global database and the three nodes
ENV = dict(
    PROJECT_NAME="waterfalls-test", ENVIRONMENT="staging", EPIC_DATA_SCHEMA="sevilleta",
    POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=str(PORT_A), POSTGRES_USER=USER, POSTGRES_PASSWORD="",
    POSTGRES_DB="head",
    EPIC_NODES=f"a=127.0.0.1:{PORT_A},b=127.0.0.1:{PORT_B},c=127.0.0.1:{PORT_DEAD}",
    EPIC_NODE_DB="epic", EPIC_NODE_CONNECT_TIMEOUT_S="2", EPIC_NODE_RETRY_S="0",
    FRB_DM_HALF_MIN="1.0", FRB_DM_HALF_MAX="1.0", FRB_SLACK_NOTIFY="false",
)
os.environ.update(ENV)

CHAN_BW_HZ = 196e6 / 8192
DAY = datetime(2026, 10, 1)
NOW = datetime.utcnow().replace(microsecond=0)
T_EVENT = NOW - timedelta(hours=2)  # CHIME's arrival at 400 MHz
DM, DM_ERR = 15.0, 0.5
K_DM = 4148.808
INT_TIME = 0.08359183673469386
N_CHAN = 4


class Cluster:
    def __init__(self, root: str, name: str, port: int):
        self.dir = os.path.join(root, name)
        self.port = port
        self.sock = root
        subprocess.run([os.path.join(PG_BIN, "initdb"), "-D", self.dir, "-U", USER, "-A", "trust", "-E", "UTF8",
                        "--no-sync"], check=True, capture_output=True)
        subprocess.run([os.path.join(PG_BIN, "pg_ctl"), "-D", self.dir, "-l", self.dir + ".log", "-w", "-o",
                        f"-p {port} -k {root} -c listen_addresses=127.0.0.1 -c fsync=off", "start"],
                       check=True, capture_output=True)

    def stop(self):
        subprocess.run([os.path.join(PG_BIN, "pg_ctl"), "-D", self.dir, "-m", "immediate", "stop"],
                       capture_output=True)

    def connect(self, db: str):
        import psycopg2
        conn = psycopg2.connect(host="127.0.0.1", port=self.port, user=USER, dbname=db)
        conn.autocommit = True
        return conn

    def create(self, db: str, *schemas: str):
        self.connect("postgres").cursor().execute(f"create database {db}")
        with self.connect(db) as conn:
            for path in schemas:
                conn.cursor().execute(open(os.path.join(BACKEND, "tests", path)).read())


def _f32(values) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes()


def make_data():
    """Rows of the per-node tables, by band, and of the global tables"""
    rng = np.random.default_rng(1)
    sessions = {672: [], 864: []}

    def session(chan0, source, start_h, hours, n_pol=4, n_chan=64, int_time=INT_TIME, start=None):
        s0 = start or DAY + timedelta(hours=start_h)
        sessions.setdefault(chan0, []).append((str(uuid.uuid4()), s0, s0 + timedelta(hours=hours), chan0, n_pol,
                                               n_chan, 47851, "0.19.0", "(128,128)", 25, int_time, source))
    # distinct start times, so every ordering is fully determined
    session(672, "sun", 0.0, 3)
    session(672, "sun", 5.2, 1.8, int_time=0.04)
    session(672, "sun", 12.0, 0.33)  # under 30 minutes: not in the daily list
    session(672, "sun", -20.5, 2, n_chan=32)
    session(864, "sun", 1.0, 3)
    session(864, "sun", 6.0, 3, n_pol=2)
    session(864, "sun", 23.83, 2.2)
    session(864, "sun", 30.0, 1)
    session(864, "crab", 2.5, 4)
    session(128, "sun", 4.0, 1)  # a band outside OBS_CHANS
    session(672, "FRB-X", 0, 2, n_chan=N_CHAN, start=T_EVENT - timedelta(hours=1))

    pixels = {672: [], 864: [], 128: []}
    # a minute of the Sun's 5x5 grid in both bands, with the exact position stored
    for chan0 in (672, 864):
        t = DAY + timedelta(hours=1, minutes=30)
        for i in range(60 * 12):
            for oy in range(-2, 3):
                for ox in range(-2, 3):
                    pixels[chan0].append((t, chan0, f"({60 + ox},{70 + oy})", "(0,0)",
                                          _f32(rng.normal(10, 1, 64 * 4)), f"({ox},{oy})", "sun",
                                          f"({60.3},{70 - 0.2})"))
            t += timedelta(seconds=INT_TIME)
    # the burst window of FRB-X in band 672, noise with a dispersed pulse
    t_inf = T_EVENT - timedelta(seconds=K_DM * DM / 400.0 ** 2)
    f_c = 672 * CHAN_BW_HZ / 1e6 + (np.arange(N_CHAN) + 0.5) * 47851 / 1e6
    delay = K_DM * DM / f_c ** 2
    t = t_inf + timedelta(seconds=float(delay.min()) - 150)
    while t < t_inf + timedelta(seconds=float(delay.max()) + 150):
        rel = (t - t_inf).total_seconds()
        for oy in range(-2, 3):
            for ox in range(-2, 3):
                v = rng.normal(100, 1, (N_CHAN, 4))
                if (ox, oy) == (0, 0):
                    v[:, 0] += 8 * (np.abs(rel - delay) < 0.5)
                pixels[672].append((t, 672, f"({64 + ox},{64 + oy})", "(0,0)", _f32(v), f"({ox},{oy})", "FRB-X",
                                    "(64,64)"))
        t += timedelta(seconds=INT_TIME)

    digest = {672: [], 864: []}
    for chan0 in (672, 864):
        cfreq = (chan0 + 31) * CHAN_BW_HZ
        for k in range(0, 24 * 20, 7):
            digest[chan0].append(("sun", DAY + timedelta(minutes=3 * k), list(rng.normal(5, 1, 4).astype(float)),
                                  [0.0] * 4, cfreq))

    voevent = (f'<voe><Param name="dm" value="{DM}"/><Param name="dm_error" value="{DM_ERR}"/>'
               f'<Param name="timestamp_utc" value="{T_EVENT.isoformat()}"/></voe>')
    watchdog = [
        ("sun", DAY - timedelta(days=5), 190.0, -3.0, "manual", DAY - timedelta(days=5), None, "watching",
         "Sun", "user", None),
        ("crab", DAY, 83.6, 22.0, "manual", DAY, DAY + timedelta(hours=8), "watched", "Pulsar", "user", None),
        ("quiet", DAY, 10.0, 10.0, "manual", DAY, DAY + timedelta(hours=8), "watched", "Pulsar", "user", None),
        ("FRB-X", T_EVENT, 30.0, 40.0, "FRB detection", T_EVENT, NOW - timedelta(hours=1), "watched",
         "CHIME", "Waterfalls-CHIME", voevent),
    ]
    return sessions, pixels, digest, watchdog


def load(conn, sessions, pixels, digest, bands=None, watchdog=None):
    from psycopg2.extras import execute_values
    cur = conn.cursor()
    for chan0 in sessions:
        if bands is None or chan0 in bands:
            execute_values(cur, "insert into sevilleta.epic_img_metadata2 values %s", sessions[chan0])
    for chan0 in pixels:
        if (bands is None or chan0 in bands) and pixels[chan0]:
            execute_values(cur, "insert into sevilleta.epic_pixels values %s", pixels[chan0], page_size=5000)
    for chan0 in digest:
        if bands is None or chan0 in bands:
            execute_values(cur, "insert into sevilleta.epic_daily_digest values %s", digest[chan0])
    if watchdog:
        execute_values(cur, "insert into public.epic_watchdog (source, event_time, ra_deg, dec_deg, event_type, "
                            "t_start, t_end, watch_status, reason, author, voevent) values %s", watchdog)


def requests() -> list[tuple[str, dict]]:
    span = dict(start_time=(DAY - timedelta(days=1)).isoformat(), end_time=(DAY + timedelta(days=2)).isoformat())
    out = []
    for sort, order in [(None, "asc"), ("chan0", "asc"), ("chan0", "desc"), ("start_time", "asc"),
                        ("end_time", "desc"), ("int_time", "asc"), ("session_duration", "desc"),
                        ("chan_bw_hz", "asc"), ("n_pol", "desc"), ("session_id", "asc")]:
        for page in (1, 2, 3):
            q = dict(source_name="sun", page=page, nrows=3, order=order) | span
            out.append(("/imaging/sessions/", q | (dict(sort=sort) if sort else {})))
    out.append(("/imaging/sessions/", dict(source_name="sun", chan0=864, nrows=10) | span))
    burst = dict(start_time=(T_EVENT - timedelta(hours=2)).isoformat(), end_time=NOW.isoformat())
    out.append(("/imaging/sessions/", dict(source_name="FRB-X", burst_only="true", nrows=10) | burst))
    out.append(("/imaging/dailyobs/", dict(day=DAY.date().isoformat())))
    out.append(("/imaging/dailyobs/days/", dict(start=(DAY - timedelta(days=3)).date().isoformat(),
                                                end=(DAY + timedelta(days=3)).date().isoformat())))
    window = dict(start_time=(DAY + timedelta(hours=1, minutes=30, seconds=10)).isoformat(),
                  end_time=(DAY + timedelta(hours=1, minutes=30, seconds=40)).isoformat(), source_name="sun")
    for chan0 in (672, 864):
        out.append(("/imaging/spectrogram/", window | dict(chan0=chan0, pixel_positions="(0,0)")))
    out.append(("/imaging/spectrogram/", window | dict(chan0=864, pixel_positions="(0,0)", interpolate="true")))
    out.append(("/imaging/dailydigest/", dict(day=DAY.date().isoformat(), source_name="sun")))
    out.append(("/imaging/lightcurve/", dict(source_name="sun", chan0=672, start_time=DAY.isoformat(),
                                             end_time=(DAY + timedelta(hours=12)).isoformat())))
    out.append(("/watchlist/all/", dict(nrows=25)))
    out.append(("/frb/events/", dict(nrows=10)))
    return out


# run in the main branch's code, against the single database "ref"
REFERENCE_SCRIPT = r"""
import json, sys
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
out = []
for path, params in json.load(open(sys.argv[1])):
    r = client.get("/api/v1" + path, params=params)
    out.append(dict(status=r.status_code, body=r.json()))
json.dump(out, open(sys.argv[2], "w"))
"""


def normalise(path: str, body):
    """The body without the missing-node flags, with spectrogram rows in time
    order (the single-database query had no ORDER BY)"""
    if isinstance(body, dict):
        body = {k: v for k, v in body.items() if k not in ("nodes_missing", "bands_missing")}
    if path == "/imaging/spectrogram/":
        body = sorted(body, key=lambda r: r["img_time"])
    return body


@unittest.skipUnless(PG_BIN, "PostgreSQL 16 initdb not found (set PG_BIN)")
class LocalDbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wf-localdb-")
        cls.a = Cluster(cls.tmp, "a", PORT_A)
        cls.b = Cluster(cls.tmp, "b", PORT_B)
        cls.a.create("epic", "schema_node.sql")
        cls.b.create("epic", "schema_node.sql")
        cls.a.create("head", "schema_global.sql")
        cls.a.create("ref", "schema_node.sql", "schema_global.sql")
        sessions, pixels, digest, watchdog = make_data()
        load(cls.a.connect("epic"), sessions, pixels, digest, bands={672})
        load(cls.b.connect("epic"), sessions, pixels, digest, bands={864, 128})
        load(cls.a.connect("head"), {}, {}, {}, watchdog=watchdog)
        load(cls.a.connect("ref"), sessions, pixels, digest, watchdog=watchdog)

        from fastapi.testclient import TestClient
        from app.core.nodes import NodeSet, get_nodes, parse_nodes
        from app.main import app
        cls.app, cls.deps = app, dict(nodes=get_nodes)
        cls.client = TestClient(app)
        cls.all_nodes = get_nodes()
        cls.up_nodes = NodeSet(parse_nodes([f"a=127.0.0.1:{PORT_A}", f"b=127.0.0.1:{PORT_B}"], user=USER),
                               schema="sevilleta")

    @classmethod
    def tearDownClass(cls):
        cls.a.stop()
        cls.b.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, nodes, path, params):
        self.app.dependency_overrides[self.deps["nodes"]] = lambda: nodes
        try:
            return self.client.get("/api/v1" + path, params=params)
        finally:
            self.app.dependency_overrides.pop(self.deps["nodes"], None)

    def reference(self, reqs):
        """Responses of the main branch's code on the single database"""
        orig = os.path.join(self.tmp, "main")
        os.makedirs(orig)
        archive = subprocess.run(["git", "-C", REPO, "archive", "main", "server/backend/app"], check=True,
                                 capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", orig], input=archive, check=True)
        req_file, out_file = os.path.join(self.tmp, "req.json"), os.path.join(self.tmp, "ref.json")
        json.dump(reqs, open(req_file, "w"))
        script = os.path.join(self.tmp, "reference.py")
        open(script, "w").write(REFERENCE_SCRIPT)
        env = os.environ | dict(POSTGRES_DB="ref", PYTHONPATH=os.path.join(orig, "server/backend"))
        subprocess.run([sys.executable, script, req_file, out_file], check=True, env=env,
                       cwd=os.path.join(orig, "server/backend"), capture_output=True)
        return json.load(open(out_file))

    def test_1_routes_match_single_database(self):
        reqs = requests()
        ref = self.reference(reqs)
        for (path, params), want in zip(reqs, ref):
            with self.subTest(path=path, params=params):
                self.assertEqual(want["status"], 200, want["body"])
                r = self.get(self.up_nodes, path, params)
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                if isinstance(body, dict) and "nodes_missing" in body:
                    self.assertEqual(body["nodes_missing"], [])
                self.assertEqual(normalise(path, body), normalise(path, want["body"]))
                self.assertTrue(want["body"] or path.startswith("/frb"), "the reference returned nothing")

    def test_2_node_down(self):
        q = dict(source_name="sun", nrows=25, start_time=(DAY - timedelta(days=1)).isoformat(),
                 end_time=(DAY + timedelta(days=2)).isoformat())
        r = self.get(self.all_nodes, "/imaging/sessions/", q)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["nodes_missing"], ["c"])
        self.assertEqual(r.headers["X-EPIC-Nodes-Missing"], "c")
        full = self.get(self.up_nodes, "/imaging/sessions/", q).json()
        self.assertEqual(r.json()["data"], full["data"])
        # the watch list leaves blank what a missing node could contradict
        rows = {w["source"]: w for w in self.get(self.all_nodes, "/watchlist/all/", dict(nrows=25)).json()["data"]}
        self.assertEqual(rows["crab"]["data_status"], "observed")
        self.assertIsNone(rows["quiet"]["data_status"])
        rows = {w["source"]: w for w in self.get(self.up_nodes, "/watchlist/all/", dict(nrows=25)).json()["data"]}
        self.assertEqual(rows["quiet"]["data_status"], "not_observed")
        # with a's server stopped, its band drops out of the digest
        self.all_nodes.band_map()
        self.a_epic_down()
        try:
            r = self.get(self.all_nodes, "/imaging/dailydigest/", dict(day=DAY.date().isoformat(), source_name="sun"))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["nodes_missing"], ["a", "c"])
            self.assertEqual(r.json()["bands_missing"], [672])
            self.assertEqual({d["cfreq"] for d in r.json()["data"]}, {np.float32((864 + 31) * CHAN_BW_HZ).item()})
            # a band on a node that is down: an empty spectrogram, flagged in the headers
            r = self.get(self.all_nodes, "/imaging/spectrogram/", dict(
                start_time=(DAY + timedelta(hours=1, minutes=30)).isoformat(),
                end_time=(DAY + timedelta(hours=1, minutes=31)).isoformat(), source_name="sun", chan0=672,
                pixel_positions="(0,0)"))
            self.assertEqual((r.status_code, r.json()), (200, []))
            self.assertEqual(r.headers["X-EPIC-Bands-Missing"], "672")
        finally:
            self.a_epic_up()

    def a_epic_down(self):
        # node a's database refuses connections, the server stays up for the global database
        self.a.connect("postgres").cursor().execute("alter database epic allow_connections false")
        self.a.connect("postgres").cursor().execute(
            "select pg_terminate_backend(pid) from pg_stat_activity where datname = 'epic'")

    def a_epic_up(self):
        self.a.connect("postgres").cursor().execute("alter database epic allow_connections true")

    def test_3_frb_pipeline(self):
        from app.frb import pipeline
        head = self.a.connect("head").cursor()
        event_id = 4
        # node c is down and may hold any band no node is known for: those wait
        done = pipeline.run_worker()
        head.execute("select chan0, status from sevilleta.epic_frb_band where event_id = %s order by chan0", (event_id,))
        self.assertEqual(head.fetchall(), [(672, "ok"), (864, "no_session")])
        self.assertTrue(done["deferred"])
        self.assertEqual(done["combined"], [])
        # node c gone from the configuration: the remaining bands are settled and the event combined
        with mock.patch.object(pipeline, "get_nodes", return_value=self.up_nodes):
            done = pipeline.run_worker()
        head.execute("select chan0, status from sevilleta.epic_frb_band where event_id = %s order by chan0", (event_id,))
        self.assertEqual(dict(head.fetchall()), {672: "ok", 864: "no_session", 1440: "no_session",
                                                 2400: "no_session", 2976: "no_session", 3168: "no_session"})
        self.assertEqual(done["combined"], [event_id])
        head.execute("select summary from sevilleta.epic_frb_analysis where event_id = %s", (event_id,))
        self.assertIsNotNone(head.fetchone())

        # the main branch's analysis of band 672 on the single database gives the same product
        orig = os.path.join(self.tmp, "main", "server/backend")
        if not os.path.exists(orig):
            self.reference([])
        env = os.environ | dict(POSTGRES_DB="ref", PYTHONPATH=orig)
        subprocess.run([sys.executable, "-m", "app.frb", "band", str(event_id), "672"], check=True, env=env, cwd=orig,
                       capture_output=True)
        cols = "status, n_time, coverage, peak_snr, peak_t_s, timeseries, z_image"
        head.execute(f"select {cols} from sevilleta.epic_frb_products where event_id = %s and chan0 = 672", (event_id,))
        mine = head.fetchone()
        ref = self.a.connect("ref").cursor()
        ref.execute(f"select {cols} from sevilleta.epic_frb_products where event_id = %s and chan0 = 672", (event_id,))
        theirs = ref.fetchone()
        self.assertEqual(mine[:5], theirs[:5])
        self.assertEqual(bytes(mine[5]), bytes(theirs[5]))
        self.assertEqual(bytes(mine[6]), bytes(theirs[6]))
        self.assertEqual(mine[0], "ok")
        self.assertGreater(mine[1], 0)
        for table in ("epic_frb_dmt",):
            q = f"select px, py, peak_snr, peak_dm, md5(map) from sevilleta.{table} where event_id = %s and chan0 = 672 order by px, py"
            head.execute(q, (event_id,))
            ref.execute(q, (event_id,))
            self.assertEqual(head.fetchall(), ref.fetchall())


if __name__ == "__main__":
    unittest.main()
