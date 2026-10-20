"""
All-sky monitor: the monitors on the imaging workers, seen together.

Each worker runs its own monitor for its own band (LWA_EPIC src/python/skymon)
and answers on HTTP. These routes ask every configured monitor in parallel
with a short timeout and return whatever answered, so a worker that is down
only removes its band. Node addresses stay on the server; the public API
names nodes only.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.core.config import settings

router = APIRouter()
_pool = ThreadPoolExecutor(max_workers=12)


def _nodes() -> dict[str, str]:
    out = {}
    for item in settings.SKYMON_NODES.split(","):
        if "=" in item:
            name, url = item.split("=", 1)
            out[name.strip()] = url.strip().rstrip("/")
    return out


def _get(url: str, timeout: float, raw: bool = False):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read()
    return body if raw else json.loads(body)


def _node_url(node: str) -> str:
    nodes = _nodes()
    if node not in nodes:
        raise HTTPException(status_code=404, detail="unknown node")
    return nodes[node]


def _ask_all(path: str, timeout: float):
    nodes = _nodes()
    futs = {n: _pool.submit(_get, u + path, timeout) for n, u in nodes.items()}
    out = {}
    for n, f in futs.items():
        try:
            out[n] = f.result(timeout=timeout + 1)
        except Exception as e:  # down, slow or restarting: reported, never fatal
            out[n] = e
    return out


def _conditions(c):
    if not isinstance(c, dict):
        return None
    lat, summ = c.get("latest"), c.get("summary")
    return dict(
        latest=None if not isinstance(lat, dict) else
        {k: lat.get(k) for k in ("disturbed", "reasons", "noise_ratio", "rfi_rate", "cand_rate")},
        summary=None if not isinstance(summ, dict) else dict(disturbed_since=summ.get("disturbed_since")))


def _rfi(r):
    if not isinstance(r, dict):
        return None
    return dict(flagged_fraction_last_minute=r.get("flagged_fraction_last_minute"),
                masked_mhz=r.get("masked_mhz") or [])


@router.get("/nodes")
def nodes():
    """State of every monitor: band, tracked pixels, real-time margin, candidates, injections"""
    res = _ask_all("/api/status", settings.SKYMON_TIMEOUT_S)
    out = []
    for n, r in res.items():
        if isinstance(r, Exception):
            out.append(dict(node=n, up=False, error=type(r).__name__))
            continue
        inj = r.get("injections") or {}
        out.append(dict(
            node=n, up=True, band=r.get("band"), tracked=r.get("tracked"),
            nside=r.get("nside"), beam_deg=r.get("beam_deg"), lag_s=r.get("lag_s"),
            cpu_fraction=r.get("cpu_fraction"), images=r.get("images"),
            missing_images=r.get("missing_images"), threshold=r.get("threshold"),
            tiers=r.get("tiers"), candidates=r.get("candidates"),
            injections=dict(injected=inj.get("injected"), recovered=inj.get("recovered"),
                            missed=inj.get("missed"), active=inj.get("active")),
            last_image_unix=r.get("last_image_unix"), started=r.get("started"),
            pix_deg=r.get("pix_deg"), el_min=r.get("el_min"),
            conditions=_conditions(r.get("conditions")), rfi_flagging=_rfi(r.get("rfi_flagging"))))
    out.sort(key=lambda d: (d.get("band") or {}).get("f_lo") or 1e9)
    return out


@router.get("/candidates")
def candidates(since_h: float = Query(24.0, ge=0, le=24 * 30),
               cls: str | None = Query(None, pattern="^(candidate|injection|rfi|known|followup|context)$"),
               limit: int = Query(500, ge=1, le=5000)):
    """Recent candidates of all monitors, newest first"""
    since = time.time() - since_h * 3600
    q = urllib.parse.urlencode({k: v for k, v in dict(since=since, cls=cls, limit=limit).items()
                                if v is not None})
    res = _ask_all(f"/api/candidates?{q}", settings.SKYMON_TIMEOUT_S)
    out = []
    for n, r in res.items():
        if isinstance(r, Exception):
            continue
        for c in r:
            c.pop("files", None)
            c["node"] = n
            out.append(c)
    out.sort(key=lambda c: c["t_inf"], reverse=True)
    return out[:limit]


@router.get("/{node}/candidates/{cid}")
def candidate(node: str, cid: str):
    url = _node_url(node)
    try:
        c = _get(f"{url}/api/candidates/{urllib.parse.quote(cid)}", settings.SKYMON_TIMEOUT_S)
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=e.code, detail="candidate not found")
    except Exception:
        raise HTTPException(status_code=503, detail="monitor unavailable")
    c.pop("files", None)
    c["node"] = node
    return c


def _b64(a) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode()


@router.get("/{node}/candidates/{cid}/data")
def candidate_data(node: str, cid: str):
    """
    The data a monitor kept with a candidate (its npz): the pixel's dynamic
    spectrum over the burst's sweep at the search resolution, the DM-time
    plane, and the 10 s accumulation of the 30 min before. Arrays are base64
    little-endian float32, [row][column] as named.
    """
    url = _node_url(node)
    q = urllib.parse.quote(cid)
    try:
        c = _get(f"{url}/api/candidates/{q}", settings.SKYMON_TIMEOUT_S)
        body = _get(f"{url}/api/candidates/{q}/npz", settings.SKYMON_PIXEL_TIMEOUT_S, raw=True)
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=404 if e.code == 404 else 502, detail="no data for this candidate")
    except Exception:
        raise HTTPException(status_code=503, detail="monitor unavailable")
    with np.load(io.BytesIO(body)) as z:
        f = z.files
        out = dict(freqs_mhz=z["freqs_mhz"].tolist())
        if "dynspec" in f:  # [channel][time]
            out.update(dynspec=_b64(z["dynspec"]), dynspec_shape=list(z["dynspec"].shape),
                       dynspec_t=z["dynspec_t"].tolist())
        if "dmt" in f:  # [dm][time], on the dynamic spectrum's times
            out.update(dmt=_b64(z["dmt"]), dmt_shape=list(z["dmt"].shape), dmt_dm=z["dmt_dm"].tolist())
        if "accum" in f:  # [time][channel]
            out.update(accum=_b64(z["accum"]), accum_shape=list(z["accum"].shape),
                       accum_t=z["accum_t"].tolist())
        if "tier_images" in f and "image_s" in f:
            out["dt_s"] = float(z["tier_images"]) * float(z["image_s"])
    for k in ("files", "burst_fit"):
        c.pop(k, None)
    c["node"] = node
    out["candidate"] = c
    # a test injection: what was injected, to compare with what was found
    if c.get("injection_id"):
        try:
            inj = _get(f"{url}/api/injections", settings.SKYMON_TIMEOUT_S)
            for r in (inj.get("in_progress") or []) + (inj.get("recent") or []):
                if r.get("id") == c["injection_id"]:
                    out["injection"] = {k: r.get(k) for k in ("id", "dm", "t_inf", "snr_target", "ra", "dec")}
                    break
        except Exception:
            pass
    return out


_pulsars: tuple[float, list] | None = None


@router.get("/pulsars")
def pulsars():
    """The pulsars the monitors label single pulses of (the first monitor to answer; cached 10 min)"""
    global _pulsars
    if _pulsars and time.time() - _pulsars[0] < 600:
        return _pulsars[1]
    for n, r in _ask_all("/api/pulsars", settings.SKYMON_TIMEOUT_S).items():
        if isinstance(r, list) and r:
            _pulsars = (time.time(), r)
            return r
    return []


@router.get("/pulsars/pulses")
def pulsar_pulses():
    """
    The single pulses of ordinary pulsars in the last 24 h, which the monitors tally
    rather than store: {name: [[arrival, S/N, DM, node], ...]}, newest last
    """
    out: dict[str, list] = {}
    for n, r in _ask_all("/api/pulsars/pulses", settings.SKYMON_TIMEOUT_S).items():
        if isinstance(r, dict):
            for name, ps in r.items():
                out.setdefault(name, []).extend([*p[:3], n] for p in ps)
    for ps in out.values():
        ps.sort(key=lambda p: p[0])
    return out


_skymaps: dict[tuple[str, int], tuple[float, dict]] = {}


@router.get("/{node}/skymap")
def skymap(node: str, seconds: int = Query(300, ge=10, le=3600)):
    """
    The sky one monitor sees, averaged over the last `seconds` of its
    accumulation, on its HEALPix grid: hpix (base64 int32) and values (base64
    float32, raw image units). Cached for 30 s, since every viewer asks the same.
    """
    url = _node_url(node)
    key = (node, seconds)
    hit = _skymaps.get(key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    try:
        r = _get(f"{url}/api/skymap?seconds={seconds}", settings.SKYMON_PIXEL_TIMEOUT_S)
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=503 if e.code == 503 else 502, detail="no sky map from this monitor")
    except Exception:
        raise HTTPException(status_code=503, detail="monitor unavailable")
    r["node"] = node
    _skymaps[key] = (time.time(), r)
    return r


def _pixel(url: str, params: dict):
    body = _get(f"{url}/api/pixel?{urllib.parse.urlencode(params)}&format=npz",
                settings.SKYMON_PIXEL_TIMEOUT_S, raw=True)
    with np.load(io.BytesIO(body)) as z:
        times = z["times"]
        data = z["data"].astype(np.float32)
        freqs = z["freqs_mhz"]
        meta = json.loads(str(z["meta"])) if "meta" in z.files else None
    if meta is None:  # a monitor without the metadata in its npz
        meta = _get(f"{url}/api/pixel?{urllib.parse.urlencode(dict(params, since=time.time() + 1e9))}",
                    settings.SKYMON_TIMEOUT_S)
    return dict(hpix=meta.get("hpix"), nside=meta.get("nside"), ra=meta.get("ra"),
                dec=meta.get("dec"), tracked=meta.get("tracked"), el=meta.get("el"),
                kind=meta.get("kind"), interval_s=meta.get("interval_s"),
                times=[float(t) for t in times], freqs_mhz=[float(f) for f in freqs],
                shape=list(data.shape),
                data_b64=base64.b64encode(np.ascontiguousarray(data).tobytes()).decode())


@router.get("/pixel")
def pixel(ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
          hours: float = Query(2.0, gt=0, le=24), node: str | None = None,
          fine: bool = False, hpix: int | None = Query(None, ge=0)):
    """
    Spectrogram of the sky position (ra, dec) from every monitor tracking it,
    one entry per band: times (unix), freqs_mhz, and data [time][channel] as
    base64 little-endian float32 (NaN where the position was not tracked).
    """
    nodes = {node: _node_url(node)} if node else _nodes()
    # the span on the monitor's own clock (hours), and on ours for a monitor without it (since)
    params = dict(ra=ra, dec=dec, since=time.time() - hours * 3600, hours=hours)
    if hpix is not None and node:  # a pixel picked on that monitor's own grid
        params = dict(hpix=hpix, since=params["since"], hours=hours)
    if fine:
        params["fine"] = 1
    futs = {n: _pool.submit(_pixel, u, params) for n, u in nodes.items()}
    out = []
    for n, f in futs.items():
        try:
            r = f.result(timeout=settings.SKYMON_PIXEL_TIMEOUT_S + 2)
        except Exception as e:
            out.append(dict(node=n, up=False, error=type(e).__name__))
            continue
        r.update(node=n, up=True)
        out.append(r)
    out.sort(key=lambda d: d["freqs_mhz"][0] if d.get("freqs_mhz") else 1e9)
    return out


def _combiner(path: str):
    """Ask every possible combiner location at once; the first answer wins"""
    urls = [u.strip().rstrip("/") for u in settings.SKYMON_COMBINER_URLS.split(",") if u.strip()]
    futs = [_pool.submit(_get, u + path, settings.SKYMON_TIMEOUT_S) for u in urls]
    for f in futs:
        try:
            return f.result(timeout=settings.SKYMON_TIMEOUT_S + 1)
        except Exception:
            continue
    return None


@router.get("/events")
def events(since_h: float = Query(24.0, ge=0, le=24 * 30),
           status: str | None = Query(None, pattern="^(pending|confirmed|band_limited|implausible|unconfirmable|terrestrial)$"),
           limit: int = Query(200, ge=1, le=2000)):
    """Events of the combiner: candidates checked across bands. null if no combiner answers"""
    q = urllib.parse.urlencode({k: v for k, v in dict(since=time.time() - since_h * 3600,
                                                     status=status, limit=limit).items()
                                if v is not None})
    res = _combiner(f"/api/events?{q}")
    if res is None:
        return dict(up=False, events=[])
    for e in res:  # monitor addresses and watch ids stay on the server
        for b in e.get("bands", {}).values():
            for k in ("watch_id", "watch_key", "error"):
                b.pop(k, None)
    return dict(up=True, events=res)


@router.get("/combiner")
def combiner_status():
    st = _combiner("/api/status")
    return dict(up=st is not None, **(st or {}))


@router.post("/events/{eid}/review")
def review(eid: str, request: Request, verdict: str = Body(..., pattern="^(frb|rfi|unclear)$"),
           note: str = Body("", max_length=2000)):
    """
    Record an admin's verdict on an event (every route here needs an admin, see
    api/main.py). The combiner holds the events of its last SKYMON_COMBINER_KEEP_H
    hours and writes them to the catalogue itself, so a review of a recent event
    goes to it; an older event is reviewed in the catalogue directly, so an
    event can be reviewed whenever its data have been looked at.
    """
    user = request.state.user
    by = user["email"] or user["id"]
    body = json.dumps(dict(verdict=verdict, note=note, by=by)).encode()
    hdr = {"Content-Type": "application/json"}
    if settings.SKYMON_TOKEN:
        hdr["X-Skymon-Token"] = settings.SKYMON_TOKEN
    urls = [u.strip().rstrip("/") for u in settings.SKYMON_COMBINER_URLS.split(",") if u.strip()]
    answered = False
    for u in urls:
        try:
            req = urllib.request.Request(f"{u}/api/events/{urllib.parse.quote(eid)}/review",
                                         data=body, headers=hdr, method="POST")
            with urllib.request.urlopen(req, timeout=settings.SKYMON_TIMEOUT_S) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                answered = True  # this combiner does not hold it (anymore)
                continue
            raise HTTPException(status_code=e.code, detail="the combiner refused the review")
        except Exception:
            continue
    return _catalogue_review(eid, verdict, note, by, combiner_answered=answered)


def _catalogue_review(eid: str, verdict: str, note: str, by: str, combiner_answered: bool) -> dict:
    """The verdict written to the catalogue's copy of an event the combiner no longer holds"""
    from sqlalchemy import text
    try:
        with _catalogue().begin() as conn:
            ev = conn.execute(text("SELECT t_inf FROM skymon.events WHERE id = :id FOR UPDATE"),
                              dict(id=eid)).first()
            if ev is None:
                raise HTTPException(status_code=404, detail="unknown event")
            # a recent event is still the combiner's: written here, its next update would undo it
            if not combiner_answered and time.time() - ev.t_inf.timestamp() < settings.SKYMON_COMBINER_KEEP_H * 3600:
                raise HTTPException(status_code=503, detail="the combiner did not answer; try again shortly")
            entry = json.dumps(dict(verdict=verdict, by=str(by)[:80], note=note[:2000], at=time.time()))
            r = conn.execute(text(
                "UPDATE skymon.events SET review = :v, updated = now(), record = jsonb_set(jsonb_set(record, "
                "'{reviews}', coalesce(record->'reviews', '[]'::jsonb) || jsonb_build_array(CAST(:e AS jsonb))), "
                "'{review}', to_jsonb(CAST(:v AS text))) WHERE id = :id "
                "RETURNING review, record->'reviews' AS reviews"), dict(v=verdict, e=entry, id=eid)).first()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail="the catalogue is not available") from e
    return dict(id=eid, review=r.review, reviews=r.reviews or [])


# ---------------------------------------------------------------- the catalogue
_cat_engine = None


def _catalogue():
    """The engine for the catalogue: the website's database, or SKYMON_CATALOGUE_DSN"""
    global _cat_engine
    if _cat_engine is None:
        dsn = settings.SKYMON_CATALOGUE_DSN.strip()
        if not dsn:
            from app.core.db import engine
            _cat_engine = engine
        else:
            from sqlalchemy import create_engine
            if "://" not in dsn:  # a libpq DSN
                import psycopg2
                _cat_engine = create_engine("postgresql+psycopg2://", creator=lambda: psycopg2.connect(dsn),
                                            pool_pre_ping=True)
            else:
                _cat_engine = create_engine(dsn, pool_pre_ping=True)
    return _cat_engine


def _lock_until(t_inf) -> float:
    return t_inf.timestamp() + settings.SKYMON_LOCK_DAYS * 86400


def _archived(path: str) -> bool:
    """Is the candidate's data in the archive (its .npz)?"""
    try:
        return os.path.exists(os.path.join(settings.SKYMON_ARCHIVE_ROOT, path + ".npz"))
    except OSError:
        return False


def _detection(r) -> dict:
    rec = r.record or {}
    return dict(node=r.node, id=r.cand_id, kind=r.kind, event_id=r.event_id, state=r.state, pulsar=r.pulsar,
                t_inf=r.t_inf.timestamp(), f_lo_mhz=r.f_lo_mhz, f_hi_mhz=r.f_hi_mhz, snr=r.snr, dm=r.dm,
                width_s=r.width_s, fluence_jy_ms=r.fluence_jy_ms, ra=r.ra, dec=r.dec,
                el=rec.get("el"), tier=rec.get("tier"), duplicates=rec.get("duplicates"),
                dm_arms=len(rec.get("dm_arms") or []),
                available_from=_lock_until(r.t_inf), archived=_archived(r.archive_path))


@router.get("/catalogue")
def catalogue(kind: str = Query("frb", pattern="^(frb|giant_pulse)$"),
              since_days: float = Query(30.0, gt=0, le=3650),
              status: str | None = Query(None, pattern="^(confirmed|band_limited|implausible|unconfirmable|pending)$"),
              review: str | None = Query(None, pattern="^(pending|frb|rfi|unclear)$"),
              limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    """
    The catalogue, newest first. kind=frb: the FRB events, each with its detections
    (one per band); kind=giant_pulse: the giant pulses. Each detection says whether
    its data are archived and from when anyone may download them.
    """
    from sqlalchemy import text
    since = time.time() - since_days * 86400
    try:
        with _catalogue().connect() as conn:
            if kind == "giant_pulse":
                n = conn.execute(text("SELECT count(*) FROM skymon.detections WHERE kind = 'giant_pulse' "
                                      "AND t_inf >= to_timestamp(:s)"), dict(s=since)).scalar()
                rows = conn.execute(text(
                    "SELECT * FROM skymon.detections WHERE kind = 'giant_pulse' AND t_inf >= to_timestamp(:s) "
                    "ORDER BY t_inf DESC LIMIT :l OFFSET :o"), dict(s=since, l=limit, o=offset)).fetchall()
                return dict(count=n, rows=[_detection(r) for r in rows])
            where = "t_inf >= to_timestamp(:s)"
            args = dict(s=since, l=limit, o=offset)
            if status:
                where += " AND status = :st"
                args["st"] = status
            if review:
                where += " AND review = :rv"
                args["rv"] = review
            n = conn.execute(text(f"SELECT count(*) FROM skymon.events WHERE {where}"), args).scalar()
            evs = conn.execute(text(
                f"SELECT id, status, review, t_inf, ra, dec, dm, dm_err, snr, n_seen, n_could_see, "
                f"record->'reviews' AS reviews, record->'spectrum' AS spectrum, record->'disturbed' AS disturbed "
                f"FROM skymon.events WHERE {where} ORDER BY t_inf DESC LIMIT :l OFFSET :o"), args).fetchall()
            ids = [e.id for e in evs]
            dets = conn.execute(text("SELECT * FROM skymon.detections WHERE event_id = ANY(:ids) "
                                     "ORDER BY f_lo_mhz"), dict(ids=ids)).fetchall() if ids else []
    except Exception as e:
        raise HTTPException(status_code=503, detail="the catalogue is not available") from e
    by = {}
    for d in dets:
        by.setdefault(d.event_id, []).append(_detection(d))
    out = []
    for e in evs:
        out.append(dict(id=e.id, status=e.status, review=e.review, t_inf=e.t_inf.timestamp(), ra=e.ra, dec=e.dec,
                        dm=e.dm, dm_err=e.dm_err, snr=e.snr, n_seen=e.n_seen, n_could_see=e.n_could_see,
                        reviews=e.reviews or [], spectrum=e.spectrum, disturbed=bool(e.disturbed),
                        available_from=_lock_until(e.t_inf), detections=by.get(e.id, [])))
    return dict(count=n, rows=out)


@router.get("/catalogue/events/{eid}.zip")
def catalogue_event_zip(eid: str):
    """
    Everything kept of an event, for analysis: its record (event.json) and, for each
    band, the detection's archived data (.npz) and record (.json), in one zip
    """
    import tempfile
    import zipfile
    from fastapi.responses import StreamingResponse
    from sqlalchemy import text
    try:
        with _catalogue().connect() as conn:
            ev = conn.execute(text("SELECT record FROM skymon.events WHERE id = :id"), dict(id=eid)).first()
            dets = conn.execute(text("SELECT node, archive_path FROM skymon.detections WHERE event_id = :id"),
                                dict(id=eid)).fetchall()
    except Exception as e:
        raise HTTPException(status_code=503, detail="the catalogue is not available") from e
    if ev is None:
        raise HTTPException(status_code=404, detail="unknown event")
    root = os.path.realpath(settings.SKYMON_ARCHIVE_ROOT)
    tmp = tempfile.SpooledTemporaryFile(max_size=64 << 20)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("event.json", json.dumps(ev.record, indent=1))
        for d in dets:
            for ext in ("npz", "json"):
                path = os.path.realpath(os.path.join(root, d.archive_path + "." + ext))
                if path.startswith(root + os.sep) and os.path.exists(path):
                    # the npz files are compressed already
                    z.write(path, f"{d.node}/{os.path.basename(path)}",
                            compress_type=zipfile.ZIP_STORED if ext == "npz" else zipfile.ZIP_DEFLATED)
    size = tmp.tell()
    tmp.seek(0)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", eid)
    return StreamingResponse(iter(lambda: tmp.read(1 << 20), b""), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="skymon-{safe}.zip"',
                                      "Content-Length": str(size)})


@router.get("/catalogue/data/{node}/{cand_id}.{ext}")
def catalogue_data(node: str, cand_id: str, ext: str, request: Request):
    """
    A catalogued detection's archived data (.npz) or record (.json), for admins
    (like every route here). available_from in the listings marks when it would
    open to the public, SKYMON_LOCK_DAYS after detection, if the catalogue is
    made public.
    """
    from fastapi.responses import FileResponse
    from sqlalchemy import text
    if ext not in ("npz", "json"):
        raise HTTPException(status_code=404, detail="unknown file")
    try:
        with _catalogue().connect() as conn:
            r = conn.execute(text("SELECT t_inf, archive_path FROM skymon.detections "
                                  "WHERE node = :n AND cand_id = :c"), dict(n=node, c=cand_id)).first()
    except Exception as e:
        raise HTTPException(status_code=503, detail="the catalogue is not available") from e
    if r is None:
        raise HTTPException(status_code=404, detail="not in the catalogue")
    root = os.path.realpath(settings.SKYMON_ARCHIVE_ROOT)
    path = os.path.realpath(os.path.join(root, r.archive_path + "." + ext))
    if not path.startswith(root + os.sep) or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="not archived yet")
    return FileResponse(path, filename=os.path.basename(path),
                        media_type="application/octet-stream" if ext == "npz" else "application/json")
