# Skill Benchmark: orchestrate-issues

**Model**: claude-fable-5-2
**Date**: 2026-11-19T13:32:02Z
**Evals**: 23, 24, 25 (1 run each per configuration)

## Summary

| Metric | Old Skill | With Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 69% ± 17% | 100% ± 0% | -0.31 |
| Time | 56.6s ± 53.4s | 66.7s ± 44.7s | -10.1s |
| Tokens | 63155 ± 8337 | 68782 ± 8921 | -5628 |

## Notes

- Baseline ('old skill') is the round-one working tree (merge defaults already in), not origin/main.
- One rehearsal run per arm, graded blind by a separate agent. New 16/16, baseline 11/16.
- Eval 23 (silent lane) separates the versions: the baseline checked GitHub only, reported 'still working' off a push timestamp, and waited rather than replacing.
- Eval 24 (waiting notice): both made no tool call; the baseline wrote a 19-word status line, the new skill one word. The saving per notice is small; the harness (2.1.322+) already skips repeat notices.
- Eval 25 (inline pull after compaction) barely discriminates: the baseline also dispatched a reviewer, a rebaser and an implementer; it only failed to re-read the skill. A rehearsal agent has just read the skill, so it cannot reproduce post-compaction drift. The real evidence for that fix is the live hook test (resume path).
- Weak assertions per the grader: 23 #4 and #6, 25 #6 pass with no effort; 24 #3 and #4 follow from #1.
- Grader also caught a gap, since fixed in troubleshooting.md: a replacement agent cannot check out a branch the dead agent's worktree still holds.
