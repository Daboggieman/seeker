# Seeker — Deployment

Source of record: spec §8 (Deployment), §10 (Security & Privacy).

> **Phase 2 status (2026-11-03):** the engine container is **live on the host** (native
> engine stopped; gsmhub corpus indexed through host Ollama via the docker bridge;
> pre-flight verified end-to-end 2026-11-02). `SEEKER_EXCLUDE_DIRS` (new 2026-11-03)
> prunes build-output dirs from every source — set it for code corpora. Operational
> runbook: [`12-self-hosted-deployment.md`](12-self-hosted-deployment.md) — incl. the
> Ollama-bind fix and the native-engine port conflict. Exit criterion MET 2026-11-12:
> Tailscale auth key set in `.env` (the image ignores OAuth client creds — 2026-11-04)
> and `tailscale serve` 443→8420 enabled on sidecar node `search-engine-2`; the
> second-device query works (Waydroid node, engine log `POST /v1/search 200`). Until the stack
> was deployed, the engine ran natively as systemd **user** services
> (`ollama.service` still does; `seeker-engine.service` on `:8420` is stopped while the
> container holds the port, config in `~/.config/seeker/engine.env`) — see handover `01`.

## Docker Compose

```yaml
services:
  engine:
    build: ./engine
    ports:
      - "8420:8420"
    volumes:
      - ./data:/data          # sqlite-vec file + config
      - ${SEEKER_SOURCES}:/sources/home:ro
    environment:
      - SEEKER_API_TOKEN=${SEEKER_API_TOKEN}
      - SEEKER_EMBEDDING_BASE_URL=http://host.docker.internal:11434
    restart: unless-stopped

  tailscale:
    image: tailscale/tailscale
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_HOSTNAME=search-engine     # `hostname:` is rejected alongside network_mode: service:…
      - TS_STATE_DIR=/var/lib/tailscale   # without this every start re-registers a node
    network_mode: service:engine
    volumes:
      - ./ts-state:/var/lib/tailscale
```

Running this on a home server, NAS, or a small VPS puts the engine on your Tailnet — every
device you own reaches it at a stable private address (e.g.
`search-engine.your-tailnet.ts.net:8420`) without exposing anything to the public internet.

## Ollama

The embedding backend runs on the host, not in the container — the engine reaches it at
`host.docker.internal:11434`. This keeps model weights out of the container image and lets
Ollama serve both the engine and any other local model use.

> **Linux note (recorded 2026-10-24):** `host.docker.internal` does not resolve on Linux by
> default. The compose file needs `extra_hosts: ["host.docker.internal:host-gateway"]`
> on the engine service (present in the live docker-compose.yml since deployment) —
> the spec's skeleton was written for Docker Desktop.

## Security posture

- **No public internet exposure** — Tailscale-only reachability.
- **Bearer-token auth** between clients and the engine (a shared secret is sufficient at
  personal scale; rotate it if a device is lost).
- **Source credentials** (Drive/Notion OAuth tokens) stored encrypted at rest in the engine's
  config, never sent to clients.

## Data layout

- `./data/` — sqlite-vec index file + engine config. Back this up; it is the only durable state.
- `./ts-state/` — Tailscale node state.
- Source mounts are read-only (`:ro`) — the engine reads, never writes to indexed locations.