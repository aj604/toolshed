# Orchestrating the #170 sub-issues (rehearsal: nothing below was run against GitHub)

## What I'd tell you before you leave

Nothing is dispatched yet, and one answer from you decides whether anything can be: **whether I may adopt PR #239**. Everything left in the graph sits behind it.

**Reply `adopt #239, merge on green into workbench/issue-170`, or tell me what to change.** With that sentence I run to the end without asking again.

### Why #239 needs your word

- #202 is in flight with open PR #239 and no assignee. This run didn't open that PR, so I treat it as someone's work, not idle work.
- #205 is blocked by #202, and #202 is the only other open node. The whole run is behind this one question, which is the only reason I'm asking instead of parking a lane.
- I will not dispatch a second implementer onto #202 while #239 is open.
- My recommendation is to adopt it: review it as it stands, fix what the review finds, and land it.
- Before I act on your yes, I read the threads on #202 and #239. If an earlier run escalated #239 to you, or you pushed to it after that, I leave it alone and say so instead.

### Merge authority

You said "full auto — dispatch, review, merge, next" and "don't stop and ask me between issues". I take that as the merge grant and won't ask for it again. Here is what it covers and what it doesn't:

| | |
|---|---|
| **Lane PRs** | Merge on review pass plus green CI into a feature branch, `workbench/issue-170`, squash, branch deleted. I create the branch off `main` unless #170 or its earlier PRs already name one, in which case I use that. |
| **`main`** | I do not merge into `main`. You didn't name it, and this repo is a plugin marketplace that installs from `main`, so a merge there ships to users. |
| **Landing** | When the graph is done I open one PR, `workbench/issue-170` into `main`, as a merge commit, for you to merge. |
| **To change that** | Reply `merge on green into main` and lane PRs and the landing PR go straight to `main`. |
| **Never, whatever the grant** | `--admin`, editing a ruleset or bypass actor, or changing a repo setting to get a merge through. A merge the branch protection refuses waits for you. |
| **Never unattended** | A diff that touches `.github/workflows/`, release steps, or permission settings. I leave that PR ready and green for you. |
| **CI** | I never merge over a red check. A check that is red for an outside reason is still red, and waiving it is yours. |

If #239 currently targets `main`, adopting it includes retargeting it to `workbench/issue-170`. Otherwise merging it would be a merge into `main`.

### Rest of the contract (defaults, no answer needed)

- **Concurrency:** 3 lanes, though this graph is serial (#202, then #205), so one runs at a time.
- **Fix rounds:** 2, each by a fresh fixer. One extra on my own authority if a lane is converging and only test gaps remain.
- **Splits:** if a size check says #205 is oversized, I file the split as sub-issues with dependency edges and dispatch the first piece.
- **Judgement calls:** I pick the recommended option and record it on the issue or PR under `## ORCHESTRATOR DECISION`, with how to reverse it.
- **Scope growth:** new issues that aren't my own splits are filed and listed, not dispatched.
- **Models:** `opus` for implementer, reviewers and fixers. `sonnet` for the premise check and any rebase, because each is fully specified and CI or a `file:line` answer checks it. A fixer drops to `sonnet` only for a located `defect` in its first round.
- **Pipelining:** off.

### Two things I read from the local checkout

- `origin` is `aj604/toolshed`, so issues and code are the same repo and I can dispatch from here.
- `ci.yml` runs on `pull_request` with no branch filter and no draft condition, so lane PRs into the feature branch get CI, and it runs while they are drafts.

One piece of shared ground: CI's version guard requires a `plugin.json` bump whenever plugin content changes. #202 and #205 are serial, so they can't collide, but #205's card will say to bump from whatever #202 landed.

## Commands, in order

### 1. Preflight (read-only, before the question above is answered)

```bash
git -C <repo> remote get-url origin
git -C <repo> fetch origin
git -C <repo> log --oneline HEAD..origin/main
git -C <repo> log --oneline --since="<createdAt of the oldest open issue>" origin/main

python3 plugins/workbench/skills/orchestrate-issues/scripts/frontier.py --repo aj604/toolshed --parent 170
python3 plugins/workbench/skills/orchestrate-issues/scripts/frontier.py --repo aj604/toolshed --parent 170 --json
```

- If the log shows a merge that removed or rewrote what #202 and #205 target, that is the first thing I report, ahead of the contract.
- If the frontier prints warnings (prose-only blockers, blockers outside scope), I show them and wait. If it reports `deadlocked` or cycles, I stop.
- Expected from the framing: #184, #190, #195, #199 `done`; #202 `in_flight`; #205 `blocked`.

```bash
gh issue view 170 --repo aj604/toolshed --comments
gh issue view 202 --repo aj604/toolshed --comments --json number,title,body,labels,assignees,comments
gh issue view 205 --repo aj604/toolshed --comments --json number,title,body,labels,assignees,comments
gh pr view 239 --repo aj604/toolshed --comments \
  --json number,isDraft,author,headRefName,headRefOid,baseRefName,body,commits,mergeStateStatus,statusCheckRollup
```

This tells me who opened #239, whether anyone escalated or pushed to it since, which branch it targets, and whether its body's only `Closes` line names #202. I also read #202 and #205 for work only a person can do; any such issue gets `needs-human` and is not dispatched.

```bash
df -h <repo>
gh api rate_limit --jq .resources.core
gh api "repos/aj604/toolshed/actions/runs?per_page=1" >/dev/null && echo ok
grep -n -A6 'pull_request' <repo>/.github/workflows/*.y*ml

gh repo view aj604/toolshed --json visibility,defaultBranchRef
gh api "repos/aj604/toolshed/rules/branches/main" --jq '[.[] | {type, ruleset: .ruleset_id}] | unique'
gh api "repos/aj604/toolshed/rules/branches/workbench/issue-170" --jq '[.[] | {type, ruleset: .ruleset_id}] | unique'
# for each ruleset id returned:
gh api "repos/aj604/toolshed/rulesets/<id>" --jq '{name, enforcement, bypass: .bypass_actors, can_bypass: .current_user_can_bypass}'
```

If a rule would refuse my merges into the feature branch, I say so in the same message as the contract.

**Size check for #205**, dispatched now because it is read-only and doesn't depend on your answer:

- Agent: `subagent_type: "workbench:premise-checker"`, `name: "premise-205"`, `run_in_background: true`, default model (`sonnet`).
- Card: `REPO: aj604/toolshed — local path <repo>`, `ISSUE: #205 — <title>`, the issue body verbatim, and the `CLAIMS` list I extract from it.
- I re-run it after #202 lands only if that merge touched what its claims are about.

Then I send the message at the top and stop. **Nothing below runs until you reply.**

### 2. After `adopt #239, merge on green into workbench/issue-170`

```bash
git fetch origin
git ls-remote --exit-code --heads origin workbench/issue-170 \
  || git push origin "origin/main:refs/heads/workbench/issue-170"

gh issue edit 202 --repo aj604/toolshed --add-assignee @me
gh pr edit 239 --repo aj604/toolshed --base workbench/issue-170     # only if it targets main
```

**Review #239.**

- Agent: `subagent_type: "workbench:spec-reviewer"`, `name: "review-202-r1"`, `run_in_background: true`, `isolation: "worktree"`, default model (`opus`).
- Card: `REPO`, `PR: #239`, `ISSUE: #202`, `BRANCH`, `ROUND: 1`, the #202 body verbatim, and a `VERIFY` block. There is no implementer report from this run, so VERIFY carries the claims in #239's body, whether the diff stays inside #202's scope, and whether it bumps `plugin.json`.

**If the verdict is `CHANGES_REQUIRED`:**

- Agent: a fresh `workbench:fixer`, `name: "fix-202-r1"`, `run_in_background: true`, `isolation: "worktree"`. `sonnet` if `KIND` is `defect`, `opus` if `design`. Add `CATCH UP: workbench/issue-170` if the base moved.
- Then a fresh `review-202-r2`, or `workbench:verifier` (`verify-202-r1`) if the fix was tests-only, confirmed with:

```bash
gh api repos/aj604/toolshed/compare/<reviewed-sha>...<head-sha> --jq '[.files[].filename]'
```

- After two failed rounds I park #202 with `needs-human` and a comment linking the PR thread. That ends the run, since #205 is behind it; I open the landing PR if anything landed and report.

### 3. Land #239 on `PASS`

Each line is its own command. The merge is never chained to the watch.

```bash
gh pr view 239 --repo aj604/toolshed --json body --jq .body        # only Closes line names #202
gh pr diff 239 --repo aj604/toolshed --name-only                   # nothing under .github/workflows or permission settings
gh pr update-branch 239 --repo aj604/toolshed                      # only if behind
gh pr ready 239 --repo aj604/toolshed
gh pr checks 239 --repo aj604/toolshed --watch --interval 60 --fail-fast     # run_in_background: true
```

When the watch reports back:

```bash
gh pr view 239 --repo aj604/toolshed --json headRefOid,mergeStateStatus,statusCheckRollup
```

I merge only if every check on the current head finished `SUCCESS`, `SKIPPED` or `NEUTRAL`, that run started after `gh pr ready`, and `mergeStateStatus` is `CLEAN`. `UNKNOWN` means I read again in a minute. Red on a check measuring this PR goes to a fresh fixer; red that looks unrelated follows the flaky-gate steps (`update-branch` for a fresh sample, then `workbench:ci-diagnostic` on a second strike).

```bash
gh pr merge 239 --repo aj604/toolshed --squash --delete-branch --match-head-commit <headRefOid>
python3 plugins/workbench/skills/orchestrate-issues/scripts/prune_worktrees.py --apply --pr 239
df -h <repo>
```

If the permission system denies the merge, I leave #239 ready and green, retry nothing by another route, and end the turn with: *"Merge of #239 into `workbench/issue-170` was denied. Reply `merge on green into workbench/issue-170` and I'll land it and everything queued behind it."*

`Closes #202` does not fire off the default branch, so I close the issue myself and confirm before re-querying:

```bash
gh issue view 202 --repo aj604/toolshed --json state --jq .state
gh issue close 202 --repo aj604/toolshed --comment "Landed in #239 (into workbench/issue-170)."
gh issue view 202 --repo aj604/toolshed --json state --jq .state
python3 plugins/workbench/skills/orchestrate-issues/scripts/frontier.py --repo aj604/toolshed --parent 170
```

### 4. #205, once the frontier reports it `ready`

If the premise check called it oversized, I file the split first (sub-issues, `blocked_by` edges, `## ORCHESTRATOR DECISION` comment on #205) and dispatch the first child instead.

```bash
gh issue edit 205 --repo aj604/toolshed --add-assignee @me
```

- Agent: `subagent_type: "workbench:implementer"`, `name: "impl-205"`, `run_in_background: true`, `isolation: "worktree"`, default model (`opus`).
- Card: `REPO: aj604/toolshed`, `ISSUE: #205 — <title>`, `BRANCH: <repo-convention name for 205>`, `BASE: workbench/issue-170`, the issue body verbatim, any premise-check corrections under `WHERE THE ISSUE IS WRONG`, and `VERIFIED CONTEXT` naming what #239 landed that #205 builds on, including the `plugin.json` version to bump from.

Then the same path as above: `review-205-r1`, fresh fixers within the two-round budget, the Step 3 landing commands against #205's PR, prune, manual close of #205, and a frontier re-query.

### 5. Landing PR and report

When the frontier says `complete`, or the run stops with work landed:

```bash
git fetch origin
git log --oneline origin/workbench/issue-170..origin/main          # did main move?
```

If `main` moved, I dispatch `workbench:rebaser` (`name: "rebase-landing"`, `BRANCH: workbench/issue-170`, `BASE: main`) after the PR is open, and let CI run on the result before calling it ready.

```bash
gh pr create --repo aj604/toolshed --base main --head workbench/issue-170 \
  --title "#170: land workbench/issue-170" --body-file - <<'BODY'
<each issue landed with its PR, every ORCHESTRATOR DECISION, what is still open>

Merge as a merge commit so each lane's squash commit survives on main.
BODY
gh issue view 170 --repo aj604/toolshed --json state --jq .state
python3 plugins/workbench/skills/orchestrate-issues/scripts/prune_worktrees.py --apply
```

I do not merge the landing PR. If the frontier reports #170 itself as `split_complete`, I close it with a comment listing the children's PRs.

The final report leads with the landing PR's link and CI state, then:

- issues landed, with PR links;
- what is still open and why;
- anything you now own, each with its link and my recommendation;
- every `ORCHESTRATOR DECISION`, with links, so you can reverse any of them;
- FOLLOW-UP findings reviewers left on merged PRs;
- worktrees the sweep kept, and why.

It reports only what actually ran. Anything I'm unsure of, I check against GitHub before writing it down.
