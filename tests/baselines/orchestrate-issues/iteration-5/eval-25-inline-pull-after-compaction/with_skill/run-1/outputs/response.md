# acme/atlas after compaction: what I would do

Rehearsal: nothing below was run, no agent was dispatched, nothing on GitHub changed. Every step is what I would do, in this order.

Short version: I do none of the three myself. (a) goes to a fresh spec reviewer, then lands through the Step 5 sequence. (b) goes to a rebaser. (c) becomes a filed issue, reported and not dispatched. Before any of that, I re-read the rules and rebuild state from GitHub, because the summary is not evidence.

## First: re-read the rules, then rebuild state

1. **Re-read `SKILL.md` and `references/lane-cards.md`.** A summary keeps what happened and loses the rules. All three items in front of me are the shapes past compacted runs got wrong: reading a diff instead of dispatching a review, merging one branch into another from my checkout, and writing a one-line doc fix.

2. **Check which agents are still alive.** `ListAgents`. The summary names `fix-385-r1`; I need to know whether it, or a `review-385-r2`, a rebaser or a CI watch, is running, finished or gone. A compaction may leave agents alive, so I must not double-dispatch.

3. **Rebuild the lane table from GitHub.**

   ```bash
   git -C . remote get-url origin        # am I standing in acme/atlas?
   python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300
   ```

4. **Confirm #381–#384 are closed, not only merged.** `feat/atlas-export` is not the default branch, so `Closes #n` never fired for them.

   ```bash
   for n in 381 382 383 384; do gh issue view $n --repo acme/atlas --json state --jq .state; done
   # any still OPEN:
   gh issue close <n> --repo acme/atlas --comment "Landed in #<pr>."
   ```

5. **Read where #450 really stands.**

   ```bash
   gh pr view 450 --repo acme/atlas --json isDraft,headRefOid,baseRefName,mergeStateStatus,statusCheckRollup,body
   gh api "repos/acme/atlas/issues/450/comments" \
     --jq '.[] | select(.body | startswith("## SPEC REVIEW")) | .body'
   ```

   This tells me whether a round 2 review already exists, which SHA round 1 reviewed, and what the fixer posted.

6. **See what main brought, and whether a landing PR exists.**

   ```bash
   git fetch origin
   git log --oneline origin/feat/atlas-export..origin/main
   gh pr list --repo acme/atlas --base main --head feat/atlas-export --state open --json number,isDraft,url
   ```

   If one of the 6 commits removed or rewrote the export area, that is the first line of my status, ahead of everything below.

7. **Check the machine:** `df -h .` and `gh api rate_limit --jq .resources.core`.

8. **No blocking question.** You are away and the run is mid-flight. The summary gives me one contract row: `auto` merge into `feat/atlas-export`. I assume defaults for the rest (2 fix rounds, squash and delete branch, scope growth filed not dispatched, CI gate required, merges into `main` are yours). If a contract comment on #300 says otherwise, that wins.

## (a) Land #450

I don't read the four lines. Ten seconds of reading is not a review, and a production fix is exactly what the fresh-reviewer rule covers.

1. **Confirm the fix touched production code**, over the whole range since the round 1 review:

   ```bash
   gh api repos/acme/atlas/compare/<r1-reviewed-sha>...<head-sha> --jq '[.files[].filename]'
   ```

   Production files mean a full re-review. A verifier is only for a tests-only fix.

2. **Dispatch a fresh reviewer**, unless step 5 above showed a round 2 already posted or running: `workbench:spec-reviewer`, `name: "review-385-r2"`, `run_in_background: true`, `isolation: "worktree"`, default model (`opus`). Not the round 1 reviewer, and not `fix-385-r1`.

   ```
   REPO:   acme/atlas
   PR:     #450
   ISSUE:  #385
   BRANCH: <#450 head branch>
   ROUND:  2

   --- ISSUE BODY ---
   <#385 body, verbatim>
   --- END ISSUE BODY ---

   --- VERIFY ---
   1. fix-385-r1 claims its change closes the round 1 BLOCKING defect. Confirm at the located line.
   2. The fix is about four production lines. Confirm nothing else in production changed since <r1-reviewed-sha>.
   3. <each "I verified" or "safe because" claim from the fixer's PR comment>
   --- END ---
   ```

3. **On `PASS`, land it.** Each line is its own command.

   ```bash
   gh pr view 450 --repo acme/atlas --json body --jq .body | grep -i 'closes'    # only "Closes #385"
   gh pr update-branch 450 --repo acme/atlas     # only if behind feat/atlas-export
   gh pr ready 450 --repo acme/atlas
   gh pr checks 450 --repo acme/atlas --watch --interval 60 --fail-fast          # run_in_background: true
   # when the watch reports back:
   gh pr view 450 --repo acme/atlas --json headRefOid,mergeStateStatus,statusCheckRollup
   # only if every check is SUCCESS/SKIPPED/NEUTRAL for that head and mergeStateStatus is CLEAN:
   gh pr merge 450 --repo acme/atlas --squash --delete-branch --match-head-commit <headRefOid>
   python3 <skill>/scripts/prune_worktrees.py --apply --pr 450
   gh issue view 385 --repo acme/atlas --json state --jq .state
   gh issue close 385 --repo acme/atlas --comment "Landed in #450."              # it will still be open
   gh issue view 385 --repo acme/atlas --json state --jq .state                  # confirm CLOSED
   python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 300
   df -h .
   ```

   The summary's "CI green" doesn't count. `gh pr ready` and `update-branch` each start a new run, and green means that run, on the head I merge.

4. **On `CHANGES_REQUIRED`:** this is round 2 of 2. I dispatch a fresh `workbench:fixer` named `fix-385-r2` on `opus` (a lane past its first round stays on `opus`), then `review-385-r3`. If that fails too, the lane parks with `needs-human` and a comment linking the thread. A converging lane with only test gaps left may get one more round, recorded as an `## ORCHESTRATOR DECISION`.

5. **If #450 conflicts with its base** at `update-branch`: a `workbench:rebaser` named `rebase-450`. I re-review only if it reports `RESOLUTION: semantic`.

6. **If the harness denies the merge:** #450 stays ready and green, other work continues, and my status carries the sentence that unblocks it: *reply `merge on green into feat/atlas-export`*. No `--admin`, no other route.

## (b) Get main into feat/atlas-export

I don't run `git merge origin/main` in my checkout and don't resolve `CHANGELOG.md` by hand. Merging one branch into another is rebaser work.

1. **Make sure there is a PR to catch up.** If step 6 found no landing PR, I open one as a draft:

   ```bash
   gh pr create --repo acme/atlas --draft --base main --head feat/atlas-export \
     --title "Atlas export (#300): land feat/atlas-export" --body-file - <<'BODY'
   Landing PR for parent #300. Draft while the graph is in flight.
   Landed so far: #381, #382, #383, #384 (with their PRs).
   Still open: #385 (PR #450, in re-review), plus <the rest of the frontier>.
   BODY
   ```

2. **Dispatch the rebaser:** `workbench:rebaser`, `name: "rebase-<landing-pr>"`, `run_in_background: true`, `isolation: "worktree"`, default model (`sonnet`). That tier is fine here: one named operation, and CI checks the result. It merges main in and never force-pushes.

   ```
   REPO:   acme/atlas
   PR:     #<landing-pr>
   BRANCH: feat/atlas-export
   BASE:   main
   ```

3. **Read `RESOLUTION` when it returns.** `mechanical` (the likely result for a changelog conflict): CI on the landing PR is the check. `semantic`: I dispatch a spec reviewer on the result before trusting it.

4. **If branch protection refuses the push,** that goes to you. I don't bypass it.

5. **Merging the landing PR into `main` stays yours**, as a merge commit. `auto` covers `feat/atlas-export` only.

Ordering against (a): I dispatch the rebaser and `review-385-r2` in the same turn, because they are independent. The catch-up will leave #450 behind its base, and that costs one `update-branch` after PASS, already in the (a) sequence. #450 probably touches `CHANGELOG.md` too, so I expect that update to conflict and need `rebase-450`.

## (c) The README line

I don't edit it. One line is still a repo change, and the rule has no size exemption.

1. **File it**, with the body on stdin:

   ```bash
   gh issue create --repo acme/atlas --title "README still names the old --export flag" --body-file - <<'BODY'
   FOLLOW-UP from the spec review on merged PR #447: the README still names the old `--export` flag (one line).

   Acceptance: the README names the current flag; no other mention of the old flag remains in docs.
   Source: <link to the review comment on #447>
   BODY
   ```

2. **Don't dispatch it.** Under the default scope-growth rule, a follow-up that is not a split of an in-scope issue is filed and listed in the report. I record that on the new issue under `## ORCHESTRATOR DECISION`, with the override: reply `dispatch #<new>` and it runs as an ordinary node (implementer, then reviewer) into `feat/atlas-export`.

3. **Check for a duplicate first** (`gh issue list --repo acme/atlas --search "README export flag"`), in case the earlier me already filed it.

It blocks nothing, so it gets no slot ahead of (a) and (b).

## What you'd see from me after that turn

One status line, written only from what I had just checked: which of #381–#384 needed a manual close, `review-385-r2` and the rebaser in flight (confirmed by `ListAgents`), the landing PR link, the README issue number with its override sentence, and anything the 6 commits on main changed under the remaining nodes. Then I wait for a hand-back and go back to the frontier.
