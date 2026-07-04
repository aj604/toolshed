# Decisions

## 2026-07-03 — Doc bloat and distillation plan
- Decided: Built `detecting-doc-bloat`/`fixing-doc-bloat` as a matched RED→GREEN pair per the
  writing-skills methodology, mirroring `detecting-doc-drift`/`fixing-doc-drift`'s build process.
- Still binds: RED/GREEN baselines are retained under `tests/baselines/` rather than discarded
  once the skill goes green.
- Code: `tests/baselines/bloat-red/`, `tests/baselines/bloat-fixing-red/`
- Source: docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md @ 09f4300 (removed in this commit)

## 2026-07-03 — Doc bloat and distillation design
- Decided: Added `detecting-doc-bloat`/`fixing-doc-bloat` as a second skill pair mirroring
  `detecting-doc-drift`/`fixing-doc-drift`'s shape (contract-emitting detector + human-gated
  applier), covering the value axis (drift covers accuracy). `DISTILL` retires a landed
  planning artifact by extracting its durable decisions into living docs plus one
  decision-log entry, then deleting it — chosen over keeping design docs verbatim forever or
  per-line-cutting them.
- Still binds: the apply-only discipline for fix skills has one owner
  (`plugins/doc-lifecycle/references/apply-discipline.md`); `DISTILL`'s two-status model
  (`pending-implementation` forbids payload, `ready` requires verified claims + one
  decision-log entry) is closed.
- Code: `plugins/doc-lifecycle/references/apply-discipline.md`,
  `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
- Source: docs/plans/2026-07-03-doc-bloat-and-distillation-design.md @ 09f4300 (removed in this commit)

## 2026-07-02 — Doc-sync automation plan
- Decided: Doc-sync automation was built test-first, with RED/GREEN/E2E records under
  `tests/baselines/doc-sync-setup-red/`.
- Still binds: mechanical gate failures (a malformed `drift-report.json`) fail the sync-gate job
  red rather than degrading silently — `validate-drift-output.py` exits nonzero on shape errors
  and the workflow's validate step carries no `continue-on-error`. The shipped `doc-sync.yml` has
  since moved past this plan's literal task steps (e.g. onto `anthropics/claude-code-action@v1`,
  per `docs/plans/HANDOFF.md`'s Row 5 note) — the plan's own code blocks are retired as stale
  procedure, not current truth.
- Code: `.github/workflows/doc-sync.yml`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`
- Source: docs/plans/2026-07-02-doc-sync-automation-plan.md @ 09f4300 (removed in this commit)

## 2026-07-02 — Doc-sync automation design
- Decided: Chose a GitHub Action runner over a Claude scheduled task (ties to one user's
  account) or local git/session hooks (fire only while someone works), with marker-based
  idempotency and a blast-radius cap that escalates to an issue rather than one giant PR;
  posture is fail loud, never half-apply.
- Still binds: nightly sync runs as a GitHub Action (`schedule` + `workflow_dispatch`);
  `.github/doc-sync-marker` advances only on a clean-run direct commit or a merged sync PR;
  a blast-radius cap escalates to a labeled issue instead of one giant PR.
- Code: `.github/workflows/doc-sync.yml`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`
- Source: docs/plans/2026-07-02-doc-sync-automation-design.md @ 09f4300 (removed in this commit)

## 2026-07-03/04 — Doc bloat nightly plan
- Decided: `doc-bloat.yml` built test-first (`sync-gate_test.py`, `render-report_test.py`
  extended with bloat-* cases) as a sibling to `doc-sync.yml`, sharing `sync-gate.py`/
  `render-report.py` rather than forking new scripts; already exercised for real (PR #23,
  merged 2026-07-04).
- Still binds: the weekly bloat sweep splits findings into two lanes by verdict — `prune`
  (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`, passage-level) and `distill` (`MERGE-DOC`/`RETIRE-DOC`, or
  `DISTILL` with `status: ready`, doc-level); a `DISTILL` `pending-implementation` record belongs
  to neither lane and is never opened as a PR.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`
- Source: docs/plans/2026-07-03-doc-bloat-nightly-plan.md @ 09f4300 (removed in this commit)

## 2026-07-03 — Doc bloat nightly design
- Decided: Bloat sweep output is a proposal (draft PR), never an auto-fix, because a bloat
  verdict is a judgment call, not a mechanically-checkable correction; the merge itself is the
  human approval gate — chosen over drift's detect→fix pipeline shape.
- Still binds: `doc-bloat.yml` stays a separate sibling workflow from `doc-sync.yml`, each with
  its own concurrency group, because drift's marker-based detect-fix model and bloat's
  marker-less detect-propose model would tangle if combined; bloat output is always a draft PR,
  never auto-merged or direct-committed, and a lane is skipped if its own draft PR is already
  open.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`
- Source: docs/plans/2026-07-03-doc-bloat-nightly-design.md @ 09f4300 (removed in this commit)
