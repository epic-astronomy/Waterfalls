from collections.abc import Generator
from typing import Annotated
from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID

from fastapi import Depends, HTTPException, status, Query
from pydantic import ValidationError
from sqlmodel import Session


# from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models.epic_data import epic_obs_period

# from app.models import users
# from app.models.users import User
from app.models import *


@dataclass
class Pagination:
    skip: int = 0
    limit: int = 0


@dataclass
class SpecgmWindowDef:
    start_time: datetime
    end_time: datetime
    session_id: UUID
    source_name: str
    pixel_positions: list[str]

@dataclass
class DailyDigestDef:
    start_time: datetime
    end_time: datetime
    source_name: str
    cfreq: float

@dataclass
class DailySourcesDef:
    start_time: datetime
    end_time: datetime


async def validate_pagination(page: int = 1, nrows: int = 10) -> Pagination:
    if nrows > settings.WATCHLIST_MAX_ROWS_PER_PAGE:
        nrows = settings.WATCHLIST_MAX_ROWS_PER_PAGE
    if page <= 0:
        page = 1
    return Pagination(limit=nrows, skip=(page - 1) * nrows)


async def validate_obs_period(
    start_time: datetime, end_time: datetime, source_name: str
) -> epic_obs_period:
    if start_time > end_time:
        raise HTTPException(
            status_code=400, detail="End time must be after the start time"
        )
    if source_name == "":
        raise HTTPException(
            status_code=400,
            detail="Query parameter source_name cannot be empty",
        )
    return epic_obs_period(
        start_time=start_time.replace(tzinfo=None), end_time=end_time.replace(tzinfo=None), source_name=source_name
    )


async def validate_specgm_window(
    start_time: datetime,
    end_time: datetime,
    source_name: str,
    session_id: UUID,
    pixel_positions: str#list[str] | None #Annotated[list[str] | None]
) -> SpecgmWindowDef:
    _ = validate_obs_period(start_time, end_time, source_name)
    if (
        end_time - start_time
    ).total_seconds() > settings.MAX_SPECTROGRAM_PERIOD_S:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot fetch spectrogram for more than {settings.MAX_SPECTROGRAM_PERIOD_S}s",
        )
       

    return SpecgmWindowDef(
        start_time=start_time,
        end_time=end_time,
        session_id=session_id,
        source_name=source_name,
        pixel_positions=pixel_positions
    )

async def validate_daily_digest_def(
        day: datetime,
        source_name: str,
        cfreq: float
) -> DailyDigestDef:
    return DailyDigestDef(
        start_time=datetime.combine(day.date(), time.min).replace(tzinfo=None),
        end_time=datetime.combine(day.date(),time.max).replace(tzinfo=None),
        source_name=source_name,
        cfreq=cfreq
    )

async def validate_daily_digest_srcs_def(
        day:datetime
) -> DailySourcesDef:
    return DailySourcesDef(
        start_time=datetime.combine(day.date(), time.min).replace(tzinfo=None),
        end_time=datetime.combine(day.date(),time.max).replace(tzinfo=None)
    )

def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_user() -> int:
    return 1


SessionDep = Annotated[Session, Depends(get_db)]
UserDep = Annotated[int, Depends(get_user)]
WatchListPagiDep = Annotated[Pagination, Depends(validate_pagination)]
ObsSessionsPagiDep = Annotated[Pagination, Depends(validate_pagination)]
ObsPeriodDep = Annotated[epic_obs_period, Depends(validate_obs_period)]
SpecgmWindowDep = Annotated[SpecgmWindowDef, Depends(validate_specgm_window)]
DailyDigestDep = Annotated[DailyDigestDef, Depends(validate_daily_digest_def)]
DailySourcesDep = Annotated[DailySourcesDef, Depends(validate_daily_digest_srcs_def)]
