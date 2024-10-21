from fastapi import APIRouter, HTTPException
from sqlmodel import select, func, text

from sqlalchemy.dialects.postgresql import TEXT
from datetime import datetime


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
)

router = APIRouter()
from app.core.config import settings


@router.get("/sessions/", response_model=epic_img_session_public)
async def get_imaging_sessions(
    session: SessionDep,
    current_user: UserDep,
    pagination: ObsSessionsPagiDep,
    obs_period: ObsPeriodDep,
):
    print(obs_period)
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
        .order_by(epic_img_metadata.session_start.label("start_time").desc())
        .order_by(epic_img_metadata.chan0.asc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    print(stmnt)
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
        .where(epic_pixels.session_id == specgm_window.session_id)
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
        .where(epic_daily_digest_table.cfreq == func.any_(settings.CFREQS))
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
        .where(epic_daily_digest_table.cfreq == func.any_(settings.CFREQS))
        .order_by(
            epic_daily_digest_table.cfreq.desc(),
            epic_daily_digest_table.img_time.asc(),
        )
    )
    data = session.exec(stmnt).all()
    return epic_daily_digest_public(stats=stats, data=data)
