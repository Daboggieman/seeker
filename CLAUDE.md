# Seeker — Rules for AI Assistants

## What this project is

Seeker is a self-hosted semantic search engine over personal files. The plan of record is
`semantic-search-build-docs.md` at the repo root, restated in build order in
[`docs/build_docs/`](docs/build_docs/) (start at its README). The running record of what is
actually built lives in [`docs/handover_docs/`](docs/handover_docs/) — start at its README and
`01-current-state.md` before doing any work.

## Standing rules

1. **Read the handover first.** `docs/handover_docs/01-current-state.md` is the resume point,
   and it lives only there.
2. **Work one phase at a time.** Do not start a phase before the previous phase exit criteria
   pass (see `docs/build_docs/09-roadmap.md`).
3. **The engine never knows the client.** One REST surface; MCP is a translation shim, not a
   second implementation.
4. **`content_hash` gates re-embedding; `embedding_model` is stored per chunk.** Never re-embed
   unchanged files; never mix embedding models between indexing and querying.
5. **Never expose the engine publicly** — Tailscale-only reachability, bearer-token auth on
   every call. Source mounts are read-only.
6. **Re-run the eval set** on any change to chunking, embedding, or the query pipeline. A
   change that lowers recall@5 does not ship.
7. **Do not commit unless asked.** The user commits and pushes outside these sessions.
8. **Record non-trivial decisions as ADRs** in `docs/adr/`; close open decisions in
   `docs/build_docs/10-open-decisions.md` when they are decided.
9. **Report, don't fix silently.** If you spot a bug in existing code, report it with a
   suggested fix approach and let the user decide.
10. **Do not install dependencies unless explicitly asked.**

## Docs maintenance

- Put new material in the document that owns the subject (see the handover README's table).
- Date every claim that could go stale; say whether a number was measured or expected.
- One fact, one home — link to the owner instead of restating it in a second file.
