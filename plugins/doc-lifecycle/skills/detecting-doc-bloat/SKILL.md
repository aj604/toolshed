---
name: detecting-doc-bloat
description: Use when auditing documentation for low-value content — redundant, verbose, duplicated, or past its useful form — proposing pruning/condensing/distillation, and whenever bloat analysis runs programmatically (nightly sweep, PR gate, or a chunk-executor invocation handed its chunk slice) and must emit a structured, parseable proposal. Read-only — it proposes, a human approves, fixing-docs applies.
---

# Detecting Doc Bloat

**Drift asks whether a doc is *accurate*; bloat asks whether it still *earns
its tokens*.** This skill is a thin router: the engine owns scope,
segmentation, membership, and validation; per-need references carry the
verdict rules; you supply judgment one bounded chunk at a time. Three
non-negotiables:

1. **A verdict requires evidence.** Every verdict names the quote, code line,
   or grep that proves the finding — never "feels redundant".
2. **The result is structured, not prose.** Verdicts per `output-contract.md`,
   shape-checked at every seam and audited by the engine. Approval of a
   record's digest is the only bridge from a finding to a file change.
3. **Read-only — this skill never edits.** A human approves digests;
   **`fixing-docs`** applies the approved subset.

Every engine command below is `python3 -m doclifecycle …` with the plugin's
`engine/` directory on `PYTHONPATH` (`plugins/doc-lifecycle/engine/README.md`
covers both spellings).

## Doc kinds (the planner hints these; override only with stated evidence)

- **living** — claim-style docs tracking the repo (README, CLAUDE.md,
  runbooks, reference). Rules: `references/verdict-lenses.md`.
- **narrative** — opens with growing-docs' `> As of` anchor (the file's first
  line, or the first line under the title), wherever the file sits. Own bar;
  never a planning artifact. Rules: `verdict-lenses.md`.
- **planning** — designs/specs/plans describing an intended change. Rules:
  `references/planning-artifacts.md`.

A directory of ephemeral artifacts is **not** a fourth kind: it is one
`RETIRE-DOC` verdict over an enumerable `scope`, whose members the engine
expands from the index (`output-contract.md`). That replaced the legacy
`POLICY` record and its `policy_scope` config — a config still declaring the
key plans normally, and the planner says so.

## The audit (run these steps, in order)

1. **Plan the chunks.** `python3 -m doclifecycle bloat-plan --repo . >
   bloat-plan.json` partitions every indexed document into bounded chunks
   (`--max-documents`, `--max-units`), content-addressed so an unchanged chunk
   keeps its id. For a dispatched sweep, `scripts/plan-chunks.py` plans from
   the repository's `.md` files and `.doc-lifecycle/audit-scope.json` instead,
   adding the dispatch ergonomics the engine has no opinion about: per-chunk
   turn budgets, `--emit-prompt` slices, and `--results-dir` resume. Either
   way `bloat-audit` re-derives every fact from the registry, so a chunk plan
   is a work order, never an authority.
2. **Judge each chunk.** Small scope (≲2 chunks): sweep inline with the
   reference rules. Large scope: never sweep inline — the manifest is your
   work order as orchestrator (do not enumerate or read the corpus yourself),
   and you dispatch **one subagent per pending chunk, in concurrent waves of
   several, never serially** (chunks are independent; a serial walk of a
   bootstrap-scale manifest is hours of avoidable wall-clock). Render each
   dispatch with `--emit-prompt` and point the subagent at (i)
   `output-contract.md` and (ii) only the reference file(s) its chunk's kinds
   need. Each subagent writes `{"chunk": "<id>", "verdicts": [...]}` to
   `chunks/<id>.json`.
3. **Name the content.** A verdict about one document names the **unit
   digests** it covers, from `python3 -m doclifecycle segment --repo . --path
   <path>` — copied verbatim, never invented or abbreviated. A bulk
   `RETIRE-DOC` names a `scope` instead, and nothing else.
4. **Shape-check every seam**: each chunk result as it lands, then the
   assembled envelope. A failing chunk is re-dispatched fresh **once**, then
   you stop and name it.
5. **Run the audit.** `python3 -m doclifecycle bloat-audit --repo . --verdicts
   bloat-verdicts.json > bloat-report.json` checks every verdict against the
   whole-repository context index — membership, destinations, units,
   file-bound `DISTILL` status — expands each `scope` into one finding per
   member, and writes the validated report. It fails closed: any problem
   records nothing and names everything, so one re-prompt fixes all of it.
   Exit 0 is a report (clean or with findings), 1 refused, 4 partial —
   something in the corpus was not examined, and the report says what.

**Headless (chunk executor):** your chunk slice arrived verbatim in the
dispatch prompt — the doc list and the output path. That slice is your entire
scope: judge exactly those docs with the reference rules, write the chunk
result, stop. You never open the manifest — it is the orchestrator's state,
and it may not even be on disk; budgets, retries, and assembly are likewise
the workflow's, not yours.

## Script invocation templates

```bash
# plan (inventory -> chunk manifest; size + projected invocations on stderr).
# To narrow scope, pass --config with exclude/include globs (include re-adds what
# it matches); the chunking keys are documented in the script docstring.
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

# shape-check one chunk result
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py \
  --chunk <dir>/chunks/<id>.json --manifest <dir>/manifest.json

# assemble every chunk result into the verdicts envelope (refuses partial
# assembly; --allow-partial skips missing chunks loudly)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py \
  --assemble <dir>/chunks --manifest <dir>/manifest.json --out bloat-verdicts.json

# shape-check the envelope, then audit it
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py \
  bloat-verdicts.json
python3 -m doclifecycle bloat-audit --repo . --verdicts bloat-verdicts.json \
  > bloat-report.json
```

## The contract

Verdicts carry only `id, verdict, path, units, evidence, destination,
proposal, status, scope, sample`; the verdicts are `CUT / CONDENSE /
EXTRACT-AND-MOVE / MERGE-DOC / RETIRE-DOC / DISTILL`; the artifact is the
envelope `{"schema_version": 1, "verdicts": [...]}`. `files`, `members`,
`occurrences`, and `contention` are refused outright — a bulk finding's
members are enumerated from the index, never asserted by the model.
`DISTILL` verdicts carry classification + landed-code evidence **only** — the
claims/insights/decision-entry authoring is the `doc-distiller` agent's
post-approval job, dispatched by `fixing-docs`. Field rules, the worked
example, and the chunk-result seam shape: **`output-contract.md`**. The
shape checker sees shape; `bloat-audit` is the authority on everything else.
Never hand off anything either one rejects.

**REQUIRED SUB-SKILL:** use **writing-docs** for every replacement or
extraction text you propose (`CONDENSE` and `EXTRACT-AND-MOVE` proposals) —
dense, anchored, no narrative.

## Presenting to a human

When a human triages in-session, summarize the report — never paste raw JSON
as the summary. Group by `path`, one line per record: its `code`, its
`evidence`, and for a `DISTILL` its `status`. Then ask which records to apply.
Nothing you present is authorization on its own; what `fixing-docs` receives
is the human's selection, minted from each record's **digest** (`mint-approval
--record <digest>`) — the id is a label the report may renumber.

## Red flags — STOP

- A prose report with no structured verdicts, or an invented verdict → the
  six enum values, the contract shape, nothing else.
- Evidence asserted, not shown ("the sections are identical", no quote) → go
  get the line or the quoted overlap.
- Naming a unit you did not read out of `segment` — a paraphrase, a line
  number, a truncated digest → the digest verbatim, or no verdict.
- Listing the files a bulk retirement covers (a `files` key, or a `scope`
  narrowed to the paths you happened to read) → declare the inclusion rule and
  let the engine enumerate; a `sample` records what you read and authorizes
  nothing.
- Skipping the shape check at a seam — chunk results as they land, the
  assembled envelope → run it; never hand off a result it rejects. (As a
  headless executor, seam validation is the workflow's own step — never a
  license to open the manifest.)
- Authoring DISTILL claims/insights/decision entries at detect time — anywhere,
  including inside `evidence` → post-approval distiller work; emit the
  classification and proof only.
- Opening the manifest, or enumerating the corpus, as a chunk executor →
  your slice arrived in the dispatch prompt; audit exactly it and stop.
- Sweeping inline when the planner projects >2 chunks → dispatch per chunk;
  the manifest is the orchestrator's work order, each executor's is its
  dispatched slice.
- Editing, deleting, or "just fixing the small one" → read-only; surface it as
  a verdict and stop.
