# GitHub recipes

Every command takes `--repo OWNER/REPO` (or the equivalent path in `gh api`).
Never rely on `gh` inferring the repo: issue trackers frequently live in a
different repo from the code, and inference silently picks the local remote —
which is the wrong one exactly when it matters most.

## Native issue dependencies

This is the graph. GitHub models it as first-class `blocked_by` / `blocking`
edges, visible in the UI, and that's what `scripts/frontier.py` reads.

**The summary on any issue** — the live gate. `blocked_by` counts only *open*
blockers, so it drops to 0 the moment the last blocker closes:

```bash
gh api repos/OWNER/REPO/issues/<n> --jq .issue_dependencies_summary
# {"blocked_by":1,"blocking":0,"total_blocked_by":1,"total_blocking":0}
```

**The edges themselves:**

```bash
gh api repos/OWNER/REPO/issues/<n>/dependencies/blocked_by --jq '[.[]|{number,state,title}]'
gh api repos/OWNER/REPO/issues/<n>/dependencies/blocking   --jq '[.[]|{number,state,title}]'
```

**Adding an edge** (this skill consumes the graph rather than authoring it — but
you'll need this when a user asks you to repair a missing edge before starting).
The gotcha: `issue_id` is the blocker's numeric **database id**, not its
`#number` and not its `node_id`. Passing the issue number here either 404s or,
worse, silently links a different issue:

```bash
BLOCKER_ID=$(gh api repos/OWNER/REPO/issues/<blocker-number> --jq .id)
gh api --method POST repos/OWNER/REPO/issues/<blocked-number>/dependencies/blocked_by \
  -F issue_id=$BLOCKER_ID
```

**Sub-issues** — the usual way a parent issue defines a graph's scope:

```bash
gh api repos/OWNER/REPO/issues/<parent>/sub_issues --paginate --jq '[.[]|{number,title,state}]'
```

**Filing a split** of an oversized issue under the contract's split authority.
Make each child a sub-issue of the oversized issue, and give serial pieces real
`blocked_by` edges:

```bash
P=<oversized-number>
C1=$(gh issue create --repo OWNER/REPO --title "<parent title> — part 1: <piece>" \
       --body-file - <<'SPLIT_EOF' | grep -oE '[0-9]+$'
<its criteria>

Part of #<oversized-number>
SPLIT_EOF
)
gh api --method POST repos/OWNER/REPO/issues/$P/sub_issues \
  -F sub_issue_id=$(gh api repos/OWNER/REPO/issues/$C1 --jq .id)
# repeat for C2..Cn; then for each serial pair:
gh api --method POST repos/OWNER/REPO/issues/$C2/dependencies/blocked_by \
  -F issue_id=$(gh api repos/OWNER/REPO/issues/$C1 --jq .id)
gh issue comment $P --repo OWNER/REPO --body "## ORCHESTRATOR DECISION — split into #$C1, #$C2… (size check: <summary>). To reverse, close the children."
```

`frontier.py` picks the children up on its own, because it recurses into
sub-issues. It reports the oversized parent as `split`, a container you don't
dispatch. Once every child is closed it reports `split_complete`: close the
parent then, with a comment listing the children's PRs. That close opens the
parent's existing downstream edges.

### If native dependencies aren't available

Older GitHub Enterprise, or the feature disabled. `frontier.py` warns when no
issue carries an `issue_dependencies_summary` — and that warning is load-bearing,
because without the summary every issue looks unblocked and the loop would
dispatch the entire graph at once against foundations that don't exist yet.

Fallback: `Blocked by: #3, #4` as the first line of the issue body. `frontier.py`
already parses this and reports it as `unlinked_prose_blockers`. Treating it as a
real gate means computing readiness yourself — every referenced issue closed —
and you should tell the user you're running on the prose fallback, because it's
only as good as the discipline that wrote it.

## Claiming and releasing

The assignee is the claim marker: it survives your context being compacted, it's
visible to the user mid-run, and it stops a resumed run from double-dispatching.

```bash
gh issue edit <n> --repo OWNER/REPO --add-assignee @me
gh issue edit <n> --repo OWNER/REPO --remove-assignee @me   # release on escalation
```

An optional label (`agent:in-flight`) makes runs legible at a glance if the user
wants one, but the assignee alone is sufficient state.

## Pull requests

The implementer opens its own PR from inside its worktree; these are the
orchestrator's side:

```bash
# what exists for this issue
gh pr list --repo OWNER/REPO --state all --limit 200 \
  --json number,state,isDraft,headRefName,baseRefName,mergedAt,url,body

gh pr ready <pr>  --repo OWNER/REPO            # draft -> ready, after review passes
gh pr checks <pr> --repo OWNER/REPO --watch    # blocks until CI settles
gh pr merge  <pr> --repo OWNER/REPO --squash --delete-branch
```

`gh pr checks` exit codes are not a simple pass/fail: **1** covers both "a check
failed" and "no checks reported on this branch", and **8** means checks are still
pending. So a repo with no CI is indistinguishable from a repo with red CI if you
only look at the exit code. Read the states instead:

```bash
gh pr checks <pr> --repo OWNER/REPO --json name,state 2>/dev/null || echo "[]"
```

An empty array means no CI is configured — proceed to merge. Otherwise merge only
when every `state` is `SUCCESS` (or `SKIPPED`/`NEUTRAL`); send `FAILURE` to a
fresh fixer, and let `--watch` settle anything still `PENDING`.

One caveat on `--watch` in an unattended run: it is a long-lived foreground
process, and a background shell chain holding it can get killed by process
reaping without ever reporting. If a watch seems to have gone quiet, don't
trust its silence — re-read the check states with the JSON form above. Bounded
polls beat one long watch when the run is measured in hours.

### Reruns, flakes, and fresh evidence

`gh run rerun <id> --failed` re-runs the **same merge commit**. A second
failure there is the same data point twice — it cannot tell a flake from a
deterministic failure, however convincing it feels. To get an independent
sample, move the commit:

```bash
gh pr update-branch <pr> --repo OWNER/REPO
# or, on older gh:
gh api --method PUT repos/OWNER/REPO/pulls/<pr>/update-branch
```

That merges the base into the branch, producing a new merge commit, and CI runs
against genuinely new state. The routing that follows (second strike → a
read-only diagnostic, pre-existing + blocking → fix it now as lane maintenance)
lives in *Flaky and broken gates* in SKILL.md.

## Review findings live on the PR

The reviewer posts; the fixer reads. Nothing passes through the orchestrator,
which is what keeps a multi-round lane from growing anyone's context.

Post (reviewer):

```bash
gh pr comment <pr> --repo OWNER/REPO --body-file - <<'REVIEW_EOF'
## SPEC REVIEW — round <k> — VERDICT: ...
REVIEW_EOF
```

Bodies go on stdin: a body file written in an agent's worktree stays there
as an untracked file. Use `gh pr comment`. `gh pr review --request-changes` and `--approve` are
rejected by GitHub on a PR opened by the same account, and every agent in the run
authenticates as the same account — so a review *event* fails where a plain
comment succeeds.

Read (fixer, or the next round's reviewer):

```bash
gh pr view <pr> --repo OWNER/REPO --comments
```

To pull just the review rounds out of a busy thread, filter on the header line
the reviewer brief mandates:

```bash
gh api "repos/OWNER/REPO/issues/<pr>/comments" \
  --jq '.[] | select(.body | startswith("## SPEC REVIEW")) | .body'
```

The last one is the current round. Earlier ones are the lane's history, and a
finding that reappears across rounds means the previous fix addressed the symptom.

## A fresh agent taking over a pushed branch

A new worktree cannot check out a branch another worktree still holds — the
implementer's worktree is usually still holding it, and git refuses with
`fatal: '<branch>' is already used by worktree at ...`. Branch under a name
nothing else is using, and push back explicitly:

```bash
git fetch origin
git checkout -B fix-<n>-r<k> origin/<branch>
# ... work ...
git push origin HEAD:<branch>
```

On a non-fast-forward rejection, `git pull --no-rebase origin <branch>` (merge,
never rebase) and push again. Never force-push a PR branch: the commits you would discard may already
have been reviewed, and the review comments anchor to them.

## Branch protection — read it before promising `auto`

What guards the default branch decides whether your merge authority is real:

```bash
BR=$(gh repo view OWNER/REPO --json defaultBranchRef --jq .defaultBranchRef.name)
gh api "repos/OWNER/REPO/rules/branches/$BR" --jq '[.[] | .type] | unique'
```

Useful fields when a ruleset is active: `enforcement`, `bypass_actors`, and
`current_user_can_bypass`. Fetch the ruleset itself for those:

```bash
gh api "repos/OWNER/REPO/rulesets/<id>" \
  --jq '{name, enforcement, bypass: .bypass_actors, can_bypass: .current_user_can_bypass}'
```

`current_user_can_bypass: "never"` is the good case — the machine enforces what
you already promised. When it says otherwise, the promise is doing the work, so
make it explicitly: **`auto` authority never includes `--admin`, never includes
editing a ruleset or adding a bypass actor, and never includes changing a repo
setting to let a merge through.** Those all convert "the guard rail stopped me"
into "I removed the guard rail", which is the one move an unattended loop must
not have. A protection-blocked merge is an escalation, full stop.

Related: check `gh repo view OWNER/REPO --json visibility`. Public repos and repos
with other people's live work raise the cost of a bad merge, and that belongs in
the conversation where the user grants `auto` — not discovered afterwards.

## Why `--delete-branch` matters to a stack

When a PR stacked on branch `A` is open and `A` gets merged and deleted, GitHub
automatically retargets that PR onto the default branch. Its diff collapses to
just its own changes. Skip `--delete-branch` and the stacked PR keeps pointing at
a stale merged branch, showing a diff that includes its parent's work — which
then fails spec review for scope creep it never committed.

## Confirming a node actually closed

`Closes #<n>` in the PR body closes the issue on merge, but only when the PR
targets the repo's **default branch**. A stacked PR merging into its parent's
branch will *not* close its issue — and neither will *any* merge in a run whose
integration branch isn't the default branch, which makes manual closing the
per-merge rule there, not the exception. Check, and close manually when it
didn't:

```bash
gh issue view <n> --repo OWNER/REPO --json state --jq .state
gh issue close <n> --repo OWNER/REPO --comment "Landed in #<pr>."
```

This is the most common reason a loop appears to stall: the work landed, the
issue stayed open, and everything downstream stayed blocked.

## Re-reading the world after a compaction

There is no local run state to recover. Rebuild from GitHub:

```bash
python3 <skill>/scripts/frontier.py --repo OWNER/REPO --parent <n>
```

`in_flight` with an open draft PR means an implementer was working and may be
gone; `in_flight` with an assignee and no branch means a claim that never
started. Both are recoverable by re-dispatching — check with the user first, so
you don't run a second implementer against a live one.
