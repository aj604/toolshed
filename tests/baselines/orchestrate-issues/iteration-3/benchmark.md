# Agent benchmark: workbench role agents (2026-10-19)

Evals 14-17 in `../evals.json`. They test the role agents, not the orchestrator.

| Arm | Agent definitions |
|---|---|
| `old` | `origin/main` at 90ea787 |
| `new` | PR #248 as first pushed (45236ef, 93e840d) |
| `new2` | PR #248 with the review touch-ups: take the repo's word for a slow suite, and delete caches before handing the worktree back |

## Results

| Eval | How it runs | old | new | new2 |
|---|---|---|---|---|
| 14 base-moved-mid-run | rehearsal, graded blind | 2/5 | 5/5 | 5/5 |
| 15 compaction-handoff | rehearsal, graded blind | 5/5 | 5/5 | not rerun |
| 16 fixer-long-e2e | rehearsal, graded blind | 1/5 | 5/5 | 5/5 |
| 17 real-implementer-children | real run, graded from the transcript | 5/12, 5/12 | 10/12, 11/12 | 11/12, 11/12, 12/12 |

Eval 17 checks subagent use from the actual `Agent` tool calls in the
stream-json transcript, not from what the agent says it did. Every `new`
and `new2` run dispatched a mutation-loop child and a separate cold
criteria-walk child: foreground, one at a time, on sonnet. No `old` run
dispatched a child.

A separate probe confirmed the design's premise: a `workbench:implementer`
dispatched as a subagent has the `Agent` tool, and its child runs (CLI
2.1.304).

## What the `new` runs taught, fixed in `new2`

- **Slow suite in the foreground.** One `new` run ran a suite the README
  puts at ~15 minutes in the foreground, under a 10-minute timeout. All
  three `new2` runs backgrounded it.
- **Stale bytecode from the mutation child.** In one `new` run, a mutant
  restored within the same second and at the same size left a `.pyc` that
  failed 7 of 11 tests in the next full suite. Both `new` runs also left
  `__pycache__/` behind. All three `new2` runs exited with `git status`
  clean, and two ran the suite with `PYTHONDONTWRITEBYTECODE=1`.

## Residual

- Two of three `new2` runs read the suite log once while the suite was still
  running ("Still running. Waiting for the completion notification.")
  before the wake. That is one extra turn, not a polling loop.
- Eval 15 doesn't discriminate between the arms: the old text already said
  to stop when deep into context.
