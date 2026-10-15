import base64

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.api.deps import SessionDep, UserDep
from app.core.config import settings
from app.frb.products import load_event

router = APIRouter()


@router.get("/events/")
async def get_frb_events(session: SessionDep, current_user: UserDep):
    """CHIME/FRB watches with a summary of their dedispersed products"""
    rows = session.execute(
        text(
            "select w.id, w.source, w.event_time, w.t_start, w.t_end, w.watch_status, "
            "count(p.chan0) filter (where p.status = 'ok'), max(p.peak_snr), max(p.created_at), max(p.dm), max(p.dm_err) "
            "from public.epic_watchdog w "
            f"left join {settings.EPIC_DATA_SCHEMA}.epic_frb_products p on p.event_id = w.id "
            "where w.event_type = 'FRB detection' group by w.id, w.source, w.event_time, w.t_start, w.t_end, w.watch_status "
            "order by w.event_time desc"
        )
    ).all()
    return [
        dict(
            id=r[0], source=r[1], event_time=r[2], t_start=r[3], t_end=r[4], watch_status=r[5],
            n_bands=r[6], max_snr=r[7], computed_at=r[8], dm=r[9], dm_err=r[10],
        )
        for r in rows
    ]


@router.get("/events/{event_id}")
async def get_frb_event(event_id: int, session: SessionDep, current_user: UserDep):
    """Dedispersed products of every band of one event"""
    event = load_event(session, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="No FRB event with a DM has this id")
    cols = [
        "chan0", "status", "note", "f_lo_mhz", "chan_bw_hz", "n_chan", "dt_s", "t0_rel_s", "n_time",
        "smear_s", "on_half_s", "coverage", "flagged", "z_image", "timeseries", "peak_snr",
        "peak_width_s", "peak_t_s", "created_at",
    ]
    rows = session.execute(
        text(
            f"select {', '.join(cols)} from {settings.EPIC_DATA_SCHEMA}.epic_frb_products "
            "where event_id = :id order by chan0 desc"
        ),
        dict(id=event_id),
    ).all()
    bands = []
    for r in rows:
        band = dict(zip(cols, r))
        for k in ("z_image", "timeseries"):
            band[k] = base64.b64encode(bytes(band[k])).decode() if band[k] is not None else None
        bands.append(band)
    return dict(event | dict(computed=bool(bands)), bands=bands)


@router.get("/events/{event_id}/dmt")
async def get_frb_dmt(event_id: int, session: SessionDep, current_user: UserDep, px: int = 0, py: int = 0):
    """DM transform of an event: the summary, the combined S/N of every pixel,
    and the combined and per-band transforms of one pixel"""
    schema = settings.EPIC_DATA_SCHEMA
    analysis = session.execute(
        text(f"select summary, created_at, notified_at from {schema}.epic_frb_analysis where event_id = :id"),
        dict(id=event_id),
    ).first()
    if analysis is None:
        return dict(computed=False)
    grid = session.execute(
        text(f"select px, py, peak_snr, peak_dm, peak_tau from {schema}.epic_frb_dmt "
             "where event_id = :id and chan0 = 0 order by py, px"),
        dict(id=event_id),
    ).all()
    cols = ["chan0", "dm_lo", "dm_step", "n_dm", "snr_dm", "map_dm_step", "map_n_dm", "map_tau0", "map_dtau",
            "map_n_tau", "map", "peak_snr", "peak_dm", "peak_tau", "peak_width_s", "extra"]
    rows = session.execute(
        text(f"select {', '.join(cols)} from {schema}.epic_frb_dmt where event_id = :id and px = :px and py = :py "
             "order by chan0 desc"),
        dict(id=event_id, px=px, py=py),
    ).all()
    transforms = []
    for r in rows:
        t = dict(zip(cols, r))
        for k in ("snr_dm", "map"):
            t[k] = base64.b64encode(bytes(t[k])).decode() if t[k] is not None else None
        transforms.append(t)
    return dict(
        computed=True, summary=analysis[0], computed_at=analysis[1], notified_at=analysis[2],
        grid=[dict(px=g[0], py=g[1], snr=g[2], dm=g[3], tau=g[4]) for g in grid],
        pixel=dict(px=px, py=py), transforms=transforms,
    )
