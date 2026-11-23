# 14 — Browser extension (Phase 4)

Status: **exit criterion MET 2026-11-13** (user's own Brave session: overlay inside
Google Docs; engine log `POST /v1/search HTTP/1.1" 200` from the docker gateway
172.19.0.1)
Branch: `phase-4-browser-extension` (worktree `.worktrees/phase-4-ext/`)
Architecture decisions: [ADR-0003](../adr/0003-browser-extension-architecture.md)

## What this is

A MV3 browser extension that puts a Seeker search overlay on any page
(`Alt+Shift+S`), so you can search indexed files without leaving the tab —
Google Docs, web PDF viewers, anything. The background worker holds the
bearer token and does every engine call; the page and content script never
see the token, and results live in a closed shadow DOM the page can't read.

```
extension/
├── manifest.json          MV3 — Chrome/Brave (service_worker background)
├── manifest-firefox.json  MV3 — Firefox (event-page background)
├── background.js          token + all engine calls (importScripts classic script)
├── content.js             overlay: closed shadow DOM, chips, results, Esc/scrim close
├── lib/engine-api.js      UMD engine client (same file: node tests + worker)
├── options.html/.js       engine URL + token settings, "Test" probe
└── tests/engine-api.test.js   node:test unit tests (10)
```

## Install (Brave / Chrome — primary browser)

Manifests are split per browser: Chromium rejects a `background` that sets
both keys (ADR-0003 §1) — `manifest.json` is the Chrome-family one.

1. Address bar: `brave://extensions` → toggle **Developer mode** (top-right)
   → **Load unpacked** → select the `extension/` folder. A visible symlink
   lives at `~/Downloads/seeker-extension` (the worktree path is a hidden
   dot-folder).
2. Click the **Seeker toolbar icon** (puzzle piece → pin) → it opens Options
   → paste the bearer token (engine URL prefilled with the tailnet endpoint)
   → **Save** → **Test** → expect `✓ engine reachable — N source(s)`
3. Google Docs → press `Alt+Shift+S` → overlay appears → type, Enter.

**Shortcut conflict:** `brave://extensions/shortcuts` → rebind toggle-seeker.

## Install (Firefox — temporary load)

1. Open `about:debugging#/runtime/this-firefox`
2. **Load Temporary Add-on…** → pick `extension/manifest-firefox.json`
   (the file itself — Firefox wants the manifest, not the folder)
3. Toolbar puzzle-piece icon → Seeker → gear/⚙ → **Options** (or click the
   Seeker toolbar button — it opens settings)
4. Paste the bearer token → **Save** → **Test** → expect
   `✓ engine reachable — N source(s)`
5. Go to Google Docs, press `Alt+Shift+S` → overlay appears → type, Enter.

Temporary means it unloads when Firefox closes — reload the same way next
session. If it becomes daily-use, decide on signing (AMO unlisted) — open
decision, not blocking.

**Shortcut conflict:** if `Alt+Shift+S` is already taken, `about:addons` →
gear icon → *Manage Extension Shortcuts* → rebind.

## Run the tests

```bash
node --test extension/tests/engine-api.test.js   # 10 tests
```

The engine client was also round-tripped against the live engine
(2026-11-12, loopback): search → 5 results · 809 ms; wrong token →
`UNAUTHORIZED`.

## Exit criterion (Phase 4)

- [x] Overlay opened inside Google Docs in Brave (`Alt+Shift+S`), query returned
      results, click copied the path, Esc closed — 2026-11-13.
- [x] Engine log shows `POST /v1/search HTTP/1.1" 200` from 172.19.0.1
      (docker gateway) during that session.

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| Options **Test** → `NETWORK_ERROR` | Tunnel or serve down — check the mobile app still searches (docs 13); engine endpoint must be `https://search-engine-2.taile24e8b.ts.net` |
| Test → `UNAUTHORIZED` | Token wrong/rotated — re-paste from engine `.env` (`SEEKER_API_TOKEN`) |
| `Alt+Shift+S` does nothing on a page | Page may block content scripts (`chrome://`, addons.mozilla.org) — try a normal page |
| Overlay opens but no source chips | Sources fetch failed — hit Test in options; chips fall back to "All" |
| Firefox loads but the overlay can't search (no background) | You picked `manifest.json` (the Chrome one) — Firefox ignores `service_worker`; reload `manifest-firefox.json` |
| Brave refuses to load the manifest | Make sure you selected the `extension/` folder (Chrome manifest is `manifest.json`); paste the exact loader error |
