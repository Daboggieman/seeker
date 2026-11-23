# Seeker

A self-hosted **semantic search engine over your own files**. Point it at folders on
your machine; it chunks them, embeds them locally (Ollama / `nomic-embed-text`), and
stores them in `sqlite-vec`. Search from any browser page (extension overlay), your
phone, an AI assistant (MCP), or plain curl — everything stays on your hardware or
inside your Tailscale network.

**Status 2026-11-17:** phases 1–4 complete and field-tested — core engine,
self-hosted deployment (second-device search proven), Android client (Waydroid
field test), browser extension (overlay in Google Docs). Live index: 4 sources,
463 documents / 910 chunks (2026-11-23). Next per roadmap: Phase 5 (Office add-in) when wanted.

## Using it

| Surface | How |
| --- | --- |
| **Browser overlay** | `brave://extensions` → Developer mode → Load unpacked → `extension/` → toolbar icon → paste token → Save → Test → `Alt+Shift+S` on any page |
| **Phone (Android)** | Install the APK (EAS account `daboggieman`), Tailscale on the device, Settings → token → Test → Save |
| **AI assistant (MCP)** | Point the client at `http://127.0.0.1:8420/mcp` (or the tailnet URL); bearer token on every call |
| **Raw API** | `curl -H "Authorization: Bearer $TK" -H 'Content-Type: application/json' -d '{"query":"…"}' http://127.0.0.1:8420/v1/search` |

Engine URLs: host clients → `http://127.0.0.1:8420`; tailnet devices →
`https://search-engine-2.taile24e8b.ts.net` (the host itself is not a tailnet node).

The full owner-operator handbook is **[docs/user_manual.md](docs/user_manual.md)** —
daily use, adding sources, engine ops, backups, security, troubleshooting, API
reference, FAQ.

## Operating it

```bash
cd /home/recoding/seeker            # live deployment lives here
docker compose up -d                # start / apply config
docker compose ps                   # health
docker logs seeker-engine-1 --tail 50
```

- **Daily sync** of every source at 09:00 — systemd user timer `seeker-sync.timer`
  (`scripts/sync-all.sh`; reads the token fresh from `.env`).
- **Nightly restic backup** of the index (`backup` service → `~/seeker-backups`;
  staged-copy design — see build docs 12 for why).
- **Token**: `SEEKER_API_TOKEN` in `.env`; rotate → `docker compose up -d` → re-paste
  in every client.

## Repo map

```
engine/       Python + FastAPI engine, connectors, pipeline, MCP shim, tests
extension/    MV3 browser extension (overlay + background worker + options)
mobile/       Expo/React Native Android client
docs/
  build_docs/     the plan: architecture, API, specs, runbooks 00–14
  handover_docs/  the record: current state board, conventions
  adr/            architecture decision records
  user_manual.md  the owner-operator handbook
```

## Working on it

- Read `docs/handover_docs/01-current-state.md` first — it is the live status board.
- The plan lives in `docs/build_docs/` (start at its README); the standing rules for
  coding sessions are build doc 11; open decisions in build doc 10.
- One branch per phase; phases land on master only when their exit criteria pass.
