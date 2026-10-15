"""Compute FRB products for finished CHIME watches in a background thread"""

import logging
import threading

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.frb.products import compute_event, pending_events

log = logging.getLogger(__name__)

# one backend at a time computes products, even with several running
LOCK_KEY = 0x45504943_46524221 & 0x7FFFFFFFFFFFFFFF


def run_pending() -> list[int]:
    done = []
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("select pg_try_advisory_lock(:k)"), dict(k=LOCK_KEY)).scalar():
            return done
        try:
            with Session(engine) as session:
                for event_id in pending_events(session):
                    try:
                        compute_event(session, event_id)
                        done.append(event_id)
                    except Exception:
                        session.rollback()
                        log.exception("FRB products failed for event %s", event_id)
        finally:
            lock_conn.execute(text("select pg_advisory_unlock(:k)"), dict(k=LOCK_KEY))
    return done


def start(stop: threading.Event) -> threading.Thread:
    def loop():
        while not stop.is_set():
            try:
                done = run_pending()
                if done:
                    log.info("FRB products computed for events %s", done)
            except Exception:
                log.exception("FRB products scan failed")
            stop.wait(settings.FRB_PRODUCTS_SCAN_S)

    thread = threading.Thread(target=loop, name="frb-products", daemon=True)
    thread.start()
    return thread
