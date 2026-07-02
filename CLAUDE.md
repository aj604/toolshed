# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. It is almost entirely
Markdown; the only executable code published is a skill helper script
(`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`, runs on
`python3`, no deps). The sample repos under `tests/fixtures/` are the only other runnable code.

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
  `superpowers:writing-skills` methodology; test records live under `tests/baselines/` — one dir
  per test milestone (`bootstrap-red/`, `bootstrap-green/`, `drift-red/`, `fixing-drift-red/`,
  `llm-doc-red/`, `writing-docs-merge-red/`), plus the original writing-docs records loose at
  the `tests/baselines/` root.
  Method, status, and resume notes: `docs/plans/HANDOFF.md`; full design:
  `docs/plans/2026-06-09-documentation-skills-suite-design.md` (suite) and
  `docs/plans/2026-06-20-reference-doc-containment-design.md` (the `docs/reference/` shape).
- **The one helper script has unit tests:** run
  `python3 tests/scripts/validate-drift-output_test.py` (stdlib `unittest`, no deps) after
  touching `detecting-doc-drift`'s `validate-drift-output.py` or its output contract.
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
