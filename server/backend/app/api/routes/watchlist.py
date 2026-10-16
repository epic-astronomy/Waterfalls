from fastapi import APIRouter, HTTPException, Request
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import and_, case, or_, true
from sqlmodel import select, func, Session, insert, update

from app.api.deps import UserDep, WatchListPagiDep
from app.api.deps import SessionDep, Pagination
from app.models.epic_data import (
    epic_watchdog,
    epic_watchdog_public,
    chime_frb_trigger,
)
from app.core.config import settings

from datetime import datetime, timedelta
from slack_sdk import WebClient

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

# Category and origin of a watch-list entry, as SQL so that filtering and
# sorting happen before pagination
SOLAR_SYSTEM = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")
CATEGORY = case(
    (or_(epic_watchdog.event_type == "FRB detection", epic_watchdog.source.op("~*")(r"^(chime-)?frb")), "frb"),
    (or_(epic_watchdog.source.op("~*")(r"^(psr|[bj][0-9]{4}[+-])"), func.lower(epic_watchdog.source) == "crab"), "pulsar"),
    (func.lower(epic_watchdog.source).in_(SOLAR_SYSTEM), "solar_system"),
    else_="other",
)
ORIGIN = case((epic_watchdog.author == "Waterfalls-CHIME", "chime"), else_="manual")
WATCHING = epic_watchdog.watch_status == "watching"
SORTABLE = {
    "source": epic_watchdog.source, "watch_status": epic_watchdog.watch_status, "t_start": epic_watchdog.t_start,
    "t_end": epic_watchdog.t_end, "reason": epic_watchdog.reason, "author": epic_watchdog.author,
    "ra_deg": epic_watchdog.ra_deg, "dec_deg": epic_watchdog.dec_deg, "origin": ORIGIN, "category": CATEGORY,
}


class WatchListRow(BaseModel):
    id: int
    source: str
    event_time: datetime | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    event_type: str | None = None
    t_start: datetime | None = None
    t_end: datetime | None = None
    watch_mode: str | None = None
    patch_type: int | None = None
    reason: str | None = None
    author: str | None = None
    watch_status: str | None = None
    voevent: str | None = None
    category: str
    origin: str


class WatchListPage(BaseModel):
    data: list[WatchListRow]
    count: int


@router.get("/all/", response_model=WatchListPage)
async def get_all_sources(
    session: SessionDep,
    current_user: UserDep,
    pagination: WatchListPagiDep,
    category: Literal["all", "frb", "pulsar", "solar_system", "other"] = "all",
    sort: str | None = None,
    order: Literal["asc", "desc"] = "asc",
    active_from: datetime | None = None,
    active_to: datetime | None = None,
):
    """The watch list, by default with what is being watched first (manual
    entries such as the Sun, then triggered ones), then the most recently
    added. A column name in `sort` orders by that column instead. With
    `active_from` and `active_to`, only sources watched during that period."""
    cond = true() if category == "all" else (CATEGORY == category)
    if active_from is not None and active_to is not None:
        cond = and_(
            cond,
            epic_watchdog.t_start < active_to.replace(tzinfo=None),
            or_(epic_watchdog.t_end.is_(None), epic_watchdog.t_end > active_from.replace(tzinfo=None)),
        )
    count = session.exec(select(func.count()).select_from(epic_watchdog).where(cond)).one()

    if sort in SORTABLE:
        column = SORTABLE[sort]
        ordering = [column.asc().nulls_last() if order == "asc" else column.desc().nulls_last()]
    else:
        ordering = [
            WATCHING.desc(),
            # among the entries being watched, manual ones (the Sun) first
            case((and_(WATCHING, ORIGIN == "manual"), 0), else_=1),
        ]
    stmnt = (
        select(epic_watchdog, CATEGORY.label("category"), ORIGIN.label("origin"))
        .where(cond)
        .order_by(*ordering, epic_watchdog.id.desc())  # then the most recently added
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    rows = session.exec(stmnt).all()
    data = [WatchListRow(**w.model_dump(), category=c, origin=o) for w, c, o in rows]
    return WatchListPage(data=data, count=count)


class WatchEvent(BaseModel):
    time: datetime
    category: str


@router.get("/events/", response_model=list[WatchEvent])
async def get_watch_events(
    session: SessionDep,
    current_user: UserDep,
    start: datetime,
    end: datetime,
    category: Literal["frb", "pulsar"] = "frb",
):
    """Trigger times of the sources of one kind added between `start` and
    `end`, for marking days on a calendar"""
    stmnt = (
        select(func.coalesce(epic_watchdog.event_time, epic_watchdog.t_start), CATEGORY)
        .where(CATEGORY == category)
        .where(func.coalesce(epic_watchdog.event_time, epic_watchdog.t_start).between(
            start.replace(tzinfo=None), end.replace(tzinfo=None)))
        .order_by(func.coalesce(epic_watchdog.event_time, epic_watchdog.t_start))
    )
    return [WatchEvent(time=t, category=c) for t, c in session.exec(stmnt).all()]


def chime_notify_slack(frb_event:chime_frb_trigger, slack_msg):
    client = WebClient(token=settings.SLACK_CHIME_NOTIFIER_TOKEN)
    client.files_upload_v2(
        channel=settings.SLACK_CHIME_NOTIFIER_CHANNEL,
        username=settings.SLACK_CHIME_NOTIFIER_UNAME,
        filename=f"{frb_event.known_source_name}_voevent.xml",
        content=f"{frb_event.voevent}",
        initial_comment=slack_msg,
        snippet_type='xml'
    )

@router.post("/watch_chime")
async def update_watchlist(
    session: SessionDep, current_user: UserDep, frb_event: chime_frb_trigger
):
    if frb_event.secret != settings.WATCHDOG_CHIME_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid secret. Unable to update the watchlist",
        )

    slack_msg = f"Watching FRB event from CHIME (source: {frb_event.known_source_name}, DM: {frb_event.dm})"
    ignore_event = False
    if frb_event.snr < 10:
        slack_msg = (
            f"Ignoring {frb_event.known_source_name} event due to low SNR"
        )
        ignore_event = True

    if frb_event.importance < 0.98:
        slack_msg = f"Ignoring {frb_event.known_source_name} event due to low importance"
        ignore_event = True

    if frb_event.dm < 10:
        slack_msg = f"Ignoring {frb_event.known_source_name} event due to low DM. We may not catch the event due to the internal latencies"
        ignore_event = True

    if ignore_event:
        chime_notify_slack(frb_event,slack_msg)
        return slack_msg
    

    # watch until the burst has crossed the lowest imaged frequency, plus a
    # margin, counting from its arrival time at infinite frequency
    delay = 4148.808 * frb_event.dm / settings.LOWEST_FREQ_MHZ**2  # seconds
    dur = delay * settings.CHIME_WATCH_MARGIN
    t_end = frb_event.timestamp_utc_inf_freq + timedelta(seconds=dur)

    # check if there is an item for the same event
    # this could be the case of repeating bursts that can arrive with a small time difference
    # so simply update the t_end with the new time
    stmnt = (
        select(epic_watchdog)
        .where(epic_watchdog.source == frb_event.known_source_name)
        .where(epic_watchdog.t_end > frb_event.timestamp_utc_inf_freq)
    )
    existing_evt = session.exec(stmnt).all()
    if existing_evt:
        slack_msg=f"Found a duplicate (repeating) event for {frb_event.known_source_name}. Extending the observation"
        # update t_end with the new one
        stmnt = (
            update(epic_watchdog)
            .where(epic_watchdog.id == existing_evt[0].id)
            .values(t_end=t_end, watch_status="watching")
        )
        session.exec(stmnt)
        session.commit()
        chime_notify_slack(frb_event,slack_msg)
        return frb_event

    # if there isn't one, insert
    new_evt = epic_watchdog(
        source=frb_event.known_source_name,
        event_time=frb_event.timestamp_utc_inf_freq,
        ra_deg=frb_event.ra,
        dec_deg=frb_event.dec,
        event_type="FRB detection",
        t_start=frb_event.timestamp_utc_inf_freq,
        t_end=t_end,
        watch_mode="continuous",
        watch_status="watching",
        patch_type=5,
        reason="Searching low-frequency counterpart for CHIME trigger",
        author="Waterfalls-CHIME",
        voevent=frb_event.voevent,
    )
    session.add(new_evt)
    session.commit()
    
    chime_notify_slack(frb_event,slack_msg)
    print(frb_event)
    return new_evt
