# Seeker — Self-Hosted Deployment Runbook

Operational companion to [`06-deployment.md`](06-deployment.md) (architecture & security
posture). Referenced by `backup.sh` and `.env.example`.

> **Status (2026-11-03):** the engine container is **live on the host** — native
> `seeker-engine.service` stopped, `gsmhub` corpus indexed through host Ollama via the
> docker bridge (pre-flight verified end-to-end 2026-11-02: health → auth → add source →
> sync → search). `SEEKER_EXCLUDE_DIRS` added 2026-11-03 after build artifacts
> (`dist/*.d.ts`) were found outranking real sources in the deployed index.
> Exit criterion — the same query from a second Tailnet device — is pending.
> Tailscale bring-up finding (2026-11-04): the `tailscale/tailscale` image ignores
> OAuth client credentials — its containerboot only reads `TS_AUTHKEY` (no
> `TS_OAUTH_*` strings in the binary), and the OAuth client lacks the API scope to
> mint keys (`POST /tailnet/-/keys` → 404 for unscoped clients). The sidecar
> authenticates with a reusable auth key tagged `tag:seeker` in `.env` instead.
> **Sidecar joined the tailnet 2026-11-05** (node `search-engine-2`, tagged
> `tag:seeker`, node state persisted via `TS_STATE_DIR`); MCP initialize (200) and
> REST `/v1/search` (200) verified through the tailnet IP with the MagicDNS Host
> header, wrong-Host still 421. Remaining for exit: delete the two stale tailnet
> nodes in the admin console → the same query from a second Tailnet device.

## Bring-up

```bash
cp .env.example .env          # fill: SEEKER_API_TOKEN, SEEKER_SOURCES, TS_AUTHKEY
docker compose up -d          # engine + tailscale sidecar + restic backup
```

- The engine publishes only `127.0.0.1:8420` on the host; Tailnet clients reach it through
  the Tailscale sidecar, which shares the engine's network namespace.
- `SEEKER_SOURCES` is mounted read-only at `/sources/home` (standing rule 7).
- `SEEKER_EXCLUDE_DIRS` (comma-separated) prunes directories from every source at any
  depth — set it for code corpora, or `dist/`, `node_modules/` and friends land in the
  index and crowd results (found 2026-11-02: a `dist/*.d.ts` outranked the real source).
- `SEEKER_MCP_ALLOWED_HOSTS` (comma-separated, e.g. `search-engine.your-tailnet.ts.net:*`)
  widens the MCP transport's DNS-rebinding guard beyond loopback — required before the
  second-device MCP query (REST `/v1/search` is unaffected by the guard).
- First run: `POST /v1/sources` with `root_path=/sources/home`, then sync.

### Prerequisite — Ollama must be reachable from the container

The engine reaches host Ollama at `host.docker.internal:11434` (`extra_hosts` maps it to
the docker bridge gateway). **Ollama's default bind is `127.0.0.1`-only, which the bridge
gateway cannot reach.** Fix applied 2026-11-02 as a systemd user drop-in
(`~/.config/systemd/user/ollama.service.d/override.conf`):

```ini
[Service]
Environment=OLLAMA_HOST=0.0.0.0
```

then `systemctl --user daemon-reload && systemctl --user restart ollama`. Loopback clients
(the native engine, CLI use) are unaffected. **Trade-off:** Ollama serves without
authentication, so this exposes it on every host interface — LAN-visible behind NAT.
Revert by deleting the drop-in and restarting the unit. (A tighter option — binding only
the docker bridge IP — breaks when docker0's address changes; not recommended.)

### Port conflict with the native dev engine

The native systemd `seeker-engine.service` holds `127.0.0.1:8420`. Running the compose
stack on the same host requires stopping it first (`systemctl --user stop
seeker-engine`) or the compose port publish fails. The compose stack is the deployment
target; the native service is the dev instance.

**Reboot race (found 2026-11-04):** the native unit is `WantedBy=default.target` with
linger enabled — it auto-starts at every boot and (`Restart=on-failure`) fights the
compose container for the port. After a reboot the native engine can win, leaving the
container healthy but unreachable on the published port (host curls hit the native
instance and its separate `engine/data/seeker.db` — smoke corpus — instead of the
deployed index). Fix applied: `systemctl --user disable --now seeker-engine.service` —
the dev instance stays available on demand (`systemctl --user start seeker-engine`,
then stop it again before compose work) but never races the container at boot.

## Backup & restore

The `backup` service runs `restic backup /data` on a loop (`BACKUP_INTERVAL_SECONDS`,
default 24h), keeping 7 daily / 4 weekly / 6 monthly snapshots, then prunes. Configure in
`.env`: `RESTIC_REPOSITORY` + `RESTIC_PASSWORD` plus the backend's credentials (B2 or S3
examples in `.env.example`).

```bash
# Restore the latest snapshot (from any machine with the repo credentials):
docker compose run --rm backup sh -c \
  'restic restore latest --target /tmp-restore && ls /tmp-restore/data'
# Then stop the engine, replace ./data/seeker.db (and -wal/-shm if present), restart.
```

Backups mount `./data` read-only — the backup container can never corrupt the index.
Test a restore after first configuring the repository; an untested backup is not a backup.

## Token rotation

Rotate `SEEKER_API_TOKEN` in `.env` (rotate if a device is lost — docs 06), then
`docker compose up -d engine` to recreate the container. Update every client's bearer
token (Claude Code MCP registration, mobile, extension) in the same breath — there is a
single shared secret at personal scale.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Sync fails: connection refused to `host.docker.internal:11434` | Ollama bound to loopback only — apply the drop-in above |
| `POST /mcp` → 421 / 400 from SDK | Host header rejected by the SDK's DNS-rebinding guard. Loopback always passes (`Host` must carry a port: `http://127.0.0.1:8420/mcp`). For a Tailscale hostname, set `SEEKER_MCP_ALLOWED_HOSTS` in `.env` (e.g. `search-engine.your-tailnet.ts.net:*`) and `docker compose up -d engine` to apply |
| Compose up fails: `TS_AUTHKEY is missing` | Required `.env` guard working as intended; generate a reusable auth key tagged `tag:seeker` at login.tailscale.com/admin/settings/keys |
| Sidecar crash-loops printing "To authenticate, visit" login URLs | OAuth client creds in `.env` are ignored by this image (containerboot has no `TS_OAUTH_*` support) — set `TS_AUTHKEY` |
| Sidecar registers a NEW node on every restart, consuming the auth key | containerboot runs tailscaled with `--state=mem:` unless `TS_STATE_DIR` is set (found 2026-11-05) — the compose file sets it to `/var/lib/tailscale` (the mounted volume) |
| Recreating the engine left the sidecar dead (`network namespace ... not running`) | The sidecar lives in the engine's netns — recreating the engine orphans it. Always `docker compose up -d` (all services), never `up -d engine` alone (found 2026-11-05) |
| Compose up fails: port 8420 in use | Native `seeker-engine.service` still running — stop it (`systemctl --user disable --now seeker-engine` if it came back after a reboot) |
| `backup` logs `restic backup failed` every interval | Repository not initialized — run `docker compose run --rm backup sh -c 'restic init'` once (it loops forever by design; check `docker compose logs backup`) |
