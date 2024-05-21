from fastapi import APIRouter, HTTPException
from sqlmodel import select, func, Session

from app.api.deps import UserDep, WatchListPagiDep
from app.api.deps import SessionDep, Pagination
from app.models.epic_data import epic_watchdog, epic_watchdog_public

router = APIRouter()


async def get_watch_list(
    session: Session, pagination: Pagination, watch_status: str = "watching"
) -> epic_watchdog_public:
    count_stmnt = (
        select(func.count())
        .where(epic_watchdog.watch_status == watch_status)
        .select_from(epic_watchdog)
    )
    count = session.exec(count_stmnt).one()
    fetch_stmnt = (
        select(epic_watchdog)
        .where(epic_watchdog.watch_status == watch_status)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    sources = session.exec(fetch_stmnt).all()

    return epic_watchdog_public(data=sources, count=count)


@router.get("/watching/", response_model=epic_watchdog_public)
async def get_watching_list(
    session: SessionDep, current_user: UserDep, pagination: WatchListPagiDep
):
    sources = await get_watch_list(session, pagination, "watching")
    return sources


@router.get("/watched/", response_model=epic_watchdog_public)
async def get_watched_list(
    session: SessionDep, current_user: UserDep, pagination: WatchListPagiDep
):
    sources = await get_watch_list(session, pagination, "watched")
    return sources
