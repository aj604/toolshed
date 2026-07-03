# Output contract — worked example

Reference for `detecting-doc-bloat`. The field set, enum rules, and validator step
live in SKILL.md; this file is the worked example. Emit one record per finding.
`evidence` is mandatory for every verdict; `proposal` is populated only for
`CONDENSE` / `EXTRACT-AND-MOVE` / `MERGE-DOC`; `status` and `payload` are populated
only for `DISTILL`. Every `proposal`/`payload` text meets the writing-docs bar.

The four records below cover the shapes that trip agents up: a `CONDENSE` with
complete replacement text, a `MERGE-DOC` naming the survivor, a `DISTILL ready`
whose implementation has landed (payload with two code-verified claims and a
decision-log entry), and a `DISTILL pending-implementation` whose code does not
exist yet (null payload — the trap: no claims may be extracted). **This is an
example of record shape, not an inventory of findings** — it shows four of the six
verdicts against one invented repo (a small caching library); your audit sweeps
for all six.

```json
[
  {
    "id": "B1",
    "doc": "README.md",
    "location": "README.md:22",
    "verdict": "CONDENSE",
    "evidence": "README.md:22-28 — seven lines of narrative carry one fact: entries expire after a TTL and are evicted LRU past a cap",
    "proposal": "Cache entries expire after `CACHE_TTL_S` (300s); beyond `MAX_ENTRIES` (1024) the least-recently-used entry is evicted (`src/cache.py:5-6`).",
    "status": null,
    "payload": null
  },
  {
    "id": "B2",
    "doc": "INSTALL.md",
    "location": null,
    "verdict": "MERGE-DOC",
    "evidence": "INSTALL.md:1-11 duplicates README.md:5-15 near-verbatim (same `pip install -e .` block, same 'requires Redis 7+ for the shared backend tests' line); no standalone reason for two install docs",
    "proposal": { "target": "README.md" },
    "status": null,
    "payload": null
  },
  {
    "id": "B3",
    "doc": "docs/plans/2025-11-02-cache-layer-design.md",
    "location": null,
    "verdict": "DISTILL",
    "evidence": "implementation landed: src/cache.py:5 `CACHE_TTL_S = 300`, cache.py:6 `MAX_ENTRIES = 1024`, cache.py:14 `get_or_fill` match the design; Problem/Options/Sketch sections are superseded scaffolding",
    "proposal": null,
    "status": "ready",
    "payload": {
      "claims": [
        {
          "claim": "Cache entries live 300 seconds (`CACHE_TTL_S`); staleness is bounded by TTL, not invalidation.",
          "target": "RUNBOOK.md",
          "evidence": "src/cache.py:5 `CACHE_TTL_S = 300`"
        },
        {
          "claim": "The cache is capped at 1024 entries (`MAX_ENTRIES`) with LRU eviction — an in-process cache, deliberately not Redis-backed.",
          "target": "RUNBOOK.md",
          "evidence": "src/cache.py:6 `MAX_ENTRIES = 1024`"
        }
      ],
      "decision_entry": "## 2025-11-02 — cache layer\n- Decided: in-process LRU cache, fixed TTL 300s, cap 1024 entries; rejected Redis-backed shared cache (operational overhead disproportionate for single-node deploys).\n- Still binds: revisit a shared cache only if cross-worker hit-rate becomes a measured bottleneck.\n- Code: src/cache.py (CACHE_TTL_S, MAX_ENTRIES, get_or_fill).\n- Source: docs/plans/2025-11-02-cache-layer-design.md (retired in this distillation)."
    }
  },
  {
    "id": "B4",
    "doc": "docs/plans/2026-03-15-sharding-design.md",
    "location": null,
    "verdict": "DISTILL",
    "evidence": "no implementation: `grep -rn 'shard' src/` returns nothing; the `shard_key`/`ShardMap` symbols the design describes exist nowhere in the repo — design describes unbuilt code",
    "proposal": null,
    "status": "pending-implementation",
    "payload": null
  }
]
```

Note the two `DISTILL` records side by side: `B3`'s code exists, so it is `ready`
and carries the full payload (claims each verified against the `src/cache.py` line
their `evidence` cites, plus a `decision_entry`); `B4`'s code does not exist, so it
is `pending-implementation` with **`payload: null`** — no landed code means no
claims to extract. Assigning `B4` a `ready` status or any payload is a contract
violation the validator rejects.

## The emitted artifact: records wrapped with a summary

The array above is the `records` payload. The canonical artifact automation
consumes wraps it with the per-verdict `summary` so the whole thing is one
parseable object:

```json
{
  "records": [ /* the records above */ ],
  "summary": {
    "cut": 0,
    "condense": 1,
    "extract_and_move": 0,
    "retire_doc": 0,
    "merge_doc": 1,
    "distill": 2
  }
}
```

A zero in the summary (here `cut: 0`) means the sweep for that verdict class ran
and found nothing — not that the class was skipped. Validate the whole result
through
`${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
before handoff (see SKILL.md step 4) — passing the wrapped
`{"records": [...], "summary": {...}}` object also checks the summary counts
against the records; passing a bare array recomputes the authoritative summary for
you. On the four-record array above the validator prints `OK: 4 record(s) valid`.

**`location` is `file:line` for passage verdicts** (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`)
— one line, numbered from 1, no ranges, the first line of the passage — and
**`null` for doc-level verdicts** (`RETIRE-DOC`/`MERGE-DOC`/`DISTILL`), which act
on a whole doc, not a line. A passage verdict's `evidence` **opens with the
passage's full extent** — `file:start-end`, or `file:start` for a one-line
passage, with `file:start` equal to `location` (B1 above: location
`README.md:22`, evidence opening `README.md:22-28`). That span is normative: the
downstream `fixing-doc-bloat` skill edits exactly the passage the span delimits,
anchored at `location`, and uses `proposal`/`payload` to carry the doc-level
verdicts. The validator rejects passage evidence that does not open with a span
matching `location`.
