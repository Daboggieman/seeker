#!/bin/sh
# restic backup loop for the seeker index (./data -> /data in the container).
#
# Repository and credentials come from .env (RESTIC_REPOSITORY, RESTIC_PASSWORD,
# plus the backend's credentials — for B2: B2_ACCOUNT_ID / B2_ACCOUNT_KEY; for
# S3: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY). RESTIC_REPOSITORY must be a
# path MOUNTED into this container (e.g. /backups) — restic cannot create a
# repo on an unmounted host path (found 2026-11-16).
#
# Keeps: 7 daily, 4 weekly, 6 monthly snapshots. Runs immediately on start,
# then every BACKUP_INTERVAL_SECONDS (default: 24h). On failure retries every
# RETRY_SECONDS (default: 15 min) — the index is occasionally unreadable while
# a sync is writing (live sqlite), and a 24h blind spot after one bad run is
# worse than a short retry loop.

set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
RETRY="${BACKUP_RETRY_SECONDS:-900}"

while :; do
    echo "[backup] $(date -u +%FT%TZ) starting backup"
    if restic backup /data; then
        restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
        echo "[backup] $(date -u +%FT%TZ) done"
        sleep "$INTERVAL"
    else
        echo "[backup] restic backup failed; retrying in ${RETRY}s" >&2
        sleep "$RETRY"
    fi
done
