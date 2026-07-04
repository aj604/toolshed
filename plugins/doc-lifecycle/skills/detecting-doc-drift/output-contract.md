# Output contract — worked example

Reference for `detecting-doc-drift`; the field set, enum rules, and validator step live in
SKILL.md — this file is the worked example only.

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

Validate before handoff — see SKILL.md step 4 for the command and rules.

`location` is the only field `fixing-doc-drift` uses to place an edit (see SKILL.md for the field's shape).
