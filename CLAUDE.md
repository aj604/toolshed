# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. It is almost entirely
Markdown; the only executable code published is five skill helper scripts
(`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`,
`plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py` and
`.../detecting-doc-bloat/scripts/list-docs.py`, plus
`scheduling-doc-sync`'s `scripts/sync-gate.py` and `scripts/render-report.py`, all `python3`, no deps)
plus the GitHub Actions templates the scheduling skill installs
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml` and `doc-bloat.yml`). The sample
repos under `tests/fixtures/` are the only other runnable code, besides the dogfooded doc-sync
install under `.github/` (`doc-sync/sync-gate.py`, `doc-sync/render-report.py`,
`doc-sync/validate-drift-output.py`, `doc-sync/validate-bloat-output.py`, `workflows/doc-sync.yml`,
`workflows/doc-bloat.yml`) and the ci+release workflow (`workflows/release.yml`).

## Layout (pointers, not descriptions)

- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there.
- `plugins/doc-lifecycle/` — the one published plugin. `.claude-plugin/plugin.json` is its
  manifest; `skills/` and `agents/` hold its contents.
- `docs/` — `plans/` (design docs + `HANDOFF.md`). Not published.
- `tests/` — `fixtures/` (runnable sample repos) and `baselines/` (RED/GREEN skill-test records).
  Not published.

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
- `detecting-doc-bloat`/`fixing-doc-bloat` were built test-first: RED baselines recorded before
  the skill existed, GREEN re-runs confirm the skill's discipline, both retained (not discarded
  once green) at `tests/baselines/bloat-red/` and `tests/baselines/bloat-fixing-red/`.
  Method, status, and resume notes: `docs/plans/HANDOFF.md`; full design:
  `docs/plans/2026-06-09-documentation-skills-suite-design.md` (suite) and
  `docs/plans/2026-06-20-reference-doc-containment-design.md` (the `docs/reference/` shape).
- **The helper scripts have unit tests** (stdlib `unittest`, no deps) at
  `tests/scripts/<script-name>_test.py`; run the matching test after touching a script or its
  output contract — `sync-gate_test.py`/`render-report_test.py` also cover `doc-bloat.yml`'s
  gate/render wiring, since both workflows share the two scripts.
- **Docs in this repo follow the contract the plugin enforces:** every line is a claim verifiable
  against the repo (the `writing-docs` skill — one door for both human and agent docs; it carries
  the agent-density bar inline and dispatches the `llm-doc-writer` agent for heavy agent-facing jobs).
- **This repo's `docs/` stays flat** (`plans/`) — a single-unit marketplace. The
  `docs/reference/` convention the plugin prescribes for larger repos
  (`plugins/doc-lifecycle/skills/bootstrapping-docs/repo-shape.md`) does not apply here; don't
  add one.

## Gotchas

- **`tests/fixtures/taskflow` needs `make setup` (plain `npm install`) after checkout**, then
  `make migrate` before `make dev` — migrate creates `.taskflow-state.json`, and api and worker
  refuse to start without it (`tests/fixtures/taskflow/Makefile:7`, comment). `make test`
  (`node --test packages/*/test/`) does not need migrate; only `@taskflow/shared` has tests
  (`Makefile:21`, comment).
