# Seeker — Coding Agent Rules

These are the standing rules every Seeker coding session works under. Read them before every
session. Breakage is reported to the user as a process deviation.

---

Give the following to any coding agent as **standing rules**.

1. **Work one phase at a time.** Begin with the phase verification step
   ([`09-roadmap.md`](09-roadmap.md)). Do not start a later phase until the current phase exit
   criteria pass.
2. **The engine never knows the client.** Every client is a thin shell around the same
   REST/MCP surface. No client-specific logic in the engine; no second implementation in an
   adapter.
3. **The MCP layer is a translation shim, not a second implementation.** Each tool calls the
   same implementation the matching REST route calls (in the engine: the shared `Engine`
   methods — clarified 2026-10-30; see handover `02`'s departure record). Business logic
   never lives in the MCP layer.
4. **`content_hash` gates re-embedding.** Never re-embed an unchanged file. A sync that
   re-embeds everything is a bug.
5. **Store `embedding_model` on every chunk.** A model switch without re-embedding is data
   corruption; the per-chunk model field is what makes re-embedding safe.
6. **Never expose the engine publicly.** Tailscale-only reachability. Bearer token on every
   client-engine call.
7. **Source mounts are read-only.** The engine reads indexed locations, never writes to them.
8. **Same embedding model for indexing and querying.** Mixing models silently is a quality
   bug that looks like a relevance bug.
9. **Re-run the eval set on any change to chunking, embedding, or the query pipeline.** A
   change that lowers recall@5 does not ship.
10. **Write tests first for the chunking and query pipeline.** Add a test for every bug fix.
11. **Do not log secrets or document content.** Snippets in logs are personal data.
12. **Do not add a connector outside the initial scope** (filesystem at launch) without an ADR.
13. **Record non-trivial decisions as ADRs** in `docs/adr/`.
14. **At the end of each phase,** report: deliverables done, tests added and passing, known
    gaps, and any deviations from this spec.
15. **One branch per phase.** Phase work happens only on that phase's own branch
    (`phase_<n>_<name>`); `master` is the integration target a phase's branch merges into
    when its exit criteria pass, never the place where in-progress phase work lands. Check
    `git branch --show-current` before starting phase work and switch to the phase's branch
    first. (Added 2026-10-30, after phase-1 work landed on `master` instead — see handover
    `01`'s phase board.)