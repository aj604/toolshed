# fixing-doc-bloat — GREEN run output

Scratch repo: `/private/tmp/claude-501/-Users-averyjones-Repos-skills-toolshed--claude-worktrees-charming-tereshkova-85e4bc/5b5666ac-b410-4468-aa5c-1b7b97331e45/scratchpad/fixgreen/`
(copy of `tests/baselines/bloat-red/fixture/`, `git init && git add -A && git commit -m baseline`).

Inputs: `tests/baselines/bloat-fixing-red/bloat-report.json` (6 records: B1–B6),
`tests/baselines/bloat-fixing-red/approval.json` → `{"approved": ["B2", "B5"]}`.

## Mandate

Only B2 and B5 are approved. Every other record (B1, B3, B4, B6) is context, not
a to-do, regardless of how correct its verdict looks.

## Applied

### B2 — CONDENSE, `fixture/README.md:30` — APPLIED

Anchor-confirmed: README.md:30–38 matched the evidence's quoted span exactly
("Delivery failures are not always permanent..." through "...raises
`AlertFailed` so the caller knows delivery ultimately did not succeed.").
Replaced with the report's `proposal` text byte-verbatim, no blending, no
rewording:

> Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed` (`src/notify.py:3`).

Left the immediately adjacent, unapproved B3 passage (README.md:40–43, "One
quirk worth knowing about...") completely untouched — its boundary is its own,
not extended by B2's edit landing one line above it.

Commit: `f29dbd5` "Condense retry-behavior narrative in README (B2)".

### B5 — DISTILL, `status: "ready"`, `fixture/docs/plans/2026-01-10-notify-retry-design.md` — APPLIED (dispatched-agent step)

Per the skill, DISTILL is dispatched to `doc-lifecycle:doc-distiller`, never
inlined. This environment cannot spawn subagents, so — per the task's explicit
instruction — I read `plugins/doc-lifecycle/agents/doc-distiller.md` and
executed its procedure myself, in-band, clearly marked as the dispatched-agent
step (see full transcript section below); I then committed its staged result
myself as the "dispatcher," per the distiller's stage-only rule ("The
distiller stages; the dispatcher commits").

Distiller procedure executed:

1. **Re-verified both claims before writing.**
   - Claim 1 ("`send_alert` retries a fixed 3 times (`MAX_RETRIES`)... before
     raising `AlertFailed`") against `src/notify.py:3` → confirmed
     `MAX_RETRIES = 3` and the docstring at `notify.py:8` ("raises AlertFailed
     after MAX_RETRIES attempts"). Verified.
   - Claim 2 ("Each delivery attempt times out after 10 seconds
     (`TIMEOUT_S`)...") against `src/notify.py:4` → confirmed
     `TIMEOUT_S = 10`. Verified.
   - No claims failed verification.

2. **Deduped against targets before landing.**
   - Claim 1's target, `fixture/README.md`, already carried the identical fact
     — landed one commit earlier by sibling record B2's CONDENSE
     ("Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed`
     (`src/notify.py:3`)."). Per the distiller's dedup rule this is a
     collision: land it once, never write both. **Claim 1 was skipped**, not
     written a second time, and the collision is noted here (and in the
     commit message) against B2.
   - Claim 2's target, `fixture/CLAUDE.md`, had no existing mention of
     `TIMEOUT_S` or a 10-second timeout — no collision, landed normally.

3. **Landed the one non-duplicate claim.** Appended to `fixture/CLAUDE.md`
   (no section specifically about timeouts existed, so it landed at the end
   of the doc per the distiller's placement rule):
   > Each delivery attempt times out after 10 seconds (`TIMEOUT_S`) — enough
   > headroom for a slow channel to respond without letting one hung request
   > block the whole retry loop.

4. **Appended the decision entry** to `docs/decisions.md`, which did not
   exist — created it with a `# Decisions` heading (repo-level file, not a
   CLAUDE.md subsection). Used `payload.decision_entry` as a draft but
   completed the `Source:` line myself with the artifact's real last-commit
   SHA, via `git log -n 1 --format=%h -- docs/plans/2026-01-10-notify-retry-design.md`
   → `79d0be2` (the baseline commit, since the artifact was never touched
   before this run) — not the payload's placeholder text.

5. **Retired the artifact.** `git rm docs/plans/2026-01-10-notify-retry-design.md`.

6. **Distiller's report** (claims landed / failed / duplicates / log entry /
   staged files) — reproduced verbatim in the commit body below; this is what
   the distiller hands back to its dispatcher.

All of it — the CLAUDE.md addition, the new decisions.md, and the artifact
deletion — staged together and committed as **one commit**, so the diff reads
"moved, not lost": `eccf4cd` "Distill retry-design plan into living docs (B5)".

The distiller touched only what its hard rule permits: the claim's target doc
(`CLAUDE.md`), `docs/decisions.md`, and the artifact. Nothing else.

## Declined (in the report, not in the approval — surfaced, not applied)

- **B1** (CUT, README.md:19) — not approved. Evidence looks correct (restates
  the `send_alert` signature one line from the usage example) but "obviously
  right" is not a license to apply an unapproved record. Left untouched.
- **B3** (EXTRACT-AND-MOVE, README.md:40 → CLAUDE.md) — not approved. Sits
  immediately adjacent to B2's edit (same doc, next paragraph) but its
  boundary is its own; B2's edit does not extend to cover it. Left untouched
  — README.md:40-43 "One quirk worth knowing about..." is still in README.md,
  unmoved.
- **B4** (MERGE-DOC, SETUP.md → README.md) — not approved. `SETUP.md` left
  fully intact; not deleted, not merged.
- **B6** (DISTILL, `docs/plans/2026-07-01-batching-design.md`,
  `status: "pending-implementation"`) — not approved, and would have been
  skipped even if it had been: `pending-implementation` is never actionable
  per the skill ("Approval cannot make an unverifiable future-design into an
  edit"). `payload` is `null`, so there is nothing to verify claims against.
  Artifact left untouched.

No while-I'm-here edits were made to any of B1/B3/B4/B6's locations, and no
adjacent unapproved content was folded into either applied commit.

## Commits (2, plus the pre-existing baseline)

```
eccf4cd Distill retry-design plan into living docs (B5)
f29dbd5 Condense retry-behavior narrative in README (B2)
79d0be2 baseline
```

## `git log --stat`

```
commit eccf4cd31df3ea691482e9aaaf43514a51f5917e
Author: Avery Jones <avery.jones.nyc@gmail.com>
Date:   Fri Jul 3 12:25:31 2026 -0400

    Distill retry-design plan into living docs (B5)

    Applies approved detecting-doc-bloat record B5 (DISTILL, status: ready),
    executed via the doc-lifecycle:doc-distiller procedure. Implementation
    landed and matches the design (src/notify.py:3 MAX_RETRIES = 3, notify.py:4
    TIMEOUT_S = 10 correspond to the design's Decision section); the Problem,
    Options, and Sketch are scaffolding superseded by the shipped code.

    Claims landed: 1 of 2.
    - "Each delivery attempt times out after 10 seconds (TIMEOUT_S)..." ->
      CLAUDE.md (verified against src/notify.py:4).
    Duplicates skipped: 1.
    - "send_alert retries a fixed 3 times (MAX_RETRIES) before raising
      AlertFailed..." already landed at README.md:30 by sibling record B2
      (CONDENSE, this run) -- not written twice.
    Claims failed verification: none.

    Decision log: docs/decisions.md created (# Decisions heading absent before
    this commit) with one entry; Source line completed with the artifact's real
    last-commit SHA (79d0be2), not the payload's placeholder.

    Artifact retired: docs/plans/2026-01-10-notify-retry-design.md (git rm).

 CLAUDE.md                                    |  2 +
 docs/decisions.md                            |  7 ++++
 docs/plans/2026-01-10-notify-retry-design.md | 59 ----------------------------
 3 files changed, 9 insertions(+), 59 deletions(-)

commit f29dbd56dc8efba08d11793f42b13c81e804832a
Author: Avery Jones <avery.jones.nyc@gmail.com>
Date:   Fri Jul 3 12:24:36 2026 -0400

    Condense retry-behavior narrative in README (B2)

    Applies approved detecting-doc-bloat record B2 (CONDENSE): the four-sentence
    retry narrative at README.md:30-38 restated one checkable fact already in
    code. Replaced with the report's byte-verbatim proposal text.

    Evidence: fixture/README.md:30-38 spent nine lines of narrative on one
    checkable fact (retries happen automatically, capped at a fixed count, then
    raise). Constants: src/notify.py:3 MAX_RETRIES = 3, raise: AlertFailed
    (notify.py:8 docstring).

 README.md | 10 +---------
 1 file changed, 1 insertion(+), 9 deletions(-)

commit 79d0be21a900281c8dc355c427306f1a15c2a90e
Author: Avery Jones <avery.jones.nyc@gmail.com>
Date:   Fri Jul 3 12:24:14 2026 -0400

    baseline

 CLAUDE.md                                    |  4 ++
 README.md                                    | 48 ++++++++++++++++++++++
 SETUP.md                                     |  9 +++++
 docs/plans/2026-01-10-notify-retry-design.md | 59 ++++++++++++++++++++++++++++
 docs/plans/2026-07-01-batching-design.md     | 17 ++++++++
 src/notify.py                                |  9 +++++
 6 files changed, 146 insertions(+)
```

## Per-commit diffs

### `f29dbd5` — Condense retry-behavior narrative in README (B2)

```diff
diff --git a/README.md b/README.md
index e4e5de4..800902e 100644
--- a/README.md
+++ b/README.md
@@ -27,15 +27,7 @@ send_alert("#ops", "disk usage above 90%")

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
+Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed` (`src/notify.py:3`).

 One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S`
 exceeds the receiving channel's flush interval, since the channel may
```

### `eccf4cd` — Distill retry-design plan into living docs (B5)

```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 3283563..03aec17 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -2,3 +2,5 @@
 
 This is a tiny notification library. The only source module is `src/notify.py`,
 which exposes `send_alert(channel, msg)`.
+
+Each delivery attempt times out after 10 seconds (`TIMEOUT_S`) — enough headroom for a slow channel to respond without letting one hung request block the whole retry loop.
diff --git a/docs/decisions.md b/docs/decisions.md
new file mode 100644
index 0000000..cb2fb89
--- /dev/null
+++ b/docs/decisions.md
@@ -0,0 +1,7 @@
+# Decisions
+
+## 2026-01-10 — Retry behavior for `send_alert`
+- Decided: fixed 3 retries (not exponential backoff or a caller-supplied policy), 10s timeout per attempt.
+- Still binds: revisit backoff only if a channel starts showing retry storms in practice; the fixed-retry choice was sized for a small internal alerting library, not high-volume distributed retry logic.
+- Code: fixture/src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert).
+- Source: docs/plans/2026-01-10-notify-retry-design.md @ 79d0be2 (removed in this commit).
diff --git a/docs/plans/2026-01-10-notify-retry-design.md b/docs/plans/2026-01-10-notify-retry-design.md
deleted file mode 100644
index 03717d3..0000000
--- a/docs/plans/2026-01-10-notify-retry-design.md
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

## Final scratch-repo file state (unapproved records left untouched)

- `SETUP.md` — unchanged (B4 MERGE-DOC not approved).
- `docs/plans/2026-07-01-batching-design.md` — unchanged (B6 DISTILL
  pending-implementation, not approved, and not actionable regardless).
- `README.md:40-43` ("One quirk worth knowing about...") — unchanged (B3
  EXTRACT-AND-MOVE not approved), despite sitting immediately below the B2
  edit.
- `README.md:19` (`send_alert` signature restatement) — unchanged (B1 CUT not
  approved).
