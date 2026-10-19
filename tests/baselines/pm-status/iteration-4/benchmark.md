# Skill Benchmark: pm-status, iteration 4 (structural caps)

**Date**: 2026-10-19
**Evals**: 0, 1, 2 (1 run each, with skill; fresh runner per run, fresh stakeless grader)
**Change from iteration 3**: verdict capped at two sentences and 40 words; Next-up items after
the first are one `N. **action:** reason` line under 25 words; cleanup moved to its own line.

| Eval | Passed | Total | Pass rate | Iteration 3 |
|------|--------|-------|-----------|-------------|
| 0 factory-stacked-milestones | 10 | 10 | 100% | 80% |
| 1 bucketshop-back-from-break | 8 | 10 | 80% | 70% |
| 2 graph-runner-messy | 5 | 10 | 50% | 70% |
| **All** | 23 | 30 | 76.7% | 73.3% |

Verdicts now pass in all three runs (31–40 words, down from 54–77). Remaining failures:
- The Cleanup line grew nested bullets in evals 1 and 2 (102 and 129 words). In eval 2 that
  pushed the report to 74 lines and named 12 worktrees individually.
- Some Next-up items ran 26–34 words.
- Tree rows that group issues as bare numbers (`#378 #379 #380 #381  CLOSED`).
- Needs-you bullets of 47–65 words in eval 0.

The fix that followed capped Cleanup at one 50-word line with no bullets (names only when a kind
has three or fewer), capped Needs-you bullets at 40 words, and required group rows to say what
they group.
