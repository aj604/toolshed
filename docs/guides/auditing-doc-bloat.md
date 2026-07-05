# Auditing and fixing bloat with `detecting-doc-bloat` and `fixing-doc-bloat`

> As of 2026-07-05 (doc-lifecycle 0.6.2 @ e5201b8; `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md`, `fixing-doc-bloat/SKILL.md`)

**You should already have:** the plugin installed and [the principles](principles.md)
read — especially §3, because this loop *is* the propose → approve → apply contract.
This is the entry point for a repo whose docs exist but have grown heavy.

Bloat is **accurate content past its useful form** — nothing here is *wrong*, which is
why drift audits don't catch it. A line restating the code beside it, a paragraph
carrying one fact, two docs with the same setup block, a design doc whose decisions
already moved into the code: all of it costs a reader attention it doesn't repay.

## Step 1 — ask for the audit

> audit the docs for bloat

`detecting-doc-bloat` walks every passage of every doc in scope. It is **read-only**: it
will not fix "just the small one" — every finding becomes a record, and it stops.

## Step 2 — read the proposal

You get a human summary grouped by doc, one line per finding, backed by a structured
JSON report. This is the skill's own worked presentation example
(`detecting-doc-bloat/SKILL.md`, "Presenting to a human"):

```
README.md
  [B1] CONDENSE   README.md:22 — 7 lines of eviction narrative → one line citing CACHE_TTL_S (src/cache.py:5)
  [B2] EXTRACT    README.md:31 — cold-start latency gotcha belongs in RUNBOOK.md
docs/plans/2025-11-02-cache-layer-design.md
  [B3] DISTILL(ready) — implementation landed (src/cache.py); 2 claims (TTL=300s, LRU cap=1024) + 1 insight (no-invalidation rationale → docs/reference/caching.md) + log entry
```

Every record carries an **ID**, one of six verdicts, and **cited evidence** — the code
line it restates, the quoted overlap, the grep. "Feels redundant" is not admissible.
(In the underlying JSON, B2's verdict is `EXTRACT-AND-MOVE`; the one-line summary
abbreviates it.)

| Verdict | Means |
|---|---|
| `CUT` | the passage restates what the adjacent code already shows |
| `CONDENSE` | many lines, one checkable fact — the record includes the one-line replacement |
| `EXTRACT-AND-MOVE` | right content, wrong doc (an operator gotcha buried in a README) |
| `MERGE-DOC` / `RETIRE-DOC` | a doc is a near-duplicate of another — fold the remainder in, or delete it |
| `DISTILL` | a design doc whose implementation landed — its durable residue gets extracted, the scaffolding retired |

## Step 3 — approve by ID (this is the only mandate there is)

> apply B1 and B3

`fixing-doc-bloat` applies **exactly the approved records**. B2 above stays untouched —
even if it's obviously right, even if B1's edit lands one paragraph away. `CONDENSE`
replacement text lands byte-verbatim; nothing gets reworded, blended, or "rounded out."

Two special cases worth knowing before your first approval:

- **`DISTILL` (ready)** is the big one: the fixer dispatches the `doc-distiller` agent,
  which re-verifies each extracted claim against the code its evidence cites, lands each
  claim in its target living doc and each insight in its durable narrative doc, appends
  one entry to `docs/decisions.md`, and retires the artifact — staged as a single commit. Decisions
  survive; scaffolding goes to git history, where it still lives if you ever need it.
- **`DISTILL` (pending-implementation)** — a design doc for code that *hasn't* landed —
  is never actionable, even if you approve it. A pending design is accurate about the
  future; the record exists to say so, not to propose an edit.

## What this loop will never do

Edit without an approved ID, delete content a record didn't span, or treat its own
summary as authorization. If that discipline ever feels slow, it's the reason a bloat PR
is reviewable at all.

## Next

This repo runs the same sweep on itself weekly. When approving records feels routine,
[put it on a schedule](scheduling-doc-sync.md).
