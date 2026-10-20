I wouldn't rebase or merge origin/main. BASE stays at a1b2c3d until the orchestrator tells me otherwise; bringing the branch up to date is its call, made after review. The new commits change only two things for me. I commit and push now, because the work is uncommitted and the branch is at risk. And I record which upstream commits overlap so the rebaser knows. I don't end my turn after that; I carry on with criterion 2.

1. **Bash** `cd /work/impl-22 && git status --short && git diff --stat`, timeout 60000, foreground.
   - Reason: confirm the uncommitted changes are only my criterion-1 work, with no stray caches.
   - Expect: changes to `src/cart/pricing.py` and `tests/cart/test_pricing.py` (or wherever the tests live), nothing else.

2. **Bash** `cd /work/impl-22 && python -m pytest -q 2>&1 | tail -40`, timeout 600000, foreground.
   - Reason: the whole suite takes 3 minutes, so it fits in the foreground. This proves criterion 1 is green against my base, a1b2c3d.
   - Expect: all tests pass.

3. **Bash** `cd /work/impl-22 && find . -name __pycache__ -prune -exec rm -rf {} + ; rm -rf .pytest_cache .coverage; git add src tests && git commit -m "cart: allow coupon stacking (criterion 1 of #22)" && git push -u origin issue-22-coupon-stacking 2>&1 | tail -5`, timeout 120000, foreground.
   - Reason: push as I go. If this lane dies, the next agent has a branch to start from.
   - Expect: a new commit on the branch, pushed, with upstream set.

4. **Bash** `cd /work/impl-22 && git log --oneline a1b2c3d..origin/main -- src/cart/pricing.py && git diff --stat a1b2c3d origin/main -- src/cart/pricing.py`, timeout 60000, foreground.
   - Reason: read-only look, so the report can name which upstream PR or commits overlap with mine. I don't change my code to fit what I see here.
   - Expect: one merged commit or PR touching pricing.py, with a line count.

5. **Edit / Bash, several calls**: implement criterion 2 and its tests on the same base. No end of turn here.

6. **Bash** `cd /work/impl-22 && python -m pytest -q 2>&1 | tail -40`, timeout 600000, foreground. Then clean caches, commit and push, as in step 3.
   - Expect: green, then a pushed commit.

7. **Agent**, subagent_type "general-purpose", model "sonnet", run_in_background false.
   - Reason: hand off the mutation loop.
   - Prompt: "Worktree /work/impl-22. For each of: (a) each criterion-1 line in src/cart/pricing.py, (b) each criterion-2 line, (c) each new branch, apply one mutation (flip the condition, drop the call, or return early). Run `python -m pytest -q tests/cart -x 2>&1 | tail -20` (timeout 600000). Record which test went red, then restore with `git checkout -- <file>`. After each restore, delete `__pycache__` and `.pytest_cache` so stale .pyc files can't mask anything. At the end, `git status` must show no changes. Return one line per mutation: `<file:line> <break> → <red test> | SURVIVED`."
   - Expect: a list. I add a test for each SURVIVED line, rerun, commit and push.

8. **Agent**, same settings.
   - Reason: hand off the cold criteria walk.
   - Prompt: "Worktree /work/impl-22. Read `git diff a1b2c3d...HEAD` cold, as a reviewer would, against these acceptance criteria: <issue #22 criteria verbatim>. For each criterion, check: is it met in code, not just described? Does any doc or ADR now contradict the change? Was any original test assertion dropped? Return each gap with file and identifier, or `none`."
   - Note: I use the SHA a1b2c3d, not `main`, so the diff isn't against a moved base.
   - Expect: `none`, or gaps that I fix, commit and push.

9. **Bash** `cd /work/impl-22 && gh pr create --draft --base main --head issue-22-coupon-stacking --title "Coupon stacking (#22)" --body-file /tmp/scratch/pr-22.md && gh pr view --json url,body -q '.url, .body' | grep -E 'Closes|https'`, timeout 120000, foreground.
   - Reason: open the draft PR, then read the body back from GitHub to confirm the only `Closes` line is `Closes #22`.
   - The body notes: "Branched from a1b2c3d; origin/main has since gained <commit/PR> touching src/cart/pricing.py — expect a conflict, left for the rebaser."
   - Expect: the PR URL, and `Closes #22` as the only Closes line.

10. **Bash** `cd /work/impl-22 && git status --short`, timeout 60000, foreground.
    - Reason: confirm the tree is clean and nothing I started is still running.
    - Expect: empty output.

**End of turn.** The final report, with the placeholders filled in from the real runs:

```
PR:        https://github.com/acme/shop/pull/<n>
BRANCH:    issue-22-coupon-stacking
SIZE:      <n> lines across <n> files
SUMMARY:   Implements coupon stacking in src/cart/pricing.py per #22, with tests for both criteria. Built and tested against BASE a1b2c3d. I did not rebase onto origin/main after it moved.
CRITERIA:  1. <criterion> — <function/identifier>, tested by <test>. 2. <criterion> — <identifier>, tested by <test>.
TESTS:     `pytest -q`, full suite on the final commit: <N> passed, 0 failed.
MUTATIONS: <per line: break → red test; any SURVIVED and the test added to kill it>
JUDGEMENT: <ambiguities resolved>. origin/main moved 6 commits past a1b2c3d mid-run, including <PR/commit> touching src/cart/pricing.py. With no orchestrator message, I held BASE and did not rebase or merge.
NOTED:     A likely rebase conflict in src/cart/pricing.py against <upstream PR/commit> (<n> lines changed upstream). It needs the rebaser before merge. <any other out-of-scope issues, or "none">
```