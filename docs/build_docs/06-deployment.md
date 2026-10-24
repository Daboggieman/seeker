# Seeker — Deployment

Source of record: spec §8 (Deployment), §10 (Security & Privacy).

## Docker Compose

```yaml
services:
  engine:
    build: ./engine
    ports:
      - "8420:8420"
    volumes:
      - ./data:/data          # sqlite-vec file + config
      - ~/Documents:/sources/home:ro
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
    restart: unless-stopped

  tailscale:
    image: tailscale/tailscale
    hostname: search-engine
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
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