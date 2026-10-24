# Seeker — Handover

The running handover for the Seeker build sessions. These documents are the record of what the
app *is* and *why*, distinct from [`../build_docs/`](../build_docs/) which holds what the app
is *meant* to be.

**Read [`01-current-state.md`](01-current-state.md) first.** It is the only document here that
dates quickly. Everything else is reference and stays true until the thing it describes
changes.

Last updated: **2026-10-24** — initial setup.

## The resume point

**It lives in [`01-current-state.md`](01-current-state.md), and only there.** Do not restate
it elsewhere — multiple copies diverge, and a stale copy is worse than no copy.

## Standing constraints

- **Do not create or amend commits unless the user asks.** That includes not staging, not
  tidying this index, and not committing "while you're in there". The user commits and pushes
  outside these sessions.
- **Physical device runs, Ollama model pulls, and production deployments remain the user's to
  run.** Report readiness; do not claim a gate passed without their evidence. Automated checks
  (`pytest -q`, `ruff`) are ours to run.
- **The spec is the source of truth.** If a claim in these docs disagrees with
  [`../../semantic-search-build-docs.md`](../../semantic-search-build-docs.md), the spec wins
  and this file should be corrected.
- **Work one phase at a time.** Never start a phase before the previous phase exit criteria
  pass — confirmed by running the verification step, not by assuming.
- **The eval set is the quality bar.** recall@5 on the eval set is recorded, not estimated.

## The documents

| File | What it holds | Read it when |
|---|---|---|
| [`01-current-state.md`](01-current-state.md) | Phase board, what is verified and when, open items | Always, first |
| [`02-engine-conventions.md`](02-engine-conventions.md) | Per-module conventions, the connector/pipeline/query chain, and the departure record | Before adding a connector or route |
| [`03-data-model-notes.md`](03-data-model-notes.md) | Decisions embedded in the schema, the content-hash gate, the embedding-model invariant | Changing the schema |
| [`04-module-reference.md`](04-module-reference.md) | Module surface: public interfaces of each component, cross-component calls | Changing a module's logic |
| [`05-architecture-decisions.md`](05-architecture-decisions.md) | Key decisions and why they were made | Questioning a dependency or an approach |
| [`06-testing-notes.md`](06-testing-notes.md) | Eval set construction, recall@5 record, test infrastructure decisions | Writing tests or tuning retrieval |
| [`07-security-notes.md`](07-security-notes.md) | Bearer token handling, credential storage at rest, the Tailscale-only posture | Implementing auth or adding a source |
| [`08-repo-structure-and-hygiene.md`](08-repo-structure-and-hygiene.md) | Repo hygiene, environment variables, the ADR process | Before git housekeeping |
| [`09-phase-acceptance.md`](09-phase-acceptance.md) | Phase-by-phase sign-off record | Closing a phase |

## Keeping it usable

- **Put new material in the document that owns the subject**, not at the top of `01`. `01` is a
  status board; if it grows past a screenful it is holding something that belongs elsewhere.
- **Date every claim** that could go stale, and say whether a number was *measured* or is
  *expected*. A recall@5 written without running the eval set becomes a stale claim.
- **When a decision is reversed, say so where the old one was written.** Several notes here
  exist only to stop a fixed thing being "fixed" again.
- **One fact, one home.** A status claim repeated in a second file is a claim that will
  disagree with itself. Link to the owner instead of restating it.
- **Write claims in the past tense about what happened, not the future tense about what will.**