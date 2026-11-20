# Landing PR #430 (issue #360) into `feat/atlas-export`

Rehearsal: nothing below has been run. This is the sequence I would run, in order, and what I would read between commands.

**PR #430 is not green yet.** `lint pass, unit skipping, e2e skipping` is a draft's run: the workflows skip the real suites on drafts, so unit and e2e have never run on this code. The PR is also 3 commits behind, so even a full run now would test a head that isn't the one I'd merge.

Your "auto merge into feat/atlas-export" is the merge grant, so I won't ask again. It covers `gh pr merge` through the front door only: no `--admin` and no bypass.

## The sequence

Each command is its own call. None of them is chained to the next with `&&` or `;`.

### 1. Catch the branch up first

```bash
gh pr update-branch 430 --repo acme/atlas
```

This goes before `gh pr ready`, so that the full CI run happens on the head I will merge.

**What I look at:** that the command succeeded and the PR head moved to a new merge commit. It is a conflict-free catch-up, so it needs no fresh spec review; CI is its check. If it reports a conflict after all, I stop here and dispatch a `workbench:rebaser` (`rebase-360`) instead of resolving it myself.

### 2. Take it out of draft

```bash
gh pr ready 430 --repo acme/atlas
```

**What I look at:** that the PR is no longer a draft. This starts a new CI run, and it is the first one where unit and e2e actually execute.

### 3. Watch CI in the background

```bash
# run_in_background: true
gh pr checks 430 --repo acme/atlas --watch --interval 60 --fail-fast
```

It runs in the background so other lanes keep advancing while it waits. `--interval 60` keeps the polling from draining the API rate limit.

**What I look at:** nothing yet. When the watch reports back, that is a prompt to look, not a verdict. It can end without the run being green in three ways:

- **Stale results.** A watch started right after `ready` or `update-branch` can see the previous run's rows (`lint pass`, two `skipping`) and exit 0 while the real run is only queued.
- **Early exit on failure.** `--fail-fast` exits on the first failure while other checks are still pending. That is a red run.
- **Late jobs.** Path-scoped or late-queued jobs can start after the watch has exited.

### 4. Read the rollup for the current head

```bash
gh pr view 430 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup,isDraft,baseRefName,body
```

**What I look at**, all of which must hold before I merge:

- **Every check finished.** Each entry in `statusCheckRollup` is `COMPLETED` with conclusion `SUCCESS`, `SKIPPED` or `NEUTRAL`. Nothing is `PENDING`, `QUEUED`, `IN_PROGRESS` or `FAILURE`.
- **Unit and e2e ran.** They show `SUCCESS`, not `SKIPPED`. A skip here would be the draft skip again, which means I'm reading the old run. A skip only counts as green when it is a path filter in the post-ready run, and that doesn't apply to a PR whose suites are meant to run.
- **It is the right run.** The checks belong to `headRefOid` (the post-`update-branch` commit) and started after `gh pr ready`.
- **`mergeStateStatus` is `CLEAN`.** `UNKNOWN` means GitHub is still computing it, so I read again in a minute. `BEHIND` means the base moved again, so I go back to step 1. `BLOCKED` or `DIRTY` means I don't merge.
- **The PR is what I think it is.** `isDraft` is false, `baseRefName` is `feat/atlas-export`, and the body's only `Closes` line is `Closes #360`.

I note the `headRefOid` value for the next command.

If checks are still running, I start the background watch again and re-read afterwards. If any check is red, see *If it goes wrong* below.

### 5. Merge that exact SHA

Only if step 4 showed the whole run green:

```bash
gh pr merge 430 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid from step 4>
```

**What I look at:** that the merge succeeded. `--match-head-commit` makes the merge fail if anything was pushed after I read the rollup, in which case I go back to step 3 for the new head.

### 6. Reclaim the lane's worktrees

```bash
python3 <repo>/plugins/workbench/skills/orchestrate-issues/scripts/prune_worktrees.py --apply --pr 430
df -h .
```

**What I look at:** what the script kept and why. A worktree kept for uncommitted changes or unpushed commits is a lane that didn't finish cleanly, and I'd look at it before deleting anything by hand.

### 7. Close issue #360 by hand

`feat/atlas-export` is not the default branch, so `Closes #360` won't fire on this merge.

```bash
gh issue view 360 --repo acme/atlas --json state --jq .state
```

**What I look at:** if it prints `OPEN`, which I expect:

```bash
gh issue close 360 --repo acme/atlas --comment "Landed in #430."
gh issue view 360 --repo acme/atlas --json state --jq .state
```

**What I look at:** `CLOSED`. I confirm this before re-querying, because an unclosed #360 keeps everything downstream blocked while reporting nothing wrong.

### 8. Re-query the frontier

```bash
python3 <repo>/plugins/workbench/skills/orchestrate-issues/scripts/frontier.py --repo acme/atlas <this run's scope selector>
```

I use the same selector the run started with (`--parent N`, `--label X`, `--milestone N` or `--issues ...`); your message doesn't say which it is.

**What I look at:** #360 as done, which issues its close made ready (those get claimed and dispatched up to the concurrency cap), and which in-flight lanes are now behind `feat/atlas-export`. A lane that is merely behind gets no rebase until it has passed review.

## If it goes wrong

- **A check is red and it's measuring this PR.** I don't merge. I dispatch a fresh `workbench:fixer` (`fix-360-r1`) with the failing job's output posted on the PR as the finding. I don't fix it myself and don't wake the implementer.
- **A check is red and it isn't plainly this PR's fault.** I follow the flaky-gate protocol: a rerun is not a fresh sample, `update-branch` is. A second failure gets a read-only `workbench:ci-diagnostic`, not a fixer.
- **A check is red for an outside reason** (a rate-limited preview deploy, a runner that never picked up the job). It is still red. Waiving it is your call, per check and in your words. I park #430 and tell you which check.
- **The merge is denied by the permission system or branch protection.** I leave #430 ready and green, keep the other lanes moving, and tell you: "Merge of #430 into `feat/atlas-export` was denied. Reply `merge on green into feat/atlas-export` and I'll land it and everything queued behind it." I retry with the same `gh pr merge` command once you've replied.
