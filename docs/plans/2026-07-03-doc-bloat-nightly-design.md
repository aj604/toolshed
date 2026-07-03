# Nightly Doc-Bloat Sweep — Design

**Date:** 2026-07-03
**Status:** Approved design, pre-implementation
**Extends:** `2026-07-02-doc-sync-automation-design.md` (the drift nightly this mirrors),
`2026-07-03-doc-bloat-and-distillation-design.md` (the bloat suite this automates)

## Problem

The suite automates the **accuracy axis**: the nightly `doc-sync` Action runs
detect-drift → gate → fix-drift → PR unattended. The **value axis**
(`detecting-doc-bloat` / `fixing-doc-bloat` / `doc-distiller`) ships as skills but has
**no unattended surface** — a repo only gets a bloat audit if a human asks for one by
hand. This design wires the bloat suite into a scheduled sweep so accumulated bloat
surfaces on its own.

## The shaping constraint: bloat can't auto-fix

The drift nightly closes a detect→auto-fix loop because a stale claim has one
evidence-backed correction — `fixing-doc-drift` lands it with no human in the loop.
**Bloat cannot close that loop.** "Does this line still earn its tokens?" is a judgment,
and `fixing-doc-bloat`'s mandate is *"apply exactly the records the human approved by ID
and nothing else."* So the automated surface is **detect → propose**; a human owns the
decision, and the apply is gated on that decision.

## Decisions (from the brainstorm)

1. **Sibling workflow, weekly.** New `doc-bloat.yml` on a weekly cron
   (default `0 4 * * 1`), not a branch of `doc-sync.yml`. The drift nightly is built on a
   `marker..HEAD` diff and a detect→fix terminus; the bloat sweep has no marker and a
   detect→propose terminus. Two state models in one workflow tangle; keep each
   single-purpose.
2. **Full sweep, whole doc set including `docs/plans/`.** Bloat lives in docs no recent
   commit touched, so diff-scoping would structurally miss it; and `DISTILL` only fires on
   planning/design docs, so excluding `docs/plans/` would leave the distill path
   permanently empty.
3. **Output is PRs, not an issue of descriptions.** Every bloat record is a *pre-authored
   fix* — `proposal`/`payload` carry the complete replacement text, verified at detect
   time. Materializing a PR is therefore cheap (place, don't re-decide), and a real diff is
   a strictly better review surface than a description. The human's approval is the
   **merge**.
4. **Two PRs, split by verdict weight.** A recommendation in a PR body dies unread; every
   actionable finding must be its own mergeable diff. The split follows the bloat contract's
   own passage-vs-doc-level distinction:

   | Lane | Branch | Verdicts | Why here |
   |------|--------|----------|----------|
   | **prune** | `doc-bloat/prune` | `CUT`, `CONDENSE`, `EXTRACT-AND-MOVE` | passage-level, in-place, reversible |
   | **distill** | `doc-bloat/distill` | `MERGE-DOC`, `RETIRE-DOC`, `DISTILL` (`ready`) | doc-level — retires/merges/rewrites whole docs; high blast radius, deserves focused review |

   Separation keeps a doc retirement or distillation from being rubber-stamped alongside
   trivial cuts.
5. **`DISTILL pending-implementation` is dropped from v1.** Null payload = no fix exists;
   it signals "this design describes unbuilt code," a different concern from bloat. Surfacing
   it is deferred (see Non-goals).
6. **Both lanes apply for real and open DRAFT PRs.** Each lane invokes `fixing-doc-bloat`
   handed *that lane's record IDs*; the `distill` lane's `DISTILL` records dispatch
   `doc-distiller`. Handing the skill a full group is inside its contract — it acts on
   exactly the set it is given; the draft-PR-plus-merge is where human approval lands. No
   detection/fixing method is inlined into YAML (the `scheduling-doc-sync` prohibition holds).
7. **Per-lane dedup.** A lane is skipped when its PR is already open, so weekly runs don't
   stack proposals.

## Architecture — extend, don't fork

`scheduling-doc-sync`'s rule holds: gate decisions live in `sync-gate.py`, run-surface
strings in `render-report.py`, doc judgment in the skills invoked by name. The bloat lane
adds subcommands to the existing scripts rather than new ones.

| File | Change |
|------|--------|
| `scheduling-doc-sync/doc-bloat.yml` | **new** shipped template — `{{BLOAT_CRON}}` knob; steps below |
| `scheduling-doc-sync/scripts/sync-gate.py` | new `bloat-pre` + `bloat-lane` subcommands (decision matrix below) |
| `scheduling-doc-sync/scripts/render-report.py` | new `bloat-pr-body` / `bloat-pr-title` / `bloat-pr-summary` / `bloat-skip-summary` surfaces |
| `detecting-doc-bloat/scripts/validate-bloat-output.py` | **exists** — add to install copy-list → `.github/doc-sync/` |
| `scheduling-doc-sync/SKILL.md` | document the second workflow: copy-list (adds `doc-bloat.yml` + `validate-bloat-output.py`), `{{BLOAT_CRON}}` knob, commit-list, upgrade note. No new label (PR-only, no issues); reuses the existing PR-create-permission preflight |
| `CLAUDE.md` | add `doc-bloat.yml` + the bloat surfaces to the dogfooded-install inventory |

## Gate decision matrix (the testable core)

`sync-gate.py` gains two subcommands. No marker, no commit count — a full sweep always has
docs to read; the only pre-condition is lane availability.

```
bloat-pre  --prune-pr-open {0|1} --distill-pr-open {0|1}
    → skip-pending   both lanes already have an open PR — nothing could be opened
    → detect         at least one lane is free

bloat-lane --report FILE --lane {prune|distill} --pr-open {0|1}
    → skip-pending   this lane's PR is already open
    → skip-empty     no applicable records for this lane
    → open           ≥1 applicable record and lane free → apply + open PR
```

Lane membership (authoritative, switched on `verdict`):
- **prune** ← `CUT`, `CONDENSE`, `EXTRACT-AND-MOVE`
- **distill** ← `MERGE-DOC`, `RETIRE-DOC`, and `DISTILL` **with `status == "ready"`**
  (a `DISTILL` with `status == "pending-implementation"` counts for neither lane — v1 drop)

## Workflow shape (`doc-bloat.yml`)

```
on: schedule (weekly) + workflow_dispatch
gather facts:   gh pr list for doc-bloat/prune and doc-bloat/distill (open?)
bloat-pre gate: skip-pending → self-explaining summary, stop; detect → continue
detect:         claude-code-action → detecting-doc-bloat full audit → bloat-report.json
assert+validate: file exists; validate-bloat-output.py
for lane in [prune, distill]:
    bloat-lane gate → open | skip-empty | skip-pending (render a summary either way)
    if open:
        apply:  claude-code-action → fixing-doc-bloat, approved IDs = this lane's records
                (distill lane dispatches doc-distiller)
        PR:     push doc-bloat/<lane>; gh pr create --draft; render bloat-pr-body/title/summary
```

Reuses the drift workflow's self-authenticated push, artifact-hygiene (report never
committed), and OAuth/API-key auth verbatim. Each lane is an independent apply+PR so a
detect with only prune findings opens exactly one PR.

## Testing (test-first, per repo convention)

RED before GREEN. New unit cases in the existing stdlib suites:

- `tests/scripts/sync-gate_test.py` — `bloat-pre` (both-open → skip-pending; one-free →
  detect), `bloat-lane` for each lane (empty → skip-empty; records present + free → open;
  pr-open → skip-pending; `DISTILL pending-implementation` excluded from the distill count;
  `MERGE-DOC` counts distill not prune).
- `tests/scripts/render-report_test.py` — `bloat-pr-body` (prune table vs distill table;
  `md_cell` escaping), `bloat-pr-title` (count/plural), `bloat-pr-summary`, `bloat-skip-summary`.

The workflow YAML itself is verified by **dogfooding**: re-run `scheduling-doc-sync` to
install `doc-bloat.yml` + the refreshed scripts + `validate-bloat-output.py` into this
repo's `.github/`, then `gh workflow run doc-bloat`.

## Non-goals / deferred

- **No auto-merge.** Draft PRs only; a human merges.
- **`DISTILL pending-implementation` surfacing.** Dropped from v1; a later "stale-design"
  signal can own it.
- **No blast-radius cap on the bloat lanes.** Detect-only-then-review means a large
  proposal is reviewed as a diff, not silently applied; a cap can be added if PRs prove
  unwieldy.
- **No PR-triggered (per-commit) bloat mode.** Weekly full-sweep only; a diff-scoped PR gate
  is a later seam, added to this workflow, not a third one.
</content>
