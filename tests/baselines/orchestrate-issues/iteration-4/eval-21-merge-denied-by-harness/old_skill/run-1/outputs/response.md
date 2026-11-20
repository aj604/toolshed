# #420 is not merged, and I won't force it

The merge of PR #420 was refused by the harness, not by GitHub: the auto-mode classifier wants an explicit instruction from you for a merge. I treat that the same way as a branch protection refusing: it goes to you. The `auto` in our contract covers `gh pr merge` through the front door and nothing else.

So I will not:

- retry the same merge, or reach it another way (`gh api .../pulls/420/merge`, a subagent told to merge, a local `git merge` and push to `feat/atlas-export`);
- change permission settings or the mode I'm running in;
- attempt the merges of #352 and #353 when they pass. The refusal is about merging as such, so those would be refused for the same reason.
- stop and wait on a blocking question. You're away for hours, and only the merge step is stuck.

The rest of the run carries on. Every lane goes as far as "passed review, green, ready to merge" and parks there, which is what the contract's `ask` merge authority does.

**What this costs you:** #351 can't start until #350 is merged and closed, so it waits for you. Nothing else is lost. When you're back, one message ("merge 420" or "merge whatever is parked") clears it.

## Actions, in order

Rehearsal: none of these has been run.

### 1. Confirm what actually happened to #420

A denied command should have changed nothing, but I check before I write it down.

```bash
gh pr view 420 --repo acme/atlas --json state,mergedAt,isDraft,baseRefName,mergeStateStatus,headRefName
gh issue view 350 --repo acme/atlas --json state,labels,assignees
```

Expected: PR `OPEN`, `mergedAt` null, base `feat/atlas-export`; issue #350 `OPEN`.

### 2. Park the #350 lane, and only that lane

Post the question on the PR, label the issue, and free the lane's slot.

```bash
gh pr comment 420 --repo acme/atlas --body-file - <<'OWNER_EOF'
## OWNER DECISION NEEDED — merge refused by the harness

This PR (issue #350) passed spec review and every check is green. The run contract says auto merge into `feat/atlas-export`, but the merge command was refused locally:

> Permission for this action was denied by the auto-mode classifier: merging a pull request requires explicit user instruction.

GitHub did not refuse it; the session's permission layer did. I have not retried it or routed around it.

**Recommendation:** merge it. Either tell the orchestrator "merge 420", or run:

    gh pr merge 420 --repo acme/atlas --squash --delete-branch
    gh issue close 350 --repo acme/atlas --comment "Landed in #420."

The manual close is needed because `feat/atlas-export` is not the default branch, so `Closes #350` will not fire. #351 stays blocked until #350 is closed.

**Alternative:** leave it open. #351 then stays blocked.
OWNER_EOF

gh issue edit 350 --repo acme/atlas --add-label needs-human
```

### 3. Leave #351 alone

It is blocked by #350, and #350 is still open. Pipelining is off in the contract, so I don't dispatch #351 stacked on #420's branch. I re-query to confirm nothing else became ready:

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas <the run's scope selector> --json
```

Expected: #350 in flight (open PR, `needs-human`), #351 blocked, #352 and #353 in flight, nothing ready. If something outside this chain is ready, it gets dispatched into the freed slot as usual.

If you'd rather #351 started now on top of #420's branch, say so; that is turning pipelining on, and it's your call.

### 4. Wait for the #352 and #353 reviews

No polling. The reviewers notify me when they finish. Each lane then advances as normal, up to but not including the merge:

- **`CHANGES_REQUIRED`:** dispatch a fresh `workbench:fixer` (`fix-352-r1` / `fix-353-r1`), model by `KIND`, then a fresh `workbench:spec-reviewer` or a `workbench:verifier` for a tests-only fix. Up to the contract's two fix rounds.
- **`PASS`:** take the PR to ready and green, in the background:

```bash
gh pr update-branch <pr> --repo acme/atlas        # only if it is behind feat/atlas-export
gh pr ready <pr> --repo acme/atlas
gh pr checks <pr> --repo acme/atlas --watch --interval 60 --fail-fast    # run_in_background: true
```

- **Green:** confirm the body's only `Closes` line names the right issue, then park the lane the same way as #350, without attempting the merge:

```bash
gh pr view <pr> --repo acme/atlas --json body --jq .body | grep -iE 'clos(e|es|ed) #'

gh pr comment <pr> --repo acme/atlas --body-file - <<'OWNER_EOF'
## OWNER DECISION NEEDED — ready to merge, waiting on you

Passed spec review, all checks green. Not merged: the harness refused the merge of #420 for want of an explicit user instruction, and the same applies here, so I did not attempt it.

**Recommendation:** merge it.

    gh pr merge <pr> --repo acme/atlas --squash --delete-branch
    gh issue close <n> --repo acme/atlas --comment "Landed in #<pr>."
OWNER_EOF

gh issue edit <n> --repo acme/atlas --add-label needs-human
```

- **Red CI on the PR's own check:** a fresh fixer. Anything that looks like a flake or a broken gate goes through the flaky-gate protocol first.

### 5. End the run when every lane is parked

Once #352 and #353 are parked (or have used up their fix rounds), nothing is left that can wake me, so the run ends. Sweep the finished worktrees, then report:

```bash
python3 <skill>/scripts/prune_worktrees.py --apply
df -h .
python3 <skill>/scripts/frontier.py --repo acme/atlas <the run's scope selector>
```

The final report will list:

- **Landed:** nothing this cycle.
- **Waiting on you:** #420 (#350), plus #352's and #353's PRs if they passed, each with its link and "merge it" as my recommendation.
- **Still blocked:** #351, behind #350.
- Any lane parked for fix rounds, reviewer FOLLOW-UP findings, and worktrees the sweep kept, with reasons.

## When you're back

Say "merge 420", or "merge everything parked". With that instruction I'd run, per PR:

```bash
gh pr merge 420 --repo acme/atlas --squash --delete-branch
python3 <skill>/scripts/prune_worktrees.py --apply --pr 420
gh issue view 350 --repo acme/atlas --json state --jq .state
gh issue close 350 --repo acme/atlas --comment "Landed in #420."     # feat/atlas-export isn't the default branch
gh issue edit 350 --repo acme/atlas --remove-label needs-human
python3 <skill>/scripts/frontier.py --repo acme/atlas <the run's scope selector>
```

That close is what unblocks #351, which I'd then claim and dispatch. If the classifier still refuses after your instruction, the fix is a permission rule on your side, and I'd tell you that instead of working around it.
