"""
python -m app.frb worker               process pending bands, then combine ready events (the Nomad job)
python -m app.frb band EVENT CHAN0     analyse one band of one event
python -m app.frb combine EVENT        combine an event's stored bands (no Slack post unless --notify)
"""

import argparse
import logging

from sqlmodel import Session

from app.core.db import engine
from app.frb import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
parser = argparse.ArgumentParser(prog="python -m app.frb")
sub = parser.add_subparsers(dest="cmd", required=True)
sub.add_parser("worker")
b = sub.add_parser("band")
b.add_argument("event_id", type=int)
b.add_argument("chan0", type=int)
c = sub.add_parser("combine")
c.add_argument("event_id", type=int)
c.add_argument("--notify", action="store_true")
args = parser.parse_args()

if args.cmd == "worker":
    print(pipeline.run_worker())
else:
    with Session(engine) as session:
        if args.cmd == "band":
            print(pipeline.process_band(session, args.event_id, args.chan0))
        else:
            s = pipeline.combine_event(session, args.event_id, notify_slack=args.notify)
            print(s["combined"], s["localisation"], "detected" if s["detected"] else "no detection")
