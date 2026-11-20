# Landing PR #430 (issue #360) into `feat/atlas-export`

Rehearsal only: nothing below was run, and no agent was dispatched.

## The short version

PR #430 is not mergeable on what `gh pr checks 430` shows now. Lint passed, but `unit` and `e2e` are skipped only because the PR is a draft, so the suites have not run on this code at all. The order is: update the branch, mark it ready so the suites start, wait for them in the background, read the states, merge, then close #360 by hand because `feat/atlas-export` is not the default branch.

One point where the skill pulls two ways, and which text I follow: its `gh` recipes say to merge when every check state is `SUCCESS` (or `SKIPPED`/`NEUTRAL`). Its Step 3 says that when workflows skip drafts, CI only starts at `gh pr ready`, and Step 5 puts `update-branch` first "so green means green on the head you merge". I follow the second pair. A skip caused by draft status is a suite that hasn't started, not one that passed, so I don't merge until `unit` and `e2e` report `SUCCESS` on the head I'm merging. A skip that remains after `ready` for another reason (a path filter, say) I'd look at before treating it as acceptable.

## Commands, in order

### 1. Bring the branch up to date first

```bash
gh pr update-branch 430 --repo acme/atlas
```

The PR is 3 commits behind with no conflicts, so this merges `feat/atlas-export` in and produces a new head. It goes before `ready` so the suites run once, against the head that will merge. No rebase agent is needed, and no fresh spec review: a conflict-free catch-up is mechanical and CI is its check.

What I look at before the next command:

```bash
gh pr view 430 --repo acme/atlas \
  --json headRefOid,baseRefName,isDraft,mergeable,mergeStateStatus,body
```

- `headRefOid` changed, so the update landed. Note the new SHA.
- `baseRefName` is `feat/atlas-export`.
- `mergeable` is not `CONFLICTING`. If the update had reported a conflict after all, I'd stop here and dispatch `workbench:rebaser` (`rebase-360`) instead of continuing.
- `body` has exactly one `Closes` line and it names #360. A clobbered body would close the wrong node.

### 2. Take it out of draft so the suites run

```bash
gh pr ready 430 --repo acme/atlas
```

What I look at:

```bash
gh pr checks 430 --repo acme/atlas --json name,state
```

`unit` and `e2e` should have left `SKIPPED` and be `PENDING` (or queued) on the new head. If they still read `SKIPPED`, the ready event did not trigger them. I would not merge on that; I'd find out why the workflows skipped before going further.

### 3. Wait for CI in the background

```bash
# run_in_background: true
gh pr checks 430 --repo acme/atlas --watch --interval 60 --fail-fast
```

Never in the foreground: a foreground watch blocks every other lane. While it runs I keep advancing other lanes.

When it reports back, I don't trust the exit code or silence (exit 1 covers both "a check failed" and "no checks reported"; 8 means pending). I re-read the states:

```bash
gh pr checks 430 --repo acme/atlas --json name,state
gh pr view 430 --repo acme/atlas --json headRefOid,mergeStateStatus
```

Merge only if all of these hold:

- `lint`, `unit` and `e2e` are each `SUCCESS`. Not skipped, not pending.
- `headRefOid` is still the SHA from step 1, so the green belongs to the head being merged.
- The PR is not behind `feat/atlas-export` again. If a sibling lane merged while CI ran, I run `gh pr update-branch` once more and wait for checks again.

If anything is red:

- Plainly this PR's fault: a fresh `workbench:fixer` gets the failing job's output as the finding (posted as a PR comment if long). I don't fix it myself and I don't wake the implementer.
- Not plainly this PR's fault: the flaky-gate protocol. `gh pr update-branch` for a fresh sample (a rerun is the same data point), and on a second strike a read-only `workbench:ci-diagnostic`, not a fixer.
- Never merge over red, skip the check, or route around it.

### 4. Merge

```bash
gh pr merge 430 --repo acme/atlas --squash --delete-branch
```

No `--admin`. If branch protection on `feat/atlas-export` refuses the merge, that is an escalation to you, not something `auto` covers.

What I look at:

```bash
gh pr view 430 --repo acme/atlas --json state,mergedAt,mergeCommit
```

`state` is `MERGED`. I check this before writing down that it landed.

### 5. Reclaim the lane's worktrees

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr 430
df -h .
```

I read what the script kept and why. A worktree kept for uncommitted changes or unpushed commits is a lane that didn't finish cleanly, and I'd look before deleting it by hand.

### 6. Close #360 by hand

`Closes #360` fires only on merges into the default branch. This merge went into `feat/atlas-export`, so the issue stays open and everything downstream stays blocked unless I close it.

```bash
gh issue view 360 --repo acme/atlas --json state --jq .state
gh issue close 360 --repo acme/atlas --comment "Landed in #430."
gh issue view 360 --repo acme/atlas --json state --jq .state
```

The last command must print `CLOSED` before I move on. A frontier query against an unclosed node only tells me the graph is stuck.

### 7. Re-query the frontier

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas <the run's scope selector>
```

You didn't give me the scope selector (`--parent N`, `--label X`, `--milestone N` or `--issues ...`), so I've left a placeholder. This shows what closing #360 unblocked, and I fill free lanes from it, lowest issue number first. If a newly unblocked node still reads blocked and the script warns that the dependency summary disagrees with the edges, I trust the edges.

## After the merge

The merge moves `feat/atlas-export` under every other in-flight lane. I don't rebase them all:

- A lane with a real conflict, or whose code calls something #430 changed, gets `workbench:rebaser` before its review.
- A lane with a fix round pending gets `CATCH UP: feat/atlas-export` on its fixer card.
- A lane that is merely behind is left alone until it has PASSed, then gets one `gh pr update-branch` right before its own merge.

Status line once all of this has actually run: "#360 landed via #430 into feat/atlas-export, closed by hand; unblocked: <from the frontier query>; in flight: <lanes>."
