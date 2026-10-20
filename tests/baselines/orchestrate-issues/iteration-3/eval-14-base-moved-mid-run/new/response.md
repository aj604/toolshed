I won't rebase or merge origin/main. The lane card says to verify against the BASE I branched from (`a1b2c3d`), and moving to a newer base is the orchestrator's call. No message has come, so I'll keep going on that base, commit criterion 1 now, finish criterion 2 and open the draft PR. I'll flag the overlap in `src/cart/pricing.py` in my report. I won't end my turn early: the fetch isn't a reason to stop.

1. **Bash** `cd /work/impl-22 && git status --short && git diff --stat` (timeout 60000, run_in_background false)
   *Reason:* make sure the uncommitted changes are only my criterion-1 work before committing. *Expect:* `M src/cart/pricing.py`, plus a modified or new `tests/cart/test_pricing.py`.

2. **Bash** `cd /work/impl-22 && pytest -q tests/cart/test_pricing.py 2>&1 | tail -20` (timeout 600000, run_in_background false)
   *Reason:* re-confirm criterion 1 is green before committing. *Expect:* all pass.

3. **Bash** `cd /work/impl-22 && git add src/cart/pricing.py tests/cart/test_pricing.py && git commit -m "cart: allow coupon stacking per #22 (criterion 1)" && git push -u origin issue-22-coupon-stacking 2>&1 | tail -5` (timeout 120000, run_in_background false)
   *Reason:* commit and push as each criterion is met, so a dead lane still leaves a usable branch. *Expect:* branch pushed.

4. **Bash** `cd /work/impl-22 && git log --oneline a1b2c3d..origin/main && git diff a1b2c3d origin/main --stat -- src/cart/pricing.py` (timeout 60000, run_in_background false)
   *Reason:* this only reads the other lane's change so I can describe the conflict risk in my report. It changes nothing in my tree. *Expect:* 6 commits, with one PR touching `pricing.py`, and roughly how many lines it changed.

5. **Read / Edit** on `src/cart/pricing.py` and `tests/cart/test_pricing.py`
   *Reason:* implement criterion 2 against `a1b2c3d`, matching the surrounding code, with tests. *Expect:* edits applied.

6. **Bash** `cd /work/impl-22 && pytest -q tests/cart/test_pricing.py 2>&1 | tail -20` (timeout 600000, run_in_background false)
   *Reason:* targeted tests for criterion 2. *Expect:* all pass.

7. **Bash** `cd /work/impl-22 && pytest -q 2>&1 | tail -30` (timeout 600000, run_in_background false)
   *Reason:* the whole suite takes about 3 min, which fits in a foreground call. *Expect:* all pass.

8. **Bash** `cd /work/impl-22 && git add src/cart/pricing.py tests/cart/test_pricing.py && git commit -m "cart: <criterion 2 summary> (#22)" && git push 2>&1 | tail -5` (timeout 120000, run_in_background false)
   *Reason:* push as I go. *Expect:* pushed.

9. **Agent** subagent_type `general-purpose`, model `sonnet`, run_in_background `false`, prompt:
   > Worktree: /work/impl-22 (branch issue-22-coupon-stacking, base a1b2c3d). Do not fetch, rebase or push. For each item below, make the break in src/cart/pricing.py, run `cd /work/impl-22 && pytest -q tests/cart/test_pricing.py 2>&1 | tail -15` (each run takes under a minute), record the result, then restore with `git checkout -- src/cart/pricing.py`. Items: (a) criterion 1, stacking: make the stacking branch apply only the first coupon. (b) criterion 1: flip the stackability condition. (c) criterion 2: <the line that delivers it>, dropping the call and returning early. (d) each new branch in `git diff a1b2c3d...HEAD -- src/` with its condition flipped. Finish with `git status --short`, which must be clean. Return one line per item: `<item>: <break> → <test that went red>` or `SURVIVED`. Nothing else.
   
   *Expect:* every item red, git status clean. If something survives, I add the test that kills it, re-run that one mutation myself, then commit and push.

10. **Agent** subagent_type `general-purpose`, model `sonnet`, run_in_background `false`, prompt:
    > Worktree: /work/impl-22. Read issue #22 (`gh issue view 22 -R acme/shop`) and then `git diff a1b2c3d...HEAD` cold, as a reviewer who doesn't know the author's intent. For each acceptance criterion, check that the code (not any description) meets it. Also look for docs or ADRs the change now contradicts (grep docs/ for coupon and stacking), and for any original test assertion that was removed or weakened. Do not edit anything. Return each gap as `<file>:<identifier> — <gap>`, or `none`.
    
    *Expect:* `none`. If there are gaps, I fix them, re-run step 7, then commit and push.

11. **Bash** `cd /work/impl-22 && gh pr create -R acme/shop --draft --base main --head issue-22-coupon-stacking --title "Coupon stacking (#22)" --body-file /scratch/pr-22.md 2>&1 | tail -3` (timeout 60000, run_in_background false). I write `/scratch/pr-22.md` first. It contains `Closes #22`, a criteria checklist, and a note: "Branched from a1b2c3d; origin/main has since merged a change to src/cart/pricing.py — rebase is the orchestrator's call."
    *Expect:* the PR URL.

12. **Bash** `gh pr view <n> -R acme/shop --json body,isDraft -q '.isDraft, .body' | grep -nE 'Closes|true|false'` (timeout 60000, run_in_background false)
    *Reason:* the scratchpad is shared, so I confirm the only Closes line is `Closes #22` and the PR is a draft. *Expect:* `true`, `Closes #22`.

**Here I end my turn. Final report:**

```
PR:        https://github.com/acme/shop/pull/<n>
BRANCH:    issue-22-coupon-stacking
SIZE:      <n> lines across 2 files
SUMMARY:   Implemented coupon stacking in src/cart/pricing.py per #22, with tests in tests/cart/test_pricing.py. Built and verified against BASE a1b2c3d.
CRITERIA:  1 — <criterion 1>: <identifier in pricing.py>, tested by <test names>.
           2 — <criterion 2>: <identifier in pricing.py>, tested by <test names>.
TESTS:     targeted tests/cart/test_pricing.py: pass. Full `pytest -q` at HEAD: <N> passed, 0 failed.
MUTATIONS: <one line per item from the mutation child: break → red test>. None survived (or: <x> survived, killed by added <test>).
JUDGEMENT: <any spec readings>. While working I saw that origin/main had moved 6 commits past a1b2c3d, including a merged PR from another lane that edits src/cart/pricing.py. I did not rebase or adapt to it: the lane card says hold BASE, and no orchestrator message asked me to move.
NOTED:     Conflict risk: <other PR #/commit> changes src/cart/pricing.py (<functions/lines from step 4>), overlapping with this PR's edits to <function>. A rebaser should expect a conflict there and re-run tests/cart/test_pricing.py after rebasing. Otherwise none.
```