# Output contract — worked example

Reference for `detecting-doc-drift`. The field set, enum rules, and validator step live in
SKILL.md; this file is the worked example. Emit one record per extracted claim. `fix` is
non-null only for `STALE`; `evidence` is mandatory for every verdict.

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
    "tier": 1,
    "verdict": "UNVERIFIABLE",
    "evidence": "no metric/threshold to check; worker body is an empty interval stub",
    "fix": null
  }
]
```

End the result with `summary: {verified: N, stale: N, unverifiable: N}`. Validate the whole
result through `scripts/validate-drift-output.py` before handoff (see SKILL.md step 4) —
passing `{"records": [...], "summary": {...}}` also checks the summary counts against the
records; passing a bare array recomputes the authoritative summary for you.
