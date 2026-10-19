# Skill Benchmark: pm-status, iteration 6 (report checker)

**Date**: 2026-10-19
**Evals**: 0, 1, 2 (1 run each, with skill; fresh runner per run). The baseline is the newest
earlier report for each eval (iteration 4 for eval 0, iteration 5 for evals 1 and 2). One fresh
stakeless grader graded all six blind against the 12 report assertions.
**Change from iteration 5**: a new Step 4 runs `scripts/check_report.py` on the draft, which
counts verdict, Needs-you and Next-up length, the Cleanup line, pictures, total lines,
Next-up reasons that repeat their Needs-you bullet, and open PRs with no CI state. Needs-you
evidence moves into the Next-up step that fixes it. A Next-up item that fixes a Needs-you
problem points back to it instead of restating it. Open PRs on the Cleanup line keep a CI/draft
parenthetical. When no session is visible, the PR trail's outcome is reported as a session bullet.

| Eval | Iteration 6 | Baseline |
|------|-------------|----------|
| 0 factory-stacked-milestones | 12/12 | 9/12 |
| 1 bucketshop-back-from-break | 11/12 | 7/12 |
| 2 graph-runner-messy | 11/12 | 8/12 |
| **All** | 34/36 (94%) | 24/36 (67%) |

Lines: 49, 41 and 62 (the baseline ran 46–66). The checker printed `ok` on all three final drafts.

Both remaining failures are Next-up actions that name nothing concrete ("Delete the three
doc-lifecycle workflows", "Commit the three docs marked ← only copy"). The checker now flags an
action with no PR, issue, branch, path or session link.

The 13th assertion (the report is the final message, after `--mark`) needs the run transcript
and wasn't graded here.

Grader's readability verdict: the iteration-6 report won every pair. Its bullets are tighter, and
each Next-up reason says why the item ranks where it does. The baselines held some richer analysis
(flake rates since the runner move, the #549 replay losses) that the tighter caps squeezed out.
