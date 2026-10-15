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

log = logging.getLogger(__name__)

VERSION = 4
K_DM = 4148.808  # dispersion delay constant, s MHz^2 cm^3 / pc
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


def _fetch_stokes_i(session: Session, source: str, chan0: int, t0: datetime, t1: datetime, n_chan: int):
    """Stokes I (XX + YY) of the source pixel, as (times, [n_rows, n_chan])"""
    times, rows = [], []
    t = t0
    while t < t1:
        t_next = min(t1, t + timedelta(seconds=FETCH_CHUNK_S))
        res = session.execute(
            text(
                f"select img_time, pixel_values from {settings.EPIC_DATA_SCHEMA}.epic_pixels "
                "where img_time >= :t0 and img_time < :t1 and source_name = :src "
                "and pix_offset::text = '(0,0)' and chan0 = :chan0"
            ),
            dict(t0=t, t1=t_next, src=source, chan0=chan0),
        )
        for img_time, values in res:
            times.append(img_time)
            rows.append(bytes(values))
        t = t_next
    if not rows:
        return np.empty(0), np.empty((0, n_chan), np.float32)
    data = np.frombuffer(b"".join(rows), dtype="<f4").reshape(len(rows), n_chan, N_POL)
    return np.array(times, dtype="datetime64[us]"), data[:, :, 0] + data[:, :, 1]


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


def band_product(session: Session, event: dict, band: dict) -> dict:
    """Dedispersed, normalised product of one band of one event"""
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

    times, stokes_i = _fetch_stokes_i(session, event["source"], band["chan0"], t_first, t_last, n_chan)
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
        text("select id, source, event_time, t_start, t_end, voevent::text from public.epic_watchdog where id = :id"),
        dict(id=event_id),
    ).first()
    if row is None:
        return None
    dm = voevent_param(row[5], "dm")
    if dm is None:
        return None
    t_inf = voevent_param(row[5], "timestamp_utc_inf_freq")
    t_inf = datetime.fromisoformat(t_inf).replace(tzinfo=None) if t_inf else row[2]
    return dict(
        id=row[0], source=row[1], t_inf=t_inf, t_start=row[3], t_end=row[4],
        dm=float(dm), dm_err=float(voevent_param(row[5], "dm_error") or 0.0),
    )


def compute_event(session: Session, event_id: int) -> list[dict]:
    """Compute and store the products of every band of an event"""
    event = load_event(session, event_id)
    if event is None:
        raise ValueError(f"Event {event_id} not found or has no DM")

    sessions = session.execute(
        text(
            f"select chan0, n_chan, chan_bw_hz, int_time, min(session_start), max(session_end) "
            f"from {settings.EPIC_DATA_SCHEMA}.epic_img_metadata2 "
            "where source_name = :src and session_end > :t0 and session_start < :t1 "
            "group by chan0, n_chan, chan_bw_hz, int_time"
        ),
        dict(src=event["source"], t0=event["t_start"], t1=event["t_end"]),
    ).all()
    bands = {
        s[0]: dict(chan0=s[0], n_chan=s[1], chan_bw_hz=s[2], int_time=s[3], start=s[4], end=s[5])
        for s in sessions
    }

    results = []
    for chan0 in sorted(set(settings.OBS_CHANS) | set(bands)):
        if chan0 in bands:
            log.info("FRB products: event %s band %s", event_id, chan0)
            res = band_product(session, event, bands[chan0])
        else:
            res = dict(
                chan0=chan0, f_lo_mhz=chan0 * settings.CHAN_BW_HZ / 1e6,
                chan_bw_hz=2 * settings.CHAN_BW_HZ, n_chan=64,
                status="no_session", note="This band was not imaging the source during the watch.",
            )
        results.append(res)

    session.execute(text(f"delete from {settings.EPIC_DATA_SCHEMA}.epic_frb_products where event_id = :id"), dict(id=event_id))
    cols = [
        "status", "note", "f_lo_mhz", "chan_bw_hz", "n_chan", "dt_s", "t0_rel_s", "n_time", "smear_s",
        "on_half_s", "coverage", "flagged", "z_image", "timeseries", "peak_snr", "peak_width_s", "peak_t_s",
    ]
    for r in results:
        session.execute(
            text(
                f"insert into {settings.EPIC_DATA_SCHEMA}.epic_frb_products "
                f"(event_id, chan0, source_name, dm, dm_err, t_inf, version, {', '.join(cols)}) values "
                f"(:event_id, :chan0, :source_name, :dm, :dm_err, :t_inf, :version, {', '.join(':' + c for c in cols)})"
            ),
            {c: r.get(c) for c in cols}
            | dict(event_id=event_id, chan0=r["chan0"], source_name=event["source"],
                   dm=event["dm"], dm_err=event["dm_err"], t_inf=event["t_inf"], version=VERSION),
        )
    session.commit()
    return results


def pending_events(session: Session) -> list[int]:
    """Finished CHIME watches without current products"""
    rows = session.execute(
        text(
            "select w.id from public.epic_watchdog w where w.event_type = 'FRB detection' "
            "and w.t_end < (now() at time zone 'utc') and w.t_end > (now() at time zone 'utc') - make_interval(days => :days) "
            f"and not exists (select 1 from {settings.EPIC_DATA_SCHEMA}.epic_frb_products p "
            "where p.event_id = w.id and p.version >= :version) order by w.t_end"
        ),
        dict(days=settings.FRB_PRODUCTS_MAX_AGE_DAYS, version=VERSION),
    ).all()
    return [r[0] for r in rows]
