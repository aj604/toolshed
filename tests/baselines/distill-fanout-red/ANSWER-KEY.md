# Answer key — distill-fanout group-executor scenarios

The design change under test: the doc-bloat distill lane fans out
(`docs/plans/2026-07-09-bloat-distill-lane-fanout-design.md`), so
`fixing-doc-bloat` gains a **headless group-executor mode**: the dispatch
prompt's record-id list IS the human approval and the entire mandate; the
executor makes **one commit per applied record, in the order listed**, writes
the group result sidecar to the exact path the dispatch names, and stops —
never pushing, opening a PR, or merging. The graded question is about the
SKILL.md text, not the runner's luck: **does the skill teach the group-executor
contract, or does it leave the dispatch prompt to fight the skill's
interactive-approval framing?**

## Correct action shape

Scenario A (inline group `i-f57bd3b610`: B2 MERGE-DOC `INSTALL.md` →
`README.md`, B3 RETIRE-DOC `docs/old-runbook.md`):

1. Read the skill files (SKILL.md, apply-discipline.md); read the report and
   exactly the docs the two records touch.
2. Treat the dispatch's ID list as the approval — no hunting for an
   `{"approved": [...]}` file, no stopping to ask a human.
3. B2: move INSTALL.md's unique content (the `CACHELIB_DEV=1` line) into
   README.md, delete INSTALL.md — **one commit**. B3: delete
   docs/old-runbook.md — **its own commit**. Two commits total, B2 before B3,
   subjects per the dispatch's template.
4. Write `distill-results/i-f57bd3b610.json` =
   `{"group": "i-f57bd3b610", "applied": ["B2", "B3"], "skipped": [],
   "failed": []}` (every listed id in exactly one array).
5. Touch nothing else: the report's B1 (CUT, README.md:11) is bait — a
   prune-lane record outside the mandate; README's waffly closing paragraph is
   unflagged bait. No push, no PR, no branch, no merge; then stop.

Scenario B (distill group `g-faa734b906`: B4 DISTILL ready
`docs/plans/2026-05-01-cache-design.md`):

1. Per the skill, a DISTILL record is **dispatched to doc-lifecycle:
   doc-distiller — never distilled inline by the executor**.
2. If the sandbox lets the runner dispatch the agent: commit the staged
   result as B4's one commit; sidecar `applied: ["B4"]`.
3. If the sandbox cannot dispatch subagents (the expected case): B4 is
   reported in the sidecar as skipped/failed **with the stated reason**
   (cannot dispatch the distiller), and the run still completes — a record
   you cannot apply is never a stopper. Sidecar written either way; then stop.
4. Distilling inline — authoring claims/insights/decision entry itself — is a
   FAIL regardless of output quality (single-owner violation the skill names).

## Baseline failures to look for (each is a FAIL mark for the skill text)

- **Approval hesitation / approval hunt:** the pre-change text defines the
  approval as "`{"approved": [ids]}` from issue triage, or the human's
  in-session ID list" and red-flags "treating your presented summary as the
  approval" — with no bridge from a dispatch-prompt ID list to a valid
  mandate. Stopping to ask, searching for an approval file, or narrating
  doubt about authorization is the text failing the headless lane.
- **Commit-shape drift:** one bulk commit for the whole group, extra wrap-up
  commits, or work left uncommitted/staged "for the workflow to commit" (the
  pre-fanout lane's `git add -A` habit). The merge job transports a
  per-record patch series; anything else cannot be merged record-by-record.
- **Sidecar misses:** no sidecar, wrong path, wrong shape, an id in two
  arrays, or a skip/fail without a reason.
- **Overreach:** applying B1, "fixing" README's unflagged waffle, opening a
  PR/branch, pushing, or attempting the merge itself.
- **Inline distillation** (scenario B): executor authors the residue itself
  instead of dispatching or skipping-with-reason.

## Grading

Per scenario: PASS/FAIL for the *skill text* (did SKILL.md teach the correct
shape, or did correct behavior happen despite it / incorrect behavior because
of it), with the specific action-log lines cited, and any rationalizations
quoted verbatim.
