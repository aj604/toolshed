# acme/ledger run (parent #10): what I do next

Nothing here needs you before you go offline. I land PR #52, split #14 into three serial sub-issues and dispatch the first, leave impl-11 alone, and keep cycling overnight. I ask no blocking question; anything that needs you parks its own lane with a `needs-human` label and a comment, and the rest keeps moving.

Two readings of the contract I'm acting on:

- **Merge authority `auto` means auto into the run's integration branch** (the feature branch the contract named; written `$INT` below). It does not cover the default branch. The landing PR from `$INT` into the default branch is yours to merge.
- **Split authority is the default, "split and report".** premise-14 came back `SIZE: oversized, CONFIDENCE: clear`, so this is not a borderline call and I file the split myself instead of waiting for you.

Rehearsal: nothing below was run.

## 1. Start landing PR #52 (issue #12)

Review PASS plus green CI on the draft is not yet mergeable green: `gh pr ready` starts a new CI run, and that run on the current head is the one that counts.

```bash
# Confirm the body closes #12 and only #12, and see whether the branch is behind
gh pr view 52 --repo acme/ledger --json body,baseRefName,headRefOid,mergeStateStatus,isDraft

# Only if mergeStateStatus is BEHIND — do this first so green means green on the head I merge
gh pr update-branch 52 --repo acme/ledger

gh pr ready 52 --repo acme/ledger

# run_in_background: true — never in the foreground
gh pr checks 52 --repo acme/ledger --watch --interval 60 --fail-fast
```

If the body's `Closes` line names the wrong issue, I fix the body before going further. I don't wait on the watch; I go straight to step 2.

## 2. Split #14 while #52's CI runs

I never dispatch #14 as one lane. I file three sub-issues following the check's cut (schema, writer, reader), each with its share of #14's acceptance criteria, with serial `blocked_by` edges, and a decision comment on #14.

```bash
gh issue view 14 --repo acme/ledger --json title,body,assignees,labels
gh api repos/acme/ledger/issues/14/dependencies/blocked_by --jq '[.[]|{number,state,title}]'

P=14
C1=$(gh issue create --repo acme/ledger --title "<#14 title> — part 1: schema" \
       --body-file - <<'SPLIT_EOF' | grep -oE '[0-9]+$'
<schema share of #14's acceptance criteria, per premise-14's cut>

Part of #14
SPLIT_EOF
)
C2=$(gh issue create --repo acme/ledger --title "<#14 title> — part 2: writer" \
       --body-file - <<'SPLIT_EOF' | grep -oE '[0-9]+$'
<writer share of #14's acceptance criteria>

Part of #14
SPLIT_EOF
)
C3=$(gh issue create --repo acme/ledger --title "<#14 title> — part 3: reader" \
       --body-file - <<'SPLIT_EOF' | grep -oE '[0-9]+$'
<reader share of #14's acceptance criteria>

Part of #14
SPLIT_EOF
)

# Make each a sub-issue of #14
for C in $C1 $C2 $C3; do
  gh api --method POST repos/acme/ledger/issues/$P/sub_issues \
    -F sub_issue_id=$(gh api repos/acme/ledger/issues/$C --jq .id)
done

# Serial edges: writer blocked by schema, reader blocked by writer (database ids, not issue numbers)
gh api --method POST repos/acme/ledger/issues/$C2/dependencies/blocked_by \
  -F issue_id=$(gh api repos/acme/ledger/issues/$C1 --jq .id)
gh api --method POST repos/acme/ledger/issues/$C3/dependencies/blocked_by \
  -F issue_id=$(gh api repos/acme/ledger/issues/$C2 --jq .id)

gh issue comment $P --repo acme/ledger --body-file - <<'EOF'
## ORCHESTRATOR DECISION — split into #C1 (schema), #C2 (writer), #C3 (reader), serial

**Why:** the premise check verified every claim but sized this issue as oversized (confidence: clear). Lanes over ~1500 changed lines pass first review about half as often.
**Alternative:** dispatch #14 as a single lane.
**To reverse:** close the three children and reply here; I'll run #14 as one lane.
EOF
```

One thing the split recipe doesn't cover: sub-issues don't inherit their parent's blockers. If the `blocked_by` query shows #14 still has an open blocker (#11 or #12, say), I copy that edge onto part 1 so the schema lane can't start ahead of its foundation, and say so in the decision comment:

```bash
gh api --method POST repos/acme/ledger/issues/$C1/dependencies/blocked_by \
  -F issue_id=$(gh api repos/acme/ledger/issues/<open-blocker> --jq .id)
```

The children inherit #14's premise check (all claims verified), so I run no new checks on them.

## 3. Merge #52 when the background watch reports

The watch ending is a prompt to look, not a verdict. Each of these is its own command:

```bash
gh pr view 52 --repo acme/ledger --json headRefOid,mergeStateStatus,statusCheckRollup
```

I merge only if every check on the current head finished `SUCCESS`, `SKIPPED` or `NEUTRAL`, the run is the one started after `gh pr ready`, and `mergeStateStatus` is `CLEAN` (`UNKNOWN` means read again in a minute). Then:

```bash
gh pr merge 52 --repo acme/ledger --squash --delete-branch --match-head-commit <headRefOid>

python3 <skill>/scripts/prune_worktrees.py --apply --pr 52
df -h .
```

`$INT` is not the default branch, so `Closes #12` won't fire. I close the issue myself and confirm it before re-querying:

```bash
gh issue view 12 --repo acme/ledger --json state --jq .state
gh issue close 12 --repo acme/ledger --comment "Landed in #52."
gh issue view 12 --repo acme/ledger --json state --jq .state     # must say CLOSED
```

If it goes another way:

- **Red on a check measuring this PR:** fresh `workbench:fixer` (`fix-12-r1`), no merge.
- **Red that doesn't look like this PR's fault:** the flaky/broken-gate protocol in `references/troubleshooting.md`, no merge.
- **Branch protection refuses the merge:** I park #52 ready and green with `needs-human`. No `--admin`, no ruleset edits.
- **The harness denies `gh pr merge`:** I leave #52 ready and green, keep the other lanes going, and put this in the status line: *Merge of #52 into `$INT` was denied. Reply `merge on green into $INT` and I'll land it and everything queued behind it.*

## 4. Re-query the frontier and fill the free slots

```bash
python3 <skill>/scripts/frontier.py --repo acme/ledger --parent 10 --json
```

I expect #14 as `split` (a container, not dispatched), part 1 as `ready` if #14 had no open blockers, parts 2 and 3 as `blocked`, #11 as `in_flight`, #12 as `done`, plus anything #12's close unblocked.

Concurrency is 3 and only impl-11 is running, so two slots are open. I fill them lowest issue number first, after reading the ready issues against each other and against #11 for shared ground (same file, a manifest or version bump, a migration number). Part 1 is a schema change, so if it adds a migration I reserve its number on the card rather than let it take the next free one.

For each issue I dispatch, claim first:

```bash
gh issue edit $C1 --repo acme/ledger --add-assignee @me
```

Then one Agent call per issue:

- `subagent_type: "workbench:implementer"`, `name: "impl-<C1>"`, `run_in_background: true`, `isolation: "worktree"`, model left at the agent's default (`opus`)
- Lane card:

```
REPO:   acme/ledger
ISSUE:  #<C1> — <#14 title> — part 1: schema
BRANCH: <branch name per repo convention>
BASE:   $INT

--- ISSUE BODY ---
<part 1's body, verbatim>
--- END ISSUE BODY ---

--- VERIFIED CONTEXT ---
<only the facts from premise-14 and from #12's landed work that the schema piece builds on, by identifier>
--- END ---
[RESERVED: migration <NNNN> (<NNNN-1> is reserved for #m)]   # only if a sibling lane also adds one
[FENCE: ...]                                                   # only if it shares a file with #11
```

Parts 2 and 3 stay undispatched. Pipelining is off, so the writer waits until the schema issue is closed, and the reader waits for the writer.

## 5. impl-11: leave it alone

It is still working, and I don't message it about #52's merge moving its base. When it opens its draft PR and hands back:

- If #52 conflicts with it or changed code it calls, I dispatch `workbench:rebaser` (`rebase-11`) before review.
- If it is merely behind, I don't rebase until it has passed review, then run `gh pr update-branch` once right before merging.
- Either way I dispatch a fresh `workbench:spec-reviewer` (`review-11-r1`) with a VERIFY block built from impl-11's report.

## 6. Keep cycling overnight

Each hand-back advances its own lane, and every merge is followed by prune, manual close, confirmed close, and a fresh frontier query. Specifically:

- **`CHANGES_REQUIRED`:** a fresh fixer, never the implementer. Up to 2 fix rounds, plus one more on my own authority if the lane is converging and only test gaps remain, recorded as an orchestrator decision. Past that the lane parks with `needs-human`.
- **Judgement calls the contract covers:** I decide, record it under `## ORCHESTRATOR DECISION` on the issue or PR, and continue.
- **Anything irreversible or out of scope:** `## OWNER DECISION NEEDED` on the issue, `needs-human`, slot freed. Only that lane stops.
- **When all three parts of #14 are closed** the frontier reports #14 as `split_complete`. I close it with a comment listing the three PRs, which opens its downstream edges.

```bash
gh issue close 14 --repo acme/ledger --comment "All parts landed: #<pr1>, #<pr2>, #<pr3>."
```

## 7. When the graph completes or the run stops

```bash
python3 <skill>/scripts/prune_worktrees.py --apply

gh pr list --repo acme/ledger --base <default> --head $INT --state open --json number,url
# if none is open:
gh pr create --repo acme/ledger --base <default> --head $INT \
  --title "#10: land $INT" --body-file - <<'BODY'
<issues landed with their PRs, every ORCHESTRATOR DECISION (the #14 split first), what is still open>
BODY
```

If the default branch moved, I send a `workbench:rebaser` at the landing PR and let CI run on the result. I do not merge it: that merge is yours, as a merge commit, not a squash.

## What you'll find in the morning

One report, in this order:

- the landing PR, with its link and CI state
- issues landed, with PR links
- what's still open and why
- every `OWNER DECISION NEEDED`, batched, each with a link and my recommendation
- every `ORCHESTRATOR DECISION`, with links, starting with the #14 split and how to reverse it
- FOLLOW-UP findings reviewers left on merged PRs
- any worktrees the sweep kept, and why

It will describe only what actually ran, checked against GitHub rather than against this plan.

**Status line as you leave:** #52 (issue #12) marked ready, merging into `$INT` once the post-ready CI run is green. #14 split into schema, writer and reader, serial; part 1 dispatched if #14 has no open blockers. impl-11 still running. No open questions for you.
