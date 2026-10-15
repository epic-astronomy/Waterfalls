"""python -m app.frb [event_id ...]: compute FRB products, or all pending ones"""

import logging
import sys

from sqlmodel import Session

from app.core.db import engine
from app.frb.products import compute_event
from app.frb.scheduler import run_pending

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
if len(sys.argv) > 1:
    with Session(engine) as session:
        for event_id in map(int, sys.argv[1:]):
            for band in compute_event(session, event_id):
                print(event_id, band["chan0"], band["status"], band.get("peak_snr"), band.get("note") or "")
else:
    print("computed:", run_pending())
