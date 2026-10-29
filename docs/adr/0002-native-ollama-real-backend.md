# ADR-0002: Native Ollama as the real model endpoint

Date: 2026-10-29
Status: Accepted
Decides: open decision 9 (real embedding backend — native Ollama vs Docker
sidecar vs hosted router), building on ADR-0001's mechanism.

## Context

ADR-0001 settled *how* model calls are made (one OpenAI-compatible wire
contract, backends chosen by config) but left *which* endpoint open. Ollama is
now installed natively on this machine (binary at `/usr/local/bin/ollama`,
server v0.40.13 on `:11434`, verified 2026-10-29). The user chose the native
install over a Docker sidecar and supplied two models:

- `qwen2.5-coder:7b` (4.7 GB) — a chat/code LLM. **Not usable for embeddings**:
  it serves `/v1/chat/completions` only.
- `nomic-embed-text` (274 MB, pulled 2026-10-29, per user's choice) — serves
  `/v1/embeddings`, **768 dimensions measured**, which matches the engine's
  default `SEEKER_EMBEDDING_DIMENSIONS=768`.

## Decision

- **Endpoint**: native Ollama at `http://localhost:11434` — the OpenAI-compatible
  routes (`/v1/embeddings`, `/v1/chat/completions`) through the existing
  ADR-0001 backends. No Docker sidecar in Phase 1.
- **Embedding model**: `nomic-embed-text` (768-dim). Chunks are tagged
  `embedding_model: "nomic-embed-text"`; the same-model rule applies as before.
- **LLM**: `qwen2.5-coder:7b`, wired via config (`SEEKER_LLM_BACKEND=openai`,
  `SEEKER_LLM_MODEL=qwen2.5-coder:7b`, `SEEKER_LLM_BASE_URL=http://localhost:11434`),
  but
  **query rewriting stays off** (open decision 1 default) — no pipeline step
  calls it yet. The config is live so the rewrite step can be enabled by a
  code change later, not a backend change.
- **"Custom AIs"**: no new integration work — any other OpenAI-compatible
  provider (LM Studio, OpenRouter, Groq, vLLM, …) is a `SEEKER_*` env-var
  change per ADR-0001. This was already built; this ADR records that it is the
  supported story, verified against a second provider kind (local Ollama).

Verified end-to-end 2026-10-29 (engine on :8777, temp corpus of 3 files):
3 indexed / 0 failed via `/v1/sources/smoke/sync`; query "how do I keep my
bread culture alive" returned bread.txt top-1 (0.513) ahead of unrelated
chunks (0.364 / 0.336) — a keyword-free semantic match, so real retrieval
quality, not pipeline mechanics. 138 tests green on a recreated venv
(Python 3.14; the handover previously recorded 3.12).

## Consequences

- The eval set (open decision 10) can now run — it was blocked on mock vectors.
- `SEEKER_EMBEDDING_DIMENSIONS` must match the chosen model's native output
  (nomic-embed-text: 768 = the default). A different model (e.g. 1024-dim)
  needs the env var set before any index is built — the store enforces one
  dimensions value per file at open.
- Local processes only: Ollama and the engine are session-scoped when started
  ad hoc (`setsid nohup …`). A systemd user unit (or Phase 2's Compose stack)
  is the durable home; not yet set up.
- `SEEKER_API_TOKEN` remains the dev default `dev-insecure-token` — fine for
  local, must be set before any Phase 2 exposure (standing rule 5).
