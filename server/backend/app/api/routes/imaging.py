from fastapi import APIRouter, HTTPException
from sqlmodel import select, func

from sqlalchemy.dialects.postgresql import TEXT

from app.api.deps import UserDep, WatchListPagiDep
from app.api.deps import (
    SessionDep,
    ObsSessionsPagiDep,
    ObsPeriodDep,
    SpecgmWindowDep,
)
from app.models.epic_data import (
    epic_img_session_public,
    epic_img_metadata,
    epic_pixels,
    epic_pixels_public,
    test_epic_pixels
)

router = APIRouter()


@router.get("/sessions/", response_model=epic_img_session_public)
async def get_imaging_sessions(
    session: SessionDep,
    current_user: UserDep,
    pagination: ObsSessionsPagiDep,
    obs_period: ObsPeriodDep,
):
    group_rows = [
        epic_img_metadata.session_id,
        epic_img_metadata.chan0,
        epic_img_metadata.n_chan,
        epic_img_metadata.n_pol,
        epic_img_metadata.chan_bw_hz,
        epic_img_metadata.int_time,
    ]
    stmnt = (
        select(func.count(func.distinct(*group_rows)))
        .where(
            epic_img_metadata.img_time.between(
                obs_period.start_time, obs_period.end_time
            )
        )
        .where(
            epic_img_metadata.source_names.contains([obs_period.source_name])
        )
    )
    count = session.exec(stmnt).one()
    stmnt = (
        select(
            *group_rows,
            func.min(epic_img_metadata.img_time).label("start_time"),
            func.max(epic_img_metadata.img_time).label("end_time"),
        )
        .group_by(*group_rows)
        .where(
            epic_img_metadata.img_time.between(
                obs_period.start_time, obs_period.end_time
            )
        )
        .where(
            epic_img_metadata.source_names.contains([obs_period.source_name])
        )
        .order_by(func.min(epic_img_metadata.img_time).label("start_time").desc())
        .order_by(epic_img_metadata.chan0.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    print(stmnt)
    obs_sessions = session.exec(stmnt).all()
    return epic_img_session_public(data=obs_sessions, count=count)


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
    data = session.exec(stmnt).all()
    return data
