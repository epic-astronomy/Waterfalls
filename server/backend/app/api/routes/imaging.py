from typing import Literal
from fastapi import APIRouter, HTTPException
from sqlmodel import select, func, text

from sqlalchemy.dialects.postgresql import TEXT
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, false, true


from app.api.deps import UserDep, WatchListPagiDep
from app.api.deps import (
    SessionDep,
    ObsSessionsPagiDep,
    ObsPeriodDep,
    SpecgmWindowDep,
    DailyDigestDep,
    DailySourcesDep,
)
from app.models.epic_data import (
    epic_img_session_public,
    epic_img_metadata,
    epic_pixels,
    epic_pixels_public,
    test_epic_pixels,
    epic_daily_digest_table,
    epic_daily_digest_public,
    daily_obs,
    epic_digest_point,
)

router = APIRouter()
from app.core.config import settings
from app.frb.products import K_DM, load_event

# cfreq is stored as real, so match bands on the recovered first channel
digest_chan0 = (
    func.round(epic_daily_digest_table.cfreq / settings.CHAN_BW_HZ)
    - settings.DIGEST_CHAN_OFFSET
)


def burst_condition(session, source_name: str):
    """SQL condition: the session spans part of the burst's crossing of its
    band, from the top edge at DM - error to the bottom edge at DM + error.
    False when the source is not a CHIME/FRB event with a DM."""
    event_id = session.execute(
        text("select id from public.epic_watchdog where source = :s and event_type = 'FRB detection' "
             "order by id desc limit 1"), dict(s=source_name)).scalar()
    event = load_event(session, event_id) if event_id is not None else None
    if event is None:
        return false()
    t_inf = event["t_inf"].replace(tzinfo=timezone.utc).timestamp()
    f_lo = epic_img_metadata.chan0 * settings.CHAN_BW_HZ / 1e6
    f_hi = f_lo + epic_img_metadata.n_chan * epic_img_metadata.chan_bw_hz / 1e6
    first = t_inf + K_DM * max(event["dm"] - event["dm_err"], 0.0) / (f_hi * f_hi)
    last = t_inf + K_DM * (event["dm"] + event["dm_err"]) / (f_lo * f_lo)
    return and_(func.extract("epoch", epic_img_metadata.session_start) < last,
                func.extract("epoch", epic_img_metadata.session_end) > first)


@router.get("/sessions/", response_model=epic_img_session_public)
async def get_imaging_sessions(
    session: SessionDep,
    current_user: UserDep,
    pagination: ObsSessionsPagiDep,
    obs_period: ObsPeriodDep,
    sort: str | None = None,
    order: Literal["asc", "desc"] = "asc",
    burst_only: bool = False,
    session_id: str | None = None,
    chan0: int | None = None,
):
    """Imaging sessions of a source within a period. With `burst_only`, for a
    CHIME/FRB source, only the sessions during which the burst crosses their
    band, allowing for the DM error."""
    burst_cond = burst_condition(session, obs_period.source_name) if burst_only else true()
    # one session and band, for restoring a page from its address
    if session_id is not None:
        burst_cond = and_(burst_cond, epic_img_metadata.session_id == session_id)
    if chan0 is not None:
        burst_cond = and_(burst_cond, epic_img_metadata.chan0 == chan0)
    sortable = {
        "start_time": epic_img_metadata.session_start,
        "end_time": epic_img_metadata.session_end,
        "chan0": epic_img_metadata.chan0,
        "chan_bw_hz": epic_img_metadata.chan_bw_hz * epic_img_metadata.n_chan,
        "int_time": epic_img_metadata.int_time,
        "session_duration": epic_img_metadata.session_end - epic_img_metadata.session_start,
        "n_pol": epic_img_metadata.n_pol,
        "session_id": epic_img_metadata.session_id,
    }
    if sort in sortable:
        column = sortable[sort]
        ordering = [column.asc() if order == "asc" else column.desc()]
    else:
        ordering = []
    # newest first, then by band, after any requested column
    ordering += [epic_img_metadata.session_start.desc(), epic_img_metadata.chan0.asc()]
    group_rows = [
        epic_img_metadata.session_id,
        epic_img_metadata.chan0,
        epic_img_metadata.n_chan,
        epic_img_metadata.n_pol,
        epic_img_metadata.chan_bw_hz,
        epic_img_metadata.int_time,
    ]
    stmnt = (
        select(func.count(epic_img_metadata.session_id))
        .where(
            func.tsrange(obs_period.start_time, obs_period.end_time, "[]").op(
                "&&"
            )(
                func.tsrange(
                    epic_img_metadata.session_start,
                    epic_img_metadata.session_end,
                    "[]",
                )
            )
        )
        .where(epic_img_metadata.source_name == obs_period.source_name)
        .where(epic_img_metadata.chan0 == func.any_(settings.OBS_CHANS))
        .where(burst_cond)
    )
    count = session.exec(stmnt).one()
    stmnt = (
        select(
            *group_rows,
            epic_img_metadata.session_start.label("start_time"),
            epic_img_metadata.session_end.label("end_time"),
        )
        .where(
            func.tsrange(obs_period.start_time, obs_period.end_time, "[]").op(
                "&&"
            )(
                func.tsrange(
                    epic_img_metadata.session_start,
                    epic_img_metadata.session_end,
                    "[]",
                )
            )
        )
        .where(epic_img_metadata.source_name == obs_period.source_name)
        .where(epic_img_metadata.chan0 == func.any_(settings.OBS_CHANS))
        .where(burst_cond)
        .order_by(*ordering)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    obs_sessions = session.exec(stmnt).all()
    return epic_img_session_public(data=obs_sessions, count=count)


@router.get("/dailyobs/", response_model=list[daily_obs])
async def get_imaging_sessions(
    session: SessionDep, current_user: UserDep, window: DailySourcesDep
):
    stmnt = (
        select(
            epic_img_metadata.source_name,
            epic_img_metadata.chan0,
            epic_img_metadata.chan_bw_hz,
        )
        .where(
            func.upper(
                func.tsrange(window.start_time, window.end_time, "[]").op("*")(
                    func.tsrange(
                        epic_img_metadata.session_start,
                        epic_img_metadata.session_end,
                        "[]",
                    )
                )
            )
            - func.lower(
                func.tsrange(window.start_time, window.end_time, "[]").op("*")(
                    func.tsrange(
                        epic_img_metadata.session_start,
                        epic_img_metadata.session_end,
                        "[]",
                    )
                )
            )
            >= text("INTERVAL '30 MINUTES'")
        )
        .where(epic_img_metadata.chan0 == func.any_(settings.OBS_CHANS))
        .distinct()
        .order_by(epic_img_metadata.chan0.desc())
    )
    print(stmnt)
    return session.exec(stmnt).all()


@router.get("/dailyobs/days/", response_model=list[date])
async def get_daily_obs_days(session: SessionDep, current_user: UserDep, start: date, end: date):
    """The UTC days from `start` to `end` with a daily digest: those with at
    least 30 minutes of an imaging session, as /dailyobs/ requires"""
    if (end - start).days > 4000:
        raise HTTPException(status_code=400, detail="At most 4000 days at a time")
    lo, hi = datetime.combine(start, time()), datetime.combine(end + timedelta(days=1), time())
    sessions = session.exec(
        select(epic_img_metadata.session_start, epic_img_metadata.session_end)
        .where(epic_img_metadata.chan0 == func.any_(settings.OBS_CHANS))
        .where(epic_img_metadata.session_start < hi)
        .where(epic_img_metadata.session_end > lo)
        .distinct()
    ).all()
    days = set()
    for s0, s1 in sessions:
        d = max(s0, lo).date()
        while datetime.combine(d, time()) < min(s1, hi):
            d0 = datetime.combine(d, time())
            if min(s1, d0 + timedelta(days=1)) - max(s0, d0) >= timedelta(minutes=30):
                days.add(d)
            d += timedelta(days=1)
    return sorted(days)


@router.get("/spectrogram/", response_model=list[test_epic_pixels])
async def get_spectrogram(
    session: SessionDep, current_user: UserDep, specgm_window: SpecgmWindowDep
):
    stmnt = (
        select(
            epic_pixels.img_time.label("img_time"),
            func.encode(epic_pixels.pixel_values, "base64").label(
                "pixel_values"
            ),
        )
        .where(
            epic_pixels.img_time.between(
                specgm_window.start_time, specgm_window.end_time
            )
        )
        .where(epic_pixels.chan0 == specgm_window.chan0)
        .where(epic_pixels.source_name == specgm_window.source_name)
        .where(
            func.cast(epic_pixels.pix_offset, TEXT)
            == func.any_([specgm_window.pixel_positions])
        )
    )

    print(stmnt.compile().string)
    data = session.exec(stmnt).all()
    return data


@router.get("/dailydigest/", response_model=epic_daily_digest_public)
async def get_daily_digest(
    session: SessionDep, current_user: UserDep, digest_def: DailyDigestDep
):
    stmnt = (
        select(
            epic_daily_digest_table.cfreq,
            func.count(epic_daily_digest_table.cfreq),
        )
        .where(epic_daily_digest_table.source_name == digest_def.source_name)
        .where(epic_daily_digest_table.img_time >= digest_def.start_time)
        .where(epic_daily_digest_table.img_time <= digest_def.end_time)
        .where(digest_chan0 == func.any_(settings.OBS_CHANS))
        .group_by(epic_daily_digest_table.cfreq)
        .order_by(epic_daily_digest_table.cfreq.desc())
    )
    stats = session.exec(stmnt).all()
    stmnt = (
        select(
            epic_daily_digest_table.img_time,
            epic_daily_digest_table.stokes_i,
            epic_daily_digest_table.stokes_v,
            epic_daily_digest_table.cfreq,
        )
        .where(epic_daily_digest_table.source_name == digest_def.source_name)
        .where(epic_daily_digest_table.img_time >= digest_def.start_time)
        .where(epic_daily_digest_table.img_time <= digest_def.end_time)
        .where(digest_chan0 == func.any_(settings.OBS_CHANS))
        .order_by(
            epic_daily_digest_table.cfreq.desc(),
            epic_daily_digest_table.img_time.asc(),
        )
    )
    data = session.exec(stmnt).all()
    return epic_daily_digest_public(stats=stats, data=data)


@router.get("/lightcurve/", response_model=list[epic_digest_point])
async def get_light_curve(
    session: SessionDep, current_user: UserDep, obs_period: ObsPeriodDep, chan0: int
):
    """Daily digest spectra of one source in one band over a time range"""
    stmnt = (
        select(epic_daily_digest_table.img_time, epic_daily_digest_table.stokes_i)
        .where(epic_daily_digest_table.source_name == obs_period.source_name)
        .where(
            epic_daily_digest_table.img_time.between(
                obs_period.start_time, obs_period.end_time
            )
        )
        .where(digest_chan0 == chan0)
        .order_by(epic_daily_digest_table.img_time.asc())
    )
    return session.exec(stmnt).all()
