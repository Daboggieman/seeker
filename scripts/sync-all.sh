#!/bin/sh
# Sync every registered Seeker source. Run by the seeker-sync.timer systemd
# user unit (daily); also fine to run by hand. The token is read fresh from
# the engine's .env on every run, so token rotation needs no change here.
#
# Only meaningful on the host (the engine is on 127.0.0.1:8420).

set -u
ENV_FILE="/home/recoding/seeker/.env"
BASE="http://127.0.0.1:8420"

TK=$(grep '^SEEKER_API_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
[ -n "$TK" ] || { echo "no SEEKER_API_TOKEN in $ENV_FILE" >&2; exit 1; }

ids=$(curl -4 -s --max-time 30 -H "Authorization: Bearer $TK" "$BASE/v1/sources" \
      | python3 -c 'import json,sys; print(" ".join(s["id"] for s in json.load(sys.stdin)))') || {
  echo "could not list sources (engine down?)" >&2; exit 1; }

for id in $ids; do
    echo "$(date -u +%FT%TZ) sync $id"
    curl -4 -s --max-time 7200 -X POST -H "Authorization: Bearer $TK" \
         "$BASE/v1/sources/$id/sync" | head -c 400
    echo
done
echo "$(date -u +%FT%TZ) all sources synced"
