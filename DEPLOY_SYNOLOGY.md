# Deploying to Synology NAS

Run TruAge Pulse as a container on your Synology DSM. Good interim hosting until you push to Railway — your NAS is already on, no monthly cost, and the SQLite DB lives on your RAID.

## Prerequisites

- DSM 7+ with **Container Manager** installed (Package Center → search "Container Manager")
  - On DSM 6 or older DSM 7 builds, this might be called "Docker" — same thing
- SSH access to the NAS (Control Panel → Terminal & SNMP → enable SSH) — optional, makes life easier
- A HubSpot Private App access token (see `DEPLOY.md` for how to create one)

## Method 1 — Container Manager GUI (easier)

### 1. Get the code onto the NAS

Easiest path: use **File Station**.

- Create folder: `/volume1/docker/truage-pulse`
- Upload the unzipped repo contents into that folder
- Create a subfolder `data` (will hold the SQLite DB)

### 2. Create a `.env` file

In `/volume1/docker/truage-pulse/.env`:

```bash
HUBSPOT_PRIVATE_APP_TOKEN=pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
FLASK_SECRET_KEY=generate-a-long-random-string-here
APP_BASE_URL=http://zivnas.local:5050
# Leave Postmark blank for now; emails will be no-op
POSTMARK_API_KEY=
```

### 3. Create the project in Container Manager

- Open **Container Manager** → **Project** tab → **Create**
- **Project name:** `truage-pulse`
- **Path:** `/docker/truage-pulse`
- **Source:** Create docker-compose.yml — but it's already there, so select **Use existing docker-compose.yml**
- Click **Next** → review → **Done**

Container Manager will build the image (~2 minutes first time, then cached) and start it.

### 4. Verify

- In Container Manager → **Container** tab, see `truage-pulse` as Running
- Open `http://zivnas.local:5050/health` in browser — should return `{"status":"ok","version":"0.4.0"}`
- Open `http://zivnas.local:5050/audit` — should load the AM Audit pulling live from HubSpot

If `zivnas.local` doesn't resolve, use the NAS's IP directly: `http://192.168.x.x:5050/audit`.

## Method 2 — SSH command line (faster if you're comfortable)

```bash
ssh admin@zivnas.local
sudo -i
cd /volume1/docker
mkdir truage-pulse && cd truage-pulse

# Upload the repo via scp from your laptop:
# scp -r truage-pulse/* admin@zivnas.local:/volume1/docker/truage-pulse/

# Create .env (paste contents)
nano .env

# Start it
docker-compose up -d --build

# Tail logs
docker-compose logs -f
```

## Reverse proxy for HTTPS (recommended)

Right now the app is on port 5050 over HTTP. To get `https://pulse.zivnas.local` (or your real domain):

1. **DSM Control Panel → Login Portal → Advanced → Reverse Proxy**
2. **Create**
3. **Source:**
   - Protocol: HTTPS
   - Hostname: `pulse.zivnas.local` (or `pulse.mytruage.org` if you have DNS pointed at the NAS)
   - Port: 443
4. **Destination:**
   - Protocol: HTTP
   - Hostname: `localhost`
   - Port: 5050
5. Save. DSM uses its own certificate (Let's Encrypt available via Control Panel → Security → Certificate).

## Updating the app

When you pull new code from the repo:

```bash
cd /volume1/docker/truage-pulse
git pull   # or upload new files via File Station
docker-compose up -d --build
```

The `data/` folder is volume-mounted, so your SQLite DB and any rules/questions you've added survive rebuilds.

## Scheduled email sends (when Postmark is configured)

Synology has **Task Scheduler** built into DSM — no separate cron needed.

1. **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**
2. **Schedule:** Daily at 6:00 PM (or whenever)
3. **Task settings → User-defined script:**
   ```bash
   docker exec truage-pulse python scripts/send_email.py audit recipient@example.com
   ```

The container is already running so this just shells in and triggers the script.

## Resource use

This is a tiny app — Flask + a few hundred HubSpot records. Expect:

- ~80 MB RAM idle, ~150 MB during a `/audit` request
- Negligible CPU (no background work between requests)
- ~50 MB disk for the image, ~1 MB for SQLite

Even a DS220+ or smaller handles this comfortably.

## When to migrate to Railway

Move when any of these matter:

- You want the app accessible from outside your home network without exposing your NAS
- You want auto-deploys from GitHub on push
- You want Postmark + cron in one place instead of split across NAS Task Scheduler and the container
- You're done iterating and want production-grade uptime

Until then, the NAS is fine. Same Dockerfile works on both — Railway uses `railway.json` and ignores the compose file; Synology uses the compose file and ignores `railway.json`. Same image, same code.
