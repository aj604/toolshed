# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. Nothing here builds or
runs except the sample repos under `tests/fixtures/`; everything published is Markdown.

## Layout (pointers, not descriptions)

- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there, which is
  why this repo lives at `skills/toolshed/` rather than as a subdir of a larger repo.
- `plugins/doc-lifecycle/` — the one published plugin. `.claude-plugin/plugin.json` is its
  manifest; `skills/` and `agents/` hold its contents.
- `docs/` — `PITCH.md` (rationale + worked example), `plans/` (design + `HANDOFF.md`). Not published.
- `tests/` — `fixtures/` (runnable sample repos) and `baselines/` (RED/GREEN skill-test records).
  Not published.

## Working on the plugin

- **Add a skill:** create `plugins/doc-lifecycle/skills/<name>/SKILL.md` with `name` and
  `description` frontmatter. Skills are auto-discovered — `plugin.json` does not enumerate them
  (`plugins/doc-lifecycle/.claude-plugin/plugin.json`).
- **Add a plugin:** new `plugins/<name>/` dir with `.claude-plugin/plugin.json`, then add an entry
  to the `plugins` array in `.claude-plugin/marketplace.json`.
- **Before committing a manifest:** `marketplace.json` and every `plugin.json` must be valid JSON.
- **Test the marketplace locally:** `/plugin marketplace add /Users/averyjones/Repos/skills/toolshed`.

## Conventions

- **Skills are built test-first** (RED → GREEN → REFACTOR with subagents) via the
  `superpowers:writing-skills` methodology; test records go under `tests/baselines/<skill>/`.
  Method, status, and resume notes: `docs/plans/HANDOFF.md`; full design:
  `docs/plans/2026-06-09-documentation-skills-suite-design.md`.
- **Docs in this repo follow the contract the plugin enforces:** every line is a claim verifiable
  against the repo (the `writing-docs` skill). Agent-facing docs defer to `writing-for-llms` for
  token economy.
- **Multi-unit repos get a `docs/reference/` convention:** the skill prescribes containing a
  larger repo's whole agent doc set (cross-unit `architecture.md`, per-unit `overview.md`,
  generated reference) in one self-contained `docs/reference/` subtree rather than scattering it
  across `docs/` root (`plugins/doc-lifecycle/skills/bootstrapping-docs/repo-shape.md`). This repo
  is a single-unit marketplace, so its own `docs/` stays flat (`PITCH.md`, `plans/`) — do not add
  a `docs/reference/` tier here.

## Gotchas

- **`tests/fixtures/taskflow` needs `make setup` after checkout** before anything runs — it
  relinks npm workspaces (`tests/fixtures/taskflow/Makefile:1`, comment). Then `make migrate`
  before `make dev`/`make test`, or api and worker exit nonzero.

## Not yet documented

- `doc-sync-automation` (4th lifecycle skill) — designed, not built. See `docs/PITCH.md` and
  `docs/plans/HANDOFF.md`.
- Per-skill behavior — read each `SKILL.md`; they are self-describing.
- Fixture internals — read the fixture's own `Makefile` / `package.json`.
