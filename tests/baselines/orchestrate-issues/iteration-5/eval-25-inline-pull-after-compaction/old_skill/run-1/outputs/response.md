# acme/atlas: what I do, in order

Rehearsal: nothing below was run and no agent was dispatched.

I edit nothing myself in any of the three: not the four-line fix, not the CHANGELOG conflict, not the README line. The summary is a lead, not state, so GitHub gets re-read before anything moves.

Contract I'm working under, in your words: "auto merge into feat/atlas-export". That covers lane PRs into `feat/atlas-export`. It does not cover any merge into `main`.

## First: rebuild state from GitHub

```bash
git -C . remote get-url origin                     # am I standing in acme/atlas?
git fetch origin
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300
gh pr view 450 --repo acme/atlas --json state,isDraft,baseRefName,headRefName,headRefOid,mergeStateStatus,statusCheckRollup,body
gh api "repos/acme/atlas/issues/450/comments" --jq '.[] | select(.body | startswith("## SPEC REVIEW")) | .body'
git log --oneline origin/feat/atlas-export..origin/main        # is it still 6 behind?
gh pr list --repo acme/atlas --base main --head feat/atlas-export --state open --json number,isDraft,url
gh issue view 385 --repo acme/atlas --json state,assignees,body
df -h .
```

What I'm checking:

- #381-#384 are closed, not just merged. Off the default branch `Closes #n` never fires. Any still open gets `gh issue close <n> --repo acme/atlas --comment "Landed in #<pr>."`, then a fresh frontier query.
- Whether a round-2 review comment is already on #450. If it is, I act on that verdict and don't dispatch another.
- The SHA that r1 reviewed, and the files changed since:
  `gh api repos/acme/atlas/compare/<r1-reviewed-sha>...<head-sha> --jq '[.files[].filename]'`
- Whether an agent dispatched before the compaction is still alive (`git worktree list`, plus the session's agent list, for `review-385-r2`, `rebase-*`, `impl-*`). If one is, I wait for its notification and don't dispatch a duplicate.
- What the 6 commits on `main` touch. If any changed code #450 calls, the rebaser in (b) goes first, #450 is updated, and only then does the r2 review run, so it judges the diff that will merge. If the overlap is CHANGELOG only, (a) and (b) go out together.
- Whether a landing PR already exists.
- What else the frontier shows as ready or in flight. Ready nodes fill the free lanes as normal, lowest number first.

## (a) Land #450

I don't read the four lines and call it reviewed. A fix that touched production code gets a fresh spec review, and green CI isn't that review.

1. If the compare call confirms production files changed (the summary says so), dispatch a fresh reviewer. It is not the r1 reviewer and not the fixer.
   - `subagent_type: workbench:spec-reviewer`, `name: review-385-r2`, `model: opus`, `isolation: worktree`, `run_in_background: true`
   - Card: `REPO: acme/atlas`, `PR: #450`, `ISSUE: #385`, `BRANCH: <head ref>`, `ROUND: 2`, the #385 body verbatim, and a VERIFY block holding the fixer's claims from its PR comment plus "the diff since r1 stays inside the r1 findings".
   - Only if the compare shows tests-only would it be `workbench:verifier` (`verify-385-r1`, sonnet) instead.
2. Wait for the notification. No polling.
3. On `CHANGES_REQUIRED`: this is round 2 of 2. Dispatch a fresh `workbench:fixer` named `fix-385-r2` on `opus` (any lane past its first round stays on opus), with `CATCH UP: feat/atlas-export` if the base moved. Then `review-385-r3`. If that fails too, park the lane: add `needs-human`, post a comment linking the PR thread, free the slot.
4. On `PASS`, each line its own command:

```bash
gh pr view 450 --repo acme/atlas --json body --jq .body      # its only Closes line must be #385
gh pr update-branch 450 --repo acme/atlas                    # only if behind feat/atlas-export
gh pr ready 450 --repo acme/atlas
gh pr checks 450 --repo acme/atlas --watch --interval 60 --fail-fast    # run_in_background: true
```

When the watch reports back:

```bash
gh pr view 450 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
```

Merge only if every check on that head is `SUCCESS`, `SKIPPED` or `NEUTRAL`, the run is the one started after `gh pr ready`, and `mergeStateStatus` is `CLEAN`. The "CI green" in the summary is for an older moment and doesn't count.

```bash
gh pr merge 450 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
python3 <skill>/scripts/prune_worktrees.py --apply --pr 450
gh issue view 385 --repo acme/atlas --json state --jq .state
gh issue close 385 --repo acme/atlas --comment "Landed in #450."        # if still open
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300
df -h .
```

If the harness denies the merge, #450 stays ready and green, and my status line says: reply `merge on green into feat/atlas-export` and I'll land it.

## (b) Bring main into feat/atlas-export

A rebaser does it. I don't resolve the CHANGELOG conflict in my checkout. Dispatched in the same turn as the r2 review, unless the `main` commits touch code #450 calls (see First).

1. If no landing PR is open, open one as a draft, so there is a PR to catch up and CI to judge the result:

```bash
gh pr create --repo acme/atlas --draft --base main --head feat/atlas-export \
  --title "#300: land feat/atlas-export" --body-file - <<'BODY'
Landed: #381, #382, #383, #384 (with their PRs). In review: #385 (PR #450).
Orchestrator decisions: <links>. Still open: <from the frontier>.
BODY
```

2. Dispatch `workbench:rebaser`, `name: rebase-landing`, `model: sonnet` (one named operation, CI checks it), `isolation: worktree`, `run_in_background: true`:

```
REPO:   acme/atlas
PR:     #<landing-pr>
BRANCH: feat/atlas-export
BASE:   main
```

   It merges `main` in. It never force-pushes.
3. When it returns:
   - `RESOLUTION: mechanical` (expected for a CHANGELOG): CI on the landing PR is the check, read with `gh pr checks <landing-pr> --repo acme/atlas --json name,state`. If the workflows skip drafts, CI only starts at `gh pr ready`.
   - `RESOLUTION: semantic`: dispatch a fresh spec review of the landing PR before I call it ready.
4. That push moves the base under #450. If #450 hasn't merged yet, the `gh pr update-branch 450` step in (a) picks it up once, right before merging. If it now conflicts, that's a `rebase-385` dispatch, not a fix round.
5. If branch protection refuses the rebaser's push to `feat/atlas-export`, that parks (b) for you. No `--admin`, no ruleset edit.
6. The landing PR into `main` is yours to merge, as a merge commit. I don't merge it.

## (c) The README line

Not edited by me, and not slipped onto #450's fixer or the rebaser as a rider. It's a FOLLOW-UP on a merged PR, so under the contract it gets filed and reported, not dispatched.

```bash
gh issue list --repo acme/atlas --search "README --export in:title,body" --state open     # already filed?
gh issue create --repo acme/atlas --title "README still names the old --export flag" --body-file - <<'BODY'
FOLLOW-UP from the spec review on #447 (merged): README still names the old `--export` flag. One line.
Filed by the #300 orchestration run; not dispatched.
BODY
```

It is not attached as a sub-issue of #300, so it stays out of the frontier. It goes in the end-of-run report with its link. If you want it in this run, say so and it becomes a normal lane: implementer, review, merge.

## Status line I'd leave you

> #381-#384 landed. #450 (#385): r1 fix pushed, r2 review running, merges on PASS + green. `feat/atlas-export`: rebaser merging `main` in via landing PR #<n> (draft). README follow-up from #447 filed as #<m>, not dispatched. Nothing waiting on you yet.
