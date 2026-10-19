# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. It publishes one plugin,
`workbench` (`plugins/workbench/`). The plugin's only executable code is
`plugins/workbench/skills/orchestrate-issues/scripts/frontier.py` and
`plugins/workbench/skills/incremental-enhancement-lanes/scripts/lanes.py` (`python3`, stdlib-only).

## Layout

- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there.
- `plugins/workbench/` — `.claude-plugin/plugin.json` is its manifest; `skills/` and `agents/`
  hold its contents; `README.md` describes them.
- `tests/baselines/orchestrate-issues/` — skill-creator eval records for `orchestrate-issues`
  (`evals.json`, `iteration-N/` runs, a run analysis) plus `test_frontier.py`, an unasserting
  smoke harness that takes `frontier.py`'s path as its argument. Not published, not run by CI.
- `tests/baselines/workbench-import/` — eval and packaging records for the `enhance`,
  `incremental-enhancement-lanes`, and `commit-to-pr` skills. `tests/scripts/workbench-helpers_test.py`
  exercises `lanes.py` offline (`python3 tests/scripts/workbench-helpers_test.py`). Neither is
  published or run by CI.
- `.github/workflows/` — `ci.yml` (version guard, script compile, `claude plugin validate .`),
  `claude.yml` (`@claude` mentions), `claude-code-review.yml` (PR review).

## Working on the plugin

- **Add a skill:** create `plugins/<plugin>/skills/<name>/SKILL.md` with `name` and
  `description` frontmatter. Skills are auto-discovered — `plugin.json` does not enumerate them.
- **Add a plugin:** new `plugins/<name>/` dir with `.claude-plugin/plugin.json`, then add an entry
  to the `plugins` array in `.claude-plugin/marketplace.json`.
- **Bump the version** in a plugin's `plugin.json` whenever its content changes — CI's version
  guard fails the PR otherwise (`.github/workflows/ci.yml`).
- **Releases:** none are automated. The bare `vX.Y.Z` tags and Releases belong to the retired
  `doc-lifecycle` (`v0.1.0` already exists), and installed doc-lifecycle upgrade lanes read the
  latest Release — tag any future plugin release with a prefix, e.g. `workbench-v0.1.0`.
- **Before committing a manifest:** run `claude plugin validate .` (CI runs the same).
- **Test the marketplace locally:** `/plugin marketplace add /path/to/toolshed` (the repo root).

## History

`doc-lifecycle`, the plugin this marketplace originally shipped, is decommissioned; its source,
engine, tests, dogfooded `.doc-lifecycle/` install, and lane workflows were removed from `main`.
Recover any of it from git history — `v0.11.1` is the last release considered working.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

This repo uses the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout. See `docs/agents/domain.md`.
