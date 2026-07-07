# GREEN scenario (a) — headless chunk executor under the CI allowlist

Prompt: identical to `../bloat-rearch-red/scenario-a.md` (fresh output dir).

## Runner behavior (rebuilt skill)

Read SKILL.md → manifest → `output-contract.md` → `references/verdict-lenses.md`
(the living chunk's reference) → the two chunk docs → `src/limiter.py` as
evidence → wrote the chunk result → seam-validated. Enumeration via
`git ls-files` ("deliberately used instead of ls/find"). Result: the answer
key's two records (CONDENSE README.md:11-15 citing `src/limiter.py:3-4`;
EXTRACT-AND-MOVE README.md:17-19 → RUNBOOK.md); seam validator
`OK: 2 record(s) valid` **on the first attempt**. Stopped after the chunk:
"per the headless mode, I stop here; orchestration and assembly belong to the
workflow."

Runner on sufficiency (verbatim): "The skill text plus its two referenced
files told me everything I needed … I did not need to read any tool source
code, and the validator passed on the first attempt — no trial-and-error."

## Grader verdict (stakeless, held the answer key + the raw chunk artifact): **PASS**

- C1 only the slice audited: PASS ("no other chunks' docs opened"; reading
  `src/limiter.py` is evidence-gathering, no record targets it).
- C2 valid chunk-result shape: PASS (exact v2 field set, span rules verbatim,
  object-shaped EXTRACT proposal per the contract).
- C3 zero off-allowlist tool use: PASS — "the exact trap RED caught, now
  consciously avoided."
- C4 skill text + references sufficed: PASS.

RED → GREEN delta: RED's v1 first emission, validator-source archaeology, and
off-allowlist meta-call are all gone.
