**Lane 21:** no fixer. The review fails its own test. Every acceptance criterion is marked met, and none of the three findings maps to a criterion:
- The README sentence and the docs anchor are docs nits.
- The logging test covers a branch no criterion asks about.

A review whose findings are all FOLLOW-UP counts as a PASS. The reviewer labelled this round KIND `test-gap`, but the skill's fix rule only defines `defect` and `design`. So I'd record an `ORCHESTRATOR DECISION` treating the lane as PASS and send it to landing. The three findings go in the end-of-run report instead of costing a fix round.

One exception: if this PR itself renamed or removed the config flag, the stale README sentence now contradicts shipped behaviour. That one finding would be a real `defect`, and I'd dispatch a fresh fixer for it.

**Lane 22:** no re-review. All of round 1's BLOCKING findings were test gaps and the fix touched only test files. I'd confirm with a compare over the whole range since the reviewed SHA, then dispatch a `sonnet` verifier to re-run the mutations. The fixer's own "went red" claim doesn't count; the verifier re-runs the mutations itself. This is round 1 of 2, so there's no budget problem.

## Ordered actions

1. **Read the lane 21 findings off the PR** (read-only):
   `gh pr view <pr-21> --repo acme/ledger --comments`
   `gh pr diff <pr-21> --repo acme/ledger --name-only`
   Check how each finding is tagged, and whether the diff touches the config flag that the README sentence describes.

2. **Lane 22: confirm the fix is tests-only** (read-only):
   `gh api repos/acme/ledger/compare/<reviewed-sha>...<head-sha> --jq '[.files[].filename]'`
   `<reviewed-sha>` is the head commit review-22-r1 judged. The output must be exactly `["tests/reader_test.rs"]`. If anything else shows up, dispatch a fresh `spec-reviewer` named `review-22-r2` instead of step 3.

3. **Dispatch the lane 22 verifier:**
   - `subagent_type: "orchestrate-issues:verifier"`
   - `isolation: "worktree"`
   - `name: "verify-22-r1"`
   - `model: "sonnet"` (the agent's default)
   - `run_in_background: true`

   Why `sonnet` is safe:
   - The mutations are already named in the review thread.
   - Each one either turns a test red or doesn't.
   - The verifier itself runs that check.

   Lane card:
   ```
   REPO:         acme/ledger
   PR:           #<pr-22>
   BRANCH:       <branch-22>
   ROUND:        1
   REVIEWED_SHA: <reviewed-sha>
   ```

4. **Lane 21, normal case (findings are untagged or FOLLOW-UP-grade).** I post this comment on the PR. It's a GitHub write, so it's described here, not run:
   ```
   ## ORCHESTRATOR DECISION
   What: Treat review-21-r1 as PASS. All 3 findings recorded as FOLLOW-UP.
   Why: Every acceptance criterion is marked met. None of the findings maps to a criterion:
        the README sentence and docs/ledger.md anchor are docs nits, and no criterion mentions logging.
        Only BLOCKING findings cost a round.
   Alternative: Fresh fixer (fix-21-r1) for all three, then a full re-review.
                The docs edits aren't tests-only, so a verifier couldn't check them.
   Override: Comment here or add needs-human, and I'll dispatch fix-21-r1.
   ```
   Then I land it under whatever merge authority the contract set:
   - **`ask` (the default):** `gh pr ready <pr-21> --repo acme/ledger`, report it as ready for review, park the lane and free its slot.
   - **`auto`:**
     1. `gh pr ready <pr-21> --repo acme/ledger`
     2. Run `gh pr checks <pr-21> --repo acme/ledger --watch --interval 60 --fail-fast` in the background.
     3. Once checks are green, confirm the PR body has a single `Closes #21`.
     4. `gh pr merge <pr-21> --repo acme/ledger --squash --delete-branch`
     5. Confirm #21 closed, prune the merged lane's worktrees, then re-query the frontier with `frontier.py`.

4b. **Lane 21, only if step 1 shows the PR made the README sentence stale.** Dispatch a fixer for that finding alone:
   - `subagent_type: "orchestrate-issues:fixer"`
   - `isolation: "worktree"`
   - `name: "fix-21-r1"`
   - `model: "sonnet"`
   - `run_in_background: true`

   `sonnet` is safe here because the finding is one named sentence and the re-review checks it. A docs change isn't tests-only, so the follow-up is a fresh `spec-reviewer` named `review-21-r2`, not a verifier. The other two findings stay FOLLOW-UP under an `ORCHESTRATOR DECISION`.

   Lane card:
   ```
   REPO:   acme/ledger
   ISSUE:  #21
   PR:     #<pr-21>
   BRANCH: <branch-21>
   ROUND:  1

   --- ISSUE BODY ---
   <issue #21 body, verbatim>
   --- END ISSUE BODY ---
   ```

5. **When `verify-22-r1` returns:**
   - **PASS:** land lane 22 the same way as step 4.
   - **CHANGES_REQUIRED:** dispatch a fresh `fix-22-r2` on `opus`, since the lane is past its first round. That is the last round in the budget of 2.

6. **Status line** (no blocking question):
   > 21: PASS by orchestrator decision, 3 follow-ups (README flag sentence, docs/ledger.md anchor, writer.rs debug-logging test). 22: verify-22-r1 in flight.

   The three lane 21 follow-ups also go in the end-of-run report.