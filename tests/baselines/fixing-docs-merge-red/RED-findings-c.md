# RED scenario C — bloat `CUT` + `DISTILL` through one door

Text under test: `fixing-doc-bloat/SKILL.md` + `references/apply-discipline.md`
at plugin version 0.27.0. Scenario: `scenario-c.md`. Grading rule:
`ANSWER-KEY.md`.

## Observable outcome

The runner **committed directly to the sandbox** — the failing shape the merged
flow exists to prevent, and one the pre-merge text explicitly instructs:

```
c8ecf08 Cut the two restating sentences from the fee-configuration section
185d4a2 Document the rounding order in fee_for
75af4a9 Fixture repo: docs, plan, billing constant, and audit config
```

The commit lands `BLOAT-001` alone, one file, two deletions. Its message carries
hand-copied `Doc-Lifecycle-Approval` / `Doc-Lifecycle-Report` /
`Doc-Lifecycle-Records` trailers taken from an approval set the text never told
it to obtain, and it names an edit plan — again, not from the skill.

`BLOAT-002` (`DISTILL`) never landed at all: `docs/plans/0001-fee-change.md` is
still in the tree and no residue document was created.

## The text-level findings

1. **The skill's own contract mandates the commit.** The headless section is
   explicit — "Make **one commit per applied record, in the order listed**" —
   and the DISTILL routing row says the distiller "stages one commit, which you
   then commit". Under the applier contract the applier never stages and never
   commits, and change approval is a person's; the pre-merge text does not merely
   omit that step, it instructs the opposite.

2. **The distiller is documented as a writer.** The routing table has it
   "author the claims/insights/decision entry post-approval and stage one
   commit"; the DISTILL section adds that it "`git rm`s the artifact — all
   **staged as one commit**". Criterion 4 of the answer key — the distiller emits
   operations rather than writing — is therefore not merely unmet but inverted,
   which is what the rewritten `agents/doc-distiller.md` had to reverse.

3. **The `POLICY` verdict row is dead.** The routing table still routes a
   `POLICY` record, a verdict `detecting-doc-bloat`'s re-architecture removed
   and `RECORD_REMEDIES` does not carry — so the pre-merge skill routes a code
   the applier would refuse outright.

4. Same as scenarios A and B: `approval`, `mint`, `applier`, `apply-plan`,
   `edit-plan`, and `validate-approval` appear nowhere in the file. Approval is
   defined as "`{\"approved\": [ids]}` from issue triage, or the human's
   in-session ID list" — a list of display ids, which the applier does not
   accept and which the answer key names as a failing shape.

The two records that DID need one door got split by the pre-merge architecture:
nothing in `fixing-doc-bloat` can land a drift record, and nothing in
`fixing-doc-drift` can land a bloat one, so a human approving a mixed selection
has to know which of two skills to open per record.

## Note on this run

The runner's written report was not returned before the RED phase closed; the
findings above are taken from the sandbox's own post-run git state (commit,
message, and tree, quoted verbatim above), which is the evidence the scenario
asked for. The text-level findings are read directly from the skill files under
test and do not depend on the runner's narration.
