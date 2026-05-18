"""
CLI: render the named report and send via email.

  python scripts/send_email.py audit recipient@example.com [recipient2@...]
  python scripts/send_email.py daily recipient@example.com

Postmark must be configured via POSTMARK_API_KEY env var; otherwise this is a no-op
(useful for testing the render path).
"""
import sys
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pulse import audit, daily, email  # noqa: E402

app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent.parent / "static"),
)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    report_name = sys.argv[1]
    recipients = sys.argv[2:]

    if report_name == "audit":
        data = audit.build_audit()
        template = "audit.html"
        subject = f"TruAge Pulse — AM Audit — {date.today().isoformat()}"
        ctx = {"r": data}
    elif report_name == "daily":
        data = daily.build_daily()
        template = "daily.html"
        subject = f"TruAge Pulse — Daily — {date.today().isoformat()}"
        ctx = {"d": data}
    else:
        print(f"Unknown report: {report_name}")
        sys.exit(1)

    with app.test_request_context():
        html = render_template(template, **ctx)

    # Inline the CSS for email clients
    css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
    css = css_path.read_text() if css_path.exists() else ""
    html = html.replace(
        '<link rel="stylesheet" href="/static/styles.css">',
        f"<style>{css}</style>"
    )

    result = email.send(to=recipients, subject=subject, html_body=html)
    print(f"Send result: {result}")


if __name__ == "__main__":
    main()
