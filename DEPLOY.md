# Deploying to Railway

Walk-before-run plan: get the app running locally first, then push to Railway as a single clean deploy.

## Phase 1 — Local development (do this first)

### 1. Create the HubSpot Private App

1. In HubSpot: **Settings → Integrations → Private Apps → Create private app**
2. Name: `TruAge Pulse`
3. Scopes (Read only):
   - `crm.objects.companies.read`
   - `crm.objects.contacts.read`
   - `crm.objects.deals.read`
   - `crm.objects.owners.read`
4. After creating, copy the **Access token**

### 2. Local setup

```bash
git clone <this-repo>
cd truage-pulse

# Copy and edit env
cp .env.example .env
# Paste your HubSpot token into HUBSPOT_PRIVATE_APP_TOKEN

# Install
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Initialize the database
python -m pulse.storage --init

# Run
python app.py
```

Open http://localhost:5000 — should land on the AM Audit, pulling live HubSpot data.

### 3. Iterate

Edit templates, categorization rules, scoring weights. Restart `python app.py` to see changes. Edit `pulse/audit/analysis.py` to refine how Conflict / Overlap / etc. are determined.

## Phase 2 — Railway deployment (when ready)

### 1. Sign up & create project

- Sign in at https://railway.app (you mentioned PRO account already)
- New Project → Deploy from GitHub repo → select this repo

### 2. Add Postgres

- In the project: **+ New → Database → Postgres**
- Railway auto-injects `DATABASE_URL` env var

### 3. Set env vars

In the service settings, add:

| Variable | Value |
|---|---|
| `HUBSPOT_PRIVATE_APP_TOKEN` | <your token> |
| `FLASK_SECRET_KEY` | <generate a long random string> |
| `POSTMARK_API_KEY` | <your Postmark token, when ready> |
| `POSTMARK_FROM_EMAIL` | `pulse@mytruage.org` |
| `APP_BASE_URL` | `https://truage-pulse.up.railway.app` (update once you point your domain) |

`DATABASE_URL` is set automatically by the Postgres plugin.

### 4. Deploy

Push to your `main` branch. Railway auto-builds and deploys. Visit the generated URL.

### 5. Initialize DB tables

In Railway's service dashboard → **Deployments → ... → Execute command**:

```
python -m pulse.storage --init
```

(One-time. Subsequent deploys leave existing data alone.)

### 6. Scheduled sends (when reports are ready to email)

Railway supports cron jobs. In the service:

- **+ New → Cron Job** in the same project
- Command: `python scripts/send_email.py audit recipient@example.com`
- Schedule: `0 8 * * 1` (Mondays 8am UTC) — adjust for ET later

### 7. Custom subdomain

Once `pulse.mytruage.org` DNS is ready:

- In Railway service: **Settings → Networking → Custom Domain**
- Add `pulse.mytruage.org`
- Update DNS at your registrar per Railway's instructions
- Update `APP_BASE_URL` env var

### 8. Auth0 (later)

When the parallel-thread Auth0 work is ready, plug in:

- Add `@requires_auth` decorator to routes in `app.py`
- Configure Auth0 callback URLs to point at this domain
- All three subdomains (pulse, 990, activation) share one Auth0 tenant

## Common issues

**502 Bad Gateway:** HubSpot token missing or invalid. Check Railway env vars.

**Slow first load:** HubSpot association calls are sequential. Could be cached — see TODO in `pulse/audit/data.py`.

**Postmark "From" address rejected:** Verify your sending domain in Postmark and add the required DNS records (SPF, DKIM).

**Cron job runs but no email arrives:** Check Postmark Activity log; could be domain verification, recipient on suppression list, etc.
