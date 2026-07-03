# Doc Bloat Audit Report

## Summary

Detected 4 bloat findings across the fixture docs. Main issues: a verbose retry-behavior section condensable to one line, duplicate setup documentation, a misplaced timeout gotcha, and two planning artifacts (one ready to distill, one pending implementation).

## Records

```json
{
  "records": [
    {
      "id": "B1",
      "doc": "README.md",
      "location": "README.md:30",
      "verdict": "CONDENSE",
      "evidence": "README.md:30-38 — nine lines of narrative carry one fact: retries are automatic, capped, then raise AlertFailed",
      "proposal": "Failed sends retry up to `MAX_RETRIES` (3) times, then raise `AlertFailed` (`src/notify.py:3`).",
      "status": null,
      "payload": null
    },
    {
      "id": "B2",
      "doc": "SETUP.md",
      "location": null,
      "verdict": "MERGE-DOC",
      "evidence": "SETUP.md:3-9 duplicates README.md:8-14 near-verbatim (same `pip install -e .` block, same 'No environment variables are required' line); no standalone reason for two setup docs",
      "proposal": { "target": "README.md" },
      "status": null,
      "payload": null
    },
    {
      "id": "B3",
      "doc": "README.md",
      "location": "README.md:40",
      "verdict": "EXTRACT-AND-MOVE",
      "evidence": "README.md:40-43 — 'One quirk worth knowing about: alerts can silently drop if TIMEOUT_S exceeds the receiving channel's flush interval...' is an operational implementation detail, not a user-level usage pattern; belongs in CLAUDE.md",
      "proposal": { "target": "CLAUDE.md", "text": "Alerts may silently drop if `TIMEOUT_S` (10s) exceeds the receiving channel's flush interval, since buffered messages are discarded before flushing if a new send attempt starts writing." },
      "status": null,
      "payload": null
    },
    {
      "id": "B4",
      "doc": "docs/plans/2026-01-10-notify-retry-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "implementation landed: src/notify.py:3 `MAX_RETRIES = 3`, src/notify.py:4 `TIMEOUT_S = 10`, src/notify.py:7 `send_alert` match the design; Problem/Options/Sketch are superseded scaffolding",
      "proposal": null,
      "status": "ready",
      "payload": {
        "claims": [
          {
            "claim": "Retries are capped at 3 attempts (fixed count, not exponential backoff) before raising `AlertFailed`.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:3 `MAX_RETRIES = 3`"
          },
          {
            "claim": "Each attempt has a 10-second timeout, giving slow channels headroom without hanging the retry loop.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:4 `TIMEOUT_S = 10`"
          }
        ],
        "decision_entry": "## 2026-01-10 — send_alert retry policy\n- Decided: fixed retry cap of 3 attempts, 10s timeout per attempt (Option A: fixed count, no backoff).\n- Still binds: upgrade to backoff only if a channel shows retry storms in practice.\n- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S).\n- Source: docs/plans/2026-01-10-notify-retry-design.md (retired in this distillation)."
      }
    },
    {
      "id": "B5",
      "doc": "docs/plans/2026-07-01-batching-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "no implementation: `grep -rn 'send_batch' src/` returns nothing; only src/notify.py exists, and it does not contain send_batch — design describes unbuilt code",
      "proposal": null,
      "status": "pending-implementation",
      "payload": null
    }
  ],
  "summary": {
    "cut": 0,
    "condense": 1,
    "extract_and_move": 1,
    "retire_doc": 0,
    "merge_doc": 1,
    "distill": 2
  }
}
```

## Validator Output

OK: 5 record(s) valid
summary: {"cut": 0, "condense": 1, "extract_and_move": 1, "retire_doc": 0, "merge_doc": 1, "distill": 2}
