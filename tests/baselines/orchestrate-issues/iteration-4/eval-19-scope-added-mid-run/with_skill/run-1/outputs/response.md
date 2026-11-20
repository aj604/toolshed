# What I do at 3am: merge both, close the issues, dispatch #343. No question to you.

Rehearsal: nothing below was run, and no agent was dispatched. These are the commands I would run, in order.

## The decision

I merge #412 and #413 into `feat/atlas-export` now, without waking you or waiting for a new yes.

- **The contract already covers it.** You agreed `auto` merge into `feat/atlas-export` on review pass + green CI. That authority belongs to the branch, not to the #300 issue list.
- **You added #340 yourself, onto the same branch.** "pick up #340 next, same branch" is scope you added mid-run, and it names no new target. A new yes is only needed for a new target: another branch, or `main`.
- **Waiting costs the run.** #343 can't start until #341 closes. Two green PRs sitting idle until you wake up would hold the rest of the #340 graph for hours.

What I do not do: merge anything into `main`, use `--admin`, or touch a ruleset. The landing PR into `main` stays yours.

## Commands, in order

`<skill>` is `plugins/workbench/skills/orchestrate-issues`.

### 1. Check both PRs before touching them

```bash
gh pr view 412 --repo acme/atlas --json baseRefName,isDraft,body,headRefOid,mergeStateStatus,statusCheckRollup
gh pr view 413 --repo acme/atlas --json baseRefName,isDraft,body,headRefOid,mergeStateStatus,statusCheckRollup
```

I confirm for each:

- the base is `feat/atlas-export`;
- the body's only `Closes` line is `Closes #341` (for #412) and `Closes #342` (for #413);
- whether it is still a draft, and whether it is behind its base.

A wrong `Closes` line or a wrong base parks that PR and I say so in the status line. The other one still proceeds.

### 2. Land #412 first (it is the one that unblocks #343)

```bash
gh pr update-branch 412 --repo acme/atlas        # only if step 1 showed it behind
gh pr ready 412 --repo acme/atlas                # only if still a draft
```

If either of those ran, it started a new CI run, so the green I saw in step 1 no longer counts. I watch in the background, never in the foreground:

```bash
# run_in_background: true
gh pr checks 412 --repo acme/atlas --watch --interval 60 --fail-fast
```

When the watch reports back (or straight away, if neither command above was needed), I read the rollup again as its own command:

```bash
gh pr view 412 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
```

I merge only if every check on that head finished `SUCCESS`, `SKIPPED` or `NEUTRAL`, at least one actually ran, and `mergeStateStatus` is `CLEAN`. Then, as a separate command, with the SHA I just read:

```bash
gh pr merge 412 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid of 412>
```

Then reclaim the disk for that lane:

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr 412
df -h .
```

### 3. Close #341 by hand and confirm it

`Closes #341` does not fire, because the merge went into a feature branch, not `main`.

```bash
gh issue view 341 --repo acme/atlas --json state --jq .state
gh issue close 341 --repo acme/atlas --comment "Landed in #412 (merged into feat/atlas-export)."
gh issue view 341 --repo acme/atlas --json state --jq .state      # must say CLOSED before I re-query
```

### 4. Land #413

The #412 merge moved the base under #413, so I bring it up to date first and let CI run on the new head.

```bash
gh pr update-branch 413 --repo acme/atlas        # if it conflicts, I dispatch workbench:rebaser (rebase-342) instead
gh pr ready 413 --repo acme/atlas                # only if still a draft
# run_in_background: true
gh pr checks 413 --repo acme/atlas --watch --interval 60 --fail-fast
```

While that watch runs I go on to step 5; I don't sit on it. When it reports:

```bash
gh pr view 413 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
gh pr merge 413 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid of 413>
python3 <skill>/scripts/prune_worktrees.py --apply --pr 413
gh issue view 342 --repo acme/atlas --json state --jq .state
gh issue close 342 --repo acme/atlas --comment "Landed in #413 (merged into feat/atlas-export)."
gh issue view 342 --repo acme/atlas --json state --jq .state
```

A conflict-free update needs no fresh spec review; CI is its check. If a rebaser reports a `semantic` resolution, #413 gets a fresh reviewer (`review-342-r2`) before it merges.

### 5. Re-query the frontier and dispatch #343

Right after #341 is confirmed closed (step 3), not after #413 lands:

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 340
```

I expect #343 to read `ready`. If it still reads blocked and the script warns that the summary disagrees with the edges, I trust the edges.

Then, for #343 and any other issue the query shows ready, lowest number first, up to the 3-lane cap:

1. Read the issue body. If the work is something only a person can do, I add `needs-human` and leave it.
2. Check it against the other in-flight lane (#413, until it merges) for shared files or sequence numbers, and fence or serialise if they overlap.
3. Re-run its premise check only if the #412 merge touched code its claims are about (`workbench:premise-checker`, `premise-343`).
4. Claim it:

   ```bash
   gh issue edit 343 --repo acme/atlas --add-assignee @me
   ```

5. Dispatch `workbench:implementer`, `name: "impl-343"`, `run_in_background: true`, `isolation: "worktree"`, with a lane card: `BASE: feat/atlas-export`, the full issue body inlined, and the few facts #341's lane established under `VERIFIED CONTEXT`.

After #413 merges and #342 closes, I query the frontier again and fill any lane that opened.

### 6. Keep the landing PR honest

The #300 graph finished this afternoon, so the landing PR (`feat/atlas-export` into `main`) should already be open. These merges add #340's work to it.

```bash
gh pr list --repo acme/atlas --base main --head feat/atlas-export --state all --json number,state,url
```

- If it is open, I update its body to list #341 / #412 and #342 / #413, and note that #340's remaining issues are still in flight. I do not merge it.
- If you already merged it, I stop and tell you before merging more into the branch, because "same branch" would then mean something different from what you agreed.

## If something refuses

- **A check goes red after `update-branch` or `ready`.** No merge. A failure this PR caused goes to a fresh fixer; anything else follows the flaky-gate protocol. The other PR keeps moving.
- **The harness denies `gh pr merge`.** I leave that PR ready and green, keep every other lane moving, and put this in the status line: *"Merge of #412 into `feat/atlas-export` was denied. Reply `merge on green into feat/atlas-export` and I'll land it and everything queued behind it."* I retry with the same command once you have answered, and by no other route.
- **Branch protection refuses the merge.** That PR is yours. I don't bypass it.

## Status line you'd read in the morning

Written only from what actually ran, for example:

> #412 merged into `feat/atlas-export`, #341 closed by hand. #413 merged, #342 closed by hand. #343 unblocked and dispatched (`impl-343`). Landing PR #<n> updated, not merged: it is yours. No open questions.
