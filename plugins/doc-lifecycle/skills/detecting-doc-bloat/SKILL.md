---
name: detecting-doc-bloat
description: Use when auditing documentation for low-value content — redundant, verbose, duplicated, or past its useful form — proposing pruning/condensing/distillation, and whenever bloat analysis runs programmatically (nightly sweep, PR gate, or a chunk-executor invocation handed its chunk slice) and must emit a structured, parseable proposal. Read-only — it proposes, a human approves, fixing-doc-bloat applies.
---

# Detecting Doc Bloat

**Drift asks whether a doc is *accurate*; bloat asks whether it still *earns
its tokens*.** This skill is a thin router: deterministic scripts plan and
validate the sweep; per-need references carry the verdict rules; you supply
judgment one bounded chunk at a time. Three non-negotiables:

1. **A verdict requires evidence.** Every record names the `file:line`, quote,
   or grep that proves the finding — never "feels redundant".
2. **The result is structured, not prose.** Records per `output-contract.md`,
   validated mechanically at every seam. Approval of record IDs is the only
   bridge from a finding to a file change.
3. **Read-only — this skill never edits.** A human approves IDs;
   **`fixing-doc-bloat`** applies the approved subset.

## Doc kinds (the planner hints these; override only with stated evidence)

- **living** — claim-style docs tracking the repo (README, CLAUDE.md,
  runbooks, reference). Rules: `references/verdict-lenses.md`.
- **narrative** — first line is growing-docs' `> As of` anchor, wherever the
  file sits. Own bar; never a planning artifact. Rules: `verdict-lenses.md`.
- **planning** — designs/specs/plans describing an intended change. Rules:
  `references/planning-artifacts.md`.
- A **policy chunk** (directory declared `policy_scope` in the repo's
  `.github/doc-sync/audit-scope.json`) yields exactly one `POLICY` record.
  Rules: `planning-artifacts.md`.

## Modes

**Interactive, small scope (the planner projects ≲2 chunks):** sweep inline
with the reference rules, emit one wrapped `{"schema": 2, ...}` report, run it
through the validator before presenting anything.

**Interactive, large scope:** never sweep inline. Run the planner — its
manifest is your work order as orchestrator; do not enumerate or read the
corpus yourself — then dispatch **one subagent per pending chunk**. Render
each dispatch with `--emit-prompt` (the chunk's slice verbatim: doc list or
policy dir + files, output path, definition of done) and point the subagent
at (i) `output-contract.md` and (ii) only the reference file(s) its chunk's
kinds need — `verdict-lenses.md` for living/narrative,
`planning-artifacts.md` for planning and policy chunks. Each subagent writes
`{"chunk": "<id>", "records": [...]}` to `chunks/<id>.json` under its working
directory — the dispatch prompt names the exact path; seam-validate each
result as it lands; a failing chunk is re-dispatched fresh **once**, then
you stop and name it. Assemble the valid results into the final report.

**Headless (chunk executor):** your chunk slice arrived verbatim in the
dispatch prompt — the doc list (or policy dir + files) and the output path.
That slice is your entire scope: judge exactly those docs with the reference
rules, write the chunk result, stop. You never open the manifest — it is the
orchestrator's state, and it may not even be on disk; budgets, retries, and
assembly are likewise the workflow's, not yours. A policy chunk means one
`POLICY` record, files copied verbatim from the dispatch.

## Script invocation templates

```bash
# plan (inventory -> chunk manifest; size + projected invocations on stderr).
# To narrow scope, pass --config with exclude/include globs (include re-adds what
# it matches); policy_scope/chunking keys are documented in the script docstring.
# Chunk ids are content-addressed, so --results-dir resume skips only chunks
# whose docs are unchanged; each chunk carries its model-invocation turn budget.
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/plan-chunks.py \
  --out <dir>/manifest.json --results-dir <dir>/chunks

# render one chunk's dispatch prompt / turn budget (slice verbatim — the
# executor never opens the manifest)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/plan-chunks.py \
  --emit-prompt <id> --manifest <dir>/manifest.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/plan-chunks.py \
  --emit-turns <id> --manifest <dir>/manifest.json

# seam-validate one chunk result
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py \
  --chunk <dir>/chunks/<id>.json --manifest <dir>/manifest.json

# assemble all chunk results into the final report (refuses partial assembly)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py \
  --assemble <dir>/chunks --manifest <dir>/manifest.json --out bloat-report.json

# validate a final wrapped report
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py bloat-report.json
```

## The contract

Records carry exactly `id, doc, location, verdict, evidence, proposal,
status, files`; verdicts are `CUT / CONDENSE / EXTRACT-AND-MOVE / RETIRE-DOC /
MERGE-DOC / DISTILL / POLICY`; the final report is wrapped with `"schema": 2`.
`DISTILL` records carry classification + landed-code evidence **only** — the
claims/insights/decision-entry authoring is the `doc-distiller` agent's
post-approval job, dispatched by `fixing-doc-bloat`. Field rules, the worked
example, and the chunk-result seam shape: **`output-contract.md`**. Never hand
off anything the validator rejects.

**REQUIRED SUB-SKILL:** use **writing-docs** for every replacement or
extraction text you propose (`CONDENSE` proposals, `EXTRACT-AND-MOVE` text) —
dense, anchored, no narrative.

## Presenting to a human

When a human triages in-session, render the report — never paste raw JSON as
the summary:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/scheduling-doc-sync/scripts/render-report.py \
  bloat-triage --report bloat-report.json
```

Then ask for the approved IDs. Nothing you present is authorization on its
own; the human's ID list is what `fixing-doc-bloat` receives.

## Red flags — STOP

- A prose report with no structured records, or an invented verdict → the
  seven enum values, the contract shape, nothing else.
- Evidence asserted, not shown ("the sections are identical", no quote) → go
  get the line or the quoted overlap.
- Skipping the validator at an orchestrator seam — chunk results as they
  land, the final report → run it; never hand off a result it rejects. (As a
  headless executor, seam validation is the workflow's own step — never a
  license to open the manifest.)
- Authoring DISTILL claims/insights/decision entries at detect time — anywhere,
  including inside `evidence` → post-approval distiller work; emit the
  classification and proof only.
- Walking a policy chunk file-by-file, or a `files` list that isn't the
  dispatch's verbatim → one `POLICY` record per policy chunk.
- Opening the manifest, or enumerating the corpus, as a chunk executor →
  your slice arrived in the dispatch prompt; audit exactly it and stop.
- Sweeping inline when the planner projects >2 chunks → dispatch per chunk;
  the manifest is the orchestrator's work order, each executor's is its
  dispatched slice.
- Editing, deleting, or "just fixing the small one" → read-only; surface it as
  a record and stop.
