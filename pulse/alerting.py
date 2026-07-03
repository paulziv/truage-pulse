"""
Crash alerting via the shared truage_core.email helper (Resend).

Sends from the unified alerts@ address (see truage_core.email); no per-service
Resend wiring needed beyond the shared RESEND_API_KEY. No-ops gracefully (logs
only) when the key isn't set.

Alerts are rate-limited per error "source" so a crash-looping route doesn't
spam the inbox — at most one email per source every ALERT_COOLDOWN_SECONDS
(default 30 min).
"""
import os
import time
import logging
import traceback

from truage_core import email as tcemail

log = logging.getLogger("truage-pulse.alerting")

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

    body_lines = [
        f"<p><b>TruAge Pulse</b> ({source}) crashed.</p>",
        f"<p><b>Message:</b> {message}</p>",
    ]
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        body_lines.append(f"<pre style='white-space:pre-wrap;font-size:.8rem'>{tb}</pre>")
    html_body = "\n".join(body_lines)

    result = tcemail.send(
        to=ALERT_TO,
        subject=f"[TruAge Pulse] Crash in {source}",
        html=html_body,
        purpose="alerts",
    )
    if result.get("ok"):
        _last_sent[source] = now
        log.info("Crash alert sent to %s for source=%s", ALERT_TO, source)
    else:
        # Never let alerting itself break the route's error handling.
        log.error("Failed to send crash alert: %s", result.get("error"))
