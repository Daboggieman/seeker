#!/bin/sh
# restic backup loop for the seeker index (./data -> /data in the container).
#
# Repository and credentials come from .env (RESTIC_REPOSITORY, RESTIC_PASSWORD,
# plus the backend's credentials — for B2: B2_ACCOUNT_ID / B2_ACCOUNT_KEY; for
# S3: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY).
#
# Keeps: 7 daily, 4 weekly, 6 monthly snapshots. Runs immediately on start,
# then every BACKUP_INTERVAL_SECONDS (default: 24h).

set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

while :; do
    echo "[backup] $(date -u +%FT%TZ) starting backup"
    if restic backup /data; then
        restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
        echo "[backup] $(date -u +%FT%TZ) done"
    else
        echo "[backup] restic backup failed; will retry next interval" >&2
    fi
    sleep "$INTERVAL"
done
