Nothing here needs you before you go. Merge authority is `auto`, and the default contract lets me split oversized issues and report afterwards, so I'd land #52, split #14 into three chained sub-issues and start part 1. You'd wake up to a status line, not a question.

**Assumptions:**
- I haven't seen the issue bodies or the new issue numbers, so `$C1`–`$C3` stand in for the parts filed from #14.
- Branch protection and visibility were checked at preflight when you agreed `auto`, and the local checkout is acme/ledger.
- Before acting I'd confirm `$C1` is really ready from the frontier, not assume it.

## Ordered actions

**1. Check PR #52 before merging (read-only)**
```bash
gh pr view 52 --repo acme/ledger --json body,isDraft,baseRefName,headRefName,mergeStateStatus,files
```
- The body must have exactly one `Closes` line, and it must be `Closes #12`.
- The base must be `main` (the default branch).
- The files must not touch CI config, release workflows or permissions. If they do, I don't merge unattended: I comment `## OWNER DECISION NEEDED`, add `needs-human` and move on.

**2. Land #52**
```bash
gh pr ready 52 --repo acme/ledger
# only if mergeStateStatus == BEHIND (no conflict): update once, right before merging
gh pr update-branch 52 --repo acme/ledger
# run_in_background: true — only if update-branch (or ready) started new checks
gh pr checks 52 --repo acme/ledger --watch --interval 60 --fail-fast
# on green:
gh pr merge 52 --repo acme/ledger --squash --delete-branch   # never --admin
gh issue view 12 --repo acme/ledger --json state --jq .state
# if not CLOSED:
gh issue close 12 --repo acme/ledger --comment "Landed in #52."
```
If the merge is refused by branch protection, the lane goes to you; I don't work around it.

**3. Free up worktrees and disk from lane 12**
```bash
git worktree list
git worktree remove --force <impl-12 path>
git worktree remove --force <review-12-r1 path>   # not impl-11's worktree
git worktree prune
df -h .
```

**4. Split #14 (a recorded decision under the split authority)**
```bash
P=14
C1=$(gh issue create --repo acme/ledger --title "<#14 title> — part 1: schema" --body-file split-14-1.md | grep -oE '[0-9]+$')
C2=$(gh issue create --repo acme/ledger --title "<#14 title> — part 2: writer" --body-file split-14-2.md | grep -oE '[0-9]+$')
C3=$(gh issue create --repo acme/ledger --title "<#14 title> — part 3: reader" --body-file split-14-3.md | grep -oE '[0-9]+$')
for C in $C1 $C2 $C3; do
  gh api --method POST repos/acme/ledger/issues/$P/sub_issues -F sub_issue_id=$(gh api repos/acme/ledger/issues/$C --jq .id)
done
# serial chain: writer waits on schema, reader waits on writer (issue_id = database id, not the number)
gh api --method POST repos/acme/ledger/issues/$C2/dependencies/blocked_by -F issue_id=$(gh api repos/acme/ledger/issues/$C1 --jq .id)
gh api --method POST repos/acme/ledger/issues/$C3/dependencies/blocked_by -F issue_id=$(gh api repos/acme/ledger/issues/$C2 --jq .id)
```
- Each body file holds that part's share of #14's acceptance criteria plus `Part of #14`.
- Before adding the chain, I'd run `gh api repos/acme/ledger/issues/14/dependencies/blocked_by`. If #14 has open blockers, I'd add the same edges to `$C1` so part 1 can't jump ahead of them.
```bash
gh issue comment 14 --repo acme/ledger --body "## ORCHESTRATOR DECISION — split into #$C1 (schema) → #$C2 (writer) → #$C3 (reader), serial, following premise-14's proposed cut (SIZE: oversized, CONFIDENCE: clear; all claims VERIFIED). Alternative: implement as one lane (rejected: oversized diffs pass first review about half as often). The parts reuse premise-14's results; no new checks. #14 stays open as the container and closes once all three parts land. To reverse, close the three parts."
```

**5. Query the frontier again**
```bash
python3 <skill>/scripts/frontier.py --repo acme/ledger --parent 10 --json
```
I expect #12 done, #11 in flight, #14 as a container, and `$C1` ready if #14 had no open blockers. Up to 2 lanes are free (concurrency 3, with impl-11 in one). I fill them lowest issue number first.

**6. Check `$C1` against #11 for overlap**
If both add a migration or schema version, I'd reserve the numbers on the card in expected merge order (`RESERVED:`). If #11 defines something the schema part uses, I'd run them one after the other instead.

**7. Claim and start part 1 (schema)**
```bash
gh issue edit $C1 --repo acme/ledger --add-assignee @me
```
- `subagent_type`: `orchestrate-issues:implementer`
- `isolation`: `worktree`
- `name`: `impl-$C1`
- `model`: `opus` (the default; no drop to sonnet)
- `run_in_background`: true
```
REPO:   acme/ledger
ISSUE:  #$C1 — <#14 title> — part 1: schema
BRANCH: issue-$C1-schema
BASE:   main
--- ISSUE BODY ---
<split-14-1.md, verbatim>
--- END ISSUE BODY ---
--- VERIFIED CONTEXT ---
Parent #14's premise check verified every claim. The schema part is serial-first:
#$C2 (writer) and #$C3 (reader) build on what this part defines, so keep it to the schema only.
--- END ---
[RESERVED: migration <NNNN> (<NNNN±1> is #11's), only if step 6 found a collision]
```
- Part 1 doesn't get a premise check of its own; it reuses #14's.
- Parts 2 and 3 wait until the part before them merges.
- If the frontier shows a second ready issue that doesn't overlap, it gets its own claim and an opus implementer in the third lane.

**8. Leave impl-11 alone**
Merging #52 moved `main` underneath it, but I don't interrupt it. The one exception: if #52 changed code that #11 calls, I'd send it a one-line note that `main` moved.

When it opens its PR, I'd rebase it before review only if there's a conflict; if it's merely behind, it gets a single `update-branch` right before merging.

**9. Status line, then wait**
> #12 landed via #52. #14 was oversized, so I split it into #$C1 → #$C2 → #$C3 (recorded decision; close the parts to reverse it). In progress: impl-11 and impl-$C1. Nothing needs you.

I don't ask you anything and don't schedule a wake-up. impl-11, impl-$C1 and any background CI check will each wake me when they finish.