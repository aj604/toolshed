# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. It is almost entirely
Markdown; the executable code published is the engine package
(`plugins/doc-lifecycle/engine/doclifecycle/`, stdlib-only — the single owner the #57
re-architecture is absorbing the helper scripts into; see its `README.md`) plus eight skill
helper scripts
(`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`,
`plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py` and
`.../detecting-doc-bloat/scripts/plan-chunks.py`, plus
`scheduling-doc-sync`'s `scripts/sync-gate.py`, `scripts/upgrade-gate.py`, `scripts/render-report.py`,
`scripts/plan-distill.py` (doc-bloat's distill-lane planner + deterministic patch merge),
and `scripts/apply-upgrade.py` (the deterministic upgrade engine — run from the pinned checkout by
the upgrade lane, not vendored into installs), all `python3`, no deps)
plus the GitHub Actions templates the scheduling skill installs
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`, `doc-bloat.yml`, and
`doc-sync-upgrade.yml`). The sample repos under `tests/fixtures/` are the only other runnable
code, besides the dogfooded doc-sync install under `.github/` (`doc-sync/sync-gate.py`,
`doc-sync/upgrade-gate.py`, `doc-sync/render-report.py`,
`doc-sync/plan-chunks.py`, `doc-sync/plan-distill.py`,
`doc-sync/validate-drift-output.py`, `doc-sync/validate-bloat-output.py`,
`doc-sync/audit-scope.json` (doc-bloat full-audit scope config), `doc-sync/drift-waivers.json`
(accepted-UNVERIFIABLE waivers the sync run surfaces consume), `doc-sync/installed-version`
(the plugin-version lockfile the upgrade workflow reads), `workflows/doc-sync.yml`,
`workflows/doc-bloat.yml`, `workflows/doc-sync-upgrade.yml`) and the ci+release workflow
(`workflows/release.yml`).

## Layout (pointers, not descriptions)

- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there.
- `plugins/doc-lifecycle/` — the one published plugin. `.claude-plugin/plugin.json` is its
  manifest; `skills/`, `agents/`, and `engine/` hold its contents.
- `CONTEXT.md` — the ubiquitous language for the #57 re-architecture (component, contract, and
  document-model terms, each with an _Avoid_ list). Use its vocabulary in engine code and tests.
- `docs/` — `plans/` (design docs + `HANDOFF.md`), `guides/` (narrative user guides). Not published.
- `tests/` — `fixtures/` (runnable sample repos), `baselines/` (RED/GREEN skill-test records),
  `scripts/` (helper-script suites), `engine/` (engine suites). Not published.

## Working on the plugin

- **Add a skill:** create `plugins/doc-lifecycle/skills/<name>/SKILL.md` with `name` and
  `description` frontmatter. Skills are auto-discovered — `plugin.json` does not enumerate them
  (`plugins/doc-lifecycle/.claude-plugin/plugin.json`).
- **Add a plugin:** new `plugins/<name>/` dir with `.claude-plugin/plugin.json`, then add an entry
  to the `plugins` array in `.claude-plugin/marketplace.json`.
- **Before committing a manifest:** `marketplace.json` and every `plugin.json` must be valid JSON.
- **Test the marketplace locally:** `/plugin marketplace add /path/to/toolshed` (the repo root).

## Conventions

- **Skills are built test-first** (RED → GREEN → REFACTOR with subagents) via the
  `superpowers:writing-skills` methodology; test records live under `tests/baselines/`, one dir
  per test milestone (see the directory for the current set), plus the original writing-docs
  records loose at the root.
- `detecting-doc-bloat`/`fixing-doc-bloat` RED/GREEN baselines are retained at
  `tests/baselines/bloat-red/` and `tests/baselines/bloat-fixing-red/`, the 2026-07-06
  rearchitecture's at `tests/baselines/bloat-rearch-red/` / `bloat-rearch-green/`, the
  2026-07-07 scale hardening's at `tests/baselines/bloat-scale-red/` / `bloat-scale-green/`,
  and the 2026-07-09 distill-lane fan-out's at `tests/baselines/distill-fanout-red/` /
  `distill-fanout-green/`;
  method, status, and resume notes: `docs/plans/HANDOFF.md`; design: `docs/decisions.md`
  (2026-06-09 suite entry; 2026-06-20 `docs/reference/` shape; 2026-07-06 rearchitecture
  entry; 2026-07-07 scale-hardening entry; 2026-07-09 distill-fan-out entry).
- The generic apply-only rules for fix skills have one owner,
  `plugins/doc-lifecycle/references/apply-discipline.md`, cited (not restated) by both
  `fixing-doc-drift` and `fixing-doc-bloat`.
- **The helper scripts have unit tests** (stdlib `unittest`, no deps) at
  `tests/scripts/<script-name>_test.py`; run the matching test after touching a script or its
  output contract — `sync-gate_test.py`/`render-report_test.py` also cover `doc-bloat.yml`'s
  gate/render wiring, since both workflows share the two scripts. `upgrade-gate_test.py` covers the
  `doc-sync-upgrade.yml` version-comparison gate, and `apply-upgrade_test.py` covers that workflow's
  deterministic wiring-regeneration engine (knob preservation, script overwrite, fail-loud on
  unextractable knobs). `plan-distill_test.py` covers the distill lane's grouping, dispatch
  rendering, sidecar seam, and patch-merge engine. `release.yml`'s CI runs every
  `tests/scripts/*_test.py` suite.
- **The engine's tests live at `tests/engine/*_test.py`** and are found by discovery
  (`python3 -m unittest discover -s tests/engine -p '*_test.py'`), which is how `release.yml`'s
  "Engine tests" step runs them — a new suite is wired by landing the file, with no list to
  update. They test only the two public seams (the library function, and `python3 -m
  doclifecycle` as a subprocess); confirm new seams before adding a suite at one.
- Sync PR bodies/titles render via `render-report.py`'s `pr-body`/`pr-title` subcommands, never
  inline YAML `jq` — keeping the logic unit-tested and the CI YAML allowlist thin.
- **Docs in this repo follow the contract the plugin enforces:** every line is a claim verifiable
  against the repo (the `writing-docs` skill — one door for both human and agent docs; it carries
  the agent-density bar inline and dispatches the `llm-doc-writer` agent for heavy agent-facing jobs).
- **This repo's `docs/` stays flat** (`plans/`, plus `guides/` — durable narrative user guides,
  each carrying growing-docs' `> As of` first-line anchor, never planning artifacts) — a
  single-unit marketplace; the
  `docs/reference/` convention the plugin prescribes for larger repos
  (`plugins/doc-lifecycle/skills/bootstrapping-docs/repo-shape.md`) does not apply here —
  don't add one.

## Gotchas

- **`tests/fixtures/taskflow` needs `make setup` (plain `npm install`) after checkout**, then
  `make migrate` before `make dev` — migrate creates `.taskflow-state.json`, and api and worker
  refuse to start without it (`tests/fixtures/taskflow/Makefile:7`, comment). `make test`
  (`node --test packages/*/test/`) does not need migrate; only `@taskflow/shared` has tests
  (`Makefile:21`, comment).

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

This repo uses the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout. See `docs/agents/domain.md`.
