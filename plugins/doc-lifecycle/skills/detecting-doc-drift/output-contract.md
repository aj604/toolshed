# Output contract — worked example

Reference for `detecting-doc-drift`. The field set, enum rules, and validator step live in
SKILL.md; this file is the worked example. Emit one record per extracted claim. `fix` is
non-null only for `STALE`, and it is the complete replacement text for the line at
`location` — never an instruction like "change X to Y"; `evidence` is mandatory for every
verdict and is one line — pointer + fact, as every example below models. Narrative history
(prior PRs, how the drift arose) does not belong in `evidence`.

```json
[
  {
    "claim": "Worker only accepts state schema 2; stale migration exits 5",
    "location": "CLAUDE.md:24",
    "kind": "behavior",
    "tier": 2,
    "verdict": "STALE",
    "evidence": "services/worker/worker.js:17-19 — `if (schema !== 3) ... process.exit(4)`",
    "fix": "Worker only accepts state schema 3; stale migration exits 4"
  },
  {
    "claim": "Reset state = `make reset`",
    "location": "CLAUDE.md:18",
    "kind": "command",
    "tier": 1,
    "verdict": "STALE",
    "evidence": "Makefile has `clean:`, no `reset` target",
    "fix": "Reset state = `make clean`"
  },
  {
    "claim": "worker is reasonably fast and handles most workloads",
    "location": "CLAUDE.md:26",
    "kind": "value",
    "tier": 3,
    "verdict": "UNVERIFIABLE",
    "evidence": "no metric/threshold to check; worker body is an empty interval stub",
    "fix": null
  }
]
```

## The emitted artifact: records wrapped with a summary

The array above is the `records` payload. The canonical artifact automation consumes wraps it
with the `summary` so the whole thing is one parseable object:

```json
{
  "records": [ /* the records above */ ],
  "summary": { "verified": 0, "stale": 2, "unverifiable": 1 }
}
```

Validate the whole result through
`${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-drift/scripts/validate-drift-output.py` before
handoff (see SKILL.md step 4) — passing the wrapped `{"records": [...], "summary": {...}}`
object also checks the summary counts against the records; passing a bare array recomputes
the authoritative summary for you.

**`location` must be a single `file:line`** (e.g. `CLAUDE.md:24`) — one line, numbered from 1,
no ranges. It is the only field the downstream `fixing-doc-drift` skill uses to place each
edit, so the validator rejects any other shape.
