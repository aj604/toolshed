# Doc bloat audit — fixture (full audit)

Scope: `tests/baselines/bloat-red/fixture/` treated as a standalone repo — `README.md`,
`CLAUDE.md`, `SETUP.md`, `docs/plans/2026-01-10-notify-retry-design.md`,
`docs/plans/2026-07-01-batching-design.md`, `src/notify.py`.

## Summary

README.md
  [B3] CUT         README.md:19 — "The `send_alert` function takes a channel and a message and delivers the message to that channel." restates the signature/docstring at src/notify.py:7-8
  [B4] CONDENSE    README.md:30 — 9 lines of retry narrative → one line citing `MAX_RETRIES` (src/notify.py:3)
  [B5] EXTRACT     README.md:40 — TIMEOUT_S/flush-interval drop quirk belongs in CLAUDE.md, not the user-facing README

SETUP.md
  [B2] RETIRE-DOC — duplicates README.md's Setup section near-verbatim; nothing unique to keep

docs/plans/2026-01-10-notify-retry-design.md
  [B1] DISTILL(ready) — implementation landed (src/notify.py: MAX_RETRIES=3, TIMEOUT_S=10); extract 2 claims to CLAUDE.md + a decision-log entry

docs/plans/2026-07-01-batching-design.md
  [B6] DISTILL(pending-implementation) — `send_batch` does not exist in src/; accurate about the future, nothing to extract yet

Six records: 1 CUT, 1 CONDENSE, 1 EXTRACT-AND-MOVE, 1 RETIRE-DOC, 0 MERGE-DOC, 2 DISTILL.
Not flagged: CLAUDE.md (4 lines, dense, no restatement — the natural landing spot for B1's
claims and B5's extraction, so it is a consolidation target, not bloat itself).

Awaiting approved IDs before any record is applied (this audit is read-only;
`fixing-doc-bloat` applies whatever subset is approved).

## Structured output

```json
{
  "records": [
    {
      "id": "B1",
      "doc": "docs/plans/2026-01-10-notify-retry-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "implementation landed: src/notify.py:3 `MAX_RETRIES = 3`, src/notify.py:4 `TIMEOUT_S = 10`, and the `send_alert` sketch (retry loop raising `AlertFailed` after MAX_RETRIES attempts) matches src/notify.py:7-9's docstring 'raises AlertFailed after MAX_RETRIES attempts'; Problem/Options/Sketch sections are superseded scaffolding",
      "proposal": null,
      "status": "ready",
      "payload": {
        "claims": [
          {
            "claim": "`send_alert` retries a fixed 3 times (`MAX_RETRIES`) with no backoff before raising `AlertFailed`.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:3 `MAX_RETRIES = 3`"
          },
          {
            "claim": "Each delivery attempt is bounded by a 10-second timeout (`TIMEOUT_S`); alerts can silently drop if `TIMEOUT_S` exceeds the receiving channel's flush interval.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:4 `TIMEOUT_S = 10`"
          }
        ],
        "decision_entry": "## 2026-01-10 — retry behavior for send_alert\n- Decided: fixed 3 retries, fixed (non-backoff) delay, 10s per-attempt timeout, built into `send_alert` itself; rejected exponential backoff with jitter (complexity disproportionate for a small internal library) and a caller-supplied retry policy object (pushes the decision back onto callers, expands public API for one hypothetical caller).\n- Still binds: revisit backoff only if a channel starts showing retry storms in practice.\n- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert).\n- Source: docs/plans/2026-01-10-notify-retry-design.md (retired in this distillation)."
      }
    },
    {
      "id": "B2",
      "doc": "SETUP.md",
      "location": null,
      "verdict": "RETIRE-DOC",
      "evidence": "SETUP.md:1-9 duplicates README.md:6-14 near-verbatim (identical 'Clone the repo, then install the package in editable mode:' + `pip install -e .` block + 'No environment variables are required to run the test suite locally.' line); SETUP.md carries no content README.md lacks",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B3",
      "doc": "README.md",
      "location": "README.md:19",
      "verdict": "CUT",
      "evidence": "README.md:19-20 'The `send_alert` function takes a channel and a message and delivers the message to that channel.' restates the signature and docstring at src/notify.py:7-8 (`def send_alert(channel, msg):` / 'Deliver msg to channel'), adding no information beyond the code shown two lines below it",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B4",
      "doc": "README.md",
      "location": "README.md:30",
      "verdict": "CONDENSE",
      "evidence": "README.md:30-38 — nine lines of narrative carry two checkable facts: delivery is retried a fixed number of times before giving up, and `send_alert` raises `AlertFailed` once attempts are exhausted",
      "proposal": "`send_alert` retries up to `MAX_RETRIES` (3) times on delivery failure before raising `AlertFailed` (`src/notify.py:3,8`).",
      "status": null,
      "payload": null
    },
    {
      "id": "B5",
      "doc": "README.md",
      "location": "README.md:40",
      "verdict": "EXTRACT-AND-MOVE",
      "evidence": "README.md:40-43 'One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S` exceeds the receiving channel's flush interval...' is an operational gotcha addressed to someone debugging delivery behavior, not a user-facing usage instruction; belongs in CLAUDE.md alongside the other operational facts about this module",
      "proposal": {
        "target": "CLAUDE.md",
        "text": "Alerts can silently drop if `TIMEOUT_S` (10s) exceeds the receiving channel's flush interval, since the channel may discard buffered messages not yet flushed when the next send attempt starts writing to it."
      },
      "status": null,
      "payload": null
    },
    {
      "id": "B6",
      "doc": "docs/plans/2026-07-01-batching-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "no implementation: `grep -rn 'send_batch' src/` returns nothing in src/notify.py, which only defines `send_alert`; the `send_batch` function the design describes does not exist yet",
      "proposal": null,
      "status": "pending-implementation",
      "payload": null
    }
  ],
  "summary": {
    "cut": 1,
    "condense": 1,
    "extract_and_move": 1,
    "retire_doc": 1,
    "merge_doc": 0,
    "distill": 2
  }
}
```

## Validator output

```
OK: 6 record(s) valid
summary: {"cut": 1, "condense": 1, "extract_and_move": 1, "retire_doc": 1, "merge_doc": 0, "distill": 2}
```
