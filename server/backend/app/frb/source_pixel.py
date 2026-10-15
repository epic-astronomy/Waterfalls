"""
Stokes I of a source interpolated at its exact position on the image.

The imager stores a 5x5 grid of pixels around each source, centred on the
pixel nearest the source and moved by whole pixels as the source crosses the
sky, every few minutes. Reading the centre pixel therefore jumps at every
move, both because the source's offset within the pixel flips and because
the grid lands on different structure in the image. Here every image's 5x5
grid is interpolated at the source's exact position with a separable
Lanczos-2 kernel, which fits inside the grid for offsets up to half a pixel.

The exact position comes from the source_pix column the imager writes (from
epic-imager v0.18). For older data it is computed with the imager's own WCS
(LWA_EPIC src/python/source_track.py, run in the imager's environment).
"""

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings

log = logging.getLogger(__name__)

N_POL = 4
CHUNK_S = 120.0  # 25 pixels x 12 images/s x 1 kB per row
TRACK_STEP_S = 10.0


def _unix(t: datetime) -> float:
    return t.replace(tzinfo=timezone.utc).timestamp()


def source_track(ra: float, dec: float, t0: datetime, t1: datetime, body: str | None = None):
    """Exact (1-based FITS) pixel position of a source, sampled every
    TRACK_STEP_S, from the imager's geometry code"""
    args = [settings.FRB_GEOMETRY_PYTHON, "-W", "ignore", "source_track.py", "--ra", str(ra), "--dec", str(dec),
            "--t0", str(_unix(t0) - TRACK_STEP_S), "--t1", str(_unix(t1) + TRACK_STEP_S),
            "--step", str(TRACK_STEP_S), "--grid-size", str(settings.FRB_GRID_SIZE),
            "--grid-res", str(settings.FRB_GRID_RES)]
    if body:
        args += ["--body", body]
    out = subprocess.run(args, cwd=settings.FRB_GEOMETRY_DIR, capture_output=True, text=True, check=True, timeout=600)
    d = json.loads(out.stdout.strip().splitlines()[-1])
    return np.array(d["t"]), np.array(d["x"]), np.array(d["y"])


def lanczos2(t: np.ndarray) -> np.ndarray:
    t = np.asarray(t, float)
    return np.where(np.abs(t) < 2, np.sinc(t) * np.sinc(t / 2), 0.0)


def interpolation_weights(dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """[n, 5, 5] weights over pixel offsets -2..2 (rows y, columns x) for a
    source at (dx, dy) pixels from the grid centre"""
    k = np.arange(-2, 3)
    wx = lanczos2(k[None, :] - np.asarray(dx)[:, None])
    wy = lanczos2(k[None, :] - np.asarray(dy)[:, None])
    wx /= wx.sum(axis=1, keepdims=True)
    wy /= wy.sum(axis=1, keepdims=True)
    return wy[:, :, None] * wx[:, None, :]


def fetch_source_stokes_i(session: Session, source: str, chan0: int, t0: datetime, t1: datetime, n_chan: int,
                          ra: float, dec: float):
    """Stokes I (XX + YY) interpolated at the source, as (times, [n_images, n_chan])"""
    track = None
    times_out, values_out = [], []
    t = t0
    while t < t1:
        t_next = min(t1, t + timedelta(seconds=CHUNK_S))
        rows = session.execute(
            text(
                f"select img_time, pix_offset[0]::int, pix_offset[1]::int, pixel_coord[0], pixel_coord[1], "
                f"source_pix[0], source_pix[1], pixel_values from {settings.EPIC_DATA_SCHEMA}.epic_pixels "
                "where img_time >= :t0 and img_time < :t1 and source_name = :src and chan0 = :chan0 order by img_time"
            ),
            dict(t0=t, t1=t_next, src=source, chan0=chan0),
        ).all()
        t = t_next
        if not rows:
            continue
        index = {}
        for r in rows:
            index.setdefault(r[0], len(index))
        n = len(index)
        grid = np.full((n, 5, 5, n_chan), np.nan, dtype=np.float32)
        centre = np.full((n, 2), np.nan)
        exact = np.full((n, 2), np.nan)
        for img_time, ox, oy, px, py, sx, sy, values in rows:
            i = index[img_time]
            if not (-2 <= ox <= 2 and -2 <= oy <= 2):
                continue
            v = np.frombuffer(bytes(values), dtype="<f4").reshape(n_chan, N_POL)
            grid[i, oy + 2, ox + 2] = v[:, 0] + v[:, 1]
            if ox == 0 and oy == 0:
                centre[i] = (px, py)
                if sx is not None:
                    exact[i] = (sx, sy)
        times = np.array(list(index), dtype="datetime64[us]")
        missing = np.isnan(exact[:, 0])
        if missing.any():
            if track is None:
                log.info("No stored source position for %s; computing its track", source)
                body = source if source.lower() in ("sun", "moon", "jupiter") else None
                track = source_track(ra, dec, t0, t1, body)
            ts = (times[missing] - np.datetime64("1970-01-01T00:00:00", "us")) / np.timedelta64(1, "s")
            exact[missing, 0] = np.interp(ts, track[0], track[1])
            exact[missing, 1] = np.interp(ts, track[0], track[2])
        ok = np.isfinite(centre[:, 0])
        d = exact[ok] - centre[ok]
        if np.nanmax(np.abs(d)) > 1.0:
            log.warning("%s is up to %.2f px from its grid centre in band %s", source, np.nanmax(np.abs(d)), chan0)
        d = np.clip(d, -1.0, 1.0)
        w = interpolation_weights(d[:, 0], d[:, 1])[..., None]  # [n, 5, 5, 1]
        g = grid[ok]
        valid = np.isfinite(g)
        num = np.where(valid, g, 0.0) * w
        den = np.where(valid, w, 0.0).sum(axis=(1, 2))
        with np.errstate(invalid="ignore", divide="ignore"):
            values_out.append((num.sum(axis=(1, 2)) / den).astype(np.float32))
        times_out.append(times[ok])
    if not times_out:
        return np.empty(0, dtype="datetime64[us]"), np.empty((0, n_chan))
    return np.concatenate(times_out), np.concatenate(values_out)
