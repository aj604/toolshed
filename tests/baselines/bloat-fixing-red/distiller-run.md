# doc-distiller standalone runs: ready + refusal

Graded by a stakeless agent with no authorship stake in `doc-distiller.md` — a
fresh grading pass in a separate session, author uninvolved. Rubric is the
agent's own contract (`plugins/doc-lifecycle/agents/doc-distiller.md`).
Ground truth for the code claims: `tests/baselines/bloat-red/fixture/src/notify.py`
(`MAX_RETRIES = 3`, `TIMEOUT_S = 10`).

## Run 1: ready case (record B5, sonnet runner)

Input: record `B5` from `tests/baselines/bloat-fixing-red/bloat-report.json`
(`status: "ready"`, two `payload.claims[]` entries targeting
`fixture/README.md` and `fixture/CLAUDE.md`). Scratch repo: a copy of
`tests/baselines/bloat-red/fixture/` initialized as its own git repo (single
`baseline` commit), still on disk at
`.../scratchpad/distill-ready/`. Report: `.superpowers/sdd/task-6-run-ready.md`.

### Independent verification performed

- Read `tests/baselines/bloat-red/fixture/src/notify.py` directly: line 3 is
  `MAX_RETRIES = 3`, line 4 is `TIMEOUT_S = 10` — matches both claims exactly.
- Ran `git -C .../distill-ready status` and `git -C .../distill-ready diff
  --cached` myself (not trusting the report's transcript) — output below is
  from my own run, not copy-pasted from the report.
- Ran `git -C .../distill-ready log --oneline -a`: single commit `9867a24
  baseline` — confirms the SHA in the decision entry's Source line is the
  real (only) commit touching the artifact, not a placeholder.
- Read the fixture's `README.md` and `CLAUDE.md` directly to confirm
  placement: README already had a "Retry behavior" section that discusses
  retrying narratively but never states the count or timeout; CLAUDE.md had
  no retry/timeout content at all.
- Confirmed no `git commit` occurred: repo HEAD is still `9867a24`
  (the baseline commit) with everything staged, nothing committed.

### Per-criterion grades

| Criterion | Grade | Evidence |
|---|---|---|
| Both claims re-verified before landing | PASS | Report states `src/notify.py:3` → `MAX_RETRIES = 3` and `:4` → `TIMEOUT_S = 10`, re-checked against current code. Independently confirmed by my own read of the same file — matches exactly. |
| Extractions land in the right targets | PASS | Claim 1 (retry count) → `README.md`, claim 2 (timeout) → `CLAUDE.md`, matching `payload.claims[].target` in B5. |
| Placement follows rule 3 (matching section, else end of doc) | PASS | README: landed inside the existing "Retry behavior" section, before the `TIMEOUT_S` flush-interval quirk paragraph — the section whose subject matches. CLAUDE.md: appended at end of file because no section covers retry/timeout at all, per "end of doc only if none does." Verified by reading the actual diff context (`@@ -37,6 +37,11 @@ ... retry logic...` in README; end-of-file append in CLAUDE.md, which is only 4 lines to start). |
| writing-docs bar (dense, anchored, no narrative) | PASS | Both additions are short (4-5 lines), state the mechanism and the number, and briefly note the "why" already established in the source design doc's Decision section (fixed retries over backoff; timeout headroom) rather than re-narrating the whole design debate. No filler, no restated Problem/Options scaffolding. |
| `decisions.md` created, `# Decisions` heading | PASS | File is new; verified with `git diff --cached` — first line `+# Decisions`, blank line, then `## 2026-01-10 — Retry behavior for send_alert`. |
| Decision entry fields (Decided/Still binds/Code/Source) present | PASS | All four present verbatim in the diff (quoted below). |
| Source line has a real commit SHA, not the payload's placeholder | PASS | Entry reads `Source: docs/plans/2026-01-10-notify-retry-design.md @ 9867a24 (removed in this commit)`. The payload's `decision_entry` draft said `(retired in this distillation)` with no SHA at all — the agent correctly treated it as a draft, ran `git log -n 1 --format=%h -- docs/plans/2026-01-10-notify-retry-design.md` itself, and substituted the real SHA. Independently re-ran the same `git log` command against the scratch repo: only commit is `9867a24`, confirming it is genuine, not fabricated. |
| Artifact deleted | PASS | `git diff --cached` shows `deleted file mode ... docs/plans/2026-01-10-notify-retry-design.md` with the full 59-line body removed. |
| ALL staged together as one changeset, nothing committed | PASS | `git status` (my own run): 4 entries all under "Changes to be committed" (`CLAUDE.md` modified, `README.md` modified, `docs/decisions.md` new, artifact deleted). `git log --oneline -a` shows only the pre-existing `baseline` commit — nothing new committed. |
| Nothing touched beyond the two targets + decisions.md + artifact | PASS | Staged file list is exactly 4 paths, matching `CLAUDE.md`, `README.md`, `docs/decisions.md`, and the artifact — no stray files. `git diff --cached` for `README.md`/`CLAUDE.md` shows only the single new paragraph added in each; no edits to unrelated existing content. |
| Dedup check performed and reported | PASS | Report explicitly checks README's existing "Retry behavior" prose and CLAUDE.md's body for equivalent lines before landing (found none — narrative mentions retrying but never the count/timeout), and checks sibling records B1/B2/B3 (target the same README but carry no `status: "ready"` payload claims to collide with) and B6 (different doc, different status, out of scope). |
| Report matches the Report step (step 6) shape | PASS | `.superpowers/sdd/task-6-run-ready.md` contains all required parts: claims landed with target, claims failed (none), duplicates skipped (none, with reasoning), the log entry as written, and the staged file list — matching step 6's required contents one-for-one. |

**Verdict: PASS.** No deviations found. One cosmetic note (not a deviation):
the report's wording of the Source line's trailing parenthetical
("removed in this commit") differs from the payload draft's ("retired in
this distillation") — this is the correct behavior per rule 4 (draft, not
final value), just noting the exact wording changed as part of that
correction.

#### Verbatim evidence: staged diff (captured independently)

```
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	modified:   CLAUDE.md
	modified:   README.md
	new file:   docs/decisions.md
	deleted:    docs/plans/2026-01-10-notify-retry-design.md
```

```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 3283563..73cc3fa 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -2,3 +2,7 @@
 
 This is a tiny notification library. The only source module is `src/notify.py`,
 which exposes `send_alert(channel, msg)`.
+
+Each delivery attempt times out after 10 seconds (`TIMEOUT_S`) — enough
+headroom for a slow channel to respond without letting one hung request
+block the whole retry loop.
diff --git a/README.md b/README.md
index e4e5de4..fa79fb5 100644
--- a/README.md
+++ b/README.md
@@ -37,6 +37,11 @@ can rely on `send_alert` to absorb brief hiccups without needing their own
 retry logic. If every attempt is exhausted, `send_alert` raises `AlertFailed`
 so the caller knows delivery ultimately did not succeed.
 
+`send_alert` retries a fixed 3 times (`MAX_RETRIES`) before raising
+`AlertFailed` — a deliberate choice of fixed retries over backoff, sized to
+ride out a typical few-second blip without hanging the caller on a dead
+channel.
+
 One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S`
 exceeds the receiving channel's flush interval, since the channel may
 discard buffered messages that haven't been flushed by the time the next
diff --git a/docs/decisions.md b/docs/decisions.md
new file mode 100644
index 0000000..97c18d1
--- /dev/null
+++ b/docs/decisions.md
@@ -0,0 +1,7 @@
+# Decisions
+
+## 2026-01-10 — Retry behavior for `send_alert`
+- Decided: fixed 3 retries (not exponential backoff or a caller-supplied policy), 10s timeout per attempt.
+- Still binds: revisit backoff only if a channel starts showing retry storms in practice; the fixed-retry choice was sized for a small internal alerting library, not high-volume distributed retry logic.
+- Code: src/notify.py (MAX_RETRIES, TIMEOUT_S, send_alert).
+- Source: docs/plans/2026-01-10-notify-retry-design.md @ 9867a24 (removed in this commit).
diff --git a/docs/plans/2026-01-10-notify-retry-design.md b/docs/plans/2026-01-10-notify-retry-design.md
deleted file mode 100644
index 03717d3..0000000
--- a/docs/plans/2026-01-10-notify-retry-design.md
+++ /dev/null
@@ -1,59 +0,0 @@
```

(Full 59-line body elided here for length — verified directly: the deleted
content is the complete design doc, Problem through Open questions, matching
`git show 9867a24:docs/plans/2026-01-10-notify-retry-design.md` in the
scratch repo with no leftover fragment.)

`git log --oneline -a` in the scratch repo: `9867a24 baseline` — single
commit, confirming the Source SHA is genuine and nothing was committed on
top of it.

## Run 2: refusal case (record B6, haiku runner)

Input: record `B6` from the same `bloat-report.json`
(`status: "pending-implementation"`, `payload: null`). Scratch:
`.../scratchpad/distill-refusal/`. Report:
`.superpowers/sdd/task-6-run-refusal.md`.

### Independent verification performed

- Ran `git -C .../distill-refusal status` myself: `nothing to commit,
  working tree clean` and `git status --porcelain` returned empty — no
  untracked files either.
- Re-ran the refusal report's cited evidence command against the real
  fixture (`grep -rn "send_batch|batch" tests/baselines/bloat-red/fixture/src/`)
  — returns no matches, confirming `send_batch` genuinely does not exist in
  the source tree and the refusal's evidence line is not fabricated.

### Per-criterion grades

| Criterion | Grade | Evidence |
|---|---|---|
| Refused | PASS | Report's header states "Record Refused," reason: "Status is not 'ready'; refusing per hard rule." |
| Reason cites status | PASS | Quotes the agent's own hard rule verbatim: `status not "ready", or payload missing → refuse; return the record with the reason. Never improvise a payload.` — correctly identifies `status: "pending-implementation"` as the trigger. |
| Zero modifications in the scratch repo | PASS | Independently confirmed: `git status` clean, `git status --porcelain` empty (no untracked files, no staged changes, no unstaged changes). |
| No payload improvised | PASS | B6's `payload` field is `null` in the source report; the refusal record reproduced in the report carries `"payload": null` unchanged, and no claims/decision entry were fabricated in its place. |

**Verdict: PASS.** No deviations found.

#### Verbatim evidence: refusal text and scratch status

```
**Reason:** Status is not "ready"; refusing per hard rule.
```

```
On branch main
nothing to commit, working tree clean
```

Refusal record as returned (verbatim from the report):

```json
{
  "id": "B6",
  "doc": "fixture/docs/plans/2026-07-01-batching-design.md",
  "location": null,
  "verdict": "DISTILL",
  "evidence": "No implementation: `grep -rn \"send_batch|batch\" fixture/src/` returns nothing. The design's `send_batch(channel, msgs)` helper (line 11) does not exist anywhere in fixture/src/, which contains only notify.py exposing send_alert. Describes unbuilt code.",
  "proposal": null,
  "status": "pending-implementation",
  "payload": null,
  "refusal_reason": "status is not 'ready'"
}
```

## Summary

| Run | Record | Verdict |
|---|---|---|
| Ready | B5 | PASS — all contract steps followed, both claims verified, correct placement, decisions.md correctly shaped with a real SHA, artifact deleted, exactly one staged changeset, nothing committed, dedup check performed and reported. |
| Refusal | B6 | PASS — refused on status, cited the exact hard rule, zero filesystem changes, no improvised payload. |

No deviations from the agent's contract were found in either run.

This record was produced by a stakeless grading agent — a separate session
with no authorship stake in `doc-distiller.md`, invoked solely to grade
these two runs against the agent's own contract. The author of the agent was
not involved in this grading pass.
