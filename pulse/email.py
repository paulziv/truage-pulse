"""
Email send via Postmark.

No-ops gracefully when POSTMARK_API_KEY is unset, which lets local dev proceed
without a Postmark account. Just sets POSTMARK_API_KEY in .env when ready.
"""
import os
import logging
import requests

log = logging.getLogger(__name__)

POSTMARK_URL = "https://api.postmarkapp.com/email"


def send(
    to: list[str] | str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> dict:
    """Send a transactional HTML email. Returns Postmark response, or stub when disabled."""
    api_key = os.environ.get("POSTMARK_API_KEY")
    from_email = os.environ.get("POSTMARK_FROM_EMAIL", "pulse@mytruage.org")
    from_name = os.environ.get("POSTMARK_FROM_NAME", "TruAge Pulse")

    if isinstance(to, str):
        to = [to]
    to_header = ", ".join(to)

    if not api_key:
        log.info("Postmark disabled (no API key) — would send to %s: %r", to_header, subject)
        return {"status": "stubbed", "to": to, "subject": subject}

    resp = requests.post(
        POSTMARK_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": api_key,
        },
        json={
            "From": f"{from_name} <{from_email}>",
            "To": to_header,
            "Subject": subject,
            "HtmlBody": html_body,
            "TextBody": text_body or _strip_html(html_body),
            "MessageStream": "outbound",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _strip_html(html: str) -> str:
    """Very basic HTML → text for the multipart fallback."""
    import re
    text = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
