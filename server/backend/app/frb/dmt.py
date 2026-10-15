"""
Dispersion measure transform of CHIME/FRB watches, for every pixel of the
5x5 grid around the source and every imaging band.

The search follows the LOFAR analysis of FRB 20180916B (Pleunis et al. 2021,
ApJL 911, L3): incoherent dedispersion over a range of trial DMs around the
known DM, a boxcar search of each dedispersed time series, an S/N threshold
of 7, RFI masked before dedispersion, and arrival times referenced to
infinite frequency. Here:

1. Each band's dynamic spectrum of each pixel, at the full 83.6 ms
   resolution, is cleaned with the CHIME/FRB L1 chain (rfi.py).
2. Each channel is shifted to the lowest trial DM, and the FDMT (fdmt.py)
   sums every track over the residual DM range. Row d of a band's transform
   becomes a time series indexed by the burst's arrival at infinite frequency.
3. Each band is searched with boxcars up to its smearing, and is smoothed to
   its smearing for the combination. Bands are combined on a common DM grid
   and time axis as sum(S/N_b) / sqrt(N). The hours of delay between bands
   give a DM precision far finer than one band alone.
4. The S/N of every pixel tests whether a peak is localised on the source,
   as a burst would be, or spread over the grid, as RFI tends to be.

Fluence limits come from the radiometer equation with a model of the sky
and array, because the EPIC images are not flux calibrated.
"""

import json
import logging
import math
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.frb import rfi
from app.frb.fdmt import fdmt
from app.frb.source_pixel import fetch_source_stokes_i
from app.frb.products import FETCH_CHUNK_S, K_DM, N_POL, _robust, load_event

log = logging.getLogger(__name__)

VERSION = 4
DM_STEP = 0.05
TAU_HALF = 60.0  # shortest span of arrival offsets searched and stored, s
MAX_TAU_HALF = 900.0
OFF_WIDTHS = 10  # independent widest boxcars outside the search window, at least
SEARCH_TAU = 5.0  # search window around the CHIME arrival, s, beyond the smearing
SNR_THRESHOLD = 7.0
PIXELS = [(px, py) for py in range(-2, 3) for px in range(-2, 3)]

# LWA-SV and the radiometer model used for fluence limits
LWASV_LAT, LWASV_LON = 34.3484, -106.8858
N_ANT = 229
T_RCV = 250.0  # K
STATION_RADIUS = 50.0  # m
BOLTZMANN = 1.380649e-23


def _boxcar(ts: np.ndarray, w: int) -> np.ndarray:
    """Centred running mean over w samples, NaN-aware"""
    if w <= 1:
        return ts.copy()
    v = np.isfinite(ts)
    c = np.concatenate([[0.0], np.cumsum(np.where(v, ts, 0.0))])
    n = np.concatenate([[0], np.cumsum(v)])
    h = w // 2
    i = np.arange(len(ts))
    a, b = np.clip(i - h, 0, len(ts)), np.clip(i - h + w, 0, len(ts))
    cnt = n[b] - n[a]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt >= w / 2, (c[b] - c[a]) / cnt, np.nan)


def _normalise(ts: np.ndarray, off: np.ndarray) -> np.ndarray:
    med, sig = _robust(ts[off & np.isfinite(ts)])
    s = sig.item() if np.isfinite(sig).all() else np.nan
    return (ts - med.item()) / s if s and s > 0 else np.full_like(ts, np.nan)


def _pool(a: np.ndarray, max_rows: int, max_cols: int) -> tuple[np.ndarray, int, int]:
    """Max-pool a 2D array to at most max_rows x max_cols"""
    fr, fc = max(1, math.ceil(a.shape[0] / max_rows)), max(1, math.ceil(a.shape[1] / max_cols))
    r, c = a.shape[0] // fr * fr, a.shape[1] // fc * fc
    with np.errstate(invalid="ignore"), np.testing.suppress_warnings() as sup:
        sup.filter(RuntimeWarning)
        pooled = np.nanmax(a[:r, :c].reshape(r // fr, fr, c // fc, fc), axis=(1, 3))
    return pooled, fr, fc


def dm_half_range(dm_err: float) -> float:
    """Half-width of the trial DMs around the CHIME DM: a multiple of the
    quoted DM error, between a floor and a cap (backend settings)"""
    return float(np.clip(settings.FRB_DM_HALF_FACTOR * dm_err, settings.FRB_DM_HALF_MIN, settings.FRB_DM_HALF_MAX))


def _elevation(ra_deg: float, dec_deg: float, when: datetime) -> float:
    jd = (when - datetime(2000, 1, 1, 12)).total_seconds() / 86400 + 2451545.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360
    h = math.radians((gmst + LWASV_LON - ra_deg) % 360)
    lat, dec = math.radians(LWASV_LAT), math.radians(dec_deg)
    return math.degrees(math.asin(math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(h)))


def _fluence_limit(f_mhz: float, elevation: float, bandwidth_hz: float, width_s: float) -> dict:
    """Radiometer-equation fluence for S/N = SNR_THRESHOLD from a model array:
    sky-dominated T_sys (60 K lambda^2.55, Lawson et al. 1987, plus 250 K),
    effective area N_ant lambda^2 / 3 capped at the station footprint, and
    projected to the source elevation"""
    lam = 299.792458 / f_mhz
    t_sys = 60.0 * lam**2.55 + T_RCV
    area = min(N_ANT * lam**2 / 3, math.pi * STATION_RADIUS**2) * max(math.sin(math.radians(elevation)), 0.0)
    if area <= 0 or bandwidth_hz <= 0:
        return dict(t_sys_k=t_sys, sefd_jy=None, fluence_limit_jyms=None)
    sefd = 2 * BOLTZMANN * t_sys / area / 1e-26
    fluence = SNR_THRESHOLD * sefd * math.sqrt(width_s / (2 * bandwidth_hz)) * 1e3
    return dict(t_sys_k=t_sys, sefd_jy=sefd, fluence_limit_jyms=fluence)


def _fetch_pixel(session: Session, source: str, chan0: int, t0: datetime, t1: datetime, n_chan: int, key):
    """Stokes I of one pixel of the 5x5 grid, as (times, [n_rows, n_chan])"""
    times, vals = [], []
    t = t0
    while t < t1:
        t_next = min(t1, t + timedelta(seconds=FETCH_CHUNK_S))
        res = session.execute(
            text(
                f"select img_time, pixel_values from {settings.EPIC_DATA_SCHEMA}.epic_pixels "
                "where img_time >= :t0 and img_time < :t1 and source_name = :src "
                "and pix_offset::text = :off and chan0 = :chan0 order by img_time"
            ),
            dict(t0=t, t1=t_next, src=source, chan0=chan0, off=f"({key[0]},{key[1]})"),
        )
        for img_time, values in res:
            times.append(img_time)
            vals.append(bytes(values))
        t = t_next
    if not vals:
        return np.empty(0, dtype="datetime64[us]"), np.empty((0, n_chan))
    data = np.frombuffer(b"".join(vals), dtype="<f4").reshape(len(vals), n_chan, N_POL)
    return np.array(times, dtype="datetime64[us]"), data[:, :, 0] + data[:, :, 1]


def band_dmt(session: Session, event: dict, band: dict, dm_half: float) -> dict:
    """DM-time transform of one band for every pixel"""
    dm, t_inf = event["dm"], event["t_inf"]
    n_chan, dt = band["n_chan"], band["int_time"] or 0.08359183673469386
    chan_bw = settings.CHAN_BW_HZ * round(band["chan_bw_hz"] / settings.CHAN_BW_HZ)
    f_lo = band["chan0"] * settings.CHAN_BW_HZ / 1e6
    edges = f_lo + np.arange(n_chan + 1) * chan_bw / 1e6
    f_c = edges[:-1] + chan_bw / 2e6
    f_hi = edges[-1]
    f_mid = (f_lo + f_hi) / 2

    dm_lo = dm - dm_half
    x_grid = np.arange(0, 2 * dm_half + DM_STEP / 2, DM_STEP)  # residual DM above dm_lo
    span = edges[0] ** -2 - edges[-1] ** -2
    d_max = int(np.ceil(2 * dm_half * K_DM * span / dt))
    smear = 2 * K_DM * dm * (chan_bw / 1e6) / f_mid**3
    w_match = max(1, int(round(smear / dt)))
    search_half = smear / 2 + SEARCH_TAU
    max_width_s = max(smear, 1.0)
    tau_half = float(np.clip(search_half + OFF_WIDTHS * max_width_s, TAU_HALF, MAX_TAU_HALF))
    pad = smear + 20.0

    # each channel on a grid of time relative to its own arrival at dm_lo
    r0 = -tau_half - pad
    r1 = tau_half + K_DM * 2 * dm_half / edges[0] ** 2 + pad
    n_t = int(np.ceil((r1 - r0) / dt)) + 1
    rel = r0 + np.arange(n_t) * dt

    base = dict(chan0=band["chan0"], f_lo_mhz=f_lo, f_hi_mhz=f_hi, smear_s=smear, width_match_s=w_match * dt,
                dm_lo=dm_lo, dm_half=dm_half)
    delay_lo = K_DM * dm_lo / f_c**2
    t_first = t_inf + timedelta(seconds=float(delay_lo.min() + r0))
    t_last = t_inf + timedelta(seconds=float(delay_lo.max() + r1))
    t_first, t_last = max(t_first, band["start"]), min(t_last, band["end"])
    if t_first >= t_last:
        when = "before this band's session started" if t_last <= band["start"] else "after this band's session ended"
        return base | dict(status="no_data", note=f"The burst reached this band {when}.", pixels={})

    # the stored map is smoothed to the smearing, so half of it is fine sampling;
    # the peak search itself runs at the full resolution
    tau_step = max(dt, w_match * dt / 2)
    tau_grid = np.arange(-tau_half, tau_half + tau_step / 2, tau_step)
    d_of_x = np.clip(np.rint(x_grid * K_DM * span / dt).astype(int), 0, d_max)
    pixels = {}
    # one pixel at a time: in the low bands a window spans about an hour
    for key in PIXELS:
        if key == (0, 0):
            # the source itself, interpolated at its exact position; the other
            # pixels stay as stored, for the comparison across the grid
            times, stokes_i = fetch_source_stokes_i(session, event["source"], band["chan0"], t_first, t_last,
                                                    n_chan, event["ra"], event["dec"])
        else:
            times, stokes_i = _fetch_pixel(session, event["source"], band["chan0"], t_first, t_last, n_chan, key)
        if not len(times):
            continue
        cleaned, mask = rfi.clean(stokes_i, dt, max(smear, 1.0))
        t_rel = (times - np.datetime64(t_inf, "us")) / np.timedelta64(1, "s")
        image = np.zeros((n_chan, n_t))
        for c in range(n_chan):
            k = np.rint((t_rel - delay_lo[c] - r0) / dt).astype(int)
            ok = (k >= 0) & (k < n_t) & np.isfinite(cleaned[:, c])
            sums = np.bincount(k[ok], weights=cleaned[ok, c], minlength=n_t)
            counts = np.bincount(k[ok], minlength=n_t)
            image[c] = np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)
        masked_frac = 1.0 - float(mask.mean())

        transform = fdmt(image, edges, d_max)  # [d_max + 1, n_t], time = arrival at the bottom edge

        # resample every trial DM onto arrival time at infinite frequency
        snr_map = np.full((len(x_grid), len(tau_grid)), np.nan)
        snr_dm = np.full(len(x_grid), np.nan)
        best = (np.nan, 0.0, 0.0, 0)
        widths = [1]
        while widths[-1] * 2 <= max(1, int(min(max_width_s, (tau_half - search_half) / OFF_WIDTHS) / dt)):
            widths.append(widths[-1] * 2)
        cache: dict[int, tuple] = {}
        for i, (x, d) in enumerate(zip(x_grid, d_of_x)):
            if d not in cache:
                row = transform[d]
                # arrival at the bottom edge = tau + K x / f_bottom^2 in this frame
                x_d = d * dt / (K_DM * span)
                tau_row = rel - K_DM * x_d / edges[0] ** 2
                off = np.abs(tau_row) > search_half + w_match * dt
                on = np.abs(tau_row) <= search_half
                matched = _normalise(_boxcar(row, w_match), off)
                peak = (np.nan, 0.0, 0)
                for w in widths:
                    s = _normalise(_boxcar(row, w), off)
                    cand = np.where(on, s, np.nan)
                    if np.isfinite(cand).any():
                        j = int(np.nanargmax(cand))
                        if not np.isfinite(peak[0]) or cand[j] > peak[0]:
                            peak = (float(cand[j]), float(tau_row[j]), w)
                cache[d] = (np.interp(tau_grid, tau_row, matched, left=np.nan, right=np.nan), peak, x_d)
            resampled, peak, x_d = cache[d]
            snr_map[i] = resampled
            snr_dm[i] = peak[0]
            if np.isfinite(peak[0]) and (not np.isfinite(best[0]) or peak[0] > best[0]):
                best = (peak[0], dm_lo + x_d, peak[1], peak[2])
        pixels[key] = dict(
            snr_map=snr_map, snr_dm=snr_dm, masked_frac=masked_frac,
            peak_snr=best[0], peak_dm=best[1], peak_tau=best[2], peak_width_s=best[3] * dt,
        )
    if not pixels:
        return base | dict(status="no_data", note="No images of the source were stored for this window.", pixels={})
    return base | dict(status="ok", note=None, dt=tau_step, tau_grid=tau_grid, tau_half=tau_half, pixels=pixels)


def combine(bands: list[dict], x_grid: np.ndarray, dm_lo: float) -> dict:
    """Combine the bands with data, per pixel, on the common DM and time grid"""
    ok = [b for b in bands if b["status"] == "ok"]
    if not ok:
        return {}
    # the span of the longest band window, sampled as finely as the finest
    # band; the smoother low-band maps are interpolated onto it
    dt = min(b["dt"] for b in ok)
    tau_half = max(b["tau_half"] for b in ok)
    tau_grid = np.arange(-tau_half, tau_half + dt / 2, dt)
    out = {}
    for key in PIXELS:
        maps = [np.array([np.interp(tau_grid, b["tau_grid"], r, left=np.nan, right=np.nan) for r in b["pixels"][key]["snr_map"]])
                for b in ok if key in b["pixels"]]
        if not maps:
            continue
        stack = np.stack(maps)
        n = np.isfinite(stack).sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            comb = np.where(n > 0, np.nansum(stack, axis=0) / np.sqrt(np.maximum(n, 1)), np.nan)
        on = np.abs(tau_grid) <= SEARCH_TAU
        for i in range(len(comb)):
            comb[i] = _normalise(comb[i], ~on)
        with np.errstate(invalid="ignore"), np.testing.suppress_warnings() as sup:
            sup.filter(RuntimeWarning)
            snr_dm = np.nanmax(np.where(on[None, :], comb, np.nan), axis=1)
        if np.isfinite(snr_dm).any():
            i = int(np.nanargmax(snr_dm))
            j = int(np.nanargmax(np.where(on, comb[i], np.nan)))
            peak = dict(peak_snr=float(snr_dm[i]), peak_dm=float(dm_lo + x_grid[i]), peak_tau=float(tau_grid[j]))
        else:
            peak = dict(peak_snr=None, peak_dm=None, peak_tau=None)
        out[key] = dict(snr_map=comb, snr_dm=snr_dm, n_bands=len(maps)) | peak
    return dict(tau_grid=tau_grid, dt=dt, pixels=out)


def _f32(a) -> bytes:
    return np.asarray(a, dtype="<f4").tobytes()


def _num(v):
    return float(v) if v is not None and np.isfinite(v) else None


def summarise(event: dict, pos, bands: list[dict], comb: dict) -> dict:
    """Event-level numbers for the page and the Slack message"""
    band_rows = []
    for b in bands:
        row = dict(chan0=b["chan0"], f_lo_mhz=b["f_lo_mhz"], f_hi_mhz=b["f_hi_mhz"], status=b["status"], note=b.get("note"),
                   smear_s=_num(b.get("smear_s")))
        f_mid = (b["f_lo_mhz"] + b["f_hi_mhz"]) / 2
        arrival = event["t_inf"] + timedelta(seconds=K_DM * event["dm"] / f_mid**2)
        row["arrival_utc"] = arrival.isoformat()
        if pos is not None:
            row["elevation_deg"] = _elevation(pos[0], pos[1], arrival)
        centre = b.get("pixels", {}).get((0, 0))
        if centre:
            row |= dict(snr=_num(centre["peak_snr"]), dm=_num(centre["peak_dm"]), tau_s=_num(centre["peak_tau"]),
                        width_s=_num(centre["peak_width_s"]), masked_frac=_num(centre["masked_frac"]))
            bw = (b["f_hi_mhz"] - b["f_lo_mhz"]) * 1e6 * (1 - centre["masked_frac"])
            if pos is not None:
                row |= _fluence_limit(f_mid, row["elevation_deg"], bw, max(b["width_match_s"], 0.0836))
        band_rows.append(row)

    combined, localisation = None, None
    pix = comb.get("pixels", {})
    if (0, 0) in pix:
        c = pix[(0, 0)]
        combined = dict(snr=_num(c["peak_snr"]), dm=_num(c["peak_dm"]), tau_s=_num(c["peak_tau"]), n_bands=c["n_bands"])
        others = [p["peak_snr"] for k, p in pix.items() if k != (0, 0) and p["peak_snr"] is not None]
        localisation = dict(
            centre_snr=_num(c["peak_snr"]),
            best_other_snr=_num(max(others)) if others else None,
            median_other_snr=_num(float(np.median(others))) if others else None,
            centre_is_brightest=bool(others) and c["peak_snr"] is not None and c["peak_snr"] >= max(others),
        )
    detected = bool(combined and combined["snr"] is not None and combined["snr"] >= SNR_THRESHOLD
                    and localisation and localisation["centre_is_brightest"])
    dm_half = dm_half_range(event["dm_err"])
    return dict(
        version=VERSION, source=event["source"], dm_chime=event["dm"], dm_err_chime=event["dm_err"],
        t_inf=event["t_inf"].isoformat(), dm_lo=event["dm"] - dm_half, dm_hi=event["dm"] + dm_half, dm_step=DM_STEP,
        search_tau_s=SEARCH_TAU, snr_threshold=SNR_THRESHOLD, bands=band_rows, combined=combined,
        localisation=localisation, detected=detected,
        method=dict(rfi="CHIME/FRB L1 clipping and detrending chain (Rafiei-Ravandi & Smith 2023)",
                    transform="FDMT (Zackay & Ofek 2017)", search="boxcar, per band and combined (Pleunis et al. 2021)"),
    )
