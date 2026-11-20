# Remaining steps for the #300 run on `acme/atlas` (rehearsal, nothing run)

The graph is done, but the work is on `feat/atlas-export`, not on `main`. I finish landing the last node, clean up, and stop. I do not take `feat/atlas-export` to `main`, and I do not merge `main` into it: neither was in the contract, and you're asleep. That hand-off is the one decision waiting for you.

`<pr>` is the PR that just merged and `<n>` is the issue it implements. `<skill>` is the skill's folder.

## 1. Confirm the last merge from GitHub

I check rather than trust the notification.

```bash
gh pr view <pr> --repo acme/atlas --json state,mergedAt,baseRefName,mergeCommit,body
```

I expect `MERGED`, base `feat/atlas-export`, and a body whose only `Closes` line names `#<n>`.

## 2. Confirm every node is really closed

`Closes #<n>` only fires on a merge into the default branch, so no merge in this run closed its issue automatically. Each one needed a manual close.

```bash
gh issue view <n> --repo acme/atlas --json state,stateReason,closedAt --jq .
# only if it is still OPEN:
gh issue close <n> --repo acme/atlas --comment "Landed in #<pr> (merged into feat/atlas-export, not yet on main)."

gh api repos/acme/atlas/issues/300/sub_issues --paginate --jq '[.[]|{number,title,state}]'
```

The second call is a cross-check on "complete": every sub-issue closed, and each closed against a merged PR.

## 3. Prune the finished lane's worktrees

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr <pr>
df -h .
```

## 4. Re-query the frontier one last time

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300
```

I'm looking for three things:

- **Still `complete`**, with no warnings.
- **No new issue filed under #300 mid-run.** If one appeared, the contract says I list it and don't dispatch it.
- **No `split_complete` container left open.** If one is, I close it with a comment listing its children's PRs.

## 5. Measure the gap to `main`, read-only

This changes nothing on GitHub or in any branch. It tells you how hard the hand-off is.

```bash
git fetch origin
git log --oneline origin/feat/atlas-export..origin/main        # the 14 commits
git log --oneline origin/main..origin/feat/atlas-export        # what the run added
MB=$(git merge-base origin/main origin/feat/atlas-export)
git diff --stat "$MB" origin/main                              # which files main touched
git diff --name-only "$MB" origin/main > /tmp/atlas-main-files.txt
git diff --name-only "$MB" origin/feat/atlas-export > /tmp/atlas-feat-files.txt
comm -12 <(sort /tmp/atlas-main-files.txt) <(sort /tmp/atlas-feat-files.txt)   # files both sides changed
git merge-tree --write-tree origin/main origin/feat/atlas-export               # textual conflicts, no checkout
gh api "repos/acme/atlas/commits/feat%2Fatlas-export/check-runs" --jq '[.check_runs[]|{name,conclusion}]'
gh pr list --repo acme/atlas --base main --head feat/atlas-export --state all --json number,state,url
```

A clean `merge-tree` only rules out textual conflicts. Every PR in this run was reviewed and tested against `feat/atlas-export` as it stood, so none of them has been checked against those 14 commits. Changes in the same module can break behaviour without conflicting.

## 6. What I leave alone, and why

- **No merge of `feat/atlas-export` into `main`.** Merge authority is `ask` by default, it covers this run's scope only, and a merge can't be undone. Shipping the branch to `main` is a new scope and needs a new yes.
- **No merge of `main` into `feat/atlas-export`, and no rebaser dispatched for it.** That would change what the branch does after every review has finished, in a module `main` also changed, with nobody reviewing the result.
- **No PR to `main` opened by me.** It isn't a node in the graph. I recommend it below instead.
- **#300 stays open.** It is the scope container, and its work isn't on `main` yet. Closing it would make the epic read as shipped.
- **No bypass of any kind** (`--admin`, ruleset edits), which the contract never allows.

## 7. Record the open decision on #300

It goes on GitHub so it outlasts this session.

```bash
gh issue comment 300 --repo acme/atlas --body-file - <<'EOF'
## OWNER DECISION NEEDED

Every sub-issue of #300 is closed and its PR is merged into `feat/atlas-export`.
None of it is on `main`.

`main` is 14 commits ahead of the point the branch was cut, and <K> of the files
those commits changed were also changed by this run: <files>.
`git merge-tree` reports <clean | conflicts in: ...>.
Nothing in this run was reviewed or tested against those 14 commits.

Decision: how `feat/atlas-export` reaches `main`.

Recommended: merge `main` into `feat/atlas-export` on its own PR, run the whole
suite and a spec review of the overlap in <module>, then open the PR to `main`
and merge it yourself.

Alternative: open `feat/atlas-export` -> `main` directly and resolve there.

To hand it to me: say which, and whether I may merge. That is a new scope and
needs its own yes.

#300 is left open until the work is on `main`.
EOF
gh issue edit 300 --repo acme/atlas --add-label needs-human
```

## 8. Final sweep, then stop

```bash
python3 <skill>/scripts/prune_worktrees.py --apply
df -h .
```

I read what the sweep kept and why. Nothing is in flight (no agent, no background CI watch), so the run ends here rather than waiting on anything.

## 9. The end-of-run report you'd wake up to

It reports only what the commands above actually returned.

- **Landed:** each sub-issue of #300 with its PR link, all merged into `feat/atlas-export`.
- **Not on `main`:** the whole run. The 14-commit gap, the files both sides changed, the `merge-tree` result, and CI on the branch tip.
- **Still open:** #300, on purpose.
- **Waiting for you:** the one decision in step 7, with its link and my recommendation.
- **Orchestrator decisions I made under the contract:** splits filed, extra fix rounds, judgement calls, each with a link so you can reverse it. This includes every manual issue close, since none closed automatically.
- **Follow-ups:** FOLLOW-UP findings reviewers left on merged PRs, and any issue filed mid-run that I did not dispatch.
- **Worktrees the sweep kept**, with the script's reason for each.
- **Anything that didn't run**, said plainly.
