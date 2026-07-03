# Span fixing re-verify — passage-span routing (2026-07-03)

Targeted re-verify after the span-contract edits to `fixing-doc-bloat/SKILL.md`
(routing rows reworded from "the line at `location`" to "the passage the
record's evidence delimits, anchored at `location`", plus a red flag and
rationalization row). Exercises the two apply paths the review flagged:

- the **approved-CUT shared-line** path (B1, `README.md:19-20`, unexercised by
  the original GREEN whose approval was `["B2","B5"]`), and
- a **multi-line CONDENSE** whose span (`README.md:30-38`) exceeds its single
  `location` line — the case where "replace the line" under-describes the run.

Fresh Sonnet subagent, fixing-doc-bloat SKILL.md + apply-discipline.md as
edited, scratch git repo with the bloat-red fixture. Inputs recorded here:
`span-reverify-bloat-report.json`, `span-reverify-approval.json`
(`{"approved": ["B1","B2","B3"]}`). Run output above; the facts below are
controller-verified from the scratch repo commits, not taken on the runner's word.

## Result: all three approved passage edits correct; span mandate honored

| Rec | Verdict | Span | Applied | Controller check |
|-----|---------|------|---------|------------------|
| B1 | CUT | README.md:19-20 | deleted only the restatement sentence; kept the `message.` tail sharing line 19 | `e8b78ba` diff: `-2/+1`, the prior sentence's `message.` survives — **no corruption on the shared line** |
| B2 | CONDENSE | README.md:30-38 | replaced **all nine** narrative lines with the proposal, byte-verbatim | `77896c8` diff: `1 insertion(+), 9 deletions(-)`; proposal `in README` == True |
| B3 | EXTRACT-AND-MOVE | README.md:40-43 | removed the gotcha from README, landed `proposal.text` verbatim in CLAUDE.md, one commit | `84008e1`: text present in CLAUDE.md verbatim, gone from README |

Unapproved B4/B5/B6 untouched. Working tree clean (`3ff8e68` → `e8b78ba` →
`77896c8` → `84008e1`).

## Why this closes the review finding

The original GREEN's CONDENSE already replaced all nine lines despite the
"replace the line" wording (graded correct); the RED probe
(`span-red-probe-output.md`) showed the shared-line CUT also came out clean by
discretionary override. Both were correct behavior *contradicting* the normative
text. Under the reworded rows the letter and the passing behavior now agree: the
mandate is the evidence-delimited passage, the multi-line CONDENSE deletes nine
lines because its span is nine lines, and the shared-line CUT deletes only the
passage's own text. No regression on the byte-verbatim / one-commit / approved-only
disciplines the original GREEN established.

**Re-verify passes for fixing-doc-bloat under the span contract.**
