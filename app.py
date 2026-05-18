"""
TruAge Pulse — Flask app entry point.

Routes:
  /            redirect to /audit
  /audit       AM Assignment Audit
  /daily       Daily Sales Pulse (stub)
  /dictionary  HubSpot Data Dictionary
  /settings    Rules of the org + open questions (admin-ish)
  /health      Liveness check for Railway
"""
import os
import logging
from pathlib import Path
from flask import Flask, render_template, redirect, request, jsonify, url_for, Response
from dotenv import load_dotenv

# Load .env before importing pulse modules (they read env vars at import time)
load_dotenv(Path(__file__).resolve().parent / ".env")

from pulse import audit, daily, dictionary, storage, export  # noqa: E402
from pulse.hubspot_client import HubSpotError  # noqa: E402

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("truage-pulse")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")


# Ensure DB exists before serving any traffic
try:
    storage.init_db()
except Exception as e:
    log.warning("Could not initialize DB: %s", e)


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return redirect(url_for("audit_view"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "0.4.2"})


@app.route("/audit")
def audit_view():
    """The AM Assignment Audit — page 1 (findings) + page 2 (anomaly punch list)."""
    if request.args.get("fresh"):
        audit.build_audit.cache_clear()
    try:
        report = audit.build_audit()
    except HubSpotError as e:
        return render_template("error.html", error=str(e)), 502
    return render_template("audit.html", r=report)


@app.route("/audit.html")
def audit_export():
    """Same audit, but as a downloadable self-contained HTML attachment."""
    try:
        report = audit.build_audit()
    except HubSpotError as e:
        return render_template("error.html", error=str(e)), 502
    html = render_template("audit.html", r=report)
    standalone = export.to_standalone_html(html)
    return Response(
        standalone,
        mimetype="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename_for("audit")}"'
        },
    )


@app.route("/daily")
def daily_view():
    """Daily Sales Pulse — stub for v1."""
    data = daily.build_daily()
    return render_template("daily.html", d=data)


@app.route("/daily.html")
def daily_export():
    """Downloadable Daily Pulse snapshot."""
    data = daily.build_daily()
    html = render_template("daily.html", d=data)
    standalone = export.to_standalone_html(html)
    return Response(
        standalone,
        mimetype="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename_for("daily")}"'
        },
    )


@app.route("/dictionary")
def dictionary_view():
    """HubSpot Data Dictionary."""
    data = dictionary.build_dictionary()
    return render_template("dictionary.html", d=data)


@app.route("/dictionary.html")
def dictionary_export():
    """Downloadable Data Dictionary snapshot."""
    data = dictionary.build_dictionary()
    html = render_template("dictionary.html", d=data)
    standalone = export.to_standalone_html(html)
    return Response(
        standalone,
        mimetype="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename_for("dictionary")}"'
        },
    )


@app.route("/settings", methods=["GET", "POST"])
def settings_view():
    """Rules of the org, open questions, schedule placeholders."""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_rule":
            rule = request.form.get("rule", "").strip()
            if rule:
                storage.add_rule(rule)
        elif action == "add_question":
            q = request.form.get("question", "").strip()
            if q:
                storage.add_question(q)
        return redirect(url_for("settings_view"))

    return render_template(
        "settings.html",
        rules=storage.list_rules(),
        questions=storage.list_open_questions(),
        send_schedule=storage.get_setting("send_schedule", {
            "audit": "weekly Monday 8am ET",
            "daily": "6pm ET Mon-Fri",
        }),
        recipients=storage.get_setting("recipients", {"audit": [], "daily": []}),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
