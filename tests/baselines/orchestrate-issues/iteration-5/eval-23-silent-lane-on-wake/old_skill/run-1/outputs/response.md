# This turn (02:26) — rehearsal, nothing run

Contract as given: `acme/atlas`, `auto` into `feat/atlas-export`, 3 lanes. Lanes: #371 (PR #441, review PASS), #372 (impl-372, silent since 00:28), #373 (impl-373, 36 min in). No questions to you; nothing here needs one.

## 1. Confirm the wake-up is news, not a replay

```bash
gh pr view 441 --repo acme/atlas --json state,isDraft,baseRefName,headRefOid,mergeStateStatus,body,statusCheckRollup
gh pr view 441 --repo acme/atlas --comments
```

Checking:
- PR is still open (if already merged, the notification is a replay — drop it).
- The reviewer's comment is actually on the thread (`POSTED`).
- Base is `feat/atlas-export`.
- The body's only `Closes` line is `Closes #371`.
- Any FOLLOW-UP findings — noted for the end report, they don't cost a round.

## 2. Land #441 (Step 5), each as its own command

```bash
gh pr update-branch 441 --repo acme/atlas     # only if step 1 showed it behind
gh pr ready 441 --repo acme/atlas
gh pr checks 441 --repo acme/atlas --watch --interval 60 --fail-fast    # run_in_background: true
```

I do **not** merge this turn. The watch is started after `ready`, in the background, and it is what wakes me next. When it reports, in a later turn and as separate commands:

```bash
gh pr view 441 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
# only if every check for the current head is SUCCESS/SKIPPED/NEUTRAL, from the post-ready run, and mergeStateStatus is CLEAN:
gh pr merge 441 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
python3 <skill>/scripts/prune_worktrees.py --apply --pr 441
gh issue view 371 --repo acme/atlas --json state
gh issue close 371 --repo acme/atlas --comment "Landed in #441."   # merge into a feature branch never fires Closes
df -h .
python3 <skill>/scripts/frontier.py --repo acme/atlas <scope selector from the contract>
```

Then fill the freed slot with the lowest-numbered ready issue. If CI is red on something measuring this PR: fresh fixer. If the merge is denied by the permission system: PR stays ready and green, other lanes continue, status line carries the unblocking sentence.

## 3. Look at the silent lane, #372 — through GitHub, not the agent

impl-372 has been quiet for 2 hours. The 00:28 "waiting on its own background work" notice was not a hand-back and needed no turn. Silence alone doesn't tell me it is dead, and I don't poll the agent, message it, or read its transcript. I check what survived on GitHub:

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas <scope selector from the contract>
gh pr list --repo acme/atlas --state all --search "372 in:body" --json number,isDraft,headRefName,updatedAt
gh api "repos/acme/atlas/branches/<impl-372 branch from my notes>" --jq '.commit.commit.committer.date'
```

What I do depends on what that shows:

- **Draft PR for #372 exists** — the work is done and the hand-back got lost. Advance the lane: dispatch `workbench:spec-reviewer` (`review-372-r1`, `opus`, background, worktree), with the VERIFY block built from the PR body since I have no implementer report.
- **Branch exists with recent pushes, no PR** — it is alive and pushing per criterion. Leave it alone.
- **Branch exists, last push long ago, or no branch at all** — I can't prove it dead: its `Agent` result has not come back null, and its worktree may still be running something. I don't dispatch a second implementer on top of it this turn. Slot stays held, the lane is flagged in the status line, and I re-check at my next wake (the #441 CI watch). If the agent then returns nothing, I dispatch a fresh implementer from the surviving branch, with a smaller job if it ran out of context.

## 4. #373

36 minutes in, no hand-back expected yet. No action.

## 5. Lanes and the end of the turn

All three slots are occupied (#371 landing, #372, #373), so no new dispatch this turn. Things that will wake me: the #441 CI watch, impl-373, impl-372 if it is alive (and review-372-r1 if I dispatched it). The turn ends with work in flight, so the run continues.

## Status line

Written after the commands above, with the bracketed parts filled from what they actually returned:

> **02:26 — acme/atlas → `feat/atlas-export`.** #371: review PASS on PR #441, marked ready, CI watching; will merge on green and close #371 by hand. #372: impl-372 silent since 00:28 (2h) — GitHub shows [draft PR #N, sent to review | branch last pushed HH:MM, still working | no branch, no PR — not confirmed dead, slot held, re-checking at next wake]. #373: impl-373 running since 01:50, nothing due yet. 3/3 lanes in use, nothing dispatched this turn. Nothing landed yet. No questions for you.
