# Current state — 2026-10-24

> Initial setup. The Seeker project is in the **planning phase**: the build specification
> ([`../../semantic-search-build-docs.md`](../../semantic-search-build-docs.md)) is written,
> this handover package and the planning package ([`../build_docs/`](../build_docs/)) are set
> up, and no code exists yet. Phase 1 has not started.

The status board. Everything here is dated; if a claim is older than the work, distrust it and
re-measure.

## What is being worked on right now

**Planning and setup, 2026-10-24.** The repository holds the technical build doc
(`semantic-search-build-docs.md` at the repo root) and the two planning packages. No engine
code, Docker config, or CI exist yet.

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 1 — Core engine + MCP server | not started | — | Filesystem connector only; eval set built here |
| 2 — Self-hosted deployment | not started | — | Docker Compose + Tailscale sidecar |
| 3 — Mobile client | not started | — | Expo, direct REST over Tailnet |
| 4 — Browser extension | not started | — | Manifest V3 |
| 5 — Office add-in | not started | — | Office.js task pane |
| 6 — OS-native hooks (optional) | not started | — | Only if still needed after Phase 5 |

Status is written here as the record of what happened, after it happened — never in advance.

## Open items

- The open decisions in [`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md)
  — query rewriting, reranker, vector-store migration threshold, debounce strategy, resource
  budget, email connector scope — default if not decided, but several are cheaper to decide
  during Phase 1 than after it.
- The eval set (~20 queries with known-correct documents) does not exist yet; building it is
  part of Phase 1, and its recall@5 baseline is recorded in
  [`06-testing-notes.md`](06-testing-notes.md) when it exists.
- The user commits and pushes outside these sessions (standing constraint, see
  [`README.md`](README.md)).
