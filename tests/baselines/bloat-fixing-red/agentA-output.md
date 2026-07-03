# Agent A — applying approved bloat-fix records (B2, B5)

## What was done

Worked on a scratch copy at
`/private/tmp/claude-501/-Users-averyjones-Repos-skills-toolshed--claude-worktrees-charming-tereshkova-85e4bc/5b5666ac-b410-4468-aa5c-1b7b97331e45/scratchpad/fixredA/`
(copied from `tests/baselines/bloat-red/fixture/`). The repo working tree itself was not modified.

Input: `tests/baselines/bloat-fixing-red/bloat-report.json` (6 records: B1–B6) and
`tests/baselines/bloat-fixing-red/approval.json` (`{"approved": ["B2", "B5"]}`).
Only B2 and B5 were applied. B1 (CUT), B3 (EXTRACT-AND-MOVE), B4 (MERGE-DOC), and B6
(DISTILL, pending-implementation) were **not** approved and were left untouched —
`SETUP.md`, the "One quirk worth knowing about" paragraph in README.md, and
`docs/plans/2026-07-01-batching-design.md` are all unchanged from the original fixture.

### B2 — CONDENSE, `fixture/README.md:30`

Replaced the nine-line retry narrative in the "Retry behavior" section with the
report's proposed single dense line (verified against `src/notify.py:3`
`MAX_RETRIES = 3` and the `AlertFailed` docstring at `notify.py:8`). Used the
proposal text verbatim.

### B5 — DISTILL (ready), `fixture/docs/plans/2026-01-10-notify-retry-design.md`

Followed the `doc-distiller` agent procedure specified in
`docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md` (Task 6), since no
`fixing-doc-bloat`/`doc-distiller` skill exists yet to dispatch to:

1. **Re-verified both claims against code** before writing anything:
   - Claim 1 evidence `src/notify.py:3` → confirmed `MAX_RETRIES = 3`.
   - Claim 2 evidence `src/notify.py:4` → confirmed `TIMEOUT_S = 10`.
2. **Landed extractions** in their named targets, in the section matching their
   subject:
   - Claim 1 (fixed-retries-over-backoff rationale) appended to README.md's
     existing "Retry behavior" section, right after the B2 condensed line (kept
     non-duplicative of B2's line — only added the part B2 doesn't already
     state: *why* fixed retries instead of backoff).
   - Claim 2 (10s per-attempt timeout rationale) appended to `fixture/CLAUDE.md`,
     which had no existing section to fold into, so appended at end of doc.
3. **Appended the decision entry** to a newly created `fixture/docs/decisions.md`
   (didn't exist — created with a `# Decisions` heading per the spec). Used
   `payload.decision_entry` from the report, completing the `Source` line with
   the last commit that touched the artifact (`git log` on
   `tests/baselines/bloat-red/fixture/docs/plans/2026-01-10-notify-retry-design.md`
   → `1c824db`) and "(removed in this commit)" per the template.
4. **Retired the artifact**: deleted
   `fixture/docs/plans/2026-01-10-notify-retry-design.md`.

Per the agent's hard rules, touched only the claims' target docs
(README.md, CLAUDE.md), `docs/decisions.md`, and the artifact itself — nothing
else.

## Full diff (scratch copy vs. original fixture)

```diff
--- a/fixture/README.md
+++ b/fixture/README.md
@@ -27,15 +27,9 @@

 ## Retry behavior

-Delivery failures are not always permanent, so the library will not give up
-on the first error it sees. Instead, when a send attempt fails, it waits
-briefly and tries again, giving transient network blips and momentary channel
-outages a chance to resolve themselves before the caller is bothered with a
-failure. This retrying continues for a small, fixed number of attempts before
-the library gives up and reports the failure back to the caller, so callers
-can rely on `send_alert` to absorb brief hiccups without needing their own
-retry logic. If every attempt is exhausted, `send_alert` raises `AlertFailed`
-so the caller knows delivery ultimately did not succeed.
+Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed`
+(`src/notify.py:3`) — fixed retries rather than backoff, sized to ride out a
+typical few-second blip without hanging the caller on a dead channel.

 One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S`
 exceeds the receiving channel's flush interval, since the channel may
```

```diff
--- a/fixture/CLAUDE.md
+++ b/fixture/CLAUDE.md
@@ -2,3 +2,7 @@

 This is a tiny notification library. The only source module is `src/notify.py`,
 which exposes `send_alert(channel, msg)`.
+
+Each delivery attempt times out after 10 seconds (`TIMEOUT_S`) — enough
+headroom for a slow channel to respond without letting one hung request block
+the whole retry loop.
```

```diff
--- /dev/null
+++ b/fixture/docs/decisions.md
@@ -0,0 +1,7 @@
+# Decisions
+
+## 2026-01-10 — Retry behavior for `send_alert`
+- Decided: fixed 3 retries (not exponential backoff or a caller-supplied policy), 10s timeout per attempt.
+- Still binds: revisit backoff only if a channel starts showing retry storms in practice; the fixed-retry choice was sized for a small internal alerting library, not high-volume distributed retry logic.
+- Code: fixture/src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert).
+- Source: fixture/docs/plans/2026-01-10-notify-retry-design.md @ 1c824db (removed in this commit).
```

```diff
--- a/fixture/docs/plans/2026-01-10-notify-retry-design.md
+++ /dev/null
@@ -1,59 +0,0 @@
-# 2026-01-10 — Retry behavior for `send_alert`
-
-## Problem
-
-`send_alert` currently fails permanently on the first delivery error. Channel
-outages tend to be transient — a few seconds of network blip, a momentary
-rate limit on the receiving side — and giving up immediately means callers
-have to implement their own retry wrapper, which several already do,
-inconsistently. We want retry handling built into `send_alert` itself so
-every caller gets the same behavior for free.
-
-## Options considered
-
-**Option A: Fixed number of retries, fixed backoff.** Retry a set number of
-times with a constant delay between attempts. Simple to implement and easy
-to reason about. Downside: doesn't adapt to slow channels, and a constant
-delay can hammer a channel that's recovering from an outage.
-
-**Option B: Exponential backoff with jitter.** Standard approach for
-distributed retry logic — delay doubles each attempt, with random jitter to
-avoid thundering-herd effects when many callers retry at once. More robust,
-but adds complexity (jitter source, max-delay cap, tests for backoff timing)
-that seems disproportionate for a small internal alerting library with a
-handful of callers.
-
-**Option C: Caller-supplied retry policy object.** Let callers pass in their
-own retry strategy (max attempts, delay function) so the library stays
-unopinionated. Rejected: this just pushes the decision back onto every
-caller, which is the problem we're trying to solve in the first place. Also
-expands the public API surface for a benefit only one caller (the batching
-feature, still unimplemented) would plausibly need.
-
-## Decision
-
-Going with Option A. Simplicity wins for a library this small, and we can
-always upgrade to backoff later if a channel starts showing retry storms in
-practice. After going back and forth, three attempts felt like the right
-balance — enough to ride out a typical few-second blip without letting a
-truly dead channel hang the caller for too long. On the timeout side, ten
-seconds per attempt gives slow channels enough headroom to respond without
-letting a single hung request block the whole retry loop for an unreasonable
-amount of time.
-
-## Sketch
-
-```python
-def send_alert(channel, msg):
-    for attempt in range(MAX_RETRIES):
-        try:
-            return channel.deliver(msg, timeout=TIMEOUT_S)
-        except DeliveryError:
-            if attempt == MAX_RETRIES - 1:
-                raise AlertFailed(channel, msg)
-    raise AlertFailed(channel, msg)
-```
-
-## Open questions
-
-None — ready to implement.
```

## Files unchanged (confirms unapproved records were not touched)

- `fixture/SETUP.md` — B4 (MERGE-DOC) not approved.
- `fixture/README.md`'s "One quirk worth knowing about..." paragraph — B3
  (EXTRACT-AND-MOVE) not approved; the paragraph remains word-for-word in
  README.md.
- `fixture/docs/plans/2026-07-01-batching-design.md` — B6
  (DISTILL/pending-implementation) not approved, and pending-implementation
  records carry no actionable payload regardless.
- `fixture/src/notify.py` — no verdict targeted source code.

## Commit message I would use

```
docs: condense retry narrative, distill landed retry-design doc

- README: replace 9-line retry-failure narrative with one line citing
  MAX_RETRIES/AlertFailed (approved bloat record B2).
- Distill docs/plans/2026-01-10-notify-retry-design.md now that its
  design has landed in src/notify.py (approved bloat record B5):
  extract the fixed-retries-over-backoff rationale to README and the
  10s-timeout rationale to CLAUDE.md, log the decision in the new
  docs/decisions.md, and retire the design doc.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```
