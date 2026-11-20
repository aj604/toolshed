# Orchestrating the rest of #170 into `phase-a-integration`

This is a rehearsal, so nothing below has run. It is what I would tell you and the commands I would run, in order. Issue and PR numbers other than #170 are placeholders (`<n>`, `<pr>`) because I have not queried GitHub.

## What I'd tell you first

Understood: `main` is frozen, so every lane PR targets and merges into `phase-a-integration`, and nothing from this run touches `main`.

One thing changes from the previous run, and it is the one that silently stalls a chain: **GitHub only fires `Closes #<n>` when a PR merges into the default branch.** Merging into `phase-a-integration` lands the work and leaves the issue open, so every downstream issue stays blocked and the frontier reports nothing wrong. After every merge I will check the issue, close it myself with a comment naming the PR, confirm the close, and only then re-query the frontier.

### Run contract

You already gave the merge grant in your own words: "everything merges into the long-lived branch phase-a-integration instead. same flow otherwise — dispatch, review, merge, keep the chain moving." I take that as `auto` into `phase-a-integration` and won't ask again. The rest is the defaults; tell me what to change, otherwise I start once preflight is clean.

| Parameter | This run |
|---|---|
| Tracker and code repo | `aj604/toolshed` (same repo; I'll confirm the checkout's `origin`) |
| Scope | open sub-issues of #170, recursively |
| Integration branch | `phase-a-integration`, as you named it. I won't create it: if it isn't on the remote I stop and ask rather than branch off a frozen `main`. |
| Merge authority | `auto` into `phase-a-integration` on review PASS plus green CI. Nothing merges into `main`. |
| Merge method | squash, delete the lane branch, pinned to the reviewed head with `--match-head-commit` |
| Issue closing | manual after every merge, as above. A split parent whose children are all closed is also closed by hand. |
| Landing | one PR, `phase-a-integration` into `main`, to be merged as a merge commit. **You merge it**, after the freeze. I open it when the graph completes or the run stops with work landed, unless one is already open, and I'll note the freeze in its body. |
| Concurrency | 3 lanes |
| Fix rounds | 2, each by a fresh fixer. One extra on my authority for a converging, tests-only lane, recorded as a decision. |
| Split authority | split and report |
| Judgement calls | apply my recommendation, recorded as `## ORCHESTRATOR DECISION` on the issue or PR |
| Scope growth | splits of in-scope issues are in scope; anything else is filed and reported, not dispatched |
| Models | implementer, reviewer, re-reviewer: `opus`. Premise check, rebase, verifier: `sonnet`. Fixer: `opus`, or `sonnet` for a first-round located `defect`. No `haiku`. |
| Pipelining | off |
| CI gate | required. `ci.yml` triggers on `pull_request` with no branch filter and no draft condition, so it runs for draft PRs into `phase-a-integration`. |

Things I will not do under `auto`: use `--admin`, edit a ruleset or repo setting to get a merge through, or merge unattended any PR that touches `.github/workflows/`, release configuration, or permissions. Those park for you. The repo is public, so a bad merge is visible.

Two repo-specific points:

- **Version guard.** CI fails a PR that changes plugin content without bumping `plugins/workbench/.claude-plugin/plugin.json`, measured against the PR's base. Each merge into `phase-a-integration` consumes a version, so parallel lanes would turn each other red. I'll reserve a version per lane on its card (`RESERVED:`) in expected merge order. A lane that merges out of order renumbers once, right before its merge.
- **Leftovers from the earlier run.** "The rest of" #170 may include claimed issues or open PRs, possibly based on `main`. I won't adopt or retarget those on my own. If preflight finds any, I'll list them and ask before the first dispatch.

After the first dispatch I won't stop to ask questions. A question parks one lane (`## OWNER DECISION NEEDED` plus the `needs-human` label) and the rest keeps moving; I batch them in the status line.

## Commands, in order

`SKILL=<repo>/plugins/workbench/skills/orchestrate-issues`

### 1. Preflight

```bash
# Am I standing in the code repo?
git -C <repo> remote get-url origin        # expect aj604/toolshed

# Does the integration branch exist? (not created if missing: stop and ask)
git -C <repo> fetch origin
git -C <repo> ls-remote --exit-code --heads origin phase-a-integration

# Has the ground moved? Both branches matter: lanes build on phase-a-integration,
# and the landing PR eventually meets main.
git -C <repo> log --oneline HEAD..origin/phase-a-integration
git -C <repo> log --oneline origin/phase-a-integration..origin/main    # how far behind main the branch is
git -C <repo> log --oneline --since="<oldest open in-scope issue's createdAt>" origin/phase-a-integration

# The graph
python3 $SKILL/scripts/frontier.py --repo aj604/toolshed --parent 170
python3 $SKILL/scripts/frontier.py --repo aj604/toolshed --parent 170 --json

# Leftovers from the earlier run: open PRs and their bases
gh pr list --repo aj604/toolshed --state open --limit 200 \
  --json number,isDraft,headRefName,baseRefName,url,body

# What guards each branch
gh api "repos/aj604/toolshed/rules/branches/phase-a-integration" --jq '[.[] | {type, ruleset: .ruleset_id}] | unique'
gh api "repos/aj604/toolshed/rules/branches/main" --jq '[.[] | {type, ruleset: .ruleset_id}] | unique'
gh api "repos/aj604/toolshed/rulesets/<id>" \
  --jq '{name, enforcement, bypass: .bypass_actors, can_bypass: .current_user_can_bypass}'   # per ruleset found
gh repo view aj604/toolshed --json visibility,defaultBranchRef

# CI triggers for PRs into the integration branch (already read locally; re-read on the fetched branch)
git -C <repo> show origin/phase-a-integration:.github/workflows/ci.yml | grep -n -A6 'pull_request'

# Can the machine carry it
df -h <repo>
gh api rate_limit --jq .resources.core
gh api "repos/aj604/toolshed/actions/runs?per_page=1" >/dev/null && echo ok
```

Stop conditions before any dispatch: the branch is missing; the frontier reports `cycles`, `deadlocked`, or prose-only blockers (shown to you for a decision); a recent merge removed or rewrote what the graph targets; an open PR or assignee from the earlier run needs your ruling. If `phase-a-integration` is behind `main`, I say so; the catch-up happens on the landing PR, not in the lanes.

For each open in-scope issue I'd read the body (`gh issue view <n> --repo aj604/toolshed --json body,labels,assignees,comments`), mark anything only a human can do with `needs-human`, and then dispatch all premise checks in parallel:

```
Agent(subagent_type: "workbench:premise-checker", name: "premise-<n>", run_in_background: true)
  REPO:  aj604/toolshed — local path <repo>
  ISSUE: #<n> — <title>
  --- ISSUE BODY --- <verbatim> --- END ISSUE BODY ---
  --- CLAIMS --- <claims I extracted> --- END ---
```

Oversized verdicts get split before dispatch (sub-issues, `blocked_by` edges, a decision comment on the parent).

### 2. Dispatch, per ready issue, lowest number first, up to 3 lanes

Before filling more than one lane I read the ready issues against each other for shared ground. `plugin.json` is known shared ground, handled by reserved versions.

```bash
gh issue edit <n> --repo aj604/toolshed --add-assignee @me
```

```
Agent(subagent_type: "workbench:implementer", name: "impl-<n>", isolation: "worktree", run_in_background: true)
  REPO:     aj604/toolshed
  ISSUE:    #<n> — <title>
  BRANCH:   <branch-name>
  BASE:     phase-a-integration
  --- ISSUE BODY --- <verbatim> --- END ISSUE BODY ---
  [--- WHERE THE ISSUE IS WRONG --- <premise corrections> --- END ---]
  [--- VERIFIED CONTEXT --- <facts earlier lanes established> --- END ---]
  RESERVED: plugin.json version <X.Y.Z> (<previous> is reserved for #<m>)
```

I confirm the first implementer's branch pushed, and that its PR's base is `phase-a-integration`, before dispatching a second lane.

### 3. Review

```
Agent(subagent_type: "workbench:spec-reviewer", name: "review-<n>-r1", isolation: "worktree", run_in_background: true)
  REPO: aj604/toolshed   PR: #<pr>   ISSUE: #<n>   BRANCH: <branch>   ROUND: 1
  --- ISSUE BODY --- <verbatim> --- END ISSUE BODY ---
  --- VERIFY --- <implementer's claims; PR base is phase-a-integration; version is the reserved one> --- END ---
```

On `CHANGES_REQUIRED`: a fresh `workbench:fixer` (`fix-<n>-r<k>`, with `CATCH UP: phase-a-integration` if the branch moved), then a fresh re-review, or a `workbench:verifier` if the fix was confirmed tests-only. I never wake the implementer.

### 4. Land, per PASSed PR. Each line is its own command.

```bash
# Confirm the body's only Closes line names this issue, and the base is the integration branch
gh pr view <pr> --repo aj604/toolshed --json body,baseRefName

gh pr update-branch <pr> --repo aj604/toolshed          # only if behind phase-a-integration
gh pr ready <pr> --repo aj604/toolshed

# run_in_background: true
gh pr checks <pr> --repo aj604/toolshed --watch --interval 60 --fail-fast

# when the watch reports back
gh pr view <pr> --repo aj604/toolshed --json headRefOid,mergeStateStatus,statusCheckRollup

# only if every check on that head is SUCCESS/SKIPPED/NEUTRAL and mergeStateStatus is CLEAN
gh pr merge <pr> --repo aj604/toolshed --squash --delete-branch --match-head-commit <headRefOid>

# confirm the merge landed
gh pr view <pr> --repo aj604/toolshed --json state,mergedAt,baseRefName

# the issue will still be OPEN, because the merge was not into main
gh issue view <n> --repo aj604/toolshed --json state --jq .state
gh issue close <n> --repo aj604/toolshed --comment "Landed in #<pr> (merged into phase-a-integration; main is frozen, so GitHub did not auto-close)."
gh issue view <n> --repo aj604/toolshed --json state --jq .state     # must say CLOSED before going on

# reclaim disk
python3 $SKILL/scripts/prune_worktrees.py --apply --pr <pr>

# only now ask GitHub what the close opened
python3 $SKILL/scripts/frontier.py --repo aj604/toolshed --parent 170
```

The close comes before the re-query on purpose: a query against an unclosed node only says the graph is stuck. If the frontier shows a `split_complete` parent, I close it too, with a comment listing the children's PRs:

```bash
gh issue close <parent> --repo aj604/toolshed --comment "All parts landed in phase-a-integration: #<pr1>, #<pr2>."
```

If the harness denies a merge, that PR stays ready and green, the other lanes continue, and my status line carries the sentence that unblocks it: reply `merge on green into phase-a-integration`.

Then back to step 2 with whatever is now ready, rebasing surviving lanes only when a real conflict or a pending fix round calls for it.

### 5. When the frontier says `complete` (or the run stops with work landed)

```bash
gh pr list --repo aj604/toolshed --base main --head phase-a-integration --state open --json number,url

# if none is open
gh pr create --repo aj604/toolshed --base main --head phase-a-integration \
  --title "#170: land phase-a-integration" --body-file - <<'BODY'
<each issue landed with its PR, every ORCHESTRATOR DECISION, what is still open>

main is frozen for the release. Do not merge until the freeze lifts. Merge with a merge commit, not a squash.
BODY
```

If `main` moved, I dispatch a `workbench:rebaser` at the landing PR (`BRANCH: phase-a-integration`, `BASE: main`) and let CI run on the result. I do not merge this PR.

```bash
python3 $SKILL/scripts/prune_worktrees.py --apply
df -h <repo>
```

### 6. Final report

Landing PR link and CI state first, then: issues landed with their PRs and the manual close for each; what is still open and why; every `OWNER DECISION NEEDED` with my recommendation; every `ORCHESTRATOR DECISION`; reviewer FOLLOW-UPs; worktrees the sweep kept and why. Only what actually ran.
