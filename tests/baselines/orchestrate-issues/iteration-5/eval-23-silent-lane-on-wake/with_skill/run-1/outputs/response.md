# Turn at 02:26: woken by review-371-r1 (PASS, PR #441)

Rehearsal: nothing below was run. Each step is what I would do, in this order.

## 0. Before advancing anything: which lanes are overdue?

| Lane | Dispatched | Last sign of life | Silent for | Limit | Overdue? |
|---|---|---|---|---|---|
| impl-372 | 00:27 | waiting notice, 00:28 | 118 min (119 since dispatch) | 90 min for an implementer, 45 since a waiting notice | **Yes** |
| impl-373 | 01:50 | dispatch | 36 min | 90 min | No |

impl-372 is past both limits, so it gets looked at before #441 moves. Hearing nothing is not evidence that it is running.

## 1. Look at impl-372, in the skill's order

**1a. The agent list.** Call `ListAgents`. This one call also confirms impl-373, which the status line will name as in flight.

- `impl-372` shows `running`: go to 1b for a quick confirmation, then step 2.
- `impl-372` is missing, `completed` or `killed`, with no hand-back: it is dead. Go to 1c, then 1d.

**1b. Its worktree**, when the list can't say, or says `running` after two silent hours:

```bash
git worktree list                                                   # find the path holding issue 372's branch
find <path> -type f -mmin -30 -not -path '*/.git/*' | head -3       # anything written in the last half hour?
lsof -a -d cwd -Fn | grep -c <path>                                 # is a process still running there?
```

No recent writes and no process means dead, whatever the list says. Either one present means alive: leave it alone. No `SendMessage` nudge, and no reading its transcript.

**1c. GitHub**, to learn what survived:

```bash
git ls-remote --heads origin '*372*'
gh pr list --repo acme/atlas --state all --search "372 in:body" \
  --json number,state,isDraft,headRefName,baseRefName,url
gh api "repos/acme/atlas/commits?sha=<branch>&per_page=5" --jq '.[] | {sha: .sha[0:7], date: .commit.committer.date, msg: .commit.message}'   # only if a branch exists
```

**1d. If dead: replace it, don't ask about it.**

1. `TaskStop` on `impl-372`. This fails harmlessly if it is already gone.
2. Dispatch a fresh implementer. The issue is already assigned to me, so no new claim.
   - `subagent_type: "workbench:implementer"`, `name: "impl-372-b"`, `run_in_background: true`, `isolation: "worktree"`, model `opus` (the default)
   - Lane card: `REPO: acme/atlas`, `ISSUE: #372 — <title>`, `BRANCH: <same branch>`, `BASE: feat/atlas-export`, the full issue body verbatim, the original card's corrections, fence and reservations, plus one line on what survived. That line is either "continue from pushed branch `<branch>` at `<sha>`; draft PR #<n> exists" or "nothing was pushed; start clean".
3. Comment on the issue:

```bash
gh issue comment 372 --repo acme/atlas --body-file - <<'EOF'
## ORCHESTRATOR NOTE: lane replaced
impl-372 (dispatched 00:27) was last heard from at 00:28 and was found dead at 02:26
(<agent list state>; no writes or processes in its worktree).
Survived: <branch at sha / draft PR #n / nothing>. Replaced by impl-372-b.
EOF
```

I don't touch the old worktree. If it holds uncommitted work, the end-of-run prune keeps it and reports it. This is the first death on this lane; a second one the same way parks it with `needs-human` rather than getting a third agent.

## 2. Advance #441 (PASS from review-371-r1)

Merge authority is `auto` into `feat/atlas-export`, so this lands without asking.

**2a. Replay check, body check and whether it is behind, in one read:**

```bash
gh pr view 441 --repo acme/atlas --json state,isDraft,baseRefName,headRefOid,mergeStateStatus,body
```

- If it is already `MERGED`, the notification is a replay: drop it.
- `baseRefName` must be `feat/atlas-export`.
- The body's only `Closes` line must be `Closes #371`. If it names another issue, I don't merge. A fixer corrects the body.

**2b. Make it ready and start CI, with the watch in the background:**

```bash
gh pr update-branch 441 --repo acme/atlas          # only if mergeStateStatus is BEHIND; do this first
gh pr ready 441 --repo acme/atlas
gh pr checks 441 --repo acme/atlas --watch --interval 60 --fail-fast     # run_in_background: true
```

**2c. The turn ends here.** Three things can wake me: the watch on #441, impl-373, and impl-372 or impl-372-b. I don't merge this turn. A merge chained straight after `gh pr ready` would be reading the previous run's checks.

I fill no new lane this turn either. All three slots are still held (371 until it merges, 372, 373).

## 3. Next wake, when the watch reports (not this turn)

Each is its own command, and each waits on the one before:

```bash
gh pr view 441 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
# only if every check for this head is SUCCESS/SKIPPED/NEUTRAL, from the run started after `gh pr ready`, and mergeStateStatus is CLEAN:
gh pr merge 441 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
python3 <skill>/scripts/prune_worktrees.py --apply --pr 441
df -h .
gh issue view 371 --repo acme/atlas --json state --jq .state      # stays OPEN: the merge is into a feature branch
gh issue close 371 --repo acme/atlas --comment "Landed in #441."
gh issue view 371 --repo acme/atlas --json state --jq .state      # confirm CLOSED before re-querying
python3 <skill>/scripts/frontier.py --repo acme/atlas <scope selector>
```

Then I fill the freed slot with the lowest-numbered ready issue. Red CI caused by the diff goes to a fresh fixer. Red for an outside reason parks the PR. The same silence check runs again first on that wake: impl-373 passes 90 minutes at 03:20.

## Status line

I write whichever matches what step 1 found.

**If impl-372 was alive:**

> 02:26, acme/atlas → `feat/atlas-export`. #371: review PASS on PR #441, marked ready, CI running; not merged yet, it merges on green. #372: impl-372 had been silent since 00:28, so I checked it at 02:26; it is running (agent list `running`, files written in the last 30 min); no PR yet. #373: impl-373 running since 01:50 (agent list, 02:26); no PR yet. Nothing merged this turn. No open questions for you.

**If impl-372 was dead:**

> 02:26, acme/atlas → `feat/atlas-export`. #371: review PASS on PR #441, marked ready, CI running; not merged yet, it merges on green. #372: impl-372 died some time after 00:28 without handing back (found at 02:26: <agent list state>, no writes or processes in its worktree). Survived: <branch at sha / nothing>. Replaced by impl-372-b at 02:2x, noted on #372. About two hours were lost on that lane. #373: impl-373 running since 01:50 (agent list, 02:26); no PR yet. Nothing merged this turn. No open questions for you.
