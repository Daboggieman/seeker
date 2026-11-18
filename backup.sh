#!/bin/sh
# restic backup loop for the seeker index (./data -> /data in the container).
#
# Repository and credentials come from .env (RESTIC_REPOSITORY, RESTIC_PASSWORD,
# plus the backend's credentials — for B2: B2_ACCOUNT_ID / B2_ACCOUNT_KEY; for
# S3: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY). RESTIC_REPOSITORY must be a
# path MOUNTED into this container (e.g. /backups) — restic cannot create a
# repo on an unmounted host path (found 2026-11-16).
#
# The live sqlite trio (seeker.db, -wal, -shm) is unreadable by restic's
# direct reads (EIO from the kernel while the engine holds the WAL mmap'd —
# found 2026-11-16; plain sequential reads work fine), so the files are first
# staged with cp and restic backs up the staged copy. A copy torn by a
# concurrent sync degrades to "slightly stale, still consistent" on restore:
# sqlite validates WAL frames by salt+checksum and ignores a mismatched one.
#
# Keeps: 7 daily, 4 weekly, 6 monthly snapshots. Runs immediately on start,
# then every BACKUP_INTERVAL_SECONDS (default: 24h). On failure retries every
# RETRY_SECONDS (default: 15 min).

set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
RETRY="${BACKUP_RETRY_SECONDS:-900}"
STAGE="/tmp/stage"

while :; do
    echo "[backup] $(date -u +%FT%TZ) starting backup"
    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    # || true: one unreadable file must not abort the whole backup
    cp -a /data/. "$STAGE"/ 2>/dev/null || true
    if restic backup "$STAGE"; then
        restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
        echo "[backup] $(date -u +%FT%TZ) done"
        sleep "$INTERVAL"
    else
        echo "[backup] restic backup failed; retrying in ${RETRY}s" >&2
        sleep "$RETRY"
    fi
done
