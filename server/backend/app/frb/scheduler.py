"""Run the FRB analysis in the API process, when FRB_PRODUCTS_ENABLED is set.
Normally the frb-analysis Nomad job runs it on the worker nodes instead."""

import logging
import threading

from app.core.config import settings
from app.frb.pipeline import run_worker

log = logging.getLogger(__name__)


def start(stop: threading.Event) -> threading.Thread:
    def loop():
        while not stop.is_set():
            try:
                done = run_worker()
                if done["bands"] or done["combined"]:
                    log.info("FRB analysis: %s", done)
            except Exception:
                log.exception("FRB analysis scan failed")
            stop.wait(settings.FRB_PRODUCTS_SCAN_S)

    thread = threading.Thread(target=loop, name="frb-analysis", daemon=True)
    thread.start()
    return thread
