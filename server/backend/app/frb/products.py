"""
Dedispersed products of CHIME/FRB watches, per imaging band.

For every band, each channel is cut out around the burst's expected arrival
in that channel and placed on a common time axis relative to it, so that a
burst at the catalogue DM lines up at zero in every channel and band. Each
channel is detrended and normalised to S/N units using the samples away from
zero, channels dominated by RFI are flagged, and the unflagged channels are
averaged into a band time series whose peak is searched with boxcar filters.

Before dedispersion the dynamic spectrum is masked and detrended with the
CHIME/FRB L1 RFI chain (rfi.py). Its fit along frequency removes undispersed
broadband RFI and gain or sky variations, which dedispersion would otherwise
turn into slanted stripes, while a burst at a DM of hundreds sweeps through
the band and is barely affected.
"""

import logging
import re
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.frb import rfi
from app.frb.source_pixel import fetch_source_stokes_i

log = logging.getLogger(__name__)

VERSION = 6
K_DM = 4148.808  # dispersion delay constant, s MHz^2 cm^3 / pc
CHIME_REF_MHZ = 400.0  # frequency of the arrival time CHIME/FRB publishes
N_POL = 4  # XX, YY, Re(XY), Im(XY) per channel in epic_pixels.pixel_values
MIN_HALF_WINDOW_S = 60.0
MAX_HALF_WINDOW_S = 900.0
# the window outside the search region holds at least this many of the widest
# boxcar, so its noise level is measured from enough independent samples
OFF_WIDTHS = 10
FETCH_CHUNK_S = 600.0
MAD_TO_SIGMA = 1.4826


def voevent_param(voevent: str, name: str) -> str | None:
    m = re.search(rf'<Param name="{name}" value="([^"]*)"', voevent or "")
    return m.group(1) if m else None


def _robust(x: np.ndarray, axis=None):
    med = np.nanmedian(x, axis=axis, keepdims=True)
    mad = np.nanmedian(np.abs(x - med), axis=axis, keepdims=True)
    return med, MAD_TO_SIGMA * mad


def _boxcar_peak(ts: np.ndarray, on: np.ndarray, off: np.ndarray, max_width: int):
    """Best boxcar S/N inside the on-pulse samples, as (snr, width, index)"""
    best = (np.nan, 1, -1)
    filled = np.where(np.isfinite(ts), ts, 0.0)
    valid = np.isfinite(ts).astype(float)
    w = 1
    while w <= max_width:
        kernel = np.ones(w)
        num = np.convolve(filled, kernel, mode="same")
        cnt = np.convolve(valid, kernel, mode="same")
        with np.errstate(invalid="ignore", divide="ignore"):
            sm = np.where(cnt >= 0.5 * w, num / cnt, np.nan)
        med, sig = _robust(sm[off])
        if np.isfinite(sig).all() and sig.item() > 0:
            snr = (sm - med.item()) / sig.item()
            cand = np.where(on, snr, np.nan)
            if np.isfinite(cand).any():
                i = int(np.nanargmax(cand))
                if not np.isfinite(best[0]) or cand[i] > best[0]:
                    best = (float(cand[i]), w, i)
        w *= 2
    return best


def band_product(pixels, event: dict, band: dict) -> dict:
    """Dedispersed, normalised product of one band of one event, from the
    pixels read through `pixels` (the band's node)"""
    dm, dm_err, t_inf = event["dm"], event["dm_err"], event["t_inf"]
    n_chan, dt = band["n_chan"], band["int_time"] or 0.08359183673469386
    chan_bw = settings.CHAN_BW_HZ * round(band["chan_bw_hz"] / settings.CHAN_BW_HZ)
    f_lo = band["chan0"] * settings.CHAN_BW_HZ / 1e6
    f_c = f_lo + (np.arange(n_chan) + 0.5) * chan_bw / 1e6  # channel centres, MHz
    f_mid = f_lo + n_chan * chan_bw / 2e6

    delay = K_DM * dm / f_c**2  # s after t_inf, per channel
    sigma_t = K_DM * dm_err / f_c**2
    smear = 2 * K_DM * dm * (chan_bw / 1e6) / f_mid**3
    on_half = smear / 2 + 3 * K_DM * dm_err / f_mid**2 + 2.0
    max_width_s = max(smear, 1.0)  # widest boxcar: the smearing within a channel
    half = float(np.clip(on_half + OFF_WIDTHS * max_width_s, MIN_HALF_WINDOW_S, MAX_HALF_WINDOW_S))
    n_half = int(np.ceil(half / dt))
    n_time = 2 * n_half + 1
    rel = (np.arange(n_time) - n_half) * dt

    out = dict(
        chan0=band["chan0"], f_lo_mhz=f_lo, chan_bw_hz=chan_bw, n_chan=n_chan, dt_s=dt,
        t0_rel_s=float(rel[0]), n_time=n_time, smear_s=smear, on_half_s=on_half,
    )

    # data needed: the window around every channel's arrival, inside the session
    t_first = t_inf + timedelta(seconds=float(delay.min()) - half - dt)
    t_last = t_inf + timedelta(seconds=float(delay.max()) + half + dt)
    t_first, t_last = max(t_first, band["start"]), min(t_last, band["end"])
    if t_first >= t_last:
        when = "before this band's session started" if t_last <= band["start"] else "after this band's session ended"
        return out | dict(status="no_data", note=f"The burst reached this band {when}.")

    # the source's value interpolated at its exact position, not the nearest pixel
    times, stokes_i = fetch_source_stokes_i(pixels, event["source"], band["chan0"], t_first, t_last, n_chan,
                                            event["ra"], event["dec"])
    if not len(times):
        return out | dict(status="no_data", note="No images of the source were stored for this window.")

    t_rel = (times - np.datetime64(t_inf, "us")) / np.timedelta64(1, "s")

    # mask RFI and detrend before dedispersion; masked samples become NaN
    stokes_i, _ = rfi.clean(stokes_i, dt, max(smear, 1.0))
    image = np.full((n_chan, n_time), np.nan)
    for c in range(n_chan):
        k = np.rint((t_rel - delay[c]) / dt).astype(int) + n_half
        ok = (k >= 0) & (k < n_time)
        sums = np.bincount(k[ok], weights=stokes_i[ok, c], minlength=n_time)
        counts = np.bincount(k[ok], minlength=n_time)
        with np.errstate(invalid="ignore", divide="ignore"):
            image[c] = np.where(counts > 0, sums / counts, np.nan)

    # off-pulse: away from zero by more than the smearing and DM uncertainty
    off = np.abs(rel)[None, :] > (smear / 2 + 3 * sigma_t[:, None] + 2.0)

    # remove a linear trend fitted to the off-pulse samples, then normalise
    for c in range(n_chan):
        m = off[c] & np.isfinite(image[c])
        if m.sum() > 10:
            image[c] -= np.polyval(np.polyfit(rel[m], image[c, m], 1), rel)
    off_vals = np.where(off, image, np.nan)
    med, sig = _robust(off_vals, axis=1)
    raw_sig = sig[:, 0].copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (image - med) / sig

    # flag dead, unusually noisy or impulsive channels
    typical = np.nanmedian(raw_sig)
    with np.errstate(invalid="ignore"):
        impulsive = np.nanmean(np.where(off, np.abs(z) > 5, np.nan), axis=1)
        flagged = (
            ~np.isfinite(raw_sig) | (raw_sig <= 0)
            | (raw_sig > 3 * typical) | (raw_sig < typical / 3)
            | (impulsive > 0.02)
        )
    z[flagged] = np.nan
    good = ~flagged
    coverage = float(np.isfinite(image[good]).mean()) if good.any() else 0.0

    ts = np.full(n_time, np.nan)
    peak = (np.nan, 1, -1)
    if good.any():
        with np.errstate(invalid="ignore"):
            ts = np.nanmean(z[good], axis=0) if good.sum() else ts
        band_off = np.abs(rel) > on_half
        m, s = _robust(ts[band_off])
        if np.isfinite(s).all() and s.item() > 0:
            ts = (ts - m.item()) / s.item()
        max_width = max(1, int(min(max_width_s, (half - on_half) / OFF_WIDTHS) / dt))
        peak = _boxcar_peak(ts, np.abs(rel) <= on_half, band_off, max_width)

    snr, width, i = peak
    return out | dict(
        status="ok",
        note=None,
        coverage=coverage,
        flagged=[int(c) for c in np.flatnonzero(flagged)],
        z_image=z.astype("<f4").tobytes(),
        timeseries=ts.astype("<f4").tobytes(),
        peak_snr=snr if np.isfinite(snr) else None,
        peak_width_s=width * dt if np.isfinite(snr) else None,
        peak_t_s=float(rel[i]) if i >= 0 else None,
    )


def load_event(session: Session, event_id: int) -> dict | None:
    row = session.execute(
        text("select id, source, event_time, t_start, t_end, voevent::text, ra_deg, dec_deg from public.epic_watchdog "
             "where id = :id"),
        dict(id=event_id),
    ).first()
    if row is None:
        return None
    dm = voevent_param(row[5], "dm")
    if dm is None:
        return None
    # CHIME/FRB measures the topocentric arrival at the bottom of its band,
    # 400 MHz (timestamp_utc); the time at infinite frequency is derived. Use
    # the measured time as the reference, with our dispersion constant.
    t_ref = voevent_param(row[5], "timestamp_utc")
    if t_ref:
        t_ref = datetime.fromisoformat(t_ref).replace(tzinfo=None)
        t_inf = t_ref - timedelta(seconds=K_DM * float(dm) / CHIME_REF_MHZ**2)
    else:
        t_inf = voevent_param(row[5], "timestamp_utc_inf_freq")
        t_inf = datetime.fromisoformat(t_inf).replace(tzinfo=None) if t_inf else row[2]
        t_ref = t_inf + timedelta(seconds=K_DM * float(dm) / CHIME_REF_MHZ**2)
    return dict(
        id=row[0], source=row[1], t_inf=t_inf, t_ref=t_ref, f_ref_mhz=CHIME_REF_MHZ, t_start=row[3], t_end=row[4],
        dm=float(dm), dm_err=float(voevent_param(row[5], "dm_error") or 0.0),
        ra=float(row[6]), dec=float(row[7]),
    )
