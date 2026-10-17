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
            last_image_unix=r.get("last_image_unix"), started=r.get("started")))
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


def _pixel(url: str, params: dict):
    body = _get(f"{url}/api/pixel?{urllib.parse.urlencode(params)}&format=npz",
                settings.SKYMON_PIXEL_TIMEOUT_S, raw=True)
    meta = _get(f"{url}/api/pixel?{urllib.parse.urlencode(dict(params, since=time.time() + 1e9))}",
                settings.SKYMON_TIMEOUT_S)
    with np.load(io.BytesIO(body)) as z:
        times = z["times"]
        data = z["data"].astype(np.float32)
        freqs = z["freqs_mhz"]
    return dict(hpix=meta.get("hpix"), nside=meta.get("nside"), ra=meta.get("ra"),
                dec=meta.get("dec"), tracked=meta.get("tracked"), el=meta.get("el"),
                kind=meta.get("kind"), interval_s=meta.get("interval_s"),
                times=[float(t) for t in times], freqs_mhz=[float(f) for f in freqs],
                shape=list(data.shape),
                data_b64=base64.b64encode(np.ascontiguousarray(data).tobytes()).decode())


@router.get("/pixel")
def pixel(ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
          hours: float = Query(2.0, gt=0, le=24), node: str | None = None,
          fine: bool = False):
    """
    Spectrogram of the sky position (ra, dec) from every monitor tracking it,
    one entry per band: times (unix), freqs_mhz, and data [time][channel] as
    base64 little-endian float32 (NaN where the position was not tracked).
    """
    nodes = {node: _node_url(node)} if node else _nodes()
    params = dict(ra=ra, dec=dec, since=time.time() - hours * 3600)
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


def _hanko_user(request: Request) -> dict:
    """
    The logged-in user, checked with the Hanko API itself: the session token
    from the hanko cookie (sent with every request to this origin) or the
    Authorization header is passed to GET /me, which only answers for a valid
    session. Raises 401 otherwise.
    """
    api = settings.NUXT_PUBLIC_HANKO_API_URL.rstrip("/")
    token = request.cookies.get("hanko") or \
        request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not api or not token:
        raise HTTPException(status_code=401, detail="log in to review")
    hdr = {"Authorization": f"Bearer {token}"}
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{api}/me", headers=hdr),
                                    timeout=5) as r:
            uid = json.loads(r.read())["id"]
    except Exception:
        raise HTTPException(status_code=401, detail="log in to review")
    email = ""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{api}/users/{uid}", headers=hdr),
                                    timeout=5) as r:
            u = json.loads(r.read())
        email = next((e["address"] for e in u.get("emails", []) if e.get("is_primary")),
                     (u.get("emails") or [{}])[0].get("address", ""))
    except Exception:
        pass
    allowed = [x.strip().lower() for x in settings.SKYMON_REVIEWERS.split(",") if x.strip()]
    if allowed and email.lower() not in allowed:
        raise HTTPException(status_code=403, detail="not a reviewer")
    return dict(id=uid, email=email)


@router.post("/events/{eid}/review")
def review(eid: str, request: Request, verdict: str = Body(..., pattern="^(frb|rfi|unclear)$"),
           note: str = Body("", max_length=2000)):
    """Record a logged-in reviewer's verdict on a combiner event"""
    user = _hanko_user(request)
    body = json.dumps(dict(verdict=verdict, note=note,
                           by=user["email"] or user["id"])).encode()
    hdr = {"Content-Type": "application/json"}
    if settings.SKYMON_TOKEN:
        hdr["X-Skymon-Token"] = settings.SKYMON_TOKEN
    urls = [u.strip().rstrip("/") for u in settings.SKYMON_COMBINER_URLS.split(",") if u.strip()]
    for u in urls:
        try:
            req = urllib.request.Request(f"{u}/api/events/{urllib.parse.quote(eid)}/review",
                                         data=body, headers=hdr, method="POST")
            with urllib.request.urlopen(req, timeout=settings.SKYMON_TIMEOUT_S) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # another combiner location, or an unknown event
            raise HTTPException(status_code=e.code, detail="the combiner refused the review")
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="the combiner did not answer")
