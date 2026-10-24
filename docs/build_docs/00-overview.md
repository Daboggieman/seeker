# Seeker — Overview

Source of record: spec §1 (Overview & Goals).

## What Seeker is

**Problem:** keyword search across scattered personal files fails when you do not remember exact
filenames or terms. Retrieval should work off *meaning*, not string matching.

Seeker is a self-hosted semantic search engine. One engine, indexed once, queryable from any
surface. It runs on your own hardware, behind your own Tailscale network, so nothing is exposed
to the public internet. Build the engine first and validate quality over MCP before investing
in polished client UIs.

## The core goal

Answer vague queries against personal documents:

> "budget disagreement doc from march"
> → "Q1 Marketing Spend.xlsx", snippet about the ad spend line item dispute, score 0.83

The engine knows nothing about which adapter is calling it. Every client is a thin shell around
the same REST/MCP surface.

## Build-order rationale

1. **Core engine** — the foundation; nothing works without it.
2. **MCP wrapper** — validates retrieval quality on real queries with zero custom UI work.
3. **Self-hosted deployment** — same query from any device on the Tailnet.
4. **Mobile app** — Expo, works off-wifi via Tailscale.
5. **Browser extension** — search inside Google Docs and browser PDFs.
6. **Office add-in** — Word/Excel/PowerPoint task pane.
7. **OS-native hooks** (optional) — Spotlight / Windows Search integration later.

Do not start a later phase before the previous phase exit criteria pass.