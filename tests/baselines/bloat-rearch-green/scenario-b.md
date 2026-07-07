# GREEN scenario (b) — policy-scope directory of 10 ephemeral artifacts

Prompt: identical to `../bloat-rearch-red/scenario-b.md`.

## Runner behavior (rebuilt skill)

Ran the planner scoped to `docs/superpowers/**` → exactly one policy chunk →
sampled 3 of the 10 artifacts → emitted **one POLICY record** (`files` = the
manifest list verbatim, proposal = retirement policy text, evidence = class
proof + landed `src/limiter.py` state) → three validator passes clean (seam,
assembly, final). "TIME PROXY: I opened 4 files from the fixture … and
authored exactly 1 record."

Sources (runner's own attribution): "One POLICY record per policy chunk,
`files` = manifest list verbatim, sample 2–3 files instead of opening all N,
cite the landed state: `references/planning-artifacts.md` ('Policy chunks: one
record, never a walk') plus SKILL.md's 'Red flags' and doc-kinds sections."
The only tool-source read was `plan-chunks.py`'s docstring/`--help` for the
`--config` scope-narrowing flag — sanctioned CLI usage (and now documented at
the SKILL.md call site; see the REFACTOR notes in README.md).

## Grader verdict (stakeless): **PASS** (all five criteria)

C1 one POLICY record: PASS. C2 files verbatim: PASS (caveat: verified from
transcript + validator passes; raw JSON not retained). C3 zero per-file walks:
PASS. C4 no detect-time payload authoring: PASS. C5 rules sourced from skill
text/references: PASS.

RED → GREEN delta: RED reached the same record only by "validator archaeology";
GREEN cites the reference file for every rule, first-attempt passes throughout.
