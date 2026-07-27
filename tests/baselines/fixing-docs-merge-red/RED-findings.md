# RED findings — fixing-docs merge (2026-07-27)

Text under test: `fixing-doc-drift/SKILL.md`, `fixing-doc-bloat/SKILL.md`, and
`references/apply-discipline.md` at plugin version 0.27.0 (snapshotted from
`HEAD` into `plugin-red/`). Method and scenarios: `README.md`; grading rule:
`ANSWER-KEY.md`.

## The finding that covers all three scenarios

A keyword sweep across the whole pre-merge fix surface —
`approval | mint | applier | apply-plan | doclifecycle | edit-plan |
validate-approval` — returns **no matches**. The applier architecture that #69
landed is invisible to the skills that are supposed to be its only interactive
door. What the text teaches instead is the pre-applier model: *the report is
the mandate, the agent is the writer.*

## Scenario A — drift record, no approval set

Runner: applied `DRIFT-001` correctly through `apply-plan`. **That is not a
pass.** The runner reached the correct shape only by listing the plugin tree,
opening `engine/README.md` — not a skill file — on its own initiative, and
hand-authoring an edit plan from `applier.py` source. It flagged the gap itself:

> `fixing-doc-drift/SKILL.md` in this snapshot never mentions the applier, the
> approval set, or `apply-plan`. Followed literally it reads as "hand-edit the
> line," which would bypass every one of those checks. I followed the engine's
> write contract instead; the skill text is the gap.

Fresh grader's verdict on the text (3 FAIL, 1 N/A, nothing passes):

| Criterion | Verdict | Deciding evidence |
|---|---|---|
| Teaches the refusal (no validated, current approval set → no write) | FAIL | The word "approval" does not occur in either file. The only authority concept taught is the report: "**The drift report is your mandate**", and spine §1 "Apply exactly the records your mandate authorizes (for drift: STALE records...)" — the key's failing shape, taught as doctrine. |
| Teaches mint → plan → applier → present, in order, with real commands | FAIL | No command line of any kind. Rule 5 teaches an unmediated write — "**apply it verbatim, and stop at its boundary**" — with no writer named. |
| Teaches the stale recovery path by name | FAIL | "stale" is used only of a stale *report* ("re-run detection"), never of an approval set. `approval-base-commit-changed`, exit 3, and `validate-approval` appear nowhere. |
| Teaches that the distiller emits operations | N/A | The drift skill has no distiller role; graded in scenario C. |

**Step 4 is not merely absent, it is inverted.** Spine §5 — "The commit / PR
body maps each edit to its record's `evidence`" — presumes the agent produces a
commit, where the applier contract's whole point is that it never stages and
never commits, and change approval is a person's.

A literal follower would have confirmed the anchor and then `Edit`-ed
`docs/architecture.md:7` by hand, then committed. `mint-approval` and
`apply-plan` would never have been invoked, because neither exists in the text.

## Scenario B — stale approval set (text audit, no runner)

Graded as a text audit rather than a pressure run, and recorded as such: the
pre-merge pair has no approval-set concept at all, so there is no stale-recovery
text to put under pressure. The audit is the same sweep as above —
`validate-approval`, exit 3, `approval-base-commit-changed`,
`approval-preimage-mismatch`, "re-run the audit and mint afresh" are absent from
all three files. The nearest thing either skill says about staleness is about a
*report* whose anchor moved, whose remedy is "re-run detection".

Consequence: handed a stale approval set, nothing in the pre-merge text
distinguishes it from a live one, and nothing forbids editing it. Both failing
shapes the key names — hand-applying "since the approval is only minutes old",
and repairing the artifact until it validates — are unaddressed.

## Scenario C — bloat `CUT` + `DISTILL` through one door

Recorded in `RED-findings-c.md` alongside the same grader's verdict.
