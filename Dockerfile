FROM python:3.12-slim

# Synology shares are often slow on first I/O; keep image lean.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
# git is required for pip to install the truage-core dependency (git+https://…)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
ARG TRUAGE_CORE_PAT
RUN TRUAGE_CORE_PAT="$TRUAGE_CORE_PAT" pip install -r requirements.txt

# Copy the app
COPY . .

# Create the data directory; will be mounted as a volume on Synology so the
# SQLite DB persists across container restarts/upgrades.
RUN mkdir -p /app/data

# Initialize the DB on first boot if missing, then start gunicorn.
# (Idempotent — init_db uses CREATE TABLE IF NOT EXISTS.)
CMD ["sh", "-c", "python -m pulse.storage --init && gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 --access-logfile - --error-logfile -"]

EXPOSE 5000
