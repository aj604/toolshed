# Stacking recipes

Everything here assumes the branch convention the loop depends on:

```
lane/<slug>/r<n>          base = lane/<slug>/r<n-1>,  or the default branch when n = 1
```

The convention isn't cosmetic — `scripts/lanes.py` reconstructs the entire run
from it after a compaction, so a branch named off-pattern is a branch that
vanishes from your state.

## Opening a round's PR onto its parent

The implementer does this, but you need to recognize a correct one:

```bash
gh pr create --repo OWNER/REPO \
  --base lane/cli-ergonomics/r1 \
  --head lane/cli-ergonomics/r2 \
  --draft --title "..." --body "..."
```

The tell for a broken stack is a round-2 diff that contains round 1's changes.
That means `--base` was the default branch. Fix it in place:

```bash
gh pr edit <pr> --repo OWNER/REPO --base lane/cli-ergonomics/r1
```

Retargeting is safe and cheap — GitHub recomputes the diff. Do it before a
reviewer reads it, not after; a reviewer handed three rounds of work will report
findings against code that already passed review.

## Reading a stack

```bash
gh pr list --repo OWNER/REPO --state open \
  --json number,headRefName,baseRefName,isDraft,title \
  --jq 'sort_by(.headRefName)[] | "\(.number)  \(.headRefName)  <- base \(.baseRefName)"'
```

Or let the script group it by lane and flag the breaks:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/incremental-enhancement-lanes/scripts/lanes.py" --repo OWNER/REPO
python3 "${CLAUDE_PLUGIN_ROOT}/skills/incremental-enhancement-lanes/scripts/lanes.py" --repo OWNER/REPO --json    # to branch on it
```

## When the default branch moves under a stack

Someone else merges to the default branch mid-run. Only the **bottom** of each stack needs
rebasing; the rounds above it are based on their siblings, not on the default branch, so they
follow automatically once r1 moves.

```bash
git fetch origin
DEFAULT_BRANCH=$(gh repo view OWNER/REPO --json defaultBranchRef -q .defaultBranchRef.name)
git rebase "origin/$DEFAULT_BRANCH" lane/<slug>/r1
git push --force-with-lease origin lane/<slug>/r1
```

Then each round above it, in order:

```bash
git rebase --onto lane/<slug>/r1 <old-r1-sha> lane/<slug>/r2
git push --force-with-lease origin lane/<slug>/r2
```

This is fiddly and it is not your job. Send it to the lane's most recent
implementer with `SendMessage` — it has the worktree and the branches. Rebasing
is ordinary lane maintenance, not a review failure, so don't spend a fix round on
it.

`--force-with-lease` rather than `--force`: if an implementer pushed while you
were rebasing, the lease refuses instead of destroying its commit.

## When the user merges a mid-stack PR during the run

GitHub retargets the orphaned child onto the merged PR's base automatically, so
`lane/x/r2` becomes a PR against the default branch containing r1+r2's changes if r1 merged.
That's usually what the user wanted. Verify rather than assume:

```bash
gh pr view <child-pr> --repo OWNER/REPO --json baseRefName,mergeable,mergeStateStatus
```

If `mergeable` is `CONFLICTING`, the child needs a rebase onto the new base —
same recipe as above, dispatched to the implementer.

Deleting the merged branch is what triggers the retarget, so if the user merged
without deleting, the child still points at a stale branch. Say so rather than
fixing their merge settings.

## Verifying a round is really only one round

Before you accept a `PASS`, the cheapest check that the stack is sound:

```bash
gh pr diff <pr> --repo OWNER/REPO --name-only
```

Two things to look at: the file list should sit inside the lane's `OWNS` globs,
and it should not repeat the file list of the round below it wholesale. Same
files across consecutive rounds is normal for a lane deepening one area; an exact
superset including earlier rounds' additions means the base is wrong.

## Handing the stacks over

The run ends with everything open. What the user needs is the review order, since
the top of a stack can't be read without the bottom:

```bash
gh pr list --repo OWNER/REPO --state open --json number,headRefName,title \
  --jq 'sort_by(.headRefName)[] | "#\(.number) \(.headRefName) — \(.title)"'
```

Present it grouped by lane, bottom-first, with each lane's charter one-liner
above it. If the user wants to take a whole lane, merging bottom-up with branch
deletion at each step lets GitHub retarget the rest as it goes:

```bash
gh pr merge <r1-pr> --repo OWNER/REPO --squash --delete-branch
# r2's PR now targets the default branch; check it, then repeat
```

Say that as a suggestion, and stop. Merging is the human's decision in this
skill — including the merge order.

## Where native tooling helps

If the repo already uses a stacking tool (Graphite, `git town`, `spr`, `ghstack`),
its restack command replaces the manual rebase chain above and will be more
reliable than it. Check for its config before hand-rolling:

```bash
ls .graphite_repo_config .git-town.toml 2>/dev/null
```

Don't introduce one that isn't already there — a stacking tool changes how
everyone on the repo works, which is far outside what this run was authorized to
decide.
