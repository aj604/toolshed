# acme/atlas #300: run contract, and what happens after your yes

Nothing below has run. This is the rehearsal you asked for: no `gh` command was sent and no agent was dispatched.

I don't have the nine sub-issue numbers, so the four ready ones appear as `#A`, `#B`, `#C`, `#D`, lowest number first.

## What I'm taking from preflight

- The graph is clean: no cycles, no prose-only blockers, no blockers outside the scope. Four issues are ready.
- I'm treating the nine up-front premise and size checks as run and clean, with no splits pending. If that isn't what "nothing wrong" covered, they go out first (see step 0 below).
- Tracker and code are both `acme/atlas`, and I'm standing in its checkout.
- The repo is private and the default branch is `main`.
- **One thing does need your decision.** The CI workflow triggers on `pull_request:` with `branches: [main]`. Lane PRs will target a feature branch, so no checks will run on them at all. "No checks reported" there means nothing ran, not that the PR is green.

## The run contract

| Parameter | Value for this run |
|---|---|
| Concurrency | 3 lanes. Three of the four ready issues start at once; the fourth takes the first free slot. |
| Integration branch | `feature/issue-300`, created off `origin/main`. I picked the name; tell me if the repo has a convention I should follow. Not `main`. |
| Merge authority | `auto` into `feature/issue-300`, on your words "go as auto as you can". That covers the nine issues, any splits I file, and anything you add to this branch later. It does not reach `main`. It never includes `--admin`, a ruleset edit, a bypass actor, or a changed repo setting. A merge the branch protection refuses comes back to you. |
| Merge method | Squash, delete branch, for lane PRs. |
| Landing | One PR, `feature/issue-300` into `main`, as a merge commit. You merge it. Nothing reaches `main` until you do, and one revert undoes the lot. |
| Fix rounds | 2, each by a fresh fixer. A converging lane whose remaining findings are tests-only may take one more on my authority, recorded on the PR. |
| Split authority | Split and report. If a size check says oversized, I file the sub-issues with native edges and dispatch the first. |
| Judgement calls | Apply my recommendation and record it under `## ORCHESTRATOR DECISION` on the issue or PR. Irreversible or out-of-scope choices park that one lane with `needs-human`. |
| Scope growth | Splits of in-scope issues are in scope. Anything else is filed and listed in the report, not dispatched. |
| Models | Implementer, spec reviewer and re-reviewer on `opus`. Premise check, rebase and verifier on `sonnet`. A fixer is on `opus`, or on `sonnet` only for a first-round located `defect`. I'll say so each time I drop a lane to `sonnet`. |
| Pipelining | Off. An issue is dispatched only after its blockers have closed. |
| CI gate | **Open: pick one, below.** I never merge over red checks. |

Three consequences of the feature branch:

- `Closes #n` doesn't fire off the default branch. After every merge I close the issue myself with a comment naming the PR, then re-query the graph.
- I won't merge these unattended even on green: anything touching CI config, release workflows, or permissions. Those park for you.
- I won't stop to ask you questions mid-run. A lane that needs you gets parked with `needs-human` and a question on its PR; the rest keep moving. You'll see them batched tonight.

### The CI choice

Because the triggers exclude `feature/issue-300`, `auto` would mean merging on review alone, and a plain yes doesn't grant that. Two ways to settle it:

1. **You widen the triggers** (recommended). Add `feature/issue-300` (or `feature/**`) to `branches:` in the workflow. It's a CI-config change, so it's yours to make. Lane PRs then get real checks, and I merge on review pass plus green.
2. **Trailing CI.** Lane PRs merge on review PASS alone. After the first merge I open the landing PR as a draft, so `main`'s CI runs on the integration branch after each merge. If it goes red I stop merging lanes and send a fixer first. A failure is found one merge late.

### The yes I need

Reply with one typed sentence:

- `merge on green into feature/issue-300, I'll widen the triggers`, or
- `merge on review pass into feature/issue-300, trailing CI`,

or tell me what to change. If your answer changes a row, I'll take it as the yes for the rest and fill in whatever it leaves open myself.

## Right after you say yes

A bare "yes" approves everything except the CI choice. In that case I dispatch and review as normal, and hold the merges with the PRs left ready until you pick. The steps below are the same either way up to landing.

### 0. Only if the premise checks haven't run

Dispatch nine `workbench:premise-checker` agents in parallel (`name: "premise-<n>"`, `sonnet`, background), each with its issue body and the claims I extracted. Any oversized verdict gets split before dispatch.

### 1. Create the integration branch

```bash
git fetch origin
git ls-remote --exit-code --heads origin feature/issue-300 \
  || git push origin "origin/main:refs/heads/feature/issue-300"
```

### 2. Read what guards both branches

```bash
gh api "repos/acme/atlas/rules/branches/feature/issue-300" --jq '[.[] | {type, ruleset: .ruleset_id}] | unique'
gh api "repos/acme/atlas/rules/branches/main" --jq '[.[] | {type, ruleset: .ruleset_id}] | unique'
# for each ruleset id returned:
gh api "repos/acme/atlas/rulesets/<id>" \
  --jq '{name, enforcement, bypass: .bypass_actors, can_bypass: .current_user_can_bypass}'
```

If a rule would refuse my merges into `feature/issue-300`, I tell you before dispatching more than one lane.

### 3. Re-read the frontier and check the ready four against each other

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300 --json
```

I read `#A`–`#D` for shared ground: a lock or generated file, a version or changelog bump, a migration or other sequence number, an interface one defines and another consumes. Overlapping lanes get serialized or fenced by region on both cards. Sequence numbers get reserved on the cards in expected merge order.

### 4. Claim, then dispatch the first lane

```bash
gh issue view <A> --repo acme/atlas --json title,body,comments,assignees,labels
gh issue edit <A> --repo acme/atlas --add-assignee @me
```

(Any existing assignee or a `needs-human` label means hands off; I'd take the next ready issue instead.)

Then an Agent call: `subagent_type: "workbench:implementer"`, `name: "impl-<A>"`, `run_in_background: true`, `isolation: "worktree"`, default model (`opus`), with this card:

```
REPO:   acme/atlas
ISSUE:  #<A> — <title>
BRANCH: issue-<A>-<slug>
BASE:   feature/issue-300

--- ISSUE BODY ---
<full issue body, verbatim>
--- END ISSUE BODY ---

[FENCE / RESERVED / BUILD lines only where step 3 found a reason]
```

### 5. Fill the other two lanes

Same claim and dispatch for `#B` and `#C`, in one message so they start together:

```bash
gh issue edit <B> --repo acme/atlas --add-assignee @me
gh issue edit <C> --repo acme/atlas --add-assignee @me
```

`#D` stays ready and unclaimed until a slot frees. Then I wait for notifications; I don't poll.

Once `impl-<A>` has pushed, I confirm its branch really landed on `acme/atlas` (`git ls-remote --heads origin issue-<A>-<slug>`). If it didn't, the other lanes have the same problem and I stop them early.

### 6. When an implementer hands back: spec review

Agent call: `subagent_type: "workbench:spec-reviewer"`, `name: "review-<n>-r1"`, `run_in_background: true`, `isolation: "worktree"`, `opus`. The card carries REPO, PR, ISSUE, BRANCH, `ROUND: 1`, the issue body, and a VERIFY block built from the implementer's own claims plus anything I doubt.

- `CHANGES_REQUIRED`: a fresh `workbench:fixer` (`fix-<n>-r1`), `sonnet` only for a first-round `defect`, `opus` for `design`. Then a fresh re-reviewer, or a `workbench:verifier` if the fix was tests-only (confirmed with the compare call).
- `PASS`: go to landing.

### 7. Landing a passed PR

First, in every case:

```bash
gh pr view <pr> --repo acme/atlas --json body,headRefOid,mergeStateStatus,baseRefName   # one `Closes` line, the right issue
gh pr update-branch <pr> --repo acme/atlas   # only if behind
gh pr ready <pr> --repo acme/atlas
```

Then it depends on your answer.

**Bare yes, no CI choice yet.** I stop here. The PR stays ready and unmerged, the lane's slot is freed, and my status line reads: *"#<pr> passed review and is ready. Lane merges are held on the CI choice: reply `merge on green into feature/issue-300, I'll widen the triggers` or `merge on review pass into feature/issue-300, trailing CI`."* Issues that don't depend on a held merge keep getting dispatched (`#D` next). If every remaining issue is behind a held merge, that is the end of the turn and I report.

**You widened the triggers.** Each of these is its own command:

```bash
gh pr checks <pr> --repo acme/atlas --watch --interval 60 --fail-fast     # run_in_background: true
# when it reports back:
gh pr view <pr> --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
# only if every check on that head is SUCCESS/SKIPPED/NEUTRAL and mergeStateStatus is CLEAN:
gh pr merge <pr> --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
```

If checks still don't appear on a PR opened before your workflow change, I update the branch to pick it up and read again. Red on this PR's own code goes to a fresh fixer.

**Trailing CI.**

```bash
gh pr view <pr> --repo acme/atlas --json headRefOid,mergeStateStatus
gh pr merge <pr> --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
```

After the first merge I open the landing PR as a draft, so `main`'s workflow runs on the integration branch:

```bash
gh pr create --repo acme/atlas --draft --base main --head feature/issue-300 \
  --title "#300: land feature/issue-300" --body-file - <<'BODY'
<issues landed so far with their PRs, orchestrator decisions, what is still open>
BODY
```

Before each later lane merge I read that PR's checks (`gh pr checks <landing-pr> --repo acme/atlas --json name,state`). If they are red, lane merges stop and a fixer goes first.

### 8. After every merge

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr <pr>
df -h .
gh issue view <n> --repo acme/atlas --json state --jq .state       # will be OPEN: merged off the default branch
gh issue close <n> --repo acme/atlas --comment "Landed in #<pr> on feature/issue-300."
gh issue view <n> --repo acme/atlas --json state --jq .state       # confirm CLOSED
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300 --json
```

Then I fill free slots from the new frontier, lowest number first, with the same claim and dispatch. Lanes still in flight are left alone unless the merge conflicts with them or changed code they call; a lane that is merely behind is updated once, right before its own merge.

If the harness denies a merge, that PR parks ready, the rest keep moving, and the status line carries the sentence that would unblock it. I retry with the same `gh pr merge` command once you've replied.

### 9. When the graph completes, or the run stops with work landed

```bash
python3 <skill>/scripts/prune_worktrees.py --apply
git fetch origin && git log --oneline origin/feature/issue-300..origin/main   # did main move?
```

If `main` moved, a `workbench:rebaser` (`BRANCH: feature/issue-300`, `BASE: main`) catches the branch up and CI runs on the result. Then the landing PR, ready for review (or `gh pr ready` on the draft, with its body updated, under trailing CI):

```bash
gh pr create --repo acme/atlas --base main --head feature/issue-300 \
  --title "#300: land feature/issue-300" --body-file - <<'BODY'
<each issue landed with its PR, every ORCHESTRATOR DECISION, what is still open>
BODY
```

I don't merge it. You do, as a merge commit (`--merge`), so each lane's squash commit survives on `main`. I also close parent #300 only if the frontier reports it complete.

### What you'll read tonight

1. The landing PR link and its CI state.
2. Issues landed, with PR links.
3. What is still open and why.
4. Every `OWNER DECISION NEEDED`, batched, each with a link and my recommendation.
5. Every `ORCHESTRATOR DECISION` I made, with links, so you can reverse any of them.
6. Reviewer follow-ups on merged PRs, and follow-up issues filed.
7. Any worktrees the sweep kept, and why.

It will report only what actually ran.
