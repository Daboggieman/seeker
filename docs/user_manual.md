# Seeker — User Manual

*For the owner-operator. Every command and number below was verified against the live
deployment on 2026-11-17. Where the manual and reality ever disagree, trust reality and
re-measure.*

---

## 1. What Seeker is

Seeker is a **personal search engine for your own files**. You point it at folders on
this machine ("sources"); it reads them, splits them into pieces, and builds a semantic
index — meaning you can search by *what a document is about*, not just by exact keywords.
You then search that index from anywhere:

- the **browser overlay** (press `Alt+Shift+S` on any web page, including Google Docs),
- the **phone app** (works off wifi, over your private Tailscale network),
- an **AI assistant** (Claude, via the MCP protocol),
- or **raw API calls** (curl).

Everything runs on your hardware. Nothing is sent to any cloud service — search queries,
documents, and embeddings all stay on this machine or inside your tailnet.

**What Seeker is not:** it does not search the web, it does not search *inside the page
you have open* (that's the browser's own Ctrl+F), and it does not look at the document
you're viewing — the overlay is a window onto your indexed files, available from
wherever you happen to be.

---

## 2. How the system fits together

```
 this machine (the host — NOT a Tailscale node)
 ┌────────────────────────────────────────────────────────────┐
 │  Ollama (systemd user unit "ollama.service", port 11434)   │
 │    └─ embedding model: nomic-embed-text (768 dimensions)   │
 │                                                            │
 │  Docker Compose stack  (lives in /home/recoding/seeker)    │
 │   ├─ seeker-engine-1    the engine — REST API on           │
 │   │                     127.0.0.1:8420 (host only)         │
 │   ├─ seeker-tailscale-1 sidecar sharing the engine's net-  │
 │   │                     work; tailnet node "search-        │
 │   │                     engine-2" (100.89.242.5); serves   │
 │   │                     https://search-engine-2.           │
 │   │                     taile24e8b.ts.net (443 → 8420)     │
 │   └─ seeker-backup-1    restic backup loop (working; §7)   │
 │                         fixed 2026-11-17                   │
 │                                                            │
 │  ./data/seeker.db        the index — the only durable state│
 └────────────────────────────────────────────────────────────┘
        │ loopback                    │ tailnet (encrypted)
        ▼                             ▼
  Brave + extension             phone / Waydroid app
  (http://127.0.0.1:8420)       (https://search-engine-2.taile24e8b.ts.net)
```

Two network facts that trip people up:

1. **The host is not a Tailscale node.** The name `search-engine-2.taile24e8b.ts.net`
   only resolves from *inside* the tailnet. From this machine, use
   `http://127.0.0.1:8420`.
2. **Other devices on your tailnet** (the phone) cannot reach `127.0.0.1` — they use
   the ts.net address above.

Both addresses serve the same engine; the token is the same.

---

## 3. Words to know

| Word | Meaning |
| --- | --- |
| **Engine** | The server program that stores the index and answers searches. |
| **Source** | A folder registered with the engine. Each has an id (e.g. `gsmhub`), a root path, and a last-synced timestamp. |
| **Document** | One file in a source. 463 documents indexed as of 2026-11-23. |
| **Chunk** | A piece of a document (~300–500 words, ~50-word overlap between neighbours) that gets embedded and searched. Chunks remember their PDF page number. 910 chunks as of 2026-11-23. |
| **Embedding** | A numeric vector describing a chunk's meaning. Similar meanings → nearby vectors. Built locally by Ollama. |
| **Semantic search** | Matching by meaning. "how do I rotate the token" can find a doc that says "change the bearer secret". |
| **Sync** | Walk a source's files and update the index. Every sync is a full walk; files whose content is unchanged (matched by hash) are skipped for re-indexing. Runs automatically every day at 09:00 (§5); you can also trigger it manually. |
| **top_k** | How many results a search returns. API default 5; the browser overlay asks for 20. |
| **Score** | Cosine similarity from -1 to 1. Higher is better; ~0.5–0.8 is a strong hit in practice. |
| **Snippet** | The first ~240 characters of the matched chunk. |
| **Bearer token** | The shared password every client sends with each call. Rotated 2026-11-17 — the live value is in `/home/recoding/seeker/.env` (`SEEKER_API_TOKEN`); see §8. |
| **Tailnet** | Your private Tailscale network. Devices in it can talk to each other over an encrypted tunnel from anywhere. |

---

## 4. Daily use

### 4.1 The browser overlay — Brave (your main browser)

The overlay is a search panel that slides over any web page. Install once:

1. Open `brave://extensions` → toggle **Developer mode** (top-right).
2. Click **Load unpacked** → select the `extension/` folder. A visible shortcut to it
   lives at **`/home/recoding/Downloads/seeker-extension`** (the real path is a hidden
   dot-folder inside the seeker repo worktree).
3. Click the **Seeker toolbar icon** (puzzle piece → pin it). That opens **Options**.
4. Set **Engine URL** to `http://127.0.0.1:8420` (host!) and paste the bearer token
   → **Save** → **Test** → expect `✓ engine reachable — N source(s)` (the count equals
   your registered sources — 4 as of 2026-11-23).
5. Press **`Alt+Shift+S`** on any page → the overlay opens.

Using it:

- **Type, then Enter** — results appear under the search box.
- **Source chips** under the box (`All`, one per source) filter the search — click a chip to restrict, click again for All.
- **Click a result** → its file path is copied to your clipboard (status line confirms `Copied path: …`). Paste it wherever you need it.
- **Esc** or click the dark background → close.
- The status line reports `N results · X ms`, or an error code (see §9).

Notes:

- Shortcut is `Alt+Shift+S` on Linux/Windows, `Command+Shift+S` on Mac. Chromium
  rejects `Ctrl+Alt` shortcuts (they collide with AltGr text input), which is why it
  isn't Ctrl+Alt+S. Rebind at `brave://extensions/shortcuts` if it clashes.
- Pages loaded *before* the extension was installed or reloaded don't have the overlay
  until you refresh them (F5).
- `brave://` pages and the Chrome Web Store never get content scripts — the shortcut
  does nothing there. Any normal site works.
- The token lives only in the extension's background worker; web pages can't see it,
  and results are rendered in a closed shadow-DOM the page can't read.

### 4.2 The overlay — Firefox

Firefox needs its own manifest (Chromium refuses a background config that lists both
forms, Firefox needs the list form):

1. `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on…** → pick
   `extension/manifest-firefox.json` (the file, not the folder).
2. Same options flow as above (puzzle icon → ⚙ → Options), same shortcut.

Temporary means Firefox unloads it on exit — reload the same way next session. If it
becomes daily-use, decide about signing (AMO unlisted); not blocking.

### 4.3 The phone app (Waydroid / any Android)

The app (`com.daboggieman.seeker`) searches the same engine over the tailnet.

First run:

1. Install the APK from the build pages at expo.dev (account **daboggieman**).
   Upgrading with `adb install -r` preserves settings.
2. Make sure the **Tailscale app in Waydroid is connected** (it disconnects when the
   host reboots — reopen the Tailscale app and toggle on).
3. In the app: **Settings** → engine URL is prefilled with
   `https://search-engine-2.taile24e8b.ts.net` (correct for the phone — keep it) →
   paste the token → **Test** → **Save**. Settings persist in the phone's secure
   keychain across restarts.
4. Search from the main screen; the source filter lives in the settings modal.

Manual testing on Waydroid (if the adb tooling is set up): UI state can be read with
`adb shell uiautomator dump` — no screenshots needed.

### 4.4 Asking an AI assistant (MCP)

The engine speaks MCP (Model Context Protocol) at `/mcp`, so Claude (or any MCP
client) can search your files as a tool. Three tools exist:

- `search_documents(query, top_k=5, source_ids)` — search,
- `list_sources()` — what's indexed and when it last synced,
- `reindex_source(source_id)` — trigger a re-sync.

Point a local client at `http://127.0.0.1:8420/mcp` (loopback hosts are always
allowed); a tailnet client uses the ts.net hostname — it's pre-approved via
`SEEKER_MCP_ALLOWED_HOSTS`. The same bearer token is required on every MCP call.

### 4.5 Raw API (curl)

```bash
# from the host — token into a variable once, never echoed
TK=$(grep '^SEEKER_API_TOKEN=' /home/recoding/seeker/.env | cut -d= -f2-)

curl -s http://127.0.0.1:8420/v1/health                        # {"status":"ok"} — no token needed
curl -s -H "Authorization: Bearer $TK" http://127.0.0.1:8420/v1/status
curl -s -H "Authorization: Bearer $TK" http://127.0.0.1:8420/v1/sources
curl -s -H "Authorization: Bearer $TK" -H 'Content-Type: application/json' \
     -d '{"query":"how does sync work","top_k":5}' \
     http://127.0.0.1:8420/v1/search
# restrict to one source:
curl -s -H "Authorization: Bearer $TK" -H 'Content-Type: application/json' \
     -d '{"query":"config","top_k":5,"filters":{"source_id":["gsmhub"]}}' \
     http://127.0.0.1:8420/v1/search
```

Every response carries an `X-Request-Id` header (echoed if you sent one) — quote it
when reporting a problem; it's in the engine log too.

---

## 5. Making your files searchable (sources & indexing)

### What's indexed today

Four sources, all on this machine:

| Source | Folder (host) | Mounted at (container) |
| --- | --- | --- |
| `gsmhub` | `/home/recoding/gsmhub` | `/sources/home` |
| `cee-tailor` | `/home/recoding/cee-tailor` | `/sources/cee-tailor` |
| `ai-router-setup` | `/home/recoding/ai-router-setup` | `/sources/ai-router-setup` |
| `ant2oia` | `/home/recoding/ant2oia` | `/sources/ant2oia` |

448 documents / 820 chunks as of 2026-11-17 — **463 / 910 as of 2026-11-23** (the daily
timer keeps it growing). Deliberately **not** indexed: `$HOME`
itself (it contains loose secret files — wallet/2FA/key notes), `Downloads`, media
folders. Never point a source at the whole home directory.

### What gets indexed — and what doesn't

| Content | Result |
| --- | --- |
| Text files (`.md`, `.txt`, code — `.ts`/`.tsx`/`.jsx` specially handled) | Indexed as text |
| PDFs **with a text layer** | Indexed, page numbers kept |
| Scanned/image-only PDFs | Indexed to nothing (OCR is a later phase) |
| `.docx`/`.xlsx`/`.pptx` office files | **Skipped** (unsupported) |
| Images, video, binaries, zip archives | Skipped |
| Hidden files/dirs (dot-prefixed) | Skipped |
| Symlinks | Never followed, never indexed |
| Dirs named in `SEEKER_EXCLUDE_DIRS` | Pruned at any depth (currently `node_modules,dist,playwright-report,test-results`) |

Chunking splits at paragraph/section boundaries (~300–500 words, ~50-word overlap), so
results point at meaningful passages, not arbitrary mid-sentence cuts.

### The one structural constraint: the mount

The engine runs in a container and can only see folders **explicitly mounted into it**.
Each mount is one line in the `engine:` service of
`/home/recoding/seeker/docker-compose.yml` (read-only); the source's `root_path` is
the container-side path:

```
.env:                 SEEKER_SOURCES=/home/recoding/gsmhub
docker-compose.yml:   ${SEEKER_SOURCES}:/sources/home:ro                  → source "gsmhub"
                      /home/recoding/cee-tailor:/sources/cee-tailor:ro    → source "cee-tailor"
                      /home/recoding/ai-router-setup:/sources/ai-router-setup:ro
                      /home/recoding/ant2oia:/sources/ant2oia:ro
```

To make a new folder searchable (say `/home/recoding/Documents`):

1. **Edit `/home/recoding/seeker/docker-compose.yml`** — in the `engine:` service,
   add a volume line:
   ```yaml
       volumes:
         - ./data:/data
         - ${SEEKER_SOURCES:?set SEEKER_SOURCES in .env}:/sources/home:ro
         - /home/recoding/Documents:/sources/documents:ro   # ← new line
   ```
   (Prefer per-folder mounts over mounting all of `$HOME` — bigger mounts mean slower
   walks and more noise.)
2. **Recreate the engine** so the mount appears:
   ```bash
   cd /home/recoding/seeker && docker compose up -d
   ```
3. **Register + sync the source:**
   ```bash
   TK=$(grep '^SEEKER_API_TOKEN=' /home/recoding/seeker/.env | cut -d= -f2-)
   curl -s -H "Authorization: Bearer $TK" -H 'Content-Type: application/json' \
        -d '{"source_id":"documents","root_path":"/sources/documents"}' \
        http://127.0.0.1:8420/v1/sources
   curl -s -X POST -H "Authorization: Bearer $TK" \
        http://127.0.0.1:8420/v1/sources/documents/sync
   ```
4. **Verify:** `GET /v1/status` — the new source should appear with a fresh
   `last_synced_at`. The overlay's chips pick it up next time you open it.

Registering a source does **not** index it — always follow with a sync call.

### Keeping the index fresh

Syncs run **automatically every day at 09:00** — a systemd user timer
(`seeker-sync.timer`) calls `/home/recoding/seeker/scripts/sync-all.sh`, which syncs
every registered source (it reads the token fresh from `.env`, so rotation needs no
change here). Check it with `systemctl --user list-timers seeker-sync.timer`. Manual
re-syncs still work anytime (or via an MCP client's `reindex_source`):

```bash
curl -s -X POST -H "Authorization: Bearer $TK" http://127.0.0.1:8420/v1/sources/gsmhub/sync
```

A sync returns its tally:

```json
{"indexed": 3, "skipped_unchanged": 205, "unsupported": 12, "pruned": 1, "failed": []}
```

- `indexed` — new/changed files added; `skipped_unchanged` — files whose content hash
  is unchanged (no re-embedding); `unsupported` — skipped types; `pruned` —
  deleted files removed from the index.
- `failed` lists individual files with `path`, `error`, `reason`, and a `suggestion`
  (e.g. "PDF could not be parsed (corrupt or image-only)").
- A source's status row reads `idle` (healthy), `syncing`, or `error` — check with
  `GET /v1/sources`. A failed sync leaves `error` in place; fix the cause and sync again.

### Removing a source

```bash
curl -s -X DELETE -H "Authorization: Bearer $TK" http://127.0.0.1:8420/v1/sources/<id>
```

This removes the source **and every document indexed from it**. The folder on disk is
untouched. (The mount line in docker-compose.yml, if you added one, is yours to remove
too.)

---

## 6. Managing the engine

All commands run from `/home/recoding/seeker` (the live deployment directory).

```bash
cd /home/recoding/seeker
docker compose ps                 # what's running, healthy?
docker compose up -d              # start / apply config changes (.env, compose edits)
docker compose restart engine     # plain restart
docker compose stop               # stop the stack
docker logs seeker-engine-1 --tail 100      # engine logs
docker logs seeker-backup-1 --tail 20       # backup logs
systemctl --user list-timers seeker-sync.timer   # daily auto-sync (09:00)
```

Every search hits the engine log like this — useful as proof a client really connected:

```
INFO: 172.19.0.1:64280 - "POST /v1/search HTTP/1.1" 200 OK     ← host/Brave (docker gateway)
INFO: 100.101.53.85:0 - "POST /v1/search HTTP/1.1" 200 OK      ← phone over the tailnet
```

**Liveness:** `curl http://127.0.0.1:8420/v1/health` → `{"status":"ok"}`. If that
fails, `docker compose up -d` and check `docker compose ps`.

**Embedding backend (Ollama)** runs natively, not in Docker:

```bash
systemctl --user status ollama     # unit "ollama.service", port 11434
systemctl --user restart ollama    # if embeddings start failing
```

The engine needs Ollama for search (queries are embedded live). If Ollama is down,
searches fail with a backend error while health still reports ok.

**Reboot note:** after a host reboot the compose stack auto-starts (`restart:
unless-stopped`); there was once a boot race between the now-disabled native
`seeker-engine.service` and the engine container for port 8420 (fixed 2026-11-04 by
disabling the native unit). If search fails right after a reboot, check Ollama first
(`systemctl --user status ollama`), then the Waydroid Tailscale app if testing from
the phone.

**First search after a fresh start is slow** (the embedding model loads on first use —
observed ~5.8 s from the phone; subsequent searches ran in ~0.6–0.8 s).

**After a code change** (engine source lives in `engine/`): rebuild with
`docker compose up -d --build engine`.

---

## 7. Backups — working since 2026-11-17

The stack runs a restic backup container (`seeker-backup-1`) that snapshots the index
(`./data`) daily, keeping 7 daily / 4 weekly / 6 monthly snapshots. Getting here took
two non-obvious fixes — worth knowing if you ever move the destination:

1. **`RESTIC_REPOSITORY` must be a path mounted into the container.** `.env` sets
   `RESTIC_REPOSITORY=/backups`; docker-compose.yml mounts
   `/home/recoding/seeker-backups:/backups`. Restic can't create a repo on an unmounted
   host path — the first `init` silently landed inside the container layer and vanished.
2. **Restic cannot read the live sqlite files directly.** While the engine holds the
   WAL mmap'd, restic's reads fail with kernel I/O errors (plain sequential reads work
   fine — this cost an afternoon to pin down). The script therefore stages a copy with
   `cp` and backs the copy up. A copy torn by a concurrent sync degrades to "slightly
   stale, still consistent" on restore: sqlite validates WAL frames by salt + checksum
   and ignores a mismatched one.

On failure it retries every 15 minutes (`BACKUP_RETRY_SECONDS`), not 24 h.

Verify:

```bash
docker logs seeker-backup-1 --tail 5         # should end with "[backup] … done"
cd /home/recoding/seeker && docker compose run --rm --entrypoint restic backup snapshots
```

What's protected: the whole index. What isn't: your source folders themselves (those
live outside `./data` — protect them with your normal file backups). To move the
destination (e.g. offsite to Backblaze B2): set `RESTIC_REPOSITORY=b2:<bucket>:<prefix>`
plus `B2_ACCOUNT_ID` / `B2_ACCOUNT_KEY` in `.env`, run `docker compose run --rm
--entrypoint restic backup init`, then `docker compose up -d --force-recreate backup`.

---

## 8. Security & privacy

**The token.** Every client-engine call carries `Authorization: Bearer <token>`, checked
in constant time. It lives in `/home/recoding/seeker/.env` (`SEEKER_API_TOKEN`) and was
rotated off the development placeholder on 2026-11-17 (the old `dev-insecure-token` is
dead — the engine returns 401 for it). Re-run the same procedure whenever you want a
fresh secret:

```bash
NEW=$(openssl rand -hex 32)
sed -i "s/^SEEKER_API_TOKEN=.*/SEEKER_API_TOKEN=$NEW/" /home/recoding/seeker/.env
cd /home/recoding/seeker && docker compose up -d      # recreates the engine with the new token
# then re-paste the new token in: the extension options, the phone app settings,
# and any MCP client config — the old token stops working the moment the engine restarts
```

Where each client keeps the token: extension → browser profile (`chrome.storage.local`),
readable only by the extension's background worker; phone app → OS secure keychain
(`expo-secure-store`); never in a web page, never logged.

**The network boundary.** The engine binds to host loopback only
(`127.0.0.1:8420`) — nothing on the LAN can reach it. The tailnet path is the Tailscale
sidecar serving HTTPS with a proper certificate. Tailscale itself is a private wire —
the public internet sees only encrypted Tailscale traffic.

**What leaves the machine: nothing.** Embeddings come from local Ollama; queries stay
on the tailnet; no cloud API is called. (The compose file has an LLM endpoint knob for
future query rewriting — it points at local Ollama too and is currently inert.)

**Known exposure trade-offs, on record:** Ollama is bound to `0.0.0.0` (LAN devices
can use it — deliberate, documented 2026-11-03); the token is shared across clients
(rotate when a device is lost — OD 8).

---

## 9. Troubleshooting

**Engine / general**

| Symptom | Cause → fix |
| --- | --- |
| `curl /v1/health` fails | Engine down → `cd /home/recoding/seeker && docker compose up -d`, then `docker compose ps` |
| Search returns backend/model errors | Ollama down → `systemctl --user restart ollama` |
| Everything worked, now nothing does (after reboot) | Check Ollama unit first, then `docker compose ps`; phone users: reconnect Tailscale in Waydroid |
| Search slow the first time | Model cold start (~5–6 s once); subsequent searches < 1 s |
| Results seem stale | Index is only as fresh as the last sync (automatic daily at 09:00) → `POST /v1/sources/<id>/sync` to sync now |
| `UNAUTHORIZED` | Wrong/rotated token in that client → re-paste from `.env` (`SEEKER_API_TOKEN`) |
| Empty results for a query you know is there | File type unsupported (§5 table), file added after last sync, or excluded dir — check the sync stats |

**Browser overlay**

| Symptom | Cause → fix |
| --- | --- |
| Options **Test** → `NETWORK_ERROR` on the ts.net URL | You're on the host — it's not a tailnet node. Use `http://127.0.0.1:8420` (the ts.net URL is for the phone) |
| Test → `NETWORK_ERROR` on `127.0.0.1:8420` | Engine down → §6 first table row |
| `Alt+Shift+S` does nothing | Refresh the page (F5) — tabs opened before the extension loaded lack the content script; or check `brave://extensions/shortcuts`; or you're on a `brave://` page |
| Brave refused to load the extension | Use the Chrome-family `manifest.json` (already default) — and the folder, not a single file |
| Firefox loads but can't search | You loaded the Chrome manifest — pick `manifest-firefox.json` instead |
| Overlay shows but no source chips | Sources fetch failed → run Test in options; chips fall back to "All" |

**Phone app**

| Symptom | Cause → fix |
| --- | --- |
| `NETWORK_ERROR` banner | Tailscale app in Waydroid disconnected (common after host reboot) → reopen and connect; verify with a fresh search — engine log should show `100.101.53.85` |
| Search works but slow | First search after cold start (~6 s) |
| Settings lost | They shouldn't be (keychain-backed) — re-enter URL `https://search-engine-2.taile24e8b.ts.net` + token |

---

## 10. API reference

Base URL (host): `http://127.0.0.1:8420` · (tailnet): `https://search-engine-2.taile24e8b.ts.net`
Auth: `Authorization: Bearer <token>` on everything except `/v1/health`.
All errors: `{"detail": {"code": "...", "message": "..."}}` with an `X-Request-Id` response header.

| Method & path | Purpose | Notes |
| --- | --- | --- |
| `GET /v1/health` | Liveness | Anonymous. `{"status":"ok"}` |
| `GET /v1/status` | Model, counts, sources | `{status, embedding_model, dimensions, documents, chunks, sources:[…]}` |
| `GET /v1/sources` | List sources | Each: `{id, type, root_path, last_synced_at, status}` |
| `POST /v1/sources` | Register a source | Body `{"source_id", "root_path"}` → 201. `root_path` must be a mounted dir (422 `VALIDATION_ERROR` otherwise). **Does not sync** — follow with the call below |
| `POST /v1/sources/{id}/sync` | Index a source | Returns `{indexed, skipped_unchanged, unsupported, pruned, failed:[…]}`; 404 `SOURCE_NOT_FOUND` for unknown ids |
| `DELETE /v1/sources/{id}` | Remove a source | 204; cascades its documents |
| `POST /v1/search` | Semantic search | Body `{"query": str (≥1 char), "top_k": 1–100 (default 5), "filters": {"source_id": ["id", …]}}` (optional). Response `{"results": [row, …]}` |
| `POST /mcp` | MCP transport | Bearer-gated like REST; tools `search_documents`, `list_sources`, `reindex_source` |

Search result row:

```json
{
  "chunk_id": "…", "document_id": "…", "title": "file name",
  "path": "path inside the source", "snippet": "first ~240 chars",
  "score": 0.62, "source_id": "gsmhub", "page": 3, "position": 12
}
```

`score` is cosine similarity (higher = closer in meaning). `page` is the PDF page
(`null` for plain text). `position` is the chunk's index within its document.

Error codes: `UNAUTHORIZED` (401) · `VALIDATION_ERROR` (422 — bad body, empty query,
non-directory root_path) · `SOURCE_NOT_FOUND` (404) · anything else → 500.

---

## 11. Current state & limits (2026-11-23)

- **Indexed:** 4 sources (`gsmhub`, `cee-tailor`, `ai-router-setup`, `ant2oia`),
  463 documents, 910 chunks (2026-11-23).
- **Retrieval quality:** baseline recall@5 = **0.50** over a 20-query eval set
  (measured on the gsmhub-only corpus, 2026-11-04) — about half of known-relevant
  files appear in the top 5. Sprawling catch-all files crowd out precise ones.
  Planned (not built): query rewriting, a reranker pass — and a re-baseline now that
  the corpus has tripled.
- **Syncs:** automatic daily at 09:00 (systemd `seeker-sync.timer`); manual anytime.
- **Backups:** working since 2026-11-17 (staged-copy design — §7); snapshots verified.
- **Token:** rotated 2026-11-17; live value in `.env` (`SEEKER_API_TOKEN`).
- **Tailnet housekeeping:** two dead nodes (`search-engine`, `search-engine-1`) remain
  in the Tailscale admin console to delete manually.
- **Not built yet:** Office add-in (Phase 5), OS-native search hooks (Phase 6), OCR,
  office-document extraction, per-source exclude rules.

---

## 12. FAQ

**Why do I get gsmhub results when I search from Google Docs?**
Because gsmhub was the only source then — four are indexed now, and results come from
all of them (click a chip to filter by source, or add more folders per §5). The overlay
never looks at the page you're on — it searches your index from wherever you are.

**Is my data sent anywhere?**
No. See §8.

**Why not Ctrl+Alt+S for the overlay?**
Chromium rejects Ctrl+Alt shortcuts at load time (they collide with AltGr character
input). `Alt+Shift+S` is the chosen binding; rebind freely.

**Can I index the same folder from two sources?**
Technically yes, but you'd get duplicate results. One source per folder.

**What happens if I delete a file?**
It stays in the index until the next sync of its source, which prunes it
(`"pruned"` in the sync stats).

**How do I search from another machine?**
Install the extension there (§4.2), put that machine on your tailnet, and set the
engine URL to `https://search-engine-2.taile24e8b.ts.net`. The token is the same.

**The engine URL field — which one do I use where?**
Host apps and browsers: `http://127.0.0.1:8420`. Anything on the tailnet (phone):
`https://search-engine-2.taile24e8b.ts.net`.

*File locations: live deployment + compose + .env → `/home/recoding/seeker` · index data
→ `/home/recoding/seeker/data/seeker.db` · engine source → `/home/recoding/seeker/engine`
(in the worktree during phase work: `.worktrees/<phase>/`) · extension → `extension/` ·
mobile app → `mobile/` · project docs → `docs/` (build docs, handover docs, ADRs).*
