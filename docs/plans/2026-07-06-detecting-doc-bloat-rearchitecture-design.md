# detecting-doc-bloat rearchitecture — harness, chunked sweeps, contract v2

Status: approved design, pre-implementation. Companion plan: to be written via
superpowers:writing-plans. Author: brainstorming session 2026-07-06 with a
pattern-corpus consultation (paths cited inline are repo-relative in
`agentic-skill-design-patterns`).

## Problem

`detecting-doc-bloat` was written as a 293-line monolithic SKILL.md carrying the
inventory step, doc-kind classification, six verdicts with inline rules, the full
per-artifact DISTILL protocol (per-section insight walk, claim verification,
decision-log drafting), precision/audience guards, the output-contract table, two
modes, a human-presentation format, and ~20 red flags. No decomposition, no
dispatch, no budgets, no checkpoints — none of the practices the plugin family
preaches.

Production evidence (career-compass, run 28833711517, 2026-07-07): one headless
full audit ran 40 turns, 42 minutes, ~$30, with 56 permission denials under the
CI allowlist, and emitted a 66-record report — 55 `DISTILL ready`, 47 of them
ephemeral `docs/superpowers/{plans,specs}/` working artifacts that should have
been one policy decision. Most of the spend was authoring 55 full DISTILL
payloads (insight walks, verified claims, decision entries) for records no human
had approved. The run then failed on a stale deployed validator; that
upgrade-channel problem is **out of scope** here (tracked separately), but the
architecture that made the run unbounded, wasteful, and all-or-nothing is this
design's target.

Root causes, in order of cost:
1. Detect-time DISTILL payload authoring is speculative — always paid, rarely
   approved.
2. No bulk verdict — N ephemeral artifacts cost N heavyweight walks.
3. One unbounded invocation — no chunking, no turn cap, no checkpoint; failure
   at minute 42 buys nothing.
4. Monolithic skill text — every invocation loads all rules for all verdicts and
   both modes; budget "instructions" in prose are exactly what the run ignored.

## Goals / non-goals

Goals: bounded, observable, resumable headless sweeps; approval-gated expensive
work; corpus-aligned decomposition; identical judgment bones interactively and
headless; deliberate, versioned contract evolution.

Non-goals: the stale-script upgrade channel (scheduling-doc-sync's territory,
separate work); changing the six-verdict judgment core, the read-only stance, or
the approve-by-ID bridge to `fixing-doc-bloat` — those work and stay.

## Pattern grounding

- Deterministic harness (`patterns/control-flow/deterministic-harness.md`):
  loops, chunking, retries, budgets live in code; the model fills judgment-shaped
  holes. Bounded autonomy as a structural property, not an instruction.
- Externalizing tools (`patterns/externalization/externalizing-tools-and-systems/
  externalizing-tools-and-systems.md`): freeze what has one goal-independent
  answer (inventory, chunk assignment, classification hints, assembly,
  validation); leave verdicts as levers.
- Validated seam / re-dispatch (`patterns/verification/validated-seam-redispatch.md`):
  contract-check each chunk where it is produced; discard-and-redispatch beats
  end-of-run validation. A bad run fails at record 8, not minute 42.
- Context envelope (`patterns/context-engineering/mechanisms/distillation/
  context-envelope.md`): don't summarize with a model what a filter can select —
  the bulk `POLICY` verdict, with mandatory file-list provenance.
- Progressive disclosure (`patterns/composition/progressive-disclosure.md`): one
  skill, thin router, per-need references. Multiple skills would be
  over-decomposition (shared contract, shared inventory).
- Heavy agent (`patterns/context-engineering/.../heavy-agent/heavy-agent.md`):
  the DISTILL protocol is authored weight consumed by the distiller — it belongs
  in the doc-distiller agent definition, loaded in the distiller's window, never
  the auditor's.
- Context alignment (`patterns/context-engineering/context-efficiency/
  context-alignment.md`): chunk by shared context space (directory + doc kind);
  dispatch per chunk, never per doc.
- Data/presentation separation (`patterns/externalization/
  externalizing-tools-and-systems/data-presentation-separation.md`): the model
  emits records; `render-report.py` owns all human presentation, including triage
  rollups.
- Durable state (`patterns/persistence/durable-state.md`): chunk results are the
  checkpoint; run-keyed CI state lives in workflow artifacts, not the repo tree.

Several of these are drafting/stub-status nodes — treated as directional; the
design decisions below are our own.

## Architecture

Five components; the first four ship in `plugins/doc-lifecycle/`, the fifth in
the scheduling-doc-sync templates.

### 1. SKILL.md — thin router (~90–110 lines)

Keeps: the three non-negotiables (evidence required, structured output,
read-only propose-only), the doc-kind summary, mode routing, and script
invocation templates. Modes:
- **Interactive, small scope** (≲2 chunks): sweep inline, records through the
  validator before presentation.
- **Interactive, large scope**: run `plan-chunks.py`, dispatch one subagent per
  chunk (chunk manifest slice + only the verdict references that chunk's kinds
  need), aggregate through the same validator. Dispatch is the interactive chunk
  executor; the harness scripts are the architecture.
- **Headless**: the invocation is one chunk executor — "read the manifest slice
  you are given, emit records for exactly those docs, stop." Orchestration
  belongs to the workflow, not the skill.

Leaves SKILL.md: per-verdict rules (→ references), the DISTILL protocol (→
doc-distiller agent), the presentation format (→ `render-report.py`), most red
flags (each moves next to the rule it guards, in the relevant reference).

### 2. references/

- `verdict-lenses.md` — the three passage questions (CUT / CONDENSE /
  EXTRACT-AND-MOVE), doc-level MERGE-DOC / RETIRE-DOC, precision guard,
  same-audience rule, narrative-doc own-bar rules, and their red flags.
- `planning-artifacts.md` — landed / pending-implementation classification,
  `DISTILL` record rules (evidence only, no payload — see contract v2), the
  `POLICY` bulk verdict, and their red flags.
- `output-contract.md` — contract v2 field table + worked example (kept as the
  shape reference it already is, updated).

A chunk executor loads only the references its chunk's doc kinds need.

### 3. Harness scripts (python3, stdlib-only, unit-tested)

- `plan-chunks.py` — inventory (absorbs `list-docs.py`) → chunk manifest.
  Groups by directory + doc-kind affinity; caps per chunk (defaults: ≤8 docs,
  ≤1200 lines; configurable via `audit-scope.json`). Emits deterministic
  doc-kind *hints* (`living | narrative | planning`) from path convention and
  the `> As of` first-line anchor; the model may override a hint only with
  stated evidence. Directories declared `policy-scope` in `audit-scope.json`
  become a single one-record `POLICY` chunk — never walked file-by-file.
  Reads existing chunk-result files and plans only the gap (resume). Reports
  manifest size and projected invocation count on the run surface; a hard
  run-level ceiling exists in config but **defaults to off** — big first runs
  are legitimate; the protections are structural.
- `validate-bloat-output.py` (extended) — three duties: validate one chunk
  result at the seam (same record rules, applied early); assemble valid chunk
  results into the final wrapped report (refusing partial assembly unless
  `--allow-partial`, which CI never passes); validate a final report (current
  behavior, updated to v2 — rejects v1-shaped reports with a single legible
  "schema v1: regenerate with the current skill" error).

Budget semantics: per-chunk `--max-turns` (~15) is a **flail detector, not a
work limiter** — total work scales by adding chunks. A chunk failing seam
validation is re-dispatched fresh once; failing twice fails the run *naming the
chunk*, with all valid chunks preserved as checkpoint. Spend is never lost; a
partial run is loud, never a silently truncated "full" report.

### 4. doc-distiller absorbs the DISTILL protocol

Detection emits `DISTILL` records with `status` and evidence only — **no
payload**. The full protocol (per-section insight walk, claim verification
against landed code, insight anchoring, decision-entry drafting) moves into the
`doc-distiller` agent definition and runs **post-approval**, when
`fixing-doc-bloat` dispatches it for approved IDs. The most expensive work in
every sweep becomes approval-gated instead of always-paid. The approving human
sees claims/insights in the resulting draft PR — the draft-PR-as-approval
surface this pipeline already uses.

### 5. Workflow v2 (doc-bloat.yml template)

Deterministic plan job (checkout → `plan-chunks.py` → manifest as job output) →
matrix job over chunks, each a claude-code-action invocation with
`--max-turns`, writing `chunks/<id>.json`, seam-validated in the same job with
one retry → deterministic assemble/gate/render jobs reusing the existing
sync-gate / render-report lane structure. YAML stays an allowlist-thin shell;
all logic in the unit-tested scripts (existing convention). The prune and
distill lanes keep their draft-PR shape; the distill lane's fixing-doc-bloat
invocation is where DISTILL payload authoring now happens.

## Contract v2

The wrapped report gains `"schema": 2`. Changes, all deliberate:

1. `DISTILL` records: `payload` removed entirely (authoring deferred to the
   distiller). `status` (`ready` / `pending-implementation`) and evidence rules
   unchanged.
2. New verdict `POLICY`: one record covering N files. Fields: `doc` = the
   covered directory, `location: null`, mandatory `files` array enumerating
   every covered path (provenance — a bulk
   record that cannot name its files is unfalsifiable), `proposal` = the policy
   text (e.g. "ephemeral process artifacts; retire after merge"), evidence =
   what makes the directory one class.
3. `summary` gains `policy` and drops nothing else.

Consumers updated atomically in the same change: `fixing-doc-bloat` (applies
`POLICY` as a policy-application, dispatches doc-distiller with record ID +
artifact path instead of a payload), `doc-distiller` (new protocol home),
`sync-gate.py` (lane routing for `POLICY` → distill lane), `render-report.py`
(v2 rendering, triage rollups), both workflow templates, and this repo's
dogfooded `.github/doc-sync/` install.

## Testing

Full writing-skills TDD — this is a rebuild, treated as a new skill:

- **RED baselines** (`tests/baselines/bloat-rearch-red/`): fresh subagents,
  stakeless graders holding the answer key. Scenarios pinned to observed
  production failures: (a) headless chunk executor under the exact CI allowlist
  — no off-allowlist tool attempts; (b) a `policy-scope` directory of ~10
  ephemeral artifacts — one `POLICY` record, zero per-file walks; (c) a landed
  planning artifact — `DISTILL ready`, no payload; (d) an invalid chunk result
  — seam rejection, one retry, then a failure naming the chunk; (e) interactive
  large scope — per-chunk dispatch, not an inline mega-sweep.
- **GREEN** (`tests/baselines/bloat-rearch-green/`): same scenarios against the
  rebuilt skill; re-GREEN any affected scenario after post-review text edits.
- **Unit tests** (existing convention, `tests/scripts/`): new
  `plan-chunks_test.py` (affinity grouping, caps, policy-scope emission, hint
  labels, gap/resume planning); extended `validate-bloat-output_test.py`
  (seam mode, assembly, `--allow-partial`, v2 accept / v1 legible reject);
  `sync-gate_test.py` / `render-report_test.py` grow `POLICY` + v2 cases (they
  also pin doc-bloat.yml wiring).
- **Fixture**: a new `tests/fixtures/` repo with a spec/plan swarm to exercise
  chunk planning and policy-scope end-to-end without a live model.
- **Real-world verification**: after release + scheduling-doc-sync re-install on
  career-compass, a workflow_dispatch run. Success: valid v2 report; no
  permission-denial storm; minutes, not tens of minutes; the superpowers swarm
  collapsed to one `POLICY` record.

`claude plugin validate` before tagging.

## Decisions worth logging

- DISTILL payload authoring moved detect-time → post-approval distill-time
  (speculative → approval-gated; the single biggest cost lever).
- Bulk `POLICY` verdict with mandatory file provenance; ephemeral-artifact
  directories are declared config (`policy-scope`), selected by filter, not
  summarized by model.
- Budgets are structural (per-chunk turn cap + seam validation + checkpoint);
  run-level spend ceiling defaults to off — refusing legitimate large runs is
  worse than pricing them visibly.
- One skill with progressive disclosure, not multiple skills; dispatch is the
  interactive chunk executor, the workflow matrix is the headless one — same
  manifest, same validator seam either way.
