from fastapi import APIRouter, HTTPException, Request
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

@router.get('/all/', response_model=epic_watchdog_public)
async def get_all_sources(session: SessionDep, current_user: UserDep, pagination: WatchListPagiDep
):
    count_stmnt = (
        select(func.count())
        .select_from(epic_watchdog)
    )
    count = session.exec(count_stmnt).one()
    fetch_stmnt = (
        select(epic_watchdog)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    sources = session.exec(fetch_stmnt).all()
    return epic_watchdog_public(data=sources, count=count)

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
    

    # set the duration to twice the arrival time at 28.1 MHz from inf MHz
    dur = 4.15 * (1 / 28.1**2 - 1 / 400**2) * frb_event.dm * 1e3 * 2  # seconds
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
