# Bloat Audit Report

## Summary

The fixture contains four findings: one setup doc that duplicates content already in the primary README, one restated line in README, and two planning artifacts (one whose implementation has landed, one pending).

### By Document

**README.md**
- [B2] CUT — README.md:19 — function signature is self-documenting; restatement adds no value

**SETUP.md**
- [B1] RETIRE-DOC — entire doc duplicates README.md:6-13; no standalone value

**docs/plans/2026-01-10-notify-retry-design.md**
- [B3] DISTILL(ready) — implementation landed (src/notify.py); extract retry constants and log entry

**docs/plans/2026-07-01-batching-design.md**
- [B4] DISTILL(pending-implementation) — no code exists yet; design is accurate about the future

---

## Structured Records

```json
{
  "records": [
    {
      "id": "B1",
      "doc": "SETUP.md",
      "location": null,
      "verdict": "RETIRE-DOC",
      "evidence": "SETUP.md:1-10 is duplicated verbatim in README.md:6-13; no unique content — the setup instructions exist in the primary living doc (README) with fuller context (usage examples follow); SETUP.md adds no independent value",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B2",
      "doc": "README.md",
      "location": "README.md:19",
      "verdict": "CUT",
      "evidence": "README.md:19-20 restates what the function signature already shows: 'The `send_alert` function takes a channel and a message and delivers the message to that channel.' The signature `send_alert(channel, msg)` on line 23 is self-documenting; this restatement adds nothing",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B3",
      "doc": "docs/plans/2026-01-10-notify-retry-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "implementation landed: src/notify.py:3 `MAX_RETRIES = 3`, line 4 `TIMEOUT_S = 10`, and send_alert docstring on line 8 confirms retry behavior. The Sketch section (lines 44-55) describes the control flow that the code implements. Problem statement, Options, and Sketch sections are scaffolding — the implementation has superseded them",
      "proposal": null,
      "status": "ready",
      "payload": {
        "claims": [
          {
            "claim": "Retry logic is fixed: three attempts (`MAX_RETRIES`), ten seconds timeout per attempt (`TIMEOUT_S`), no backoff.",
            "target": "README.md",
            "evidence": "src/notify.py:3-4 `MAX_RETRIES = 3`, `TIMEOUT_S = 10`"
          },
          {
            "claim": "`send_alert` raises `AlertFailed` after exhausting all retry attempts, giving callers certainty about delivery status.",
            "target": "README.md",
            "evidence": "src/notify.py:8 docstring 'raises AlertFailed after MAX_RETRIES attempts'"
          }
        ],
        "decision_entry": "## 2026-01-10 — Retry behavior for `send_alert`\n- Decided: fixed three retries, ten-second timeout per attempt, no backoff. Simplicity wins for a library this small; can upgrade to exponential backoff if retry storms emerge in practice.\n- Still binds: if a channel shows pathological retry behavior, revisit backoff strategies, but only with measured data.\n- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert).\n- Source: docs/plans/2026-01-10-notify-retry-design.md (retired in this distillation)."
      }
    },
    {
      "id": "B4",
      "doc": "docs/plans/2026-07-01-batching-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "no implementation: `grep -rn 'send_batch\\|batch' src/notify.py` returns nothing; `send_batch(channel, msgs)` and batch delivery logic described in the proposal do not exist in the codebase — design describes unbuilt code",
      "proposal": null,
      "status": "pending-implementation",
      "payload": null
    }
  ],
  "summary": {
    "cut": 1,
    "condense": 0,
    "extract_and_move": 0,
    "retire_doc": 1,
    "merge_doc": 0,
    "distill": 2
  }
}
```

**Validator output:** `OK: 4 record(s) valid — summary: {"cut": 1, "condense": 0, "extract_and_move": 0, "retire_doc": 1, "merge_doc": 0, "distill": 2}`
