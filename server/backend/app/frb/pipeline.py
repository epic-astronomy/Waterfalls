"""
FRB analysis as a queue of (event, band) work items shared by the worker
nodes, and a combination step once every band of an event is done.

A worker takes any pending band, guarded by a Postgres advisory lock on
(event, band), so the six workers process the bands of an event in parallel
and a stopped worker's share is picked up by the others. Each band stores its
dedispersed product and its DM-time transform for all 25 pixels. When every
band of an event has a result, or FRB_COMBINE_AFTER_H hours after the watch
ended, whichever worker gets there first combines the bands, writes the
summary and, if FRB_SLACK_NOTIFY is set, posts it to Slack once.
"""

import json
import logging
import socket
from datetime import timedelta

import numpy as np
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.frb import dmt, notify, products
from app.frb.products import load_event

log = logging.getLogger(__name__)

LOCK_NS = 0x46524200  # first key of the (event, band) advisory locks
COMBINE_LOCK_BAND = -1
SCHEMA = settings.EPIC_DATA_SCHEMA


def _band_sessions(session: Session, event: dict) -> dict[int, dict]:
    rows = session.execute(
        text(
            f"select chan0, n_chan, chan_bw_hz, int_time, min(session_start), max(session_end) from {SCHEMA}.epic_img_metadata2 "
            "where source_name = :src and session_end > :t0 and session_start < :t1 group by chan0, n_chan, chan_bw_hz, int_time"
        ),
        dict(src=event["source"], t0=event["t_start"], t1=event["t_end"]),
    ).all()
    return {r[0]: dict(chan0=r[0], n_chan=r[1], chan_bw_hz=r[2], int_time=r[3], start=r[4], end=r[5]) for r in rows}


def expected_bands(session: Session, event: dict) -> list[int]:
    return sorted(set(settings.OBS_CHANS) | set(_band_sessions(session, event)), reverse=True)


def _store_product(session: Session, event: dict, r: dict) -> None:
    cols = ["status", "note", "f_lo_mhz", "chan_bw_hz", "n_chan", "dt_s", "t0_rel_s", "n_time", "smear_s", "on_half_s",
            "coverage", "flagged", "z_image", "timeseries", "peak_snr", "peak_width_s", "peak_t_s"]
    session.execute(text(f"delete from {SCHEMA}.epic_frb_products where event_id = :id and chan0 = :c"),
                    dict(id=event["id"], c=r["chan0"]))
    session.execute(
        text(f"insert into {SCHEMA}.epic_frb_products (event_id, chan0, source_name, dm, dm_err, t_inf, version, "
             f"{', '.join(cols)}) values (:event_id, :chan0, :source_name, :dm, :dm_err, :t_inf, :version, "
             f"{', '.join(':' + c for c in cols)})"),
        {c: r.get(c) for c in cols} | dict(event_id=event["id"], chan0=r["chan0"], source_name=event["source"],
                                           dm=event["dm"], dm_err=event["dm_err"], t_inf=event["t_inf"],
                                           version=products.VERSION),
    )


_DMT_INSERT = (
    f"insert into {SCHEMA}.epic_frb_dmt (event_id, chan0, px, py, dm_lo, dm_step, n_dm, snr_dm, map_dm_step, map_n_dm, "
    "map_tau0, map_dtau, map_n_tau, map, peak_snr, peak_dm, peak_tau, peak_width_s, extra, version) values "
    "(:event_id, :chan0, :px, :py, :dm_lo, :dm_step, :n_dm, :snr_dm, :map_dm_step, :map_n_dm, :map_tau0, :map_dtau, "
    ":map_n_tau, :map, :peak_snr, :peak_dm, :peak_tau, :peak_width_s, cast(:extra as jsonb), :version)"
)


def _dmt_row(event_id, chan0, key, res, dm_lo, tau_grid, pool=None) -> dict:
    """A row of epic_frb_dmt; the map is stored at full resolution unless pooled"""
    snr_map = res["snr_map"]
    dtau = float(tau_grid[1] - tau_grid[0])
    fr = fc = 1
    if pool:
        snr_map, fr, fc = dmt._pool(snr_map, *pool)
    return dict(
        event_id=event_id, chan0=chan0, px=key[0], py=key[1], dm_lo=dm_lo, dm_step=dmt.DM_STEP,
        n_dm=len(res["snr_dm"]), snr_dm=dmt._f32(res["snr_dm"]), map=dmt._f32(snr_map),
        map_n_dm=snr_map.shape[0], map_n_tau=snr_map.shape[1], map_dm_step=dmt.DM_STEP * fr, map_dtau=dtau * fc,
        map_tau0=float(tau_grid[0] + dtau * (fc - 1) / 2), peak_snr=dmt._num(res.get("peak_snr")),
        peak_dm=dmt._num(res.get("peak_dm")), peak_tau=dmt._num(res.get("peak_tau")),
        peak_width_s=dmt._num(res.get("peak_width_s")),
        extra=json.dumps({k: dmt._num(res[k]) for k in ("masked_frac", "n_bands") if k in res}),
        version=dmt.VERSION,
    )


def process_band(session: Session, event_id: int, chan0: int) -> str:
    """Dedispersed product and DM transform of one band of one event"""
    event = load_event(session, event_id)
    if event is None:
        raise ValueError(f"Event {event_id} not found or has no DM")
    sessions = _band_sessions(session, event)
    dm_half = dmt.dm_half_range(event["dm_err"])
    f_lo = chan0 * settings.CHAN_BW_HZ / 1e6
    meta = dict(f_lo_mhz=f_lo, f_hi_mhz=f_lo + 128 * settings.CHAN_BW_HZ / 1e6, dm_lo=event["dm"] - dm_half, dm_half=dm_half)

    if chan0 not in sessions:
        status, note = "no_session", "This band was not imaging the source during the watch."
        _store_product(session, event, dict(chan0=chan0, f_lo_mhz=f_lo, chan_bw_hz=2 * settings.CHAN_BW_HZ, n_chan=64,
                                            status=status, note=note))
    else:
        band = sessions[chan0]
        log.info("FRB band: event %s band %s dedispersed product", event_id, chan0)
        _store_product(session, event, products.band_product(session, event, band))
        log.info("FRB band: event %s band %s DM transform over +-%.1f", event_id, chan0, dm_half)
        res = dmt.band_dmt(session, event, band, dm_half)
        status, note = res["status"], res.get("note")
        meta |= {k: res[k] for k in ("f_lo_mhz", "f_hi_mhz", "smear_s", "width_match_s") if k in res}
        session.execute(text(f"delete from {SCHEMA}.epic_frb_dmt where event_id = :id and chan0 = :c"),
                        dict(id=event_id, c=chan0))
        if status == "ok":
            meta |= dict(dt=res["dt"], tau_half=res["tau_half"])
            for key, px in res["pixels"].items():
                session.execute(text(_DMT_INSERT), _dmt_row(event_id, chan0, key, px, res["dm_lo"], res["tau_grid"]))

    session.execute(
        text(f"insert into {SCHEMA}.epic_frb_band (event_id, chan0, status, note, products_version, dmt_version, meta, host, updated_at) "
             "values (:id, :c, :s, :n, :pv, :dv, cast(:m as jsonb), :h, clock_timestamp() at time zone 'utc') on conflict (event_id, chan0) do update set "
             "status = excluded.status, note = excluded.note, products_version = excluded.products_version, "
             "dmt_version = excluded.dmt_version, meta = excluded.meta, host = excluded.host, "
             "updated_at = clock_timestamp() at time zone 'utc'"),
        dict(id=event_id, c=chan0, s=status, n=note, pv=products.VERSION, dv=dmt.VERSION, m=json.dumps(meta),
             h=socket.gethostname()),
    )
    session.commit()
    return status


def _load_band(session: Session, event_id: int, row) -> dict:
    """A band's stored result, in the form dmt.combine and dmt.summarise take"""
    chan0, status, note, meta = row
    band = dict(chan0=chan0, status=status, note=note, pixels={}) | meta
    if status != "ok":
        return band
    cols = ["px", "py", "snr_dm", "map", "map_n_dm", "map_n_tau", "map_tau0", "map_dtau", "peak_snr", "peak_dm",
            "peak_tau", "peak_width_s", "extra"]
    for r in session.execute(
        text(f"select {', '.join(cols)} from {SCHEMA}.epic_frb_dmt where event_id = :id and chan0 = :c"),
        dict(id=event_id, c=chan0),
    ):
        d = dict(zip(cols, r))
        snr_map = np.frombuffer(bytes(d["map"]), dtype="<f4").reshape(d["map_n_dm"], d["map_n_tau"]).astype(float)
        band["pixels"][(d["px"], d["py"])] = dict(
            snr_map=snr_map, snr_dm=np.frombuffer(bytes(d["snr_dm"]), dtype="<f4").astype(float),
            peak_snr=d["peak_snr"], peak_dm=d["peak_dm"], peak_tau=d["peak_tau"], peak_width_s=d["peak_width_s"],
            masked_frac=(d["extra"] or {}).get("masked_frac"),
        )
        band["tau_grid"] = d["map_tau0"] + np.arange(d["map_n_tau"]) * d["map_dtau"]
    return band


def combine_event(session: Session, event_id: int, notify_slack: bool | None = None) -> dict:
    """Combine the stored bands of an event, store the result and summary"""
    event = load_event(session, event_id)
    if event is None:
        raise ValueError(f"Event {event_id} not found or has no DM")
    pos = session.execute(text("select ra_deg, dec_deg from public.epic_watchdog where id = :id"), dict(id=event_id)).first()
    rows = {r[0]: r for r in session.execute(
        text(f"select chan0, status, note, meta from {SCHEMA}.epic_frb_band where event_id = :id"), dict(id=event_id))}
    bands = []
    for chan0 in expected_bands(session, event):
        if chan0 in rows:
            bands.append(_load_band(session, event_id, rows[chan0]))
        else:
            f_lo = chan0 * settings.CHAN_BW_HZ / 1e6
            bands.append(dict(chan0=chan0, f_lo_mhz=f_lo, f_hi_mhz=f_lo + 128 * settings.CHAN_BW_HZ / 1e6,
                              status="not_analysed", note="No worker analysed this band in time.", pixels={}))

    dm_half = dmt.dm_half_range(event["dm_err"])
    dm_lo = event["dm"] - dm_half
    x_grid = np.arange(0, 2 * dm_half + dmt.DM_STEP / 2, dmt.DM_STEP)
    comb = dmt.combine(bands, x_grid, dm_lo)

    session.execute(text(f"delete from {SCHEMA}.epic_frb_dmt where event_id = :id and chan0 = 0"), dict(id=event_id))
    for key, res in comb.get("pixels", {}).items():
        pool = (401, 480) if key == (0, 0) else (101, 240)
        session.execute(text(_DMT_INSERT), _dmt_row(event_id, 0, key, res, dm_lo, comb["tau_grid"], pool))

    summary = dmt.summarise(event, pos, bands, comb)
    session.execute(
        text(f"insert into {SCHEMA}.epic_frb_analysis (event_id, dmt_version, summary, created_at) values (:id, :v, cast(:s as jsonb), clock_timestamp() at time zone 'utc') "
             "on conflict (event_id) do update set dmt_version = excluded.dmt_version, summary = excluded.summary, "
             "created_at = clock_timestamp() at time zone 'utc'"),
        dict(id=event_id, v=dmt.VERSION, s=json.dumps(summary)),
    )
    session.commit()

    if settings.FRB_SLACK_NOTIFY if notify_slack is None else notify_slack:
        notified = session.execute(text(f"select notified_at from {SCHEMA}.epic_frb_analysis where event_id = :id"),
                                   dict(id=event_id)).scalar()
        if notified is None and notify.post(event_id, summary):
            session.execute(text(f"update {SCHEMA}.epic_frb_analysis set notified_at = now() at time zone 'utc' "
                                 "where event_id = :id"), dict(id=event_id))
            session.commit()
    return summary


def _recent_events(session: Session) -> list[int]:
    """Finished CHIME watches recent enough to analyse"""
    return [r[0] for r in session.execute(
        text("select id from public.epic_watchdog where event_type = 'FRB detection' "
             "and t_end < (now() at time zone 'utc') "
             "and t_end > (now() at time zone 'utc') - make_interval(days => :days) order by t_end"),
        dict(days=settings.FRB_PRODUCTS_MAX_AGE_DAYS),
    )]


def pending_bands(session: Session) -> list[tuple[int, int]]:
    """(event, band) pairs without a current result"""
    done = {(r[0], r[1]) for r in session.execute(
        text(f"select event_id, chan0 from {SCHEMA}.epic_frb_band where products_version >= :pv and dmt_version >= :dv"),
        dict(pv=products.VERSION, dv=dmt.VERSION))}
    out = []
    for event_id in _recent_events(session):
        event = load_event(session, event_id)
        if event is None:
            continue
        out += [(event_id, c) for c in expected_bands(session, event) if (event_id, c) not in done]
    return out


def ready_to_combine(session: Session) -> list[int]:
    """Events whose bands are all done, or whose time to wait has run out,
    and that have no current combination"""
    out = []
    for event_id in _recent_events(session):
        current = session.execute(
            text(f"select dmt_version, created_at from {SCHEMA}.epic_frb_analysis where event_id = :id"), dict(id=event_id)
        ).first()
        bands = session.execute(
            text(f"select chan0, updated_at from {SCHEMA}.epic_frb_band where event_id = :id "
                 "and products_version >= :pv and dmt_version >= :dv"),
            dict(id=event_id, pv=products.VERSION, dv=dmt.VERSION),
        ).all()
        if not bands:
            continue
        if current and current[0] >= dmt.VERSION and current[1] >= max(b[1] for b in bands):
            continue  # combined since the last band changed
        event = load_event(session, event_id)
        complete = {b[0] for b in bands} >= set(expected_bands(session, event))
        overdue = session.execute(
            text("select t_end < (now() at time zone 'utc') - :h * interval '1 hour' from public.epic_watchdog where id = :id"),
            dict(id=event_id, h=settings.FRB_COMBINE_AFTER_H),
        ).scalar()
        # past the deadline, combine without missing bands, but not while a
        # worker is still on one of them
        in_progress = session.execute(
            text("select count(*) from pg_locks where locktype = 'advisory' and objsubid = 2 and classid = :ns and objid >= 0"),
            dict(ns=LOCK_NS + event_id),
        ).scalar()
        if complete or (overdue and not in_progress):
            out.append(event_id)
    return out


def _with_lock(event_id: int, chan0: int, fn) -> bool:
    """Run fn while holding the (event, band) advisory lock; False if taken"""
    with engine.connect() as conn:
        if not conn.execute(text("select pg_try_advisory_lock(:a, :b)"), dict(a=LOCK_NS + event_id, b=chan0)).scalar():
            return False
        try:
            fn()
        finally:
            conn.execute(text("select pg_advisory_unlock(:a, :b)"), dict(a=LOCK_NS + event_id, b=chan0))
            conn.commit()
    return True


def run_worker() -> dict:
    """Process pending bands until none is left that no one else holds, then
    combine any event that is ready"""
    done = dict(bands=[], combined=[])
    with Session(engine) as session:
        while True:
            progressed = False
            for event_id, chan0 in pending_bands(session):
                def work():
                    try:
                        process_band(session, event_id, chan0)
                    except Exception as e:
                        session.rollback()
                        log.exception("FRB band failed: event %s band %s", event_id, chan0)
                        session.execute(
                            text(f"insert into {SCHEMA}.epic_frb_band (event_id, chan0, status, note, products_version, "
                                 "dmt_version, host) values (:id, :c, 'failed', :n, :pv, :dv, :h) on conflict (event_id, chan0) "
                                 "do update set status = 'failed', note = excluded.note, products_version = excluded.products_version, "
                                 "dmt_version = excluded.dmt_version, host = excluded.host, updated_at = clock_timestamp() at time zone 'utc'"),
                            dict(id=event_id, c=chan0, n=f"The analysis failed: {type(e).__name__}.", pv=products.VERSION,
                                 dv=dmt.VERSION, h=socket.gethostname()))
                        session.commit()
                    done["bands"].append((event_id, chan0))
                if _with_lock(event_id, chan0, work):
                    progressed = True
                    break  # re-read the queue, other workers may have moved on
            if not progressed:
                break
        for event_id in ready_to_combine(session):
            if _with_lock(event_id, COMBINE_LOCK_BAND, lambda: combine_event(session, event_id)):
                done["combined"].append(event_id)
    return done
