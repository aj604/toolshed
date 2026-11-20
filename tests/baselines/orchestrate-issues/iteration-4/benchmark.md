# Skill Benchmark: orchestrate-issues

**Model**: claude-fable-5-2
**Date**: 2026-11-18T03:47:40Z
**Evals**: 3, 4, 8, 10, 18, 19, 20, 21, 22 (1 run each per configuration)

## Summary

| Metric | With Skill | Old Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 98% ± 5% | 49% ± 40% | +0.49 |
| Time | 87.1s ± 29.1s | 67.4s ± 17.8s | +19.7s |
| Tokens | 70917 ± 4280 | 63552 ± 3341 | +7365 |

## Notes

- One run per configuration; rehearsals, graded by a separate agent. Evals 18-22 were graded blind (arm labels hidden) on the first pass.
- New evals 18-22: new skill 32/32, old skill 15/32. Evals 18-20 separate the versions (old 1/8, 1/6, 2/6).
- Eval 21 (merge denied by the harness) does not discriminate: the old skill also parked one PR and kept the rest moving.
- Eval 22 differs only on the head pin (old 5/6). The old skill re-read checks in rehearsal, though real runs chained the merge 32+ times; a rehearsal under-tests this rule.
- Evals 18 and 22 were rerun on the new skill after the 'no checks ran' rule and the typed merge sentence were added; eval 18 gained two assertions and the old-skill answer was regraded against them. Eval 22's rerun grade was reported by the grader without a file and re-derived from the response text.
- Regression on older evals (new skill only, no old-skill arm): eval 3 6/7 (never says the repo is public, only queries visibility), eval 4 4/4, eval 8 7/7, eval 10 6/6. Evals 0-2 were not run: the live #170 graph they read is now complete.
- Pass-rate and cost rows in the summary mix the nine new-skill runs with five old-skill runs; compare evals 18-22 for like-for-like.
