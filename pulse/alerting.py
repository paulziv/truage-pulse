"""
Crash alerting via Resend — the same provider pez-portal already uses
successfully to send the actual report emails, rather than depending on this
repo's pulse/email.py (Postmark) which isn't confirmed to have a working key
configured. No-ops gracefully (logs only) when RESEND_API_KEY isn't set on
this service.

Alerts are rate-limited per error "source" so a crash-looping route doesn't
spam the inbox — at most one email per source every ALERT_COOLDOWN_SECONDS
(default 30 min).
"""
import os
import time
import logging
import traceback

import requests

log = logging.getLogger("truage-pulse.alerting")

RESEND_URL = "https://api.resend.com/emails"
ALERT_TO = os.environ.get("ALERT_EMAIL", "ziv.paul@gmail.com")
ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", "1800"))

_last_sent: dict[str, float] = {}


def send_crash_alert(source: str, message: str, exc: Exception | None = None) -> None:
    """Email ALERT_TO that something crashed. `source` is a short stable
    identifier (used for rate-limiting), e.g. 'audit_report' or 'daily_view'."""
    now = time.time()
    last = _last_sent.get(source, 0)
    if now - last < ALERT_COOLDOWN_SECONDS:
        log.info(
            "Alert for %r suppressed (sent %.0fs ago, cooldown %ds)",
            source, now - last, ALERT_COOLDOWN_SECONDS,
        )
        return

    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "alerts@mytruage.org")

    body_lines = [
        f"<p><b>TruAge Pulse</b> ({source}) crashed.</p>",
        f"<p><b>Message:</b> {message}</p>",
    ]
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        body_lines.append(f"<pre style='white-space:pre-wrap;font-size:.8rem'>{tb}</pre>")
    html_body = "\n".join(body_lines)

    if not api_key:
        log.warning(
            "RESEND_API_KEY not set — crash alert NOT sent (would have gone to %s). "
            "Source=%s Message=%s", ALERT_TO, source, message,
        )
        return

    try:
        resp = requests.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [ALERT_TO],
                "subject": f"[TruAge Pulse] Crash in {source}",
                "html": html_body,
            },
            timeout=15,
        )
        resp.raise_for_status()
        _last_sent[source] = now
        log.info("Crash alert sent to %s for source=%s", ALERT_TO, source)
    except Exception as send_exc:
        # Never let alerting itself break the route's error handling.
        log.error("Failed to send crash alert: %s", send_exc)
