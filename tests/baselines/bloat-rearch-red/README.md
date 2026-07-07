# bloat-rearch RED baselines — method

Baseline (RED) runs for the detecting-doc-bloat rearchitecture
(`docs/plans/2026-07-06-detecting-doc-bloat-rearchitecture-design.md`), run
2026-07-06 against the **pre-rebuild monolithic SKILL.md** (293 lines, contract
v1) with the fixture `tests/fixtures/plan-swarm/` and the answer key
`tests/fixtures/plan-swarm-ANSWER-KEY.md`.

## Method

- One fresh subagent per scenario (a, b, c, e), given only the on-disk SKILL.md
  path, the fixture path, and the scenario task — no rearchitecture context.
  Scenario (d) is scripted (no model): an invalid chunk result pushed through
  the seam validator, plus assembly over a gap.
- One fresh **stakeless grader** per scenario (never the author), given only
  the runner's verbatim output and the answer key.
- Prompts are recorded verbatim in each scenario file, alongside the runner
  output, the grader verdict, and rationalizations quoted verbatim.

## Sequencing note (read before comparing to GREEN)

Per the plan, the deterministic harness scripts (`plan-chunks.py`, the v2
`validate-bloat-output.py`) were **already landed** when RED ran — they are
code with their own unit-test TDD cycle; the writing-skills Iron Law gates the
*skill text*, which was still v1. This contaminated the runs in an
instructive direction: several runners recovered to near-correct v2 behavior
**by reading the validator's source code and being rejected by it**, not from
the skill text. That recovery is itself the documented baseline failure — in
production (headless, `--max-turns 15`) those recovery turns are the flail and
spend the rearchitecture exists to remove, and a runner without the new
scripts on disk would have shipped the v1 payload-authoring behavior observed
at career-compass (run 28833711517). Graded criteria therefore center on:
**did the skill text itself teach the correct behavior?** It did not, in any
scenario.

## Verdicts (details per scenario file)

| Scenario | Result | Core failure |
|---|---|---|
| (a) headless chunk executor | FAIL | first emission v1-shaped (per SKILL.md), rejected at the seam; recovered only by reverse-engineering validator source; one off-allowlist meta-tool call |
| (b) policy-scope swarm | FAIL | skill text has no POLICY verdict — correct one-record outcome reached only via the landed harness scripts, not the text |
| (c) landed planning artifact | FAIL | full detect-time DISTILL payload authored (claim + insight + decision entry) per the v1 text, then discarded on validator rejection — the speculative cost, paid |
| (d) invalid chunk result | FAIL (architectural) | the v1 architecture has no seam: `validate-bloat-output.py [FILE]` end-of-run only; new seam/assembly outputs recorded in scenario-d.md |
| (e) interactive large scope | see scenario-e.md | run recorded with the same contamination caveat |
