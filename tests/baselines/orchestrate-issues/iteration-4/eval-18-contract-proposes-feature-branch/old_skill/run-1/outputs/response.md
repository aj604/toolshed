# Run contract for acme/atlas #300

Nothing below has run. This is the contract I'd state back, then the actions I'd take once you say yes.

I'm taking preflight as given, per your message: I'm standing in a checkout of `acme/atlas`, `main` hasn't moved under the graph, the frontier is clean (no cycles, no prose-only blockers, no out-of-scope blockers), 4 of the 9 sub-issues are ready, premise and size checks came back with no corrections and nothing oversized, branch protection would not refuse a normal `gh pr merge`, and disk, API rate limit and Actions are fine.

## The contract

| Parameter | Value for this run | Note |
|---|---|---|
| Scope | Parent #300 and its 9 sub-issues in `acme/atlas` | Tracker and code repo are the same. |
| Concurrency | 3 lanes | The 4th ready issue waits for the first free slot. |
| Merge authority | **`auto`** | You said "as auto as you can". I merge on spec-review PASS plus green CI, with no stop for you. This is the one I need an explicit yes on, because a merge to `main` can't be undone while you're away. It covers this scope only. |
| Merge method | Squash, delete branch | |
| Integration branch | `main` (the default branch) | Every PR targets `main`, so `Closes #<n>` closes the issue on merge and opens the next edge. I still verify each close. |
| Fix rounds | 2 | Each by a fresh fixer. A lane that is converging with only test gaps left may take one more round on my authority, recorded on the PR. |
| Split authority | Split and report | If a later size check says oversized, I file the sub-issues with native edges and dispatch the first. |
| Judgement calls | Apply recommended | I decide, record it under `## ORCHESTRATOR DECISION` on the issue or PR, and continue. Irreversible or out-of-scope choices park that lane only. |
| Scope growth | Follow-ups filed, not dispatched | Splits of in-scope issues are in scope. Anything else is filed and listed in tonight's report. |
| Models | `opus` for implementers, spec reviewers and re-reviewers. `sonnet` for premise checks, rebases and verifiers. Fixers on `opus`, or `sonnet` for a first-round `defect` finding. | The `sonnet` roles are fully specified before dispatch, mechanically checkable, and checked downstream by CI or the re-review. `design` findings and any round past the first stay on `opus`. No `haiku`. |
| Pipelining | Off | An issue is dispatched only after its blockers have merged. Your CI triggers on `pull_request` with `branches: [main]`, so a PR stacked onto a blocker's branch would get no CI at all. With pipelining off, every PR targets `main` and is checked. |
| CI gate | Required | I never merge over red or pending checks. `pull_request:` has no draft filter, so CI runs on the draft PR while review happens. |

What `auto` does not include:

- **No bypassing.** No `--admin`, no ruleset or bypass-actor edit, no repo setting changed to let a merge through. A merge the protection refuses parks that lane for you.
- **No unattended merge of a PR that touches CI config, release workflows or the permission system.** Those wait for you even when review passes and CI is green.
- **Nothing outside #300.** A new scope needs a new yes.

The repo is private, which lowers the cost of a bad merge, but each merge still lands on `main`.

Once the first agent is dispatched I won't stop to ask you anything. A lane that needs you gets its question posted under `## OWNER DECISION NEEDED`, the `needs-human` label, and its slot freed; the rest keeps moving. You'll find all open questions batched in the report.

**Say yes to this contract, and to `auto` merge in particular, and I start.**

## Right after you say yes

Issue numbers below are placeholders: `A < B < C < D` are the four ready sub-issues, lowest number first.

1. **Re-query the frontier**, so I dispatch against the graph as it is now.

   ```bash
   python3 /tmp/oi-eval/old/skills/orchestrate-issues/scripts/frontier.py --repo acme/atlas --parent 300 --json
   ```

2. **Read the four ready issues against each other for shared ground.**

   ```bash
   gh issue view <A> --repo acme/atlas --json number,title,body,assignees,labels,comments
   # same for B, C, D
   ```

   I look for a shared lock, manifest or generated file, a version or changelog bump CI requires, an interface one issue defines and another consumes, and sequence numbers such as migrations. For each overlap I pick one of:
   - serialize the two lanes (whole-file overlap, or define/consume);
   - `FENCE:` on both cards (different regions of one file);
   - `RESERVED:` on each card (sequence numbers, handed out in expected merge order).

   I also skip any issue that has an assignee, or whose body describes work only a person can do. The latter gets `needs-human` and a mention in the report.

3. **Claim the first three**, before any dispatch.

   ```bash
   gh issue edit <A> --repo acme/atlas --add-assignee @me
   gh issue edit <B> --repo acme/atlas --add-assignee @me
   gh issue edit <C> --repo acme/atlas --add-assignee @me
   ```

4. **Dispatch three implementers**, in one message. Each is an Agent call with `subagent_type: "workbench:implementer"`, `run_in_background: true`, `isolation: "worktree"`, `name: "impl-<n>"`, and the default `opus` model. Every blocker of a ready issue is closed, so the base is `main`. Each lane card:

   ```
   REPO:          acme/atlas
   ISSUE:         #<A> — <title>
   BRANCH:        issue-<A>-<slug>
   BASE:          main

   --- ISSUE BODY ---
   <full body of #A, verbatim>
   --- END ISSUE BODY ---

   [--- CLARIFYING COMMENTS --- ... --- END ---]      only if a comment changes the spec
   [FENCE: ...] [RESERVED: ...] [BUILD: ...]          only if step 2 called for them
   ```

   #D stays ready and unclaimed until a slot frees.

5. **Wait.** I don't poll. Each implementer wakes me when its draft PR is open.

## The loop from there

For each lane that reports back:

1. **Spec review.** Dispatch a fresh `workbench:spec-reviewer` (`name: "review-<n>-r1"`, worktree isolation, `opus`). Its card carries the issue body and a VERIFY block built from the implementer's own claims and anything I doubt. The reviewer posts findings on the PR and returns `VERDICT`, `KIND`, `POSTED`.
2. **On `CHANGES_REQUIRED`:** dispatch a fresh `workbench:fixer` (`fix-<n>-r<k>`), never the implementer. Model follows `KIND`: `sonnet` for a first-round `defect`, `opus` for `design`. If `main` moved under the lane, the card carries `CATCH UP: main`. A tests-only fix, confirmed with the compare call, gets a `workbench:verifier`; anything touching production code gets a fresh spec reviewer. After 2 rounds the lane parks with `needs-human`.
3. **On `PASS`:** confirm the PR body's only `Closes` line names the right issue, then land it.

   ```bash
   gh pr update-branch <pr> --repo acme/atlas        # only if behind
   gh pr ready <pr> --repo acme/atlas
   gh pr checks <pr> --repo acme/atlas --watch --interval 60 --fail-fast    # run in the background
   # when that reports green:
   gh pr merge <pr> --repo acme/atlas --squash --delete-branch
   python3 /tmp/oi-eval/old/skills/orchestrate-issues/scripts/prune_worktrees.py --apply --pr <pr>
   df -h .
   gh issue view <n> --repo acme/atlas --json state --jq .state    # must be CLOSED
   ```

   If the issue is still open, I close it with `gh issue close <n> --repo acme/atlas --comment "Landed in #<pr>."` before going on.
4. **Re-query the frontier** and fill free slots, lowest number first: claim, then dispatch. #D goes into the first free slot, and newly unblocked issues follow.
5. **Rebase survivors only when needed.** A real conflict before review gets a `workbench:rebaser`. A lane that is merely behind gets one `gh pr update-branch`, right before its merge.

Red CI that measures the PR goes to a fresh fixer. Red CI that looks unrelated gets a fresh sample with `gh pr update-branch`, then a read-only `workbench:ci-diagnostic` on a second strike. I never merge over it.

The run ends when the frontier reports complete or deadlocked, or when every remaining lane is parked on you.

## What you'll find tonight

I'd first sweep leftover worktrees:

```bash
python3 /tmp/oi-eval/old/skills/orchestrate-issues/scripts/prune_worktrees.py --apply
```

Then the report lists:

- issues landed, with PR links;
- what's still open and why;
- every `OWNER DECISION NEEDED`, batched, each with a link and my recommendation;
- every `ORCHESTRATOR DECISION` I made, with links, so you can reverse any of them;
- reviewer FOLLOW-UP findings and follow-up issues filed;
- any worktree the sweep kept, and why.

It will state only what actually ran, checked against GitHub rather than against my memory of the run.
