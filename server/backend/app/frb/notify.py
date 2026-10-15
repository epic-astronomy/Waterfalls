"""Post the result of an FRB analysis to the CHIME events Slack channel"""

import logging
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.core.config import settings

log = logging.getLogger(__name__)


def analysis_url(event_id: int) -> str:
    return f"{settings.WATERFALLS_PUBLIC_URL.rstrip('/')}/waterfalls/spectrograms/frb?event={event_id}"


def message(event_id: int, s: dict) -> str:
    t_inf = datetime.fromisoformat(s["t_inf"]).strftime("%Y-%m-%d %H:%M:%S")
    ok = [b for b in s["bands"] if b["status"] == "ok"]
    lines = [
        f"EPIC dispersion search of *{s['source']}* is complete. CHIME DM {s['dm_chime']:.2f} ± {s['dm_err_chime']:.2f} pc cm⁻³, "
        f"burst at infinite frequency {t_inf} UTC."
    ]
    c, loc = s.get("combined"), s.get("localisation")
    if s["detected"]:
        lines.append(
            f"Candidate at S/N {c['snr']:.1f} combining {c['n_bands']} bands, DM {c['dm']:.2f}, "
            f"{c['tau_s']:+.1f} s from the CHIME arrival, brightest in the source pixel."
        )
    elif c and c["snr"] is not None:
        where = "the source pixel" if loc and loc["centre_is_brightest"] else "another pixel of the 5x5 grid"
        lines.append(
            f"No burst above S/N {s['snr_threshold']:.0f} in the {len(ok)} bands with data. The best combined S/N in the source "
            f"pixel is {c['snr']:.1f} at DM {c['dm']:.2f}, and the brightest peak is in {where}."
        )
    else:
        lines.append("No band had data around the expected arrival.")
    missing = [b for b in s["bands"] if b["status"] != "ok"]
    for b in missing:
        lines.append(f"{b['f_lo_mhz']:.2f}–{b['f_hi_mhz']:.2f} MHz has no data. {b['note']}")
    lines.append(f"<{analysis_url(event_id)}|Open the analysis in Waterfalls>")
    return "\n".join(lines)


def post(event_id: int, summary: dict) -> bool:
    if not (settings.FRB_SLACK_NOTIFY and settings.SLACK_CHIME_NOTIFIER_TOKEN and settings.SLACK_CHIME_NOTIFIER_CHANNEL):
        log.info("FRB analysis of event %s not posted to Slack (disabled or not configured)", event_id)
        return False
    client = WebClient(token=settings.SLACK_CHIME_NOTIFIER_TOKEN)
    text = message(event_id, summary)
    try:
        client.chat_postMessage(channel=settings.SLACK_CHIME_NOTIFIER_CHANNEL, text=text,
                                username=settings.SLACK_CHIME_NOTIFIER_UNAME or None, unfurl_links=False)
    except SlackApiError as e:
        # a custom username needs chat:write.customize; post under the app's name otherwise
        if e.response.get("error") != "missing_scope":
            raise
        client.chat_postMessage(channel=settings.SLACK_CHIME_NOTIFIER_CHANNEL, text=text, unfurl_links=False)
    return True
