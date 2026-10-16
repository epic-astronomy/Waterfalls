import base64
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.api.deps import SessionDep, UserDep
from app.core.config import settings
from app.frb.products import CHIME_REF_MHZ, load_event

router = APIRouter()


def _param(name: str) -> str:
    return f"""substring(w.voevent::text from '<Param name="{name}" value="([^"]*)"')"""


# Columns of the event list, as SQL, so that sorting happens before pagination
EVENT_COLUMNS = {
    "source": "w.source",
    "event_time": "w.event_time",
    "t_ref": f"{_param('timestamp_utc')}::timestamp",
    "dm": f"{_param('dm')}::float",
    "dm_err": f"{_param('dm_error')}::float",
    "n_bands": "coalesce(p.n_bands, 0)",
    "max_snr": "p.max_snr",
    "computed_at": "p.computed_at",
}
# the table's display columns sort by the value behind them
SORT_ALIASES = {"dm_text": "dm", "products": "n_bands", "snr_text": "max_snr"}


@router.get("/events/")
async def get_frb_events(
    session: SessionDep,
    current_user: UserDep,
    page: int = Query(1, ge=1),
    nrows: int = Query(10, ge=1, le=100),
    sort: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    start: datetime | None = None,
    end: datetime | None = None,
):
    """CHIME/FRB watches with a summary of their dedispersed products, a page
    at a time. By default the most recent trigger comes first; a column name
    in `sort` orders by that column instead. With `start` and `end`, only the
    events triggered in that period (a calendar day on the page)."""
    schema = settings.EPIC_DATA_SCHEMA
    period = ""
    params: dict = {}
    if start is not None and end is not None:
        period = "and w.event_time >= :start and w.event_time < :end "
        params = dict(start=start.replace(tzinfo=None), end=end.replace(tzinfo=None))
    count = session.execute(
        text("select count(*) from public.epic_watchdog w where w.event_type = 'FRB detection' " + period), params
    ).scalar_one()
    key = SORT_ALIASES.get(sort, sort)
    if key in EVENT_COLUMNS:
        ordering = f"{EVENT_COLUMNS[key]} {'asc' if order == 'asc' else 'desc'} nulls last, w.id desc"
    else:
        ordering = "w.event_time desc, w.id desc"
    names = list(EVENT_COLUMNS)
    rows = session.execute(
        text(
            f"select w.id, w.t_start, w.t_end, w.watch_status, {', '.join(EVENT_COLUMNS.values())} "
            "from public.epic_watchdog w "
            "left join (select event_id, count(*) filter (where status = 'ok') n_bands, max(peak_snr) max_snr, "
            f"max(created_at) computed_at from {schema}.epic_frb_products group by event_id) p on p.event_id = w.id "
            "where w.event_type = 'FRB detection' " + period +
            f"order by {ordering} limit :limit offset :offset"
        ),
        dict(limit=nrows, offset=(page - 1) * nrows, **params),
    ).all()
    data = [
        dict(id=r[0], t_start=r[1], t_end=r[2], watch_status=r[3], **dict(zip(names, r[4:])), f_ref_mhz=CHIME_REF_MHZ)
        for r in rows
    ]
    return dict(data=data, count=count)


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
