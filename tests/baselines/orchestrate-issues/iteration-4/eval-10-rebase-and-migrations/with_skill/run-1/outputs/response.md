# Plan for the four lanes on acme/ledger

Rehearsal: nothing below was run. No command touched GitHub and no agent was dispatched. Everything is what I would do, in order.

I'm taking the contract as you stated it: 3 lanes, `auto` merge, squash and delete branch, lane PRs targeting `main`. I never edit a file myself; every change goes to a subagent.

## Summary

| Lane | State | Move |
|---|---|---|
| #30 / PR #60 | PASS, 2 behind `main`, no conflict | Update the branch once, mark ready, wait for green on the new head, merge. No rebaser, no re-review. |
| #31 | Implementer still working, adds a migration | Don't interrupt its work. Send one short message reserving migration `0020`. |
| #32 | CHANGES_REQUIRED (defect), `main` moved in the same module | One fresh fixer with `CATCH UP: main`. No separate rebase. Then a fresh full re-review. |
| #33 | Ready, adds a migration | Waits for the slot #60 frees. Dispatched with `RESERVED: migration 0021`. |

The migration numbers are the shared ground here. #31 and #33 would both take `0020` if each picked the next free number, and whichever merged second would have to renumber, re-run CI, and possibly do it again. So I reserve them now, in expected merge order: `0020` for #31, `0021` for #33.

## Lane by lane

### #30 / PR #60: land it

It is merely behind, with no conflict, and it has passed. That is the case where the branch is updated once, right before merging, and not before. A conflict-free catch-up is mechanical, so CI is its check and it does not get another spec review.

The update goes first so that green means green on the head I merge. `gh pr update-branch` and `gh pr ready` each start a new CI run, so I watch in the background and then read the rollup for the current head as a separate step. The merge is its own command, only after I have read that output.

After the merge I prune that PR's worktrees, confirm issue #30 closed (it should, since the PR targets the default branch, but I check), and re-query the frontier.

### #31: reserve its migration number, otherwise leave it alone

The implementer is still running, so I don't tell it the base moved; it finishes and opens its PR on its own. The one thing I do send is the reservation, because it settles something it is working on right now and costs less than a renumber later:

> RESERVED: your migration is `0020`. `0021` belongs to #33. Don't take the next free number.

When its PR opens, it goes to a fresh spec reviewer as usual. If `main` has only moved without conflict by then, I don't rebase it until it passes.

### #32: one fixer that catches up first

A fix round is pending anyway, so I don't dispatch a rebaser and then a fixer. That would be two pushes and two CI runs. The fixer's card carries `CATCH UP: main`, so it merges `main` in first and then fixes the findings, in one push.

It is a fresh `workbench:fixer`, not the original implementer woken up, and it reads the findings off the PR thread itself.

Model: `sonnet`, which is a deliberate drop from `opus`. The three conditions hold:
1. The task is specified: the reviewer classified the round as `defect`, located to a file and line.
2. It is mechanically checkable: the suite fails if the fix is wrong.
3. Something runs that check: CI, plus the re-review below.

The one risk is the catch-up merge. The merged PR touched the same module, so resolving it may need judgement. If the fixer reports that the merge changed what the code does, or disputes a finding, the next agent on this lane is on `opus`.

Afterwards it gets a fresh full spec review (`review-32-r2`), not a verifier, even if the fix itself was tests-only. The push will contain a merge of production code in the module this lane changes, and the reviewer should judge the diff that will actually merge. I'd confirm with the compare call and put the merged PR in the reviewer's VERIFY block.

This is round 1 of the 2 fix rounds in the contract. The catch-up does not count as a round.

### #33: dispatch when #60's slot frees

Three lanes are in flight (#30, #31, #32), so #33 waits. Merging #60 frees a slot, and #33 goes then, after a fresh frontier query confirms it is still ready and unassigned.

Before dispatching I read #33 against #31 for overlap beyond the migration (same tables, same module, a shared schema file). If they rewrite the same file I serialize them; if they touch different regions I fence both cards.

Its card carries `RESERVED: migration 0021 (0020 is reserved for #31)`. Base is `main`, after #60 has landed. Model is `opus`.

### If merge order differs from the reservation

One rule, applied only at merge time: a lane whose number is not the next one after the highest on `main` renumbers to that next one, right before it merges. Nobody renumbers in anticipation.

So if #33 passes first, a rebaser renumbers it `0021 -> 0020` just before its merge, and #31 later renumbers `0020 -> 0021` just before its own. Each lane moves at most once. A renumber is mechanical, so CI checks it and there is no re-review.

## Commands, in order

Turn 1, all started together.

Check the migration assumption (read-only):

```bash
git fetch origin
git ls-tree --name-only origin/main migrations/ | tail -3      # confirm 0019 is still the highest
gh pr view 60 --repo acme/ledger --json files --jq '[.files[].path | select(startswith("migrations/"))]'
gh pr view <pr-for-32> --repo acme/ledger --json files --jq '[.files[].path | select(startswith("migrations/"))]'
```

If #60 or #32's PR adds a migration, the reservations shift up by one and I say so.

Start landing #60:

```bash
gh pr update-branch 60 --repo acme/ledger
gh pr ready 60 --repo acme/ledger
# run_in_background: true
gh pr checks 60 --repo acme/ledger --watch --interval 60 --fail-fast
```

Message the running implementer for #31 (`SendMessage` to `impl-31`, the text quoted above).

Dispatch the fixer for #32 (Agent tool, `subagent_type: "workbench:fixer"`, `name: "fix-32-r1"`, `model: "sonnet"`, `isolation: "worktree"`, `run_in_background: true`):

```
REPO:   acme/ledger
ISSUE:  #32
PR:     #<pr-for-32>
BRANCH: <branch-for-32>
ROUND:  1
CATCH UP: main

--- ISSUE BODY ---
<full body of #32, verbatim>
--- END ISSUE BODY ---
```

Then I wait. Nothing is polled.

When the #60 watch reports back, each as its own command:

```bash
gh pr view 60 --repo acme/ledger --json headRefOid,mergeStateStatus,statusCheckRollup
```

Only if every check on that head is `SUCCESS`, `SKIPPED` or `NEUTRAL`, the run is the one started after `gh pr ready`, and `mergeStateStatus` is `CLEAN`:

```bash
gh pr merge 60 --repo acme/ledger --squash --delete-branch --match-head-commit <headRefOid>
```

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr 60
df -h .
gh issue view 30 --repo acme/ledger --json state --jq .state
# only if still OPEN:
gh issue close 30 --repo acme/ledger --comment "Landed in #60."
python3 <skill>/scripts/frontier.py --repo acme/ledger <scope selector>
```

If a check is red, #60 does not merge. A failure caused by its diff goes to a fresh fixer; anything else follows the flaky-gate protocol. If the merge is refused by branch protection or by the permission system, the PR stays ready and green, the other lanes keep moving, and I report it with the sentence that would clear it. I never use `--admin`.

Then dispatch #33, if the frontier still shows it ready:

```bash
gh issue edit 33 --repo acme/ledger --add-assignee @me
```

Agent tool, `subagent_type: "workbench:implementer"`, `name: "impl-33"`, `isolation: "worktree"`, `run_in_background: true`, default model (`opus`):

```
REPO:     acme/ledger
ISSUE:    #33 — <title>
BRANCH:   <branch-for-33>
BASE:     main

--- ISSUE BODY ---
<full body of #33, verbatim>
--- END ISSUE BODY ---

[--- WHERE THE ISSUE IS WRONG --- <premise-check corrections, if any> --- END ---]
[FENCE: <only if #31 and #33 share a file>]
RESERVED: migration 0021 (0020 is reserved for #31)
```

If #33 has no premise check on record from preflight and names specific code, a `workbench:premise-checker` (`premise-33`, `sonnet`) runs first and its corrections go on the card.

When the #32 fixer reports back:

```bash
gh api repos/acme/ledger/compare/<reviewed-sha>...<head-sha> --jq '[.files[].filename]'
```

Then a fresh `workbench:spec-reviewer`, `name: "review-32-r2"`, `opus`, `ROUND: 2`, with VERIFY listing the fixer's claims and "the catch-up merge of `main` brought in <merged PR>, which touched <module>; confirm the lane's change still does what #32 asks on top of it". On PASS, #32 lands with the same sequence as #60. If #60 merged after the fixer's catch-up, #32 is merely behind again, and the `gh pr update-branch` at the start of that landing sequence covers it.

When the #31 implementer opens its PR: fresh `workbench:spec-reviewer` (`review-31-r1`), with "migration is numbered `0020`" in VERIFY. If `main` conflicts with it or changed code it calls, a `workbench:rebaser` (`rebase-31`) goes first.

Renumber at merge time, only if needed (Agent tool, `subagent_type: "workbench:rebaser"`, `sonnet`):

```
REPO:   acme/ledger
PR:     #<pr>
BRANCH: <branch>
BASE:   main
RENUMBER: migrations/0021_<name>.sql -> 0020 (0020 is the next number after main's highest)
```

## What I'm assuming

- `auto` merge into `main` is something you granted in your own words when the contract was agreed. If lane PRs actually target a feature branch, the plan is the same with that branch in place of `main`, plus a manual `gh issue close` after every merge, since `Closes #n` won't fire.
- #31 was dispatched without a reservation. If its card already reserved a number, I keep that one and give #33 the next.
- Neither #60 nor #32's PR adds a migration. The first commands check this.
