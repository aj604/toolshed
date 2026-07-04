# Durable narrative docs + DISTILL insight extraction — design

**Date:** 2026-07-04
**Status:** implemented in this branch

## Problem

The suite's doc taxonomy recognized two kinds: *living claim-style docs* (track the
current repo, line-governed by `writing-docs`) and *planning artifacts* (describe an
intended change; distilled once landed). Two consequences:

1. **Breadth had no durable home.** `repo-shape.md` routed narrative architecture,
   conceptual overviews, and design rationale to "process docs (`plans/`)" — the same
   folder the bloat machinery treats as a retirement queue. `growing-docs` prescribes
   creating narrative docs (walkthroughs, ADRs) but named no location. An architecture
   doc describes the *current* system, so its "implementation" is landed by definition:
   under the two-kind taxonomy it is `DISTILL ready` the day it is written.
2. **Distillation was lossy for insight.** The `ready` payload carried only
   code-verified `claims` plus one `decision_entry`. Breadth that is durable but not
   code-verifiable — rationale for deliberate absences, rejected alternatives with
   reasons, deferred-work seams, the system-shape picture — had nowhere to land and was
   deleted with the artifact. The 2026-07-04 sweep (PRs #25/#26) demonstrated both
   failures: the suite's de facto architecture doc was distilled to an 11-line entry,
   the losses clustered exactly in rationale-for-deliberate-absences, and inbound
   references (CLAUDE.md, HANDOFF.md, workflow headers) were left dangling.

## Decision

1. **Third doc kind: the durable narrative doc.** Walkthroughs, ADRs,
   conceptual/architecture overviews, workflow docs. It tracks the current repo as
   narrative; `growing-docs` owns its bar and template.
2. **The classifier is the marker, not the directory.** `growing-docs`' mandatory
   first-line `> As of <date> (<anchors>)` anchor doubles as the durable-narrative
   marker. `detecting-doc-bloat` classifies an anchored doc as narrative wherever it
   sits — never as a planning artifact, never `DISTILL`. Directory-based classification
   was rejected: it breaks on moves, and the prescribed home is shared with claim docs.
3. **Address: `docs/reference/`.** One containment subtree holds the whole agent doc
   set, claim-style and narrative alike, domain-grouped (unit narrative beside the
   unit's `overview.md`, cross-unit narrative beside `architecture.md`). Repos without
   the tree use `docs/` until it exists. Never `docs/plans/`. A separate top-level
   home (e.g. `docs/adr/`) was rejected: it re-scatters the agent set repo-shape.md
   Rule 1 contains.
4. **DISTILL grows an `insights` channel.** The `ready` payload adds optional
   `insights: [{insight, target, anchor}]` — durable breadth extracted into a narrative
   doc instead of deleted. An insight is not code-verifiable; its honesty checks are:
   true of the artifact's own text (no extrapolated grander rationale), not a
   restatement of a claim or the decision entry, and anchored to its provenance
   (`path @ SHA`, `file:line`, or date). `claims` may now be empty when insights carry
   the residue; an all-empty payload is invalid. Protecting breadth via
   `audit-scope.json` excludes was rejected: excluding `docs/plans/` silently empties
   the distill lane, and excludes protect directories, not content.
   Recognition is forced, not hoped for: every `ready` record requires a per-section
   **insight walk** ("if this section vanishes, is there a decision, constraint, or
   deliberate absence a future maintainer could wrongly 'fix'?") whose outcome the
   record's `evidence` must state (`insight sweep: none — …` when dry), and the
   bloat draft-PR body renders each DISTILL row's claim/insight counts so a human
   reviewer sees `0 insights` and can reject an unexamined distill.
5. **Distiller hardening.** `doc-distiller` additionally: lands insights (creating the
   narrative target with its `> As of` line if absent, refreshing it if present),
   verifies every historical assertion in the decision entry against the artifact's
   own text before landing it, and repoints the artifact's inbound references
   (docs, skill files, workflow comment headers; frozen `tests/baselines/` records
   excepted) — a retirement that leaves dangling pointers is incomplete.

## Changes

- `detecting-doc-bloat/SKILL.md` — three-kind classification (step 1), narrative
  own-bar judging (step 2), insight residue + narrative exemption (step 3), payload
  contract row, red flags.
- `detecting-doc-bloat/scripts/validate-bloat-output.py` (+ dogfooded copy,
  + `tests/scripts/validate-bloat-output_test.py`) — `insights` shape validation;
  claims-or-insights non-empty rule.
- `detecting-doc-bloat/output-contract.md` — worked example gains an insight and
  the insight-sweep evidence clause.
- `scheduling-doc-sync/scripts/render-report.py` (+ dogfooded copy,
  + `tests/scripts/render-report_test.py`) — DISTILL rows in the bloat PR body
  carry `(N claims, M insights)`.
- `agents/doc-distiller.md` — insights landing, decision-entry verification,
  inbound-reference sweep, widened touch-list.
- `fixing-doc-bloat/SKILL.md` — dispatch contract updated to match.
- `growing-docs/SKILL.md` — "Where narrative docs live" section; anchor doubles as
  marker.
- `bootstrapping-docs/repo-shape.md` — narrative routing fixed (was `plans/`), tree
  example, failure mode.
- `writing-docs/SKILL.md` — placement-table row routing narrative to growing-docs.
- `CLAUDE.md` — DISTILL convention updated.
