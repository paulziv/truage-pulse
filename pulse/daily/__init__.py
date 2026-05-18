"""
Daily Sales Pulse — stub for v1.

Full spec lives in DAILY_PULSE_SPEC.md at the repo root.
Wire up after the audit is in production.
"""
from datetime import datetime


def build_daily():
    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "status": "stub",
        "message": (
            "Daily Sales Pulse is not yet wired up. "
            "See DAILY_PULSE_SPEC.md for the build spec."
        ),
    }
