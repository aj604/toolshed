# Remaining steps for acme/atlas, parent #300 (rehearsal: nothing below was run)

The run isn't finished at `complete`. The work sits on `feat/atlas-export`, one merge away from `main`, and you need something to review when you wake up. What's left: close out the last lane, open the landing PR, catch the branch up with `main` through an agent, let CI run on the result, sweep worktrees, and report.

I would not merge into `main`. Under the default contract a merge into the default branch is `ask`, you changed nothing, and you're asleep. I also would not ask a blocking question; the landing PR and the report are how the decision reaches you.

Placeholders: `<last-pr>` and `<n>` are the PR that just merged and its issue, `<landing-pr>` is the PR opened in step 4, and `<skill>` is the `orchestrate-issues` skill folder.

## 1. Close out the last lane

`Closes #<n>` never fires on a merge into a feature branch, so I would confirm the issue closed and close it by hand if it didn't.

```bash
gh pr view <last-pr> --repo acme/atlas --json state,mergedAt,baseRefName
gh issue view <n> --repo acme/atlas --json state --jq .state
# only if that prints OPEN:
gh issue close <n> --repo acme/atlas --comment "Landed in #<last-pr>."
```

Then reclaim that lane's disk, as after every merge:

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr <last-pr>
df -h .
```

## 2. Confirm the graph from GitHub, not from memory

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300 --json
gh issue view 300 --repo acme/atlas --json state --jq .state
```

- I expect `complete`, with no `in_flight`, no `needs-human` nodes and no warnings.
- If any node reads `split_complete`, I would close it with a comment listing its children's PRs.
- Anything filed mid-run that isn't a split of an in-scope issue stays undispatched and goes in the report.
- I would report #300's own state as I find it. If it is still open, the report says so; the work has not reached `main` yet.

## 3. Read what `main` gained

Fourteen commits, some in the same module, is the case where a feature branch hides or rebuilds work `main` already has. I would read them before anyone merges anything.

```bash
git fetch origin
git log --oneline origin/feat/atlas-export..origin/main
git diff --stat origin/feat/atlas-export...origin/main
git merge-tree --write-tree origin/main origin/feat/atlas-export   # read-only: does it conflict, and where
```

I would note which of the 14 commits touch the export module, and whether any of them removes, renames or rewrites something the landed lanes build on. Those notes go into the landing PR body and the reviewer's VERIFY block in step 6.

I would not run `git merge` in my own checkout. The catch-up is an agent's job.

## 4. Open the landing PR

First check that one isn't already open, and whether the repo allows merge commits:

```bash
gh pr list --repo acme/atlas --base main --head feat/atlas-export --state open --json number,url,isDraft
gh api repos/acme/atlas --jq '{allow_merge_commit, allow_squash_merge, allow_rebase_merge}'
```

Gather the body from GitHub:

```bash
gh pr list --repo acme/atlas --base feat/atlas-export --state merged --limit 200 \
  --json number,title,mergedAt,url,body
gh api repos/acme/atlas/issues/300/sub_issues --paginate --jq '[.[]|{number,title,state}]'
# for each landed issue and PR, the decisions I recorded:
gh api "repos/acme/atlas/issues/<n>/comments" \
  --jq '.[] | select(.body | contains("## ORCHESTRATOR DECISION")) | {html_url, body}'
```

Then open it, with the body on stdin. I would open it as a draft, because the branch is 14 commits behind and I can't call it ready until the catch-up is green. The rebaser's card also needs a PR number, which is why this comes before step 5.

```bash
gh pr create --repo acme/atlas --base main --head feat/atlas-export --draft \
  --title "Atlas export (#300): land feat/atlas-export" --body-file - <<'BODY'
## What this lands
<one line per issue: #<n> <title>, landed in #<pr>>

## Orchestrator decisions
<each ORCHESTRATOR DECISION with its link: splits filed, extra fix rounds, judgement calls>

## Still open
<FOLLOW-UP findings left on merged PRs, follow-up issues filed but not dispatched, state of #300>

## Catch-up with main
main moved 14 commits since this branch was cut; <which ones touch the export module>.
A catch-up merge of main is in progress. I'll update this section with its result.

## How to merge
Merge commit, not squash (`gh pr merge <landing-pr> --repo acme/atlas --merge`), so each lane's
squash commit survives on main. <If merge commits are disabled on this repo, say so here and
leave the method to you.>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
```

If a landing PR is already open, I would skip the create and use that one.

## 5. Dispatch the catch-up

One `workbench:rebaser`, in the background, in its own worktree, on its default `sonnet`. The task is one named operation and CI checks it, which is why `sonnet` is acceptable here.

```
Agent(
  subagent_type: "workbench:rebaser",
  name: "rebase-<landing-pr>",
  run_in_background: true,
  isolation: "worktree",
  prompt:
    REPO:   acme/atlas
    PR:     #<landing-pr>
    BRANCH: feat/atlas-export
    BASE:   main
)
```

It merges `main` in and pushes; it never force-pushes. Then I would wait for its notification without polling.

If the push to `feat/atlas-export` is refused by branch protection, I would not go around it. The landing PR stays as it is and the report says the catch-up is yours.

## 6. Act on what the rebaser returns

It returns `PUSHED`, `RESOLUTION` and `TESTS`.

- **`none` or `mechanical`:** no fresh review. CI is the check; go to step 7.
- **`semantic`:** resolving a conflict changed what the code does, which is likely with same-module commits. I would dispatch a fresh `workbench:spec-reviewer` (`name: "review-<landing-pr>-r1"`, background, worktree, `opus`) on the landing PR, with the bodies of the issues whose code the conflict touched and a VERIFY block naming each resolved conflict and the overlapping `main` commits from step 3.
  - `PASS`: go to step 7.
  - `CHANGES_REQUIRED`: a fresh `workbench:fixer`, model by `KIND`, then a fresh re-review, within the 2-round budget. Past that, the PR stays a draft and the report says why.
- **It dies or returns nothing:** I would check whether a merge commit reached the branch (`gh pr view <landing-pr> --repo acme/atlas --json headRefOid,mergeable`), then dispatch a fresh rebaser from that point. I would not read its transcript.

## 7. Let CI run on the caught-up head

```bash
# run_in_background: true
gh pr checks <landing-pr> --repo acme/atlas --watch --interval 60 --fail-fast
# when that reports back, as its own command:
gh pr view <landing-pr> --repo acme/atlas --json headRefOid,mergeStateStatus,mergeable,statusCheckRollup
```

Green means every check on the current head finished `SUCCESS`, `SKIPPED` or `NEUTRAL`, at least one actually ran, and `mergeStateStatus` is `CLEAN`. (A `BLOCKED` state that only reflects a required human review is expected, and I would report it as that.)

If that is green, mark it ready. `gh pr ready` starts a new run, so I would watch and read again before reporting a CI state:

```bash
gh pr ready <landing-pr> --repo acme/atlas
# run_in_background: true
gh pr checks <landing-pr> --repo acme/atlas --watch --interval 60 --fail-fast
# then, as its own command:
gh pr view <landing-pr> --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
```

If it is red:

- **A check measuring this code:** paste the failing output into a PR comment and dispatch a fresh fixer.
- **Not plainly this PR's fault:** `gh pr update-branch` for a fresh sample; a second strike gets a read-only `workbench:ci-diagnostic`, not a fixer.
- **Red for an outside reason:** still red. I would leave the PR as a draft and name the check in the report. I would not waive it or make it green by another route.

Then update the "Catch-up with main" section of the PR body with the result (`gh pr edit <landing-pr> --repo acme/atlas --body-file -`, heredoc on stdin), and read the body back.

## 8. Stop short of the merge

No `gh pr merge` on the landing PR, no `--admin`, no ruleset or setting change. The PR is left ready for review, and the report carries the sentence that hands me the merge if you want that: *"Reply `merge #<landing-pr> into main` and I'll land it as a merge commit on green."*

## 9. Sweep and report

```bash
python3 <skill>/scripts/prune_worktrees.py --apply
df -h .
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300
```

The final report, in this order, containing only what actually happened:

1. **The landing PR:** link, CI state on its current head, how the catch-up resolved (`none`, `mechanical` or `semantic`, and whether it was re-reviewed), and that it is waiting on you to merge with a merge commit.
2. **Issues landed,** each with its PR link.
3. **What's still open and why,** including #300's state and anything filed mid-run that I did not dispatch.
4. **Anything you now own:** every `OWNER DECISION NEEDED`, batched, each with its link and my recommendation. The merge into `main` is the first of these.
5. **Every `ORCHESTRATOR DECISION`** I made under the contract, with links, so you can reverse any of them.
6. **FOLLOW-UP findings** reviewers left on merged PRs, and follow-up issues filed.
7. **Worktrees the sweep kept,** with its reason for each.

Any step that didn't run, or whose result I couldn't confirm on GitHub, is reported as that.

Then I stop. With nothing in flight and the only remaining act being yours, that is the end of the run.
