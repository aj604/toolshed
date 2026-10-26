# CLAUDE.md

This repo builds **Workbench**, a Claude Code plugin with five skills for autonomous
improvements, GitHub issue orchestration, parallel enhancement lanes, pull requests, and
project status. `toolshed` is its marketplace name; preserve the install coordinates
`aj604/toolshed` and `workbench@toolshed` when editing public copy.

The plugin lives in `plugins/workbench/`. Its only executable code is
`plugins/workbench/skills/orchestrate-issues/scripts/frontier.py`,
`plugins/workbench/skills/orchestrate-issues/scripts/prune_worktrees.py`,
`plugins/workbench/skills/incremental-enhancement-lanes/scripts/lanes.py`,
`plugins/workbench/skills/pm-status/scripts/gather.py` and
`plugins/workbench/skills/pm-status/scripts/check_report.py` (`python3`, stdlib-only).

## Layout

- `README.md` — Workbench's public landing page; `plugins/workbench/README.md` is its usage guide.
- `CONTRIBUTING.md` — contributor setup and validation; `docs/marketing.md` holds launch copy.
- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there.
- `plugins/workbench/` — `.claude-plugin/plugin.json` is its manifest; `skills/` and `agents/`
  hold its contents; `README.md` describes them.
- `tests/baselines/orchestrate-issues/` — skill-creator eval records for `orchestrate-issues`
  (`evals.json`, `iteration-N/` runs, a run analysis) plus `test_frontier.py`, an unasserting
  smoke harness that takes `frontier.py`'s path as its argument. Not published, not run by CI.
- `tests/baselines/workbench-import/` — eval and packaging records for the `enhance`,
  `incremental-enhancement-lanes`, and `commit-to-pr` skills. `tests/scripts/workbench-helpers_test.py`
  exercises `lanes.py`, `gather.py`, `check_report.py` and `prune_worktrees.py` offline (`python3 tests/scripts/workbench-helpers_test.py`).
  Neither is published or run by CI.
- `tests/baselines/pm-status/` — `evals.json` for `pm-status` plus benchmark summaries. The evals
  run against private repos, so per-run reports stay out of this public repo.
- `.github/workflows/` — `ci.yml` (version guard, script compile, `claude plugin validate .`),
  `claude.yml` (`@claude` mentions), `claude-code-review.yml` (PR review).

## Working on the plugin

- **Add a skill:** create `plugins/<plugin>/skills/<name>/SKILL.md` with `name` and
  `description` frontmatter. Skills are auto-discovered — `plugin.json` does not enumerate them.
- **Add a plugin:** new `plugins/<name>/` dir with `.claude-plugin/plugin.json`, then add an entry
  to the `plugins` array in `.claude-plugin/marketplace.json`.
- **Bump the version** in a plugin's `plugin.json` whenever its content changes — CI's version
  guard fails the PR otherwise (`.github/workflows/ci.yml`).
- **Releases:** manual; use `workbench-vX.Y.Z` tags and preserve the existing Latest release
  pointer. Before publishing a release or changing that pointer, read `docs/migration.md`
  for the legacy upgrade constraint.
- **Before committing a manifest:** run `claude plugin validate .` (CI runs the same).
- **Test the marketplace locally:** `/plugin marketplace add /path/to/toolshed` (the repo root).

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

This repo uses the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout. See `docs/agents/domain.md`.
