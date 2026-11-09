# Seeker — Mobile Client Runbook

Operational companion to [`07-client-adapters.md`](07-client-adapters.md) (Phase 3 spec) and
[`09-roadmap.md`](09-roadmap.md) (exit criterion). Branch: `phase-3-mobile-client`.

> **Status (2026-11-05):** scaffold + plumbing + UI complete — Expo SDK 58 / RN 0.88 /
> TypeScript strict in `mobile/`; typed engine API client ([`engineApi.ts`]), keychain
> settings (expo-secure-store), search screen (bar → chips → results) + settings modal.
> 6/6 unit tests, tsc clean, Metro bundle verified.
>
> **2026-11-06: installable APK built via EAS** — profile `preview`, package
> `com.daboggieman.seeker`, version 1.0.0 (code 1), keystore held in EAS cloud
> (Build Credentials `5V9KI99OkL`). Verified: manifest + `assets/index.android.bundle`
> (Hermes) + `lib/arm64-v8a/*`. **Pending: the device test (exit criterion).**

## What it is

Thin shell over the REST API (standing rule 2 — the engine never knows the client):

- `POST /v1/search` — search bar, `top_k=20`, `filters.source_id` from the chips
- `GET /v1/sources` — filter chips + the settings "Test" probe (proves reachability
  **and** token in one call; `/v1/health` is anonymous and proves neither)
- `GET /v1/health` — unused by the app (kept for curl checks)
- Bearer token on every authed call; `X-Request-Id` echoed per request; errors surface
  the engine's `{code, message}` shape

Engine URL + token live in the device keychain (expo-secure-store) — the token is never
bundled into the app source. Rotate it (docs 06 / OD 8) and re-enter it in Settings.

## Install the APK (EAS build)

Built 2026-11-06, both builds finished (fingerprint `794b5dd4…`):
- https://expo.dev/accounts/daboggieman/projects/seeker/builds/27ca1a24-d48a-4e6a-b880-35472ecb75a1
- https://expo.dev/accounts/daboggieman/projects/seeker/builds/1f812021-6f6d-431f-96dc-6afb61272b32

(Identical artifacts; APK also in the host's `~/Downloads/` as
`application-27ca1a24-…apk`, 66.9 MB.) Rebuild after code changes:

```bash
cd /home/recoding/seeker/mobile
node --dns-result-order=ipv4first node_modules/eas-cli/bin/run \
  build -p android --profile preview --non-interactive --no-wait
```

**Always invoke eas via `node --dns-result-order=ipv4first` on this host** (not `npx
eas-cli`): the host's IPv6 is dead while api.expo.dev has AAAA records, and eas-cli's
node-fetch intermittently dials v6 first → `request to … failed, reason:` errors on
small calls. Separately, the host's uplink stalls on large requests (~100 KB+ bodies
ETIMEDOUT ~25-50% of the time, any HTTP stack), so **wrap every eas call in a retry
loop** — a run is **submitted** when it prints
`See logs: https://expo.dev/accounts/daboggieman/projects/seeker/builds/<id>`
(grep for `See logs`, not "queued"). Failed retries after the archive upload are
wasted ~10 s re-uploads, not queued builds. Watch progress:

```bash
node --dns-result-order=ipv4first node_modules/eas-cli/bin/run build:list
```

On the phone: open the build page → **Install** → allow "install unknown apps" for the
browser → open **Seeker**, then the first-run Settings flow below.

## Run it

Prerequisites on the phone: **Expo Go** (app store) and **Tailscale** logged into the
tailnet. The engine must be up on the host (`docker compose ps` in `/home/recoding/seeker`).

```bash
cd /home/recoding/seeker/mobile
npx expo start --tunnel   # dev-server over ngrok; API calls still go direct via Tailscale
```

Open the project in Expo Go (scan the QR). First run opens Settings:

1. Engine URL is prefilled with the deployed node (`http://search-engine-2.taile24e8b.ts.net:8420`)
2. Paste `SEEKER_API_TOKEN` (from the host's `/home/recoding/seeker/.env`)
3. **Test** → expect "✓ engine reachable — N sources" → **Save**

`--tunnel` is needed for Expo Go to load the JS bundle when the phone is off wifi; the
search traffic itself always goes direct over the Tailnet. On the same wifi, `--lan` is
faster. Note the API base URL is independent of how the bundle is served.

## Exit criterion

**Search works from the phone off wifi** (Tailscale on, wifi off, same query returns the
right files). This doubles as the Phase-2 exit criterion (same query from a second
Tailnet device — docs 12).

## Known gaps / notes

- Results are view-only: long-press shares the file path; opening indexed files on the
  phone is future scope.
- APK has no auto-update — rebuild + reinstall after changes (Expo Go remains the fast
  dev loop via `npx expo start --tunnel`).
- `SEEKER_API_TOKEN` is still `dev-insecure-token` on the deployment — rotate before
  daily use from the phone.
