# Bloat Audit Results

## Summary

Full audit of the fixture's documentation found 4 findings:

**SETUP.md**
  [B1] RETIRE-DOC — duplicates README.md:6-14 (identical setup block and environment note); no unique content

**README.md**
  [B2] CONDENSE — README.md:28 — 11 lines on retry behavior condensable to one line citing src/notify.py:3-4

**docs/plans/2026-01-10-notify-retry-design.md**
  [B3] DISTILL(ready) — implementation landed (src/notify.py constants and docstring); extract retry behavior decision and constants to CLAUDE.md

**docs/plans/2026-07-01-batching-design.md**
  [B4] DISTILL(pending-implementation) — send_batch() design not yet implemented

## Structured Records

```json
{
  "records": [
    {
      "id": "B1",
      "doc": "SETUP.md",
      "location": null,
      "verdict": "RETIRE-DOC",
      "evidence": "SETUP.md:1-10 is a near-duplicate of README.md:6-14; both contain identical 'Clone the repo, then install the package in editable mode' setup block and 'No environment variables required' line. SETUP.md carries no unique content beyond what README.md includes.",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B2",
      "doc": "README.md",
      "location": "README.md:28",
      "verdict": "CONDENSE",
      "evidence": "README.md:28-38 — 11 lines carry one fact: on delivery failure, send_alert retries up to a fixed count before raising AlertFailed. The checkable details (count, timeout values) are constants in src/notify.py:3-4.",
      "proposal": "On delivery failure, `send_alert` automatically retries up to `MAX_RETRIES` (3) times before raising `AlertFailed` (`src/notify.py:3`).",
      "status": null,
      "payload": null
    },
    {
      "id": "B3",
      "doc": "docs/plans/2026-01-10-notify-retry-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "Implementation landed: src/notify.py:3 `MAX_RETRIES = 3`, src/notify.py:4 `TIMEOUT_S = 10`, src/notify.py:8 docstring 'retries...after MAX_RETRIES attempts' match the design. The Problem/Options/Sketch sections are now scaffolding; the core decisions (fixed-count retry with per-attempt timeout) are in the code.",
      "proposal": null,
      "status": "ready",
      "payload": {
        "claims": [
          {
            "claim": "Delivery failures trigger automatic retry: up to 3 attempts with 10-second timeout per attempt.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:3-4 MAX_RETRIES = 3, TIMEOUT_S = 10"
          },
          {
            "claim": "After MAX_RETRIES exhausted, send_alert raises AlertFailed.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:8 docstring 'raises AlertFailed'"
          }
        ],
        "decision_entry": "## 2026-01-10 — retry behavior for send_alert\n- Decided: automatic retries on delivery failure, fixed count (3 attempts), fixed timeout (10s per attempt); rejected exponential backoff (complexity disproportionate for small library).\n- Still binds: can upgrade to exponential backoff if retry storms appear in practice.\n- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert docstring).\n- Source: docs/plans/2026-01-10-notify-retry-design.md (distilled in this audit)."
      }
    },
    {
      "id": "B4",
      "doc": "docs/plans/2026-07-01-batching-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "No implementation: grep -n 'send_batch' src/notify.py returns nothing; send_batch helper described in the design does not exist in code.",
      "proposal": null,
      "status": "pending-implementation",
      "payload": null
    }
  ],
  "summary": {
    "cut": 0,
    "condense": 1,
    "extract_and_move": 0,
    "retire_doc": 1,
    "merge_doc": 0,
    "distill": 2
  }
}
```

## Validator Output

OK: 4 record(s) valid
summary: {"cut": 0, "condense": 1, "extract_and_move": 0, "retire_doc": 1, "merge_doc": 0, "distill": 2}
