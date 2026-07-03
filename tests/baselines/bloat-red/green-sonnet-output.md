# Doc bloat audit — fixture (full audit)

Scope: `tests/baselines/bloat-red/fixture/` treated as a standalone repo — `CLAUDE.md`,
`README.md`, `SETUP.md`, `docs/plans/2026-01-10-notify-retry-design.md`,
`docs/plans/2026-07-01-batching-design.md`, `src/notify.py`. Living docs: `CLAUDE.md`,
`README.md`. Planning artifacts: both files under `docs/plans/`. `SETUP.md` is a living doc
(setup instructions) that turns out to be a full duplicate of README's Setup section.

6 findings, ordered by leverage (doc-level and distillations first):

**SETUP.md**
  [B4] RETIRE-DOC — its entire body (SETUP.md:1-9) is a byte-for-byte duplicate of
  README.md's Setup section (README.md:6-14); confirmed with `diff README.md SETUP.md`.
  Nothing unique to preserve, so retire rather than merge.

**docs/plans/2026-01-10-notify-retry-design.md**
  [B5] DISTILL(ready) — the retry design has landed: `src/notify.py:3` `MAX_RETRIES = 3`,
  `src/notify.py:4` `TIMEOUT_S = 10`, and the `AlertFailed` docstring all match the design's
  Decision and Sketch sections. Extract 2 claims to CLAUDE.md + one decision-log entry;
  the Problem/Options-considered/Sketch scaffolding is superseded by the code.

**docs/plans/2026-07-01-batching-design.md**
  [B6] DISTILL(pending-implementation) — `grep -n batch src/notify.py` finds nothing;
  `send_batch` does not exist yet. Accurate about the future, not bloat — record exists to
  say so, payload is null, nothing to edit.

**README.md**
  [B1] CUT   README.md:19 — "The `send_alert` function takes a channel and a message and
  delivers the message to that channel" restates the signature shown two lines later in the
  code block and in `src/notify.py:7`.
  [B2] CONDENSE   README.md:30 — 9 lines of retry narrative → one line citing `MAX_RETRIES`
  and `AlertFailed` (`src/notify.py:3,8`).
  [B3] EXTRACT   README.md:40 — the `TIMEOUT_S` silent-drop quirk is an operational gotcha
  aimed at a debugger, not a first-time caller; belongs in CLAUDE.md.

Please reply with the approved record IDs (e.g. "B1, B4, B5") to hand off to
`fixing-doc-bloat`. Nothing above is applied — this is a proposal only.

## Structured output

```json
{
  "records": [
    {
      "id": "B4",
      "doc": "SETUP.md",
      "location": null,
      "verdict": "RETIRE-DOC",
      "evidence": "SETUP.md:1-9 is byte-for-byte identical in content to README.md:6-14 (same 'Clone the repo, then install the package in editable mode' line, same `pip install -e .` block, same 'No environment variables are required to run the test suite locally' line, confirmed via `diff README.md SETUP.md` which shows SETUP.md's body as a strict subset/duplicate of README.md's Setup section); SETUP.md carries nothing README.md lacks",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B5",
      "doc": "docs/plans/2026-01-10-notify-retry-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "implementation landed: src/notify.py:3 `MAX_RETRIES = 3` matches the design's decision of three attempts, src/notify.py:4 `TIMEOUT_S = 10` matches the design's decision of ten seconds per attempt, and src/notify.py:8 docstring 'raises AlertFailed after MAX_RETRIES attempts' matches the design's Sketch section (`raise AlertFailed(channel, msg)`); Problem/Options considered/Sketch sections are superseded scaffolding",
      "proposal": null,
      "status": "ready",
      "payload": {
        "claims": [
          {
            "claim": "`send_alert` retries a delivery failure up to `MAX_RETRIES` (3) times before raising `AlertFailed`, so callers do not need their own retry wrapper for transient channel blips.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:3 `MAX_RETRIES = 3`; src/notify.py:8 docstring 'raises AlertFailed after MAX_RETRIES attempts'"
          },
          {
            "claim": "Each delivery attempt is bounded by `TIMEOUT_S` (10 seconds); a channel that never flushes within that window can silently drop the alert instead of surfacing an error.",
            "target": "CLAUDE.md",
            "evidence": "src/notify.py:4 `TIMEOUT_S = 10`"
          }
        ],
        "decision_entry": "## 2026-01-10 — retry behavior for send_alert\n- Decided: fixed 3 retries, fixed 10s per-attempt timeout, no backoff; rejected exponential backoff with jitter (disproportionate complexity for a small internal library) and a caller-supplied retry policy object (pushes the decision back onto every caller).\n- Still binds: revisit only if a channel starts showing retry storms in practice.\n- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S, AlertFailed).\n- Source: docs/plans/2026-01-10-notify-retry-design.md (retired in this distillation)."
      }
    },
    {
      "id": "B6",
      "doc": "docs/plans/2026-07-01-batching-design.md",
      "location": null,
      "verdict": "DISTILL",
      "evidence": "no implementation: `grep -n 'batch' src/notify.py` returns nothing; the `send_batch` symbol the design describes exists nowhere in the repo (src/notify.py only defines `send_alert`) — design describes unbuilt code",
      "proposal": null,
      "status": "pending-implementation",
      "payload": null
    },
    {
      "id": "B1",
      "doc": "README.md",
      "location": "README.md:19",
      "verdict": "CUT",
      "evidence": "README.md:19 'The `send_alert` function takes a channel and a message and delivers the message to that channel' restates the signature already shown in the code block two lines later (README.md:23 `from src.notify import send_alert`, README.md:25 `send_alert(\"#ops\", ...)`) and in src/notify.py:7 `def send_alert(channel, msg):` — adds no information beyond the name and the example",
      "proposal": null,
      "status": null,
      "payload": null
    },
    {
      "id": "B2",
      "doc": "README.md",
      "location": "README.md:30",
      "verdict": "CONDENSE",
      "evidence": "README.md:30-38 — nine lines of narrative carry three checkable facts: delivery is retried a fixed number of times, then `AlertFailed` is raised if every attempt fails",
      "proposal": "Failed deliveries are retried up to `MAX_RETRIES` (3) times; if every attempt fails, `send_alert` raises `AlertFailed` (`src/notify.py:3,8`).",
      "status": null,
      "payload": null
    },
    {
      "id": "B3",
      "doc": "README.md",
      "location": "README.md:40",
      "verdict": "EXTRACT-AND-MOVE",
      "evidence": "README.md:40-43 'One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S` exceeds the receiving channel's flush interval...' is an operational gotcha (the tell: \"quirk worth knowing\", \"silently\") addressed to someone debugging a production drop, not to a first-time caller of `send_alert` — belongs in CLAUDE.md alongside the other operational facts about this module, not in the user-facing README",
      "proposal": {
        "target": "CLAUDE.md",
        "text": "Alerts can silently drop if `TIMEOUT_S` exceeds the receiving channel's flush interval: the channel may discard buffered messages that haven't been flushed by the time the next send attempt starts writing to it."
      },
      "status": null,
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
