# Doc Bloat Analysis & Planning-Artifact Distillation — Design

**Date:** 2026-07-03
**Status:** Approved design, pre-implementation
**Extends:** `2026-06-09-documentation-skills-suite-design.md` (the suite this slots into)

## Problem

The doc-lifecycle suite covers the **accuracy axis**: bootstrap → write → detect drift →
fix drift → schedule. It has no owner for the **value axis** — content that is accurate
but redundant, verbose, or past its useful form. `fixing-doc-drift` names the gap
explicitly ("cutting unverifiable lines is a deliberate writing-docs cleanup, never a
silent side effect of a drift sync") but no skill owns that deliberate cleanup pass.

The motivating case is **planning artifacts** (designs, specs, implementation plans).
They are high-signal while work is in flight, and landing them in the repo is correct —
that moves knowledge off the workspace into the knowledge base. But once the
implementation merges, the same document degrades: code duplicates its detail, spec
duplicates design, and the load-bearing residue (decisions, constraints, rationale) is
buried in verbosity. Carrying everything rots agent context; carrying nothing makes the
rationale undiscoverable (git history keeps it, but nobody finds what they don't know
existed). Bloat here is not a defect — it is a **phase transition that never happened**.

## Shape: mirror the drift pair

Two skills, same encapsulation the drift pair uses. No monolith: each has one job, and
the human gate lives *between* them.

### `detecting-doc-bloat` — contract skill, never edits

Audits docs against the writing-docs bar and emits structured records. Mirrors
`detecting-doc-drift`: two modes, closed enums, evidence mandatory, machine-parseable
output, read-only by contract.

**Modes:**
- **full-audit** — whole doc set (interactive or scheduled headless run).
- **diff-scoped** — only docs the PR touched (CI gate). When a planning artifact lands
  in a PR, the gate does **not** object — it emits a `DISTILL` record with status
  `pending-implementation`. Landing the artifact is the point; the record marks it for
  later distillation.

**Verdict enum (closed):**

| Verdict | Granularity | Meaning |
|---|---|---|
| `CUT` | passage | No durable value; delete |
| `CONDENSE` | passage | Same claims, dense form; proposed replacement text mandatory |
| `EXTRACT-AND-MOVE` | passage | Signal belongs in a different living doc; target mandatory |
| `RETIRE-DOC` | doc | Doc no longer earns its slot |
| `MERGE-DOC` | doc | Heavy overlap with a named other doc |
| `DISTILL` | doc | Planning artifact whose implementation has landed (or is pending — see status) |

Full doc-set restructuring (splits, tree reorganization) is out of scope — that is
bootstrapping-docs repo-shape territory.

**Record shape:** mirrors the drift contract — id, doc, location, verdict, evidence,
proposed replacement where the verdict is not pure deletion. `DISTILL` records carry a
status (`pending-implementation` | `ready`) and, when `ready`, an extra payload: the
durable claims found, each with a target living doc; a draft decision-log entry; and the
retirement (delete) of the artifact. Every extracted claim must be verified against code
— same evidence discipline as drift. A `pending-implementation` record carries no
payload (there is no landed code to verify against); it marks the artifact so a later
full-audit run re-judges it.

**Consumers (three, two headless):**
1. **Interactive** — human triages the proposal in-session; approved items go to the fix
   skill in the same sitting.
2. **Scheduled headless** — the record set becomes one GitHub issue per run (updated if
   an unresolved one exists, never duplicated). No repo mutation, ever.
3. **PR gate** — diff-scoped mode in CI; emits records (notably `DISTILL
   pending-implementation`); enforcement posture beyond that is deferred (see Open
   questions: policy).

### The human gate

Nothing is applied without explicit human approval of specific record IDs — in-session
approval interactively, issue triage headless. The issue body is a **manufactured
artifact** (targeted-response pattern), designed for triage, not a record dump: summary
up top, records grouped by doc and verdict, each with a stable ID, its evidence, and its
proposed replacement, in a form where approving is marking items. The structured records
travel with it (collapsed block or attached), so the fix step parses records, not prose.

### `fixing-doc-bloat` — applies the approved subset, nothing else

Same discipline spine as `fixing-doc-drift`: only approved records, no while-I'm-here
edits, blast-radius stop on whole-doc rewrites that weren't approved as such.

- Simple verdicts (`CUT`, `CONDENSE`, `EXTRACT-AND-MOVE`) are bounded edits, applied
  inline; edits meet the writing-docs bar.
- `DISTILL` is a heavy job (verify claims against code, extract into multiple docs,
  draft the decision entry, retire the artifact) — the skill **dispatches** it rather
  than inlining, following the writing-docs → llm-doc-writer precedent. The distillation
  procedure has one owner (the dispatched agent's prompt/reference doc in the plugin);
  neither skill restates its method.
- The shared apply-discipline spine (approved-records-only, no-scope-creep, blast-radius
  stop) gets **one owner**: a reference file in the plugin that both fix skills cite —
  no duplicated method, no "if they diverge, X wins" hedge.

### Distillation residue

Per approved artifact, `DISTILL` produces:
1. **Extractions** — durable repo-tracking claims merged into their living docs, meeting
   the writing-docs bar.
2. **One decision-log entry** — appended to a single rolling log (default
   `docs/decisions.md`; no per-decision files). Entry: date, what was decided, the
   constraints that still bind, links to the code and to the artifact's last commit.
   The log is itself a repo-tracking doc — writing-docs owns its bar, drift detection
   audits it.
3. **Retirement** — the artifact deleted **in the same commit** as the extractions and
   log entry, so the diff is self-evidently "moved, not lost."

## Automation posture

The record contract is automation-ready from day one; the wiring is a later increment.
When wired into scheduling-doc-sync: bloat cadence much slower than nightly (bloat
accretes over weeks; a nightly bloat issue is itself noise), and the existing validated
seam applies — a `validate-bloat-output`-style gate checks records against the contract
before any automation acts on them, mirroring `sync-gate.py` / `validate-drift-output.py`.

## Pattern grounding

Maps onto the sibling pattern library
(`~/Repos/scratchpad/agentic-skill-design-patterns/`): contract keystone (the record
contract as the seam), context envelope (the detection report across the detect→fix
seam, and the decision log as a repo-level envelope — built once, consumed many times),
encapsulation & subskill delegation (the pair; `DISTILL` behind a dispatch), heavy agent
(the dispatched distill job), human-in-the-loop gate (issue triage as a packed dispatch
with a constrained answer shape), effect discipline (read-only detection; transactional
extract+delete commit), validated seam (output validator before automation), targeted
response (the manufactured issue body), deterministic harness (the existing Action
pipeline, when wired), config-as-bootstrap (the deferred policy file's shape).

## Build method

`superpowers:writing-skills` TDD (RED → GREEN → REFACTOR with subagents), baselines
under `tests/baselines/`. Expected RED axis, by drift-suite precedent: not recall
(capable agents spot bloat) but **contract adherence** — free-form prose instead of
records, deletions proposed without evidence, distillation attempted inline without the
gate. Build order: detecting-doc-bloat first (fixing consumes its output), then
fixing-doc-bloat + the dispatched distillation procedure.

## Out of scope (v1)

- scheduling-doc-sync wiring (contract is ready; wiring is its own increment).
- Full doc-set restructuring verdicts.
- The PR-gate **policy layer** (repo-declared rules like "no specs outside plans/").

## Open questions

- **Policy config** — deferred, unresolved by choice. When revisited, its shape is
  config-as-bootstrap: human-authored YAML, one concern, scoped to the plugin.
- **Scheduled cadence default** (weekly vs. monthly) — decide at wiring time.
- **Decision-log growth** — entries are compact, but the log will eventually earn its
  own `CONDENSE` pass; acceptable, revisit if it becomes real.
