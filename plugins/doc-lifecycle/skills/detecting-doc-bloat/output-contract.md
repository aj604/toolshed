# Output contract v2 — field rules + worked example

Reference for `detecting-doc-bloat`. This file is the contract's one home: the
field table, a worked example, and the chunk-result seam shape. Validate every
artifact with `scripts/validate-bloat-output.py` before any handoff.

## Record fields

Each record uses exactly these eight fields (no extras — `payload` no longer
exists; the doc-distiller authors distillation content post-approval):
`id`, `doc`, `location`, `verdict`, `evidence`, `proposal`, `status`, `files`.
Approval is **by `id`** — the human returns a subset of IDs and
`fixing-doc-bloat` applies exactly those.

| Field | Rule |
|---|---|
| `id` | non-empty string, unique within the report (e.g. `"B1"`) — approval is by ID |
| `doc` | path of the judged doc; for `POLICY`, the covered directory. Non-empty string |
| `location` | passage verdicts (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`): `file:line`, single line, no ranges — the **first line of the passage** (its anchor; the full extent opens `evidence`). Doc-level verdicts (`RETIRE-DOC`/`MERGE-DOC`/`DISTILL`/`POLICY`): must be `null` |
| `verdict` | one of `CUT` / `CONDENSE` / `EXTRACT-AND-MOVE` / `RETIRE-DOC` / `MERGE-DOC` / `DISTILL` / `POLICY` — literal enum, no invented values |
| `evidence` | mandatory non-empty string for **every** verdict. Passage verdicts: must **open with the passage's full extent** — `file:start-end` (`file:start` if one line), where `file:start` equals `location` — then the proof. The span is normative: it is what `fixing-doc-bloat` deletes or replaces. `DISTILL`: the landed-code proof (or the grep-returns-nothing proof) plus at most brief classification framing — never the doc's substance (no claims, insights, or decision content) |
| `proposal` | `CONDENSE`: non-empty string, the complete replacement line. `EXTRACT-AND-MOVE`: `{"target": <doc>, "text": <text to land>}`, both non-empty. `MERGE-DOC`: `{"target": <survivor doc>}`. `POLICY`: non-empty string, the policy text. All others (`CUT`/`RETIRE-DOC`/`DISTILL`): `null` |
| `status` | `DISTILL` only: `"pending-implementation"` or `"ready"`. All other verdicts: `null` |
| `files` | `POLICY` only: non-empty array enumerating **every covered path** (provenance — a bulk record that cannot name its files is unfalsifiable; in a chunked run this is the manifest chunk's file list, verbatim). All other verdicts: `null` |

## Worked example

Five records covering the shapes that trip agents up. **This is an example of
record shape, not an inventory of findings** — these records are from an
invented repo (a small caching library plus an ephemeral-artifact swarm); your
audit sweeps for all seven verdicts.

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
    "files": null
  },
  {
    "id": "B2",
    "doc": "INSTALL.md",
    "location": null,
    "verdict": "MERGE-DOC",
    "evidence": "INSTALL.md:1-11 duplicates README.md:5-15 near-verbatim (same `pip install -e .` block, same 'requires Redis 7+ for the shared backend tests' line); no standalone reason for two install docs",
    "proposal": { "target": "README.md" },
    "status": null,
    "files": null
  },
  {
    "id": "B3",
    "doc": "docs/plans/2025-11-02-cache-layer-design.md",
    "location": null,
    "verdict": "DISTILL",
    "evidence": "implementation landed: src/cache.py:5 `CACHE_TTL_S = 300`, cache.py:6 `MAX_ENTRIES = 1024`, cache.py:14 `get_or_fill` match the design; Problem/Sketch sections are superseded scaffolding",
    "proposal": null,
    "status": "ready",
    "files": null
  },
  {
    "id": "B4",
    "doc": "docs/plans/2026-03-15-sharding-design.md",
    "location": null,
    "verdict": "DISTILL",
    "evidence": "no implementation: `grep -rn 'shard' src/` returns nothing; the `shard_key`/`ShardMap` symbols the design describes exist nowhere in the repo — design describes unbuilt code",
    "proposal": null,
    "status": "pending-implementation",
    "files": null
  },
  {
    "id": "B5",
    "doc": "docs/superpowers",
    "location": null,
    "verdict": "POLICY",
    "evidence": "2 dated plan/spec artifacts, both for work already merged (git log confirms); one class of ephemeral process artifact, not 2 findings",
    "proposal": "Ephemeral process artifacts; retire after the work merges.",
    "status": null,
    "files": [
      "docs/superpowers/plans/2026-06-01-batching-plan.md",
      "docs/superpowers/specs/2026-06-01-batching-spec.md"
    ]
  }
]
```

B3 (`ready`) carries **no payload of any kind**: the claims, insights, and
decision entry for an approved distillation are authored by the
`doc-distiller` agent **after a human approves this ID** — never at detect
time, and never smuggled into `evidence` (its `evidence` is the landed-code
proof, full stop). B4 (`pending-implementation`) exists to *say* the design is
pending — never propose deleting it. B5's `files` must name every covered path;
in a chunked run it is the dispatched chunk's list verbatim.

## The emitted artifact: a schema-2 wrapped report

```json
{
  "schema": 2,
  "records": [ /* the records above */ ],
  "summary": {
    "cut": 0,
    "condense": 1,
    "extract_and_move": 0,
    "retire_doc": 0,
    "merge_doc": 1,
    "distill": 2,
    "policy": 1
  }
}
```

`"schema": 2` is mandatory — the validator rejects a bare array or an
unversioned wrapper with a single "regenerate with the current skill" error.
A zero in the summary means the sweep for that verdict class ran and found
nothing — not that the class was skipped. On success the validator prints the
authoritative summary recomputed from the records.

## Chunk results (the seam artifact)

A chunk executor (interactive dispatch or the headless workflow matrix) never
emits the wrapped report. It emits exactly:

```json
{"chunk": "<dispatched chunk id>", "records": [ /* v2 records */ ]}
```

Rules the seam validator enforces (`--chunk <file> --manifest <manifest>`):

- A **sweep** chunk's records may only name docs in that chunk's slice, and a
  sweep chunk never emits `POLICY`.
- A **policy** chunk's result is exactly one `POLICY` record: `doc` = the
  chunk's `dir`, `files` = the chunk's file list verbatim. Never a
  file-by-file walk.
- Empty `records` is valid — a clean chunk says so.

Assembly (`--assemble <dir> --manifest <manifest> --out bloat-report.json`)
seam-validates every chunk, renumbers ids `B1..Bn`, and writes the wrapped
schema-2 report. Missing chunks fail the assembly by name, unless
`--allow-partial` (what CI passes): then they are skipped **loudly** — each
lands in the report's optional `unswept` list (`[{"chunk": id, "docs":
[paths]}]`, rendered as a PR-body banner), and the next run's
content-addressed resume sweeps exactly them. An invalid chunk always fails.
