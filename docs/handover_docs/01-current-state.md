# Current state — 2026-10-24

> Initial setup. The Seeker project is in the **planning phase**: the build specification
> ([`../../semantic-search-build-docs.md`](../../semantic-search-build-docs.md)) is written,
> this handover package and the planning package ([`../build_docs/`](../build_docs/)) are set
> up, and no code exists yet. Phase 1 has not started.

The status board. Everything here is dated; if a claim is older than the work, distrust it and
re-measure.

## What is being worked on right now

**Pre-flight for Phase 1, 2026-10-24.** Environment verified: Python 3.12.3, Docker 29.9 +
Compose v5.6, Expo stack present. **Ollama is not installed on this machine** (no binary, no
service, nothing on `:11434`) — decided 2026-10-24 to build the engine against a **mock
embedding backend** and defer the real-backend decision (native install vs Docker sidecar) to
open decision 9 in
[`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md). The eval-set
source directory is also deferred — the user will point at one during Phase 1 (open decision
10). Repository layout was decided (D6 in
[`../build_docs/01-architecture-and-stack.md`](../build_docs/01-architecture-and-stack.md)):
`engine/` Python package at repo root, engine runs locally via uvicorn in Phase 1, Docker
enters only at Phase 2.

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 1 — Core engine + MCP server | in progress | chunker: 55 tests green | Mock embeddings; filesystem connector only; on branch `phase_1_core_engine` |
| 2 — Self-hosted deployment | not started | — | Docker Compose + Tailscale sidecar; see Linux `host-gateway` note in build docs 06 |
| 3 — Mobile client | not started | — | Expo, direct REST over Tailnet |
| 4 — Browser extension | not started | — | Manifest V3 |
| 5 — Office add-in | not started | — | Office.js task pane |
| 6 — OS-native hooks (optional) | not started | — | Only if still needed after Phase 5 |

Status is written here as the record of what happened, after it happened — never in advance.

## Open items

- **Real embedding backend decision** (open decision 9): native Ollama install vs Docker
  sidecar. The eval set cannot run on mock vectors — recall@5 on mock embeddings measures the
  pipeline, not retrieval quality.
- **Eval-set source directory** (open decision 10): user to supply; `~/Documents` is empty.
- The open decisions in [`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md)
  — query rewriting, reranker, vector-store migration threshold, debounce strategy, resource
  budget, email connector scope — default if not decided, but several are cheaper to decide
  during Phase 1 than after it.
- The user commits and pushes outside these sessions (standing constraint, see
  [`README.md`](README.md)).
