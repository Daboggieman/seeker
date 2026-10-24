# Seeker — Planning Package

This is the **plan**: what Seeker is meant to be, and the decisions that are locked. The running
record of what is actually built — current state, conventions in force, verified test results,
history — is a separate package in [`../handover_docs/`](../handover_docs/); start at
[`../handover_docs/README.md`](../handover_docs/README.md) before doing any work.

The source of record for everything here is
[`../../semantic-search-build-docs.md`](../../semantic-search-build-docs.md). These docs
restate it in build order and add nothing that contradicts it. If a claim here disagrees with
the spec, the spec wins and this file should be corrected.

Read in this order:

1. **00-overview.md** — the product in one page, the architectural stance, the core goal
2. **01-architecture-and-stack.md** — system diagram, module boundaries, tech stack
3. **02-data-model.md** — document, chunk, and source schemas
4. **03-api-design.md** — REST API endpoints and request/response shapes
5. **04-core-engine-specs.md** — connectors, chunking, embeddings, vector store, query pipeline
6. **05-mcp-server.md** — MCP tool definitions and wrapping strategy
7. **06-deployment.md** — Docker Compose, Tailscale private networking
8. **07-client-adapters.md** — client adapters by build phase (MCP, mobile, browser, Office)
9. **08-testing-and-validation.md** — eval set, recall tracking, CI gates
10. **09-roadmap.md** — phased milestones with exit criteria
11. **10-open-decisions.md** — open questions, defaults, and how to close them
12. **11-coding-agent-rules.md** — standing rules every coding session works under

## The one-paragraph summary

Seeker is a self-hosted semantic search engine over personal files — local disk, Drive, PDFs,
email — indexed once and queryable from any surface (desktop, mobile, VS Code, browser, Office).
The core engine is Python + FastAPI with `nomic-embed-text` via Ollama and `sqlite-vec` for
zero-ops vector storage, wrapped as an MCP server for Claude Desktop and VS Code. Everything
lives behind Tailscale so no port is exposed to the public internet. Build order: core engine
→ MCP validation → self-hosted deploy → mobile → browser extension → Office add-in.