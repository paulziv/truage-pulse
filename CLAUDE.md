# CLAUDE.md — truage-pulse

> Repo: `paulziv/truage-pulse`. Deployed to Railway (TruAge/HubSpot cluster). Also runnable on the Synology NAS (same Dockerfile). The existing `README.md` is accurate and detailed — **read it too**; this file adds the verified specifics and reconciles a few stale claims.

## What this service is
An internal Flask reporting hub for TruAge Activation ops. Three report pages that pull **live** from HubSpot on each load (no pre-generated files like the activation-report has):
- `/audit` — **AM Assignment Audit** (the main, fully-built report)
- `/daily` — **Daily Sales Pulse** (still a v1 **stub**; spec in `DAILY_PULSE_SPEC.md`)
- `/dictionary` — **HubSpot Data Dictionary** (field/pipeline/owner reference)
- `/settings` — rules-of-org, open questions, schedule/recipients (persisted in DB)

## Tech stack (verified)
- **Python 3.12**, **Flask 3.0** + Jinja templates, served by **gunicorn** (2 workers).
- HubSpot via `requests` (`pulse/hubspot_client.py`), **Private App token** — env var **`HUBSPOT_PRIVATE_APP_TOKEN`** (note: *different name* from activation-report's `HUBSPOT_TOKEN`).
- **Postgres** (`psycopg2-binary`) when `DATABASE_URL` is set, else **SQLite** (`data/pulse.db`) — same schema (`pulse/storage.py`).
- Email: **Postmark** (`pulse/email.py`), no-op without `POSTMARK_API_KEY`. (Activation-report uses Resend instead — intentional divergence, see arch doc.)
- Deploy: Dockerfile (python:3.12-slim); boot cmd runs `python -m pulse.storage --init` then gunicorn on `$PORT` (default 5000). `railway.json` builder=DOCKERFILE, healthcheck `/health`.

## Entry point & routes (`app.py`)
- `/` → redirect to `/audit`.
- `/audit` → returns a **loading-shell HTML immediately**; client JS then `fetch`es `/audit/report` and swaps the document in. This hides the ~30–45s HubSpot pull (and Railway cold starts) behind a progress UI. `?fresh=1` clears the cache.
- `/audit/report` → the real report (renders `templates/audit.html`). `/audit.html` → same, as a standalone downloadable attachment (`pulse/export.to_standalone_html`).
- `/daily`, `/daily.html`, `/dictionary`, `/dictionary.html` → same view/export pattern.
- `/settings` (GET/POST) → add rules / open questions.
- `/health` → `{"status":"ok","version":...}`. `/errors` → recent crashes (from `error_log` table).
- All routes funnel exceptions through `_handle_pipeline_error` → logs, `storage.record_error`, `alerting.send_crash_alert`, renders `error.html` (502).

## AM Assignment Audit — how it works (`pulse/audit/`)
`audit.build_audit()` (cached 5 min via `pulse/cache.py`):
1. **Priority population** (`data.fetch_priority_companies`): HubSpot companies with **≥2 associated contacts AND ≥1 associated deal** (~58 accounts). Then `hydrate_contacts` pulls each company's contacts (this is the path fixed for the N+1 associations bug — keep batched).
2. **Categorize** each account (`analysis.categorize`) into one of five buckets:
   - **Clean** — company owner matches all contact owners, none unassigned.
   - **Partial** — right company AM, but some contacts unowned *or* owned by a non-AM (e.g. Support).
   - **Overlap** — ≥2 *active* AMs across the contacts.
   - **Conflict** — company owner set but owns none of the contacts (or company unowned while a contact is owned).
   - **Orphaned** — no active AM anywhere (owner null/inactive AND no AM on any contact).
3. **Hygiene Score** (`score.compute`), weighted blend 0–100:
   `score = (Clean×1.0 + Partial×0.6 + Overlap×0.4 + Conflict×0.2 + Orphaned×0.0) / Total × 100`.
   Thresholds: **≥85 green**, **60–84 yellow**, **<60 red**. History persisted via `storage.record_score`.
4. **Inactive-owner sweep** (`data.fetch_inactive_owner_records`): every company/contact/deal still owned by a designated inactive user, regardless of contact/deal count — catches orphaned vendor/manufacturer records the priority sweep misses.

### Hardcoded org constants (`pulse/audit/data.py`) — the stage-role/owner-ID mappings
- **AM_OWNER_IDS**: `79423140` Eddie McFarlane, `87813531` Megan Terry, `1367430633` Lisa Rountree.
- **INACTIVE_OWNER_IDS**: `79761095` Grant Bleecher, `1285253947` Bryan Esser.
- **OTHER_OWNER_IDS** (active, non-AM, for labels): `87367233` Patrick Abernathy (Support), `89184631` Lia LoBello Reynolds (NACS), `78438676` Stephanie Sikorski.
These are v1 hardcoded constants; the roadmap is to move them into settings.

## Daily Sales Pulse — status
Route is stubbed. `DAILY_PULSE_SPEC.md` defines the intended report (Health Score with weighted components, top-5 urgency ranking with `stall_multiplier`/`stage_progress_multiplier`, wins, new deals, threshold crossings). Not yet wired — `pulse/daily/` is a stub package.

## Run locally
```bash
cp .env.example .env          # set HUBSPOT_PRIVATE_APP_TOKEN
pip install -r requirements.txt
python -m pulse.storage --init
python app.py                 # http://localhost:5000
```
HubSpot scopes: companies.read, contacts.read, deals.read, owners.read.

## Deploy
Push `main` → Railway auto-deploys (Docker). Env: `HUBSPOT_PRIVATE_APP_TOKEN` (required), `DATABASE_URL` (Postgres in prod), `POSTMARK_API_KEY`/`POSTMARK_FROM_EMAIL`/`POSTMARK_FROM_NAME` (email), `FLASK_SECRET_KEY`. Also deployable to Synology (`DEPLOY_SYNOLOGY.md`) with a mounted `/app/data` volume for the SQLite DB.

## Reconciliation notes (README is slightly stale)
- README says "Hosting: Local dev now, Railway later" and "Auth0 (planned)". **It is live on Railway now** (per top-level INFRA_README, at a Railway URL). Auth0 gating most likely happens at the **pez-portal** layer in front of it rather than in this app — its routes are auth-naive. Confirm when documenting pez-portal.
- README references `pulse/audit/README.md`; the authoritative scoring math is in `pulse/audit/score.py` (captured above).

## Cleanup debt
- `apply_truage_pulse_n1_fix.sh` — one-off patch script; safe to remove once confirmed applied.


---

## ✅ Phase 1 complete — truage-core adoption (2026-07-03)
Shared logic now lives in **truage-core**:
- `pulse/hubspot_client.py` is a thin **shim** re-exporting `truage_core.hubspot.client` (HubSpotClient/get_client/HubSpotError) — the fail-loud retry client is shared with the Activation Report (~218 lines removed).
- `pulse/audit/data.py` imports the owner-ID maps (`AM_OWNER_IDS`, `INACTIVE_OWNER_IDS`, `OTHER_OWNER_IDS`) from `truage_core.config`.
- Installed via `requirements.txt` git+PAT pin; Dockerfile installs `git` for pip.
- Verified byte-identical via `tests/characterization/` (cassette replay → audit metrics unchanged). Token still `HUBSPOT_PRIVATE_APP_TOKEN` (client also accepts canonical `HUBSPOT_TOKEN`).
