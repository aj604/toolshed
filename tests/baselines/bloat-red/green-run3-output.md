# Bloat Audit Report

## Summary

Five findings across the fixture repo: one redundant doc (SETUP.md duplicates README's setup section), one narrative condensable to a single line (retry behavior description), one operational gotcha misplaced in user docs, and two design docs — one landed (retry design, ready to distill) and one pending implementation (batching design).

## Findings by document

**SETUP.md**
  [B1] RETIRE-DOC — duplicates README.md:6-14 entirely; no unique content

**README.md**
  [B2] CONDENSE — README.md:28 — seven lines on retry behavior → one line citing MAX_RETRIES
  [B3] EXTRACT-AND-MOVE — README.md:40 — timeout/flush-interval gotcha belongs in CLAUDE.md

**docs/plans/2026-01-10-notify-retry-design.md**
  [B4] DISTILL(ready) — implementation landed (src/notify.py:3-4); extract retry strategy + decision to distill

**docs/plans/2026-07-01-batching-design.md**
  [B5] DISTILL(pending-implementation) — no batching code in repo; design describes unbuilt feature

---

## Structured records (JSON)

```json
{
  "records": [
    {
      "id": "B1",
      "doc": "SETUP.md",
      "location": null,
      "verdict": "RETIRE-DOC",
      "evidence": "SETUP.md:1-9 and README.md:6-14 are identical — both contain 'Clone the repo, then install the package in editable mode: pip install -e .' and 'No environment variables are required to run the test suite locally.' SETUP.md adds no unique content; README.md is the primary user-facing doc and subsumes it.",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B2",
      "doc": "README.md",
      "location": "README.md:28",
      "verdict": "CONDENSE",
      "evidence": "README.md:28-38 — seven lines of narrative carry one checkable fact: the library retries with a fixed number of attempts (MAX_RETRIES, see src/notify.py:3) before raising AlertFailed. The paragraph restates this in multiple ways without adding new information.",
      "proposal": "Delivery failures are retried up to `MAX_RETRIES` (3) attempts; if all fail, `send_alert` raises `AlertFailed`.",
      "status": null,
      "payload": null
    },
    {
      "id": "B3",
      "doc": "README.md",
      "location": "README.md:40",
      "verdict": "EXTRACT-AND-MOVE",
      "evidence": "README.md:40-43 is an operational gotcha: 'alerts can silently drop if TIMEOUT_S exceeds the receiving channel's flush interval'. This is tuning guidance for operators/agents, not end-user information. It belongs in CLAUDE.md (agent context) not in a user-facing README.",
      "proposal": {
        "target": "CLAUDE.md",
        "text": "**Timeout interaction:** Alerts silently drop if `TIMEOUT_S` (src/notify.py:4, currently 10) exceeds the receiving channel's flush interval, since the channel may discard buffered messages by the time the next send attempt starts."
      },
      "status": null,
      "payload": null
    },
    {
      "id": "B4",
      "doc": "docs/plans/2026-01-10-notify-retry-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "Implementation landed: src/notify.py:3 defines `MAX_RETRIES = 3` and src/notify.py:4 defines `TIMEOUT_S = 10`, matching the design decision. The Sketch section (lines 44-55) is now superseded by the shipped code. Problem, Options, and Decision sections are scaffolding; durable constraints are the 3-retry limit, 10s timeout, and the rationale (fixed backoff chosen over exponential for simplicity in a small library).",
      "proposal": null,
      "status": "ready",
      "payload": {
        "claims": [
          {
            "claim": "Delivery retry logic is built into `send_alert` with a fixed retry count (3 attempts) and timeout (10 seconds per attempt) rather than exponential backoff, prioritizing simplicity for a small internal library.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:3 `MAX_RETRIES = 3`, src/notify.py:4 `TIMEOUT_S = 10`"
          },
          {
            "claim": "The library can be upgraded to exponential backoff if retry storms or slow-channel behavior becomes a measured bottleneck in production.",
            "target": "CLAUDE.md",
            "evidence": "docs/plans/2026-01-10-notify-retry-design.md Decision section"
          }
        ],
        "decision_entry": "## 2026-01-10 — retry behavior\n- Decided: fixed-retry strategy (3 attempts, 10s timeout per attempt) for `send_alert`, chosen over exponential backoff for simplicity in a small internal alerting library.\n- Still binds: revisit exponential backoff if channel retry storms or slow-response behavior becomes a measured issue in production.\n- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert).\n- Source: docs/plans/2026-01-10-notify-retry-design.md (retired in this distillation)."
      }
    },
    {
      "id": "B5",
      "doc": "docs/plans/2026-07-01-batching-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "Implementation not landed: `grep -rn 'batch' src/notify.py` returns no matches; `send_batch` and batch delivery logic are not present in the codebase. The design describes unbuilt code.",
      "proposal": null,
      "status": "pending-implementation",
      "payload": null
    }
  ],
  "summary": {
    "cut": 0,
    "condense": 1,
    "extract_and_move": 1,
    "retire_doc": 1,
    "merge_doc": 0,
    "distill": 2
  }
}
```

---

**Validator output:**
```
OK: 5 record(s) valid
summary: {"cut": 0, "condense": 1, "extract_and_move": 1, "retire_doc": 1, "merge_doc": 0, "distill": 2}
```
