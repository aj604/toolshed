# Skill Benchmark: pm-status, iteration 5 (one-line Cleanup, tighter Needs you)

**Date**: 2026-10-19
**Evals**: 1, 2 (the two weakest in iteration 4; 1 run each, fresh runner, fresh stakeless grader)
**Change from iteration 4**: Cleanup is one line of at most 50 words with no bullets; Needs-you
bullets are capped at 40 words; rows that group issues must say what they group.

| Eval | Passed | Total | Pass rate | Iteration 4 |
|------|--------|-------|-----------|-------------|
| 1 bucketshop-back-from-break | 6 | 10 | 60% | 80% |
| 2 graph-runner-messy | 7 | 10 | 70% | 50% |

| Eval | Lines / words: iteration 1 → 4 → 5 |
|------|--------------------------------------|
| 1 | 43/778 → 60/823 → 48/674 |
| 2 | 53/961 → 74/979 → 66/950 |

The Cleanup fix held: one line in both runs, with no nested bullets. Next up plus Cleanup fell
from 275 to 221 words (eval 1) and from 267 to 227 (eval 2).

Most failures are near misses on the caps: 3-sentence verdicts of 36–38 words, Next-up lines of
27–29 words, and a 53-word Cleanup line. Two are content gaps: eval 1 reported no session outcome
(its only in-window session was off-topic), and the bot PRs on its Cleanup line lost their
CI/review/draft state.

Open shape issues for a future iteration:
- Next-up reasons restate their Needs-you bullet instead of pointing back to it.
- Needs-you bullets still run 38–53 words.
