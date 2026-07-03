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
from pulse import alerting  # noqa: E402
from pulse.hubspot_client import HubSpotError  # noqa: E402

from truage_core import logging as tclog, runlog  # noqa: E402
tclog.configure_stdlib_json(os.environ.get("LOG_LEVEL", "INFO"), service="nacstam")
log = logging.getLogger("truage-pulse")

app = Flask(__name__)


@app.before_request
def _bind_request_id():
    """Adopt the caller's correlation id (portal forwards X-Request-ID) or mint one."""
    tclog.bind_request_id(request.headers.get(tclog.REQUEST_ID_HEADER))


@app.after_request
def _emit_request_id(resp):
    """Expose the correlation id on the response so gunicorn access logs (via
    --access-logformat) and the portal can capture it under X-Request-ID."""
    rid = tclog.current_request_id()
    if rid:
        resp.headers[tclog.REQUEST_ID_HEADER] = rid
    return resp


app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")


def _handle_pipeline_error(source: str, exc: Exception):
    """Log, persist to the error_log table, and email an alert for any
    pipeline/route crash — not just the explicitly-typed HubSpotError cases.
    Returns a rendered error page (502) so the caller can `return` it directly.
    """
    import traceback as tb_module
    tb_text = "".join(tb_module.format_exception(type(exc), exc, exc.__traceback__))
    log.error("%s crashed: %s", source, exc)
    try:
        runlog.record_error(
            "nacstam", source, str(exc),
            traceback_text=tb_text,
            correlation_id=tclog.current_request_id(),
        )
    except Exception as store_exc:
        log.warning("Could not record error to DB: %s", store_exc)
    alerting.send_crash_alert(source, str(exc), exc)
    return render_template("error.html", error=str(exc)), 502


# Ensure DB exists before serving any traffic
try:
    storage.init_db()
    runlog.init_tables()
except Exception as e:
    log.warning("Could not initialize DB: %s", e)


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return redirect(url_for("audit_view"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "0.4.2"})


@app.route("/errors")
def errors_view():
    """Recent crashes across all routes/pipelines — durable (Postgres in
    production), for reviewing what happened beyond what's convenient to
    scroll through in raw Railway logs."""
    limit = request.args.get("limit", default=50, type=int)
    return jsonify(runlog.recent_errors(limit=limit, service="nacstam"))


_AUDIT_LOADING_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>TruAge Pulse — Loading…</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#F5F0E8;min-height:100vh;display:flex;align-items:center;
         justify-content:center;padding:2rem 1.5rem;}
    .card{background:#fff;border:1px solid #DDD8CE;border-radius:14px;
          padding:2.5rem 2.5rem 2rem;max-width:460px;width:100%;
          box-shadow:0 4px 24px rgba(0,32,63,0.08);text-align:center;}
    .ring{display:inline-block;width:48px;height:48px;margin-bottom:1.25rem;
          border:4px solid #DDD8CE;border-top-color:#36ECDE;
          border-radius:50%;animation:spin 0.9s linear infinite;}
    @keyframes spin{to{transform:rotate(360deg);}}
    .msg{font-size:1.05rem;font-weight:700;color:#1A2332;margin-bottom:0.3rem;}
    .sub{font-size:0.82rem;color:#7A7060;margin-bottom:1.75rem;}
    .steps{text-align:left;border-top:1px solid #EDE8DF;padding-top:1.25rem;
           display:flex;flex-direction:column;gap:0.6rem;margin-top:0.25rem;}
    .step{display:flex;align-items:center;gap:0.75rem;font-size:0.84rem;color:#c5bdb3;}
    .step.done{color:#087f5b;}
    .step.active{color:#1A2332;font-weight:500;}
    .step-icon{width:18px;flex-shrink:0;text-align:center;font-size:0.82rem;}
    .mini-ring{width:13px;height:13px;border:2px solid #DDD8CE;
               border-top-color:#36ECDE;border-radius:50%;
               animation:spin 0.8s linear infinite;display:inline-block;vertical-align:middle;}
    .warn{display:none;margin-top:1.25rem;padding:0.75rem 1rem;
          background:#fff8e1;border:1px solid #e6b800;border-radius:8px;
          font-size:0.82rem;color:#7a5c00;line-height:1.5;}
  </style>
</head>
<body>
<div class="card">
  <div class="ring"></div>
  <div class="msg" id="msg">Connecting to HubSpot&hellip;</div>
  <div class="sub">Hang tight &mdash; this usually takes 30&ndash;45 seconds</div>
  <div class="steps">
    <div class="step" id="s1"><span class="step-icon">&#x25CB;</span><span>Authenticating with HubSpot API</span></div>
    <div class="step" id="s2"><span class="step-icon">&#x25CB;</span><span>Fetching account manager records</span></div>
    <div class="step" id="s3"><span class="step-icon">&#x25CB;</span><span>Analysing AM assignments &amp; overlaps</span></div>
    <div class="step" id="s4"><span class="step-icon">&#x25CB;</span><span>Scoring hygiene and flagging conflicts</span></div>
    <div class="step" id="s5"><span class="step-icon">&#x25CB;</span><span>Assembling your report</span></div>
  </div>
  <div class="warn" id="warn">
    Still working&hellip; Railway may be waking up a cold service. Sit tight &mdash; it will arrive.
  </div>
</div>
<script>
  const MSGS=[
    ["Connecting to HubSpot…","Pulling your latest account data"],
    ["Crunching the numbers…","Counting AMs, checking assignments"],
    ["Scanning account records…","Matching owners to territories"],
    ["Checking assignment conflicts…","Hang tight — almost done"],
    ["Almost there…","Building your report now"],
  ];
  const STEP_MS=[600,9000,19000,30000,41000];
  let i=0;
  const msgEl=document.getElementById('msg');
  function cycleMsgs(){
    const[h]=MSGS[i%MSGS.length]; msgEl.textContent=h; i++;
    setTimeout(cycleMsgs,3500);
  }
  cycleMsgs();
  function activate(n){
    if(n>1){const p=document.getElementById('s'+(n-1));if(p){p.className='step done';p.querySelector('.step-icon').innerHTML='&#x2713;';}}
    const el=document.getElementById('s'+n);if(el){el.className='step active';el.querySelector('.step-icon').innerHTML='<span class="mini-ring"></span>';}
  }
  STEP_MS.forEach((ms,idx)=>setTimeout(()=>activate(idx+1),ms));
  setTimeout(()=>{document.getElementById('warn').style.display='block';},50000);
  // Fetch the report; when ready, swap the entire document
  const url = '/audit/report' + window.location.search;
  fetch(url)
    .then(r=>{
      if(!r.ok) throw new Error('HTTP '+r.status);
      return r.text();
    })
    .then(html=>{
      document.open(); document.write(html); document.close();
    })
    .catch(err=>{
      msgEl.textContent='Could not load report';
      document.querySelector('.sub').textContent=err.message+' — try refreshing the page.';
    });
</script>
</body>
</html>"""


@app.route("/audit")
def audit_view():
    """Return loading shell immediately; JS fetches /audit/report in the background."""
    if request.args.get("fresh"):
        audit.build_audit.cache_clear()
    return _AUDIT_LOADING_SHELL, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/audit/report")
def audit_report():
    """The AM Assignment Audit data endpoint — called by the loading shell."""
    if request.args.get("fresh"):
        audit.build_audit.cache_clear()
    try:
        report = audit.build_audit()
    except HubSpotError as e:
        return render_template("error.html", error=str(e)), 502
    except Exception as e:
        return _handle_pipeline_error("audit_report", e)
    return render_template("audit.html", r=report)


@app.route("/audit.html")
def audit_export():
    """Same audit, but as a downloadable self-contained HTML attachment."""
    try:
        report = audit.build_audit()
    except HubSpotError as e:
        return render_template("error.html", error=str(e)), 502
    except Exception as e:
        return _handle_pipeline_error("audit_export", e)
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
    try:
        data = daily.build_daily()
    except Exception as e:
        return _handle_pipeline_error("daily_view", e)
    return render_template("daily.html", d=data)


@app.route("/daily.html")
def daily_export():
    """Downloadable Daily Pulse snapshot."""
    try:
        data = daily.build_daily()
    except Exception as e:
        return _handle_pipeline_error("daily_export", e)
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
    try:
        data = dictionary.build_dictionary()
    except Exception as e:
        return _handle_pipeline_error("dictionary_view", e)
    return render_template("dictionary.html", d=data)


@app.route("/dictionary.html")
def dictionary_export():
    """Downloadable Data Dictionary snapshot."""
    try:
        data = dictionary.build_dictionary()
    except Exception as e:
        return _handle_pipeline_error("dictionary_export", e)
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
