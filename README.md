# TruAge Pulse

Internal reporting hub for TruAge Activation operations. Hosts the AM Assignment Audit, Daily Sales Pulse, and HubSpot Data Dictionary as web pages that pull live from HubSpot. Sends scheduled email summaries.

## What's here

Three reports plus a settings page, all served by a single Flask app:

- `/audit` — Account Manager Assignment Audit
- `/daily` — Daily Sales Pulse (stub for v1; spec exists)
- `/dictionary` — HubSpot Data Dictionary (field catalog, pipelines, definitions)
- `/settings` — Send schedule, recipients, scoring thresholds, rules of the org

## Stack

| Concern | Tech | Why |
|---|---|---|
| Web framework | Flask + Jinja | Simple, plays nice with Python data work |
| Templating | Jinja | Built into Flask |
| Storage | SQLite (local) / Postgres (Railway) | Identical schema, swap via DATABASE_URL |
| HubSpot | Private App access token | Scoped, revocable, no OAuth dance |
| Email send | Postmark | Best-in-class transactional email, ~$15/mo |
| Email receive | Deferred to v2 | Walk before run |
| Auth | Auth0 (planned) | Coming from parallel thread; shared across pulse/990/activation subdomains |
| Hosting | Local dev now, Railway later | Iterate locally, deploy once shape is right |

## Quick start (local)

```bash
# 1. Set up env
cp .env.example .env
# Edit .env — at minimum, set HUBSPOT_PRIVATE_APP_TOKEN

# 2. Install deps
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Initialize the database
python -m pulse.storage --init

# 4. Run the app
python app.py
# Visit http://localhost:5000
```

## Where things live

```
truage-pulse/
├── app.py                    # Flask entry, routes
├── pulse/
│   ├── hubspot_client.py    # All HubSpot API calls go through here
│   ├── audit/               # AM Assignment Audit
│   │   ├── data.py          #   Pull companies/contacts from HubSpot
│   │   ├── analysis.py      #   Categorize (Clean/Conflict/Overlap/etc)
│   │   └── score.py         #   Compute Hygiene Score 0–100
│   ├── daily/               # Daily Sales Pulse (stub)
│   ├── dictionary/          # Data Dictionary
│   │   └── data.py          #   Field catalog, pipeline definitions
│   ├── email.py             # Postmark wrapper (no-op without API key)
│   └── storage.py           # SQLite/Postgres abstraction
├── templates/               # Jinja templates per report
├── static/styles.css        # Shared styles, score block, pills
├── scripts/
│   ├── generate_audit.py    # CLI: regenerate audit to disk
│   └── send_email.py        # CLI: trigger scheduled send
└── data/pulse.db            # SQLite (gitignored)
```

## Reports

### AM Assignment Audit (`/audit`)
Pulls every company with ≥2 contacts AND ≥1 deal, plus all records owned by inactive users (Grant, Bryan). Categorizes each account as Clean / Partial / Overlap / Conflict / Orphaned and computes a weighted Hygiene Score. Page 2 is the data anomaly punch list — explicit reassignment instructions per record.

See `pulse/audit/README.md` for scoring math and category definitions.

### Daily Sales Pulse (`/daily`)
Stub for v1. Spec exists in repo root as `DAILY_PULSE_SPEC.md`. Will render the manager-facing EOD report from the earlier conversation — health score, top 5 deals to work, yesterday's wins, this week's new deals, threshold crossings.

### Data Dictionary (`/dictionary`)
HubSpot field catalog with descriptions, pipeline + stage maps, owner roster, shared metric definitions, and a change log. The reference doc everything else points back to.

## Settings (`/settings`)

A simple form (post-Auth0):
- Send schedules per report
- Recipient lists per report  
- Score thresholds (green/yellow/red cutoffs)
- "Rules of the org" markdown — Lia=NACS, Patrick=Support, etc.

For now, settings live in SQLite via `pulse/storage.py` and are also exposable via env vars.

## Email send

Postmark transactional. Service is a no-op when `POSTMARK_API_KEY` is unset — useful during local dev. Email subject format: `TruAge Pulse — <Report Name> — <Date>`.

## What's intentionally NOT here yet

- Inbound email parsing — deferred per "walk before run"
- Auth0 wiring — coming from parallel thread; routes are auth-naive for now
- Postgres — schema is Postgres-compatible but we run SQLite locally  
- Production scheduler — Railway cron will trigger sends; locally use `scripts/send_email.py`

## Deployment paths

- **Local dev** — `python app.py`, fastest iteration
- **Synology NAS** — see `DEPLOY_SYNOLOGY.md`. Good interim host; uses the same Dockerfile as Railway.
- **Railway** — see `DEPLOY.md`. Production path when ready.

Same code, same image, three environments.
