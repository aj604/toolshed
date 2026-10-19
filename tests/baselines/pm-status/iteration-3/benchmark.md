# Skill Benchmark: pm-status, iteration 3 (visual report shape)

**Date**: 2026-10-19
**Evals**: 0, 1, 2 (1 run each, with skill; fresh runner per run, fresh stakeless grader)
**Baseline**: iteration-1 reports from the previous skill text (no pictures, no verdict)

| Eval | Passed | Total | Pass rate |
|------|--------|-------|-----------|
| 0 factory-stacked-milestones | 8 | 10 | 80% |
| 1 bucketshop-back-from-break | 7 | 10 | 70% |
| 2 graph-runner-messy | 7 | 10 | 70% |

Failures shared by all three runs:
- Verdict ran 4–6 sentences against "one or two sentences".
- Next up items carried 40–64-word reasons, and catch-all cleanup items had nested bullets.

Grader's readability verdict: iteration 3 scans faster than iteration 1 because of the
pictures (epic trees, aligned landed lists, step-sequence top actions), but the verdict and
Next up are still heavier than the target. The fix that followed made those rules structural:
word caps, a fixed `N. **action:** reason` line shape, and a separate `**Cleanup:**` line.

Per-run reports stay out of this repo because the eval repos are private.
