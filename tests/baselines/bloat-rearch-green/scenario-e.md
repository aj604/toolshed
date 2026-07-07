# GREEN scenario (e) — interactive large scope (15 docs)

Prompt: identical to `../bloat-rearch-red/scenario-e.md` (fresh working dir).

## Runner behavior (rebuilt skill)

Read SKILL.md + `output-contract.md` only ("I did not read any of the 15
target docs") → ran the planner (15 docs → 4 chunks, projected invocations 4)
→ "since 4 > 2 projected chunks, no inline sweeping — I dispatched 4
general-purpose subagents in parallel, one per pending manifest chunk", each
given exactly the skill-enumerated inputs (chunk verbatim, `output-contract.md`,
one reference file by kind; sweep executors also pointed at writing-docs per
the REQUIRED SUB-SKILL clause) → seam-validated all four results → assembled →
final-validated → rendered via `render-report.py bloat-triage`, never raw JSON.

"Tool-source archaeology or trial-and-error? None. Every script invocation ran
exactly as templated in SKILL.md on the first attempt … No script source was
read, and no invocation had to be retried."

Assembled report: B1 POLICY (10 files, manifest-verbatim), B2 CONDENSE
README.md:11-15, B3 EXTRACT-AND-MOVE README.md:17-19 → RUNBOOK.md, B4 DISTILL
ready (landed-symbol evidence only), B5 DISTILL pending-implementation
(grep-nothing proof); narrative guide chunk clean (`records: []`).

## Grader verdict (stakeless; verified the JSON artifacts, not just the transcript): **PASS** (all five criteria)

- C1 shape (plan → dispatch → seam → assemble → triage): PASS, artifacts corroborate.
- C2 records match the key, "verified from the JSON": PASS — including "files = all 10 covered paths (verified identical to the manifest's policy chunk list)" and "Chunk-slice integrity also holds".
- C3 no residue: PASS — grader's own greps over report + chunk files: no `payload`, no claims/insights/decision content anywhere.
- C4 skill text taught the shape: PASS — mode decision quoted from the skill text.
- C5 no double-spend: PASS — orchestrator read none of the corpus (a top-level `ls` of names only, disclosed).

RED → GREEN delta: RED started the inline mega-sweep, was bounced by the
validator, recovered via design-doc archaeology, and paid the corpus twice.
GREEN went manifest-first on the skill text alone.

## REFACTOR notes

- Applied (read-review-only): SKILL.md's interactive-large mode now says "its
  manifest is the inventory; do not enumerate or read the corpus yourself"
  (the runner's harmless pre-planner `ls` prompted it).
- Recorded, no change: future GREEN harnesses should capture tool-call logs so
  the no-archaeology/no-double-spend criteria are artifact-verifiable, not
  self-reported; the contract's field table already shows both proposal shapes
  (string for CONDENSE/POLICY, object for EXTRACT-AND-MOVE/MERGE-DOC).
