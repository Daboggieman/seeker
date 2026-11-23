# ADR-0003: Browser extension architecture (Phase 4)

Date: 2026-11-12
Status: Accepted
Phase: 4 — browser extension (docs/build_docs/09-roadmap.md)

## Context

Phase 4 ships a way to search the engine from inside any web page — the exit
criterion is a working search overlay inside Google Docs (docs/build_docs/
07-client-adapters.md). The host machine runs Firefox only, so Firefox MV3 is
the load-unpacked target (superseded 2026-11-13: Brave is now installed on the host
and is the primary target — the Phase-4 exit was met in Brave; Firefox remains the
fallback); Chrome must keep working because the client's other
machines may use it.

Constraints that shaped the design:

- No build tooling may be required to load the extension (it must stay a
  "select the folder and go" affair, like the rest of this project's clients).
- The bearer token must not become readable by arbitrary web pages — the
  content script runs in every tab (`<all_urls>`).
- Rule 11 (docs/build_docs/11-coding-agent-rules.md): no secrets and no search
  content in logs.
- The engine contract is fixed by the mobile client (docs/build_docs/
  13-mobile-client.md): `POST /v1/search` with `{query, top_k, filters}`,
  `{"detail":{code,message}}` errors, `X-Request-Id` on every call.

## Decisions

### 1. MV3 with per-browser manifests + a classic background script via importScripts

Chromium hard-rejects a `background` dict that sets both `scripts` and
`service_worker`: `extensions/common/manifest_handlers/background_info.cc`
counts background "solutions" and fails on >1 (`kInvalidBackgroundCombination`).
Brave load-unpacked failed with exactly this right after a shortcut fix on
2026-11-13 — the dual-key single-manifest pattern is dead in Chrome-family
browsers. So there are two manifests sharing everything else:

- `manifest.json` — Chrome/Brave: `"background": {"service_worker": "background.js"}`
- `manifest-firefox.json` — Firefox: `"background": {"scripts": ["background.js"]}`

Both point at the SAME classic script, which starts with
`importScripts('lib/engine-api.js')` — valid in a Chrome service worker and a
Firefox event page alike. ES-module workers (`"type": "module"`) would need a
separate Firefox story or a bundler — neither is acceptable here.

Same class of constraint on commands: Chromium rejects `Ctrl+Alt+<key>`
suggested keys at manifest-parse time (AltGr aliasing; the loader failed with
"Invalid value for 'commands[1].default': Ctrl+Alt+S"), so the default is
`Alt+Shift+S` / `Command+Shift+S`.

### 2. Token lives only in the background worker; the page never sees it

- The token is stored in `chrome.storage.local` and read only by
  `background.js` (`getSettings()`).
- Content scripts never receive the token — they send `seeker:search` /
  `seeker:sources` / `seeker:probe` messages and get results back.
- The host page cannot read either: results render inside a **closed** shadow
  root (`attachShadow({mode:'closed'})`), so page JS cannot reach into the
  overlay DOM.

Residual trade-off: `chrome.storage.local` is plaintext inside the browser
profile — weaker than the mobile client's OS keychain (docs 13). Accepted:
anyone who can read the profile already has every cookie and saved password.
Rotation story is unchanged (rotate in the engine `.env`, re-paste in
options).

### 3. Overlay as a closed shadow DOM, no framework, no build step

`content.js` injects one host `<div>` and builds the entire overlay inside a
closed shadow root with inline styles. Zero cost until toggled
(`document_idle` + lazy DOM construction). No framework: the overlay is ~200
lines of strings and event listeners, and a bundler would break decision 1.
Plain JS with a UMD wrapper for `lib/engine-api.js` so the same file runs in
node tests (`require`) and in the worker (`importScripts`).

### 4. Trigger = `chrome.commands`, not page handlers

`Alt+Shift+S` / `Cmd+Shift+S` (rebindable at `about:addons` → gear →
"Manage Extension Shortcuts"). A browser-level shortcut fires reliably inside
Google Docs, where the page's own key handlers would fight an in-page
listener. `Ctrl+Alt+<key>` is deliberately avoided: Chromium rejects
`Ctrl+Alt` combinations at manifest-parse time (they alias AltGr text input on
Windows/Linux — the loader fails with "Invalid value for 'commands…'"). The toolbar button (manifest `action`) opens the options page —
clicking it is not a toggle.

### 5. `<all_urls>` content script

The spec (docs 07) wants Google Docs **and any browser-based PDF viewer**
without per-site integration, so the content script matches `<all_urls>` at
`document_idle` and does nothing until toggled. This is the standard
trade-off: one permission instead of a site list that always lags.

### 6. Options-page "Test" = authed `GET /v1/sources`

Same reasoning as the mobile client: one call proves reachability, TLS, DNS,
and token validity together ("✓ engine reachable — N source(s)").

## Testing

- `node --test extension/tests/engine-api.test.js` — 10 unit tests on the
  engine client (URL normalization, headers, request-id, error mapping,
  search body shape, source fetching).
- Real-engine contract round-trip (2026-11-12): search through
  `lib/engine-api.js` against `http://127.0.0.1:8420` returned 5 results in
  809 ms; a wrong token was correctly rejected `UNAUTHORIZED`. (The tailnet
  URL is not reachable from the host shell — the host is not a tailnet node —
  so loopback stands in for the wire check.)
- In-browser overlay behavior (the actual exit criterion: Google Docs) is a
  user-side test — docs/build_docs/14-browser-extension.md has the checklist.
