# GREEN scenario (c) — landed planning artifact

Prompt: identical to `../bloat-rearch-red/scenario-c.md`.

## Runner behavior (rebuilt skill)

Read SKILL.md → `output-contract.md` → `references/planning-artifacts.md`
("verdict-lenses.md not needed" — correct routing). Classified the doc as a
true planning artifact, ran the landed-implementation grep + full read of
`src/limiter.py`, and emitted one record: `DISTILL`, `status: "ready"`,
evidence = the four landed symbols with `file:line` each, `proposal`/`files`
null. Validator: `OK: 1 record(s) valid`, first attempt.

The load-bearing line (verbatim): "Authored one v2 record … — classification
plus landed-code evidence only; **no claims/insights/decision-entry content
authored, per the detect-time prohibition**. … Nothing drafted and discarded."

## Grader verdict (stakeless): **PASS** (all four criteria)

- C1 DISTILL ready with landed-code evidence: PASS.
- C2 evidence = landed-code proof only: PASS, one nit — the trailing
  "Problem/Design/Sketch sections are superseded scaffolding" clause is
  classification framing, not insight content; the contract wording was
  adjusted post-GREEN to admit exactly that (read-review-only edit, see
  README.md).
- C3 no drafted-and-discarded residue: PASS.
- C4 sources = skill text/references: PASS.

RED → GREEN delta: RED authored a full payload (claim + insight + decision
entry) and, after the validator bounce, relocated the insight walk into
`evidence`. GREEN authored none of it — the speculative cost is gone, which is
the design's single biggest lever.
