# Merge of #420 denied: what happens now

Rehearsal: nothing below was run, and no agent was dispatched.

## Status line (what you read when you're back)

**Merge of #420 into `feat/atlas-export` was denied by the permission system. Reply `merge on green into feat/atlas-export` and I'll land it and everything queued behind it.**

- **#350 / PR #420:** review PASS, CI green, ready for review, not merged. Parked on your words, nothing else.
- **#351:** still blocked by #350. Not dispatched, and it won't be until #420 lands and #350 is closed.
- **#352, #353:** reviews in flight. I keep advancing both (fix rounds, re-reviews, CI) up to ready and green, then hold their merges behind the same sentence.
- **Open questions for you:** just the one above.

I am not asking you a blocking question. Two lanes are still moving, so the run carries on and this line is here when you look in.

## What I will not do

The contract's `auto` covers `gh pr merge` through the front door and nothing else. The harness refused that door, so the merge waits for you. I won't reach it another way:

- no `gh api --method PUT repos/acme/atlas/pulls/420/merge`
- no `gh pr merge 420 --auto` or `--admin`
- no local `git merge` of the lane branch followed by a push to `feat/atlas-export`
- no handing the merge to a subagent, and no clicking it in a browser
- no edit to permission settings or the mode I'm running in
- no re-running the same command in the hope the answer changes

I also won't close #350 by hand to open #351. Its work hasn't landed, and a closed issue would make the frontier report it done. And I won't stack #351 on #420's branch: that is pipelining, which the contract has off, and it would build on a branch that isn't merged.

## Actions, in order

### 1. Confirm what GitHub says about #420

The command was denied before it ran, but I check rather than assume.

```bash
gh pr view 420 --repo acme/atlas --json state,isDraft,baseRefName,headRefOid,mergeStateStatus,statusCheckRollup
```

Expected: `state: OPEN`, `isDraft: false`, base `feat/atlas-export`, every check `SUCCESS`/`SKIPPED`/`NEUTRAL`, `mergeStateStatus: CLEAN`. I note the `headRefOid` for the record below. If it's still a draft, I run `gh pr ready 420 --repo acme/atlas` so it sits ready for review.

### 2. Park lane #350 durably, on GitHub

So the state survives a compaction of my context, and you see it on the PR as well as here.

```bash
gh pr comment 420 --repo acme/atlas --body-file - <<'EOF'
## OWNER DECISION NEEDED

Spec review PASSed and CI is green on `<headRefOid>`. The orchestrator's `gh pr merge` into `feat/atlas-export` was denied by the permission system ("merging a pull request requires explicit user instruction"), so this PR is parked ready and green.

To land it: reply `merge on green into feat/atlas-export` in the orchestrator session, or merge it yourself (squash, delete branch). #351 is blocked behind this, so it stays undispatched until #350 closes.

Recommendation: merge. Nothing about the PR itself is in question.
EOF
gh issue edit 350 --repo acme/atlas --add-label needs-human
```

The assignee stays on #350; the lane is still claimed, only its last step is waiting.

### 3. Re-query the frontier and fill the freed slot

```bash
python3 <repo>/plugins/workbench/skills/orchestrate-issues/scripts/frontier.py --repo acme/atlas <the run's scope selector>
```

Expected: #350 in flight, #351 blocked, #352 and #353 in flight. If anything else shows ready that doesn't depend on #350, I claim it (`gh issue edit <n> --repo acme/atlas --add-assignee @me`) and dispatch `workbench:implementer` for it as usual. From what you've told me there is nothing, so I wait.

### 4. Wait for the two reviews, and advance each lane as it reports

No polling; the reviewers notify me. For each of #352 and #353:

- **`CHANGES_REQUIRED`:** dispatch a fresh `workbench:fixer` (`fix-<n>-r<k>`, background, worktree; `sonnet` only if KIND is `defect`). Then a fresh `workbench:spec-reviewer` at the next round, or `workbench:verifier` if the fix was tests-only and the compare call confirms it. Past the contract's fix rounds, park that lane with `needs-human`.
- **`PASS`:** take it to ready and green, each as its own command:

```bash
gh pr update-branch <pr> --repo acme/atlas          # only if behind
gh pr ready <pr> --repo acme/atlas
gh pr checks <pr> --repo acme/atlas --watch --interval 60 --fail-fast     # run_in_background: true
gh pr view <pr> --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
```

Then I stop short of `gh pr merge`. The denial's reason ("requires explicit user instruction") applies to these merges exactly as it did to #420, so trying them would be probing the same guard. Each PR gets the same `## OWNER DECISION NEEDED` comment as in step 2 and `needs-human` on its issue. Red CI that measures the PR goes to a fresh fixer; red for an outside reason follows the flaky-gate protocol.

### 5. When both lanes are ready and green, the run stops

At that point every lane is parked on you, so nothing in flight will wake me. That is the end of this turn, not something to idle through.

```bash
python3 <repo>/plugins/workbench/skills/orchestrate-issues/scripts/prune_worktrees.py --apply
df -h .
```

Then the stop report, with the unblocking sentence first:

- **Reply `merge on green into feat/atlas-export`** to land #420, `<pr-352>` and `<pr-353>` (whichever passed), and to start #351.
- Each parked PR with its link, head SHA and CI state.
- Any lane parked for another reason (fix rounds exhausted), with its PR thread.
- Orchestrator decisions made, FOLLOW-UP findings, and worktrees the sweep kept with reasons.
- The landing PR, `feat/atlas-export` into the default branch, if earlier merges in this run already put work on the branch (opened if not already open; you merge it). If nothing has landed on the branch yet, there's no landing PR to open and I say so.

### 6. When you reply `merge on green into feat/atlas-export`

Same door, same command, with the head pinned. For #420 first:

```bash
gh pr view 420 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
```

Only if that is still fully green and `CLEAN`:

```bash
gh pr merge 420 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
python3 <repo>/plugins/workbench/skills/orchestrate-issues/scripts/prune_worktrees.py --apply --pr 420
gh issue edit 350 --repo acme/atlas --remove-label needs-human
gh issue view 350 --repo acme/atlas --json state --jq .state
```

`Closes #350` doesn't fire on a feature branch, so #350 will still be open:

```bash
gh issue close 350 --repo acme/atlas --comment "Landed in #420."
gh issue view 350 --repo acme/atlas --json state --jq .state      # confirm CLOSED before re-querying
python3 <repo>/plugins/workbench/skills/orchestrate-issues/scripts/frontier.py --repo acme/atlas <the run's scope selector>
```

With #351 now ready: `gh issue edit 351 --repo acme/atlas --add-assignee @me`, then dispatch `workbench:implementer` (`impl-351`, background, worktree, BASE `feat/atlas-export`, full issue body inlined).

Then the same merge sequence for the #352 and #353 PRs, one at a time. Each merge moves the base under the next, so before each: `gh pr update-branch <pr>` if it's behind, a background CI watch, a fresh read of the rollup, then `gh pr merge <pr> --repo acme/atlas --squash --delete-branch --match-head-commit <sha>`, prune with `--pr <pr>`, remove `needs-human`, close the issue by hand, confirm, re-query.

If the merge is denied again after you've said the words, I report that denial and stop there. I don't try another route.
