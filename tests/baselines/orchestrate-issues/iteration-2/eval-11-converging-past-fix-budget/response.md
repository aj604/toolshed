Lane #40 gets one more fix round, and I approve it myself without waking you. The contract allows one extra round when a lane is converging: every earlier BLOCKING finding is closed, the diff hasn't grown, and the only thing left is a missing test. I record that as an `ORCHESTRATOR DECISION` on PR #70 and send a fresh fixer to write the short-position test. If the fix touches only test files, a verifier checks it instead of a full re-review. If that passes, #40 lands under whatever merge authority the run contract set. If anything goes wrong, #40 parks with `needs-human` and waits for you. The other three lanes keep running the whole time, and I ask you nothing.

Choices worth knowing:
- **Fixer model is `opus`, not `sonnet`.** The lane-card rule keeps any lane past its first round on opus, even though a missing test is a `defect`.
- **Verifier model is `sonnet`.** It's the default and qualifies on all three counts: the mutation is named (flip the short-position margin refusal), the test either goes red or it doesn't, and the verifier runs that check itself.
- **This is the last round, not the start of more.** If the verifier fails, or the fix touches production code and review finds something new, the lane stops. The park comment will say it's a converging stop, not a thrashing one, so you know it needs a small decision rather than a rethink.

## Ordered actions

1. **Record the extra round** (GitHub write; not run in rehearsal):
   ```bash
   gh pr comment 70 --repo acme/ledger --body "## ORCHESTRATOR DECISION
   What: one extra fix round (round 3) for #40, beyond the agreed 2.
   Why: the lane is converging. review-40-r3 confirms every earlier BLOCKING finding is closed and the diff hasn't grown. The one remaining BLOCKING finding is a missing test (short-position margin refusal; the long case is covered).
   Alternative: park now with needs-human.
   Override: add needs-human to #40 / PR #70 and I'll stop the lane."
   ```
2. **Check whether the base moved** (read-only): `gh pr view 70 --repo acme/ledger --json baseRefName,mergeStateStatus,headRefOid`. Save `headRefOid` as REVIEWED_SHA. If the PR is behind and a sibling merged code this lane calls, add `CATCH UP` to the fixer's card.
3. **Dispatch the fixer:** Agent, `subagent_type: "orchestrate-issues:fixer"`, `run_in_background: true`, `isolation: "worktree"`, `name: "fix-40-r3"`, `model: "opus"`.
   ```
   REPO:   acme/ledger
   ISSUE:  #40
   PR:     #70
   BRANCH: <PR #70 head branch>
   ROUND:  3
   [CATCH UP: <default branch>]   # only if step 2 says so

   --- ISSUE BODY ---
   <#40 body, verbatim>
   --- END ISSUE BODY ---
   ```
4. **Wait.** Other lanes advance as their notifications arrive. No `AskUserQuestion`.
5. **When fix-40-r3 returns `FILES: tests-only`**, confirm it (read-only):
   `gh api repos/acme/ledger/compare/<REVIEWED_SHA>...<new head sha> --jq '[.files[].filename]'`
   - **Test files only:** dispatch the verifier: Agent, `subagent_type: "orchestrate-issues:verifier"`, `run_in_background: true`, `isolation: "worktree"`, `name: "verify-40-r3"`, `model: "sonnet"`.
     ```
     REPO:         acme/ledger
     PR:           #70
     BRANCH:       <PR #70 head branch>
     ROUND:        3
     REVIEWED_SHA: <REVIEWED_SHA>
     ```
   - **Production code touched:** dispatch a fresh reviewer instead: `subagent_type: "orchestrate-issues:spec-reviewer"`, `run_in_background: true`, `isolation: "worktree"`, `name: "review-40-r4"`, `model: "opus"`. Its card carries the #40 body verbatim, plus a VERIFY block asking it to confirm the short-position refusal is tested and to explain why production code changed for a test-only finding.
6. **If the result is PASS, land it.**
   - **Under `auto`:**
     - `gh pr ready 70 --repo acme/ledger`
     - Check the body has only `Closes #40`.
     - `gh pr checks 70 --repo acme/ledger --watch --interval 60 --fail-fast`, run in the background.
     - If it's behind: `gh pr update-branch 70 --repo acme/ledger`.
     - On green: `gh pr merge 70 --repo acme/ledger --squash --delete-branch`.
     - Confirm #40 closed, then prune lane-40 worktrees (`git worktree list` / `remove --force` / `prune`) and re-query `frontier.py`.
   - **Under `ask`:** stop at ready-for-review and add it to your morning list.
7. **If it's anything other than PASS, park the lane.** No fourth round.
   - `gh issue edit 40 --repo acme/ledger --add-label needs-human`
   - `gh pr comment 70 --repo acme/ledger --body "## OWNER DECISION NEEDED …"`. The comment says it's a converging stop, links the thread, names the open finding, and gives my recommendation.
   - Free the slot, keep the other lanes going, and add #40 to the batched questions in the status line and the final report.