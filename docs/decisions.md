# Decisions

## 2026-07-03 — Doc bloat and distillation plan
- Decided: Built `detecting-doc-bloat`/`fixing-doc-bloat` as a matched RED→GREEN pair per the
  writing-skills methodology, mirroring `detecting-doc-drift`/`fixing-doc-drift`'s build process.
- Still binds: RED/GREEN baselines are retained under `tests/baselines/` rather than discarded
  once the skill goes green.
- Code: `tests/baselines/bloat-red/`, `tests/baselines/bloat-fixing-red/`
- Source: docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md @ 09f4300 (removed in this commit)
