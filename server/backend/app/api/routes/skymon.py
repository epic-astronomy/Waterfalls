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
from fastapi import APIRouter, HTTPException, Query

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
               cls: str | None = Query(None, pattern="^(candidate|injection|rfi)$"),
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
