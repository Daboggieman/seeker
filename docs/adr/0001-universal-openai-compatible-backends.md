# ADR-0001: Universal OpenAI-compatible backends for embeddings and LLM calls

Date: 2026-10-26
Status: Accepted
Decides: the shape of open decision 9's replacement path (embedding backend
mechanism); partially supersedes spec §3's "embedding model via Ollama" as the
*only* supported backend.

## Context

The spec names `nomic-embed-text` via Ollama as the embedding backend and a
local model via Ollama for optional query rewriting. Ollama is not installed
on this machine (verified 2026-10-24, open decision 9), and the user asked for
provision to use either a local runtime or a hosted router ("a universal setup
to accept any endpoint").

## Decision

All model calls go through one wire contract: the OpenAI-compatible HTTP API.

- `OpenAICompatibleEmbeddingBackend` — `POST {base_url}/v1/embeddings`
- `OpenAICompatibleLLMBackend` — `POST {base_url}/v1/chat/completions`

Both take `base_url`, `api_key`, `model_name`. This one contract covers:

| Target | base_url |
|---|---|
| Ollama (native or sidecar) | `http://localhost:11434` |
| LM Studio | local port |
| OpenRouter, Groq, Together, vLLM, Cerebras | hosted router URL + key |

Backends are chosen by config (`SEEKER_*` env vars, `engine/src/seeker/config.py`),
built by factories (`engine/src/seeker/factories.py`); downstream code depends
only on the `EmbeddingBackend` / `LLMBackend` protocols. The mock backends
(`embedding_model: "mock"`, deterministic hashing vectors) remain the default so
the engine runs with zero setup and the tests need no network.

## Consequences

- Swapping mock → any real backend is a config change, not a code change.
- `embedding_model` is stored per chunk (data model invariant), so the stored
  name is whatever the config said — "mock", "nomic-embed-text", or a router's
  model id. The same-model rule (query embeddings must match chunk embeddings)
  is enforced by that field, not by the backend class.
- Bearer auth is always sent (`Authorization: Bearer ...`); local runtimes that
  ignore it get the placeholder `not-required`. No credentials ever leave engine
  config.
- Still open: *which* real endpoint the deployment uses (open decision 9 —
  native Ollama vs Docker sidecar vs router) and the eval-set source directory
  (open decision 10). The eval set cannot run on mock vectors.
