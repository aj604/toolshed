# Contributing to Workbench

Workbench is a Claude Code plugin published through the `toolshed`
marketplace. Most changes are to skill instructions, agent definitions, or
the standard-library Python helpers that support them.

## Make a change

- Skills live in `plugins/workbench/skills/<name>/SKILL.md`. A skill needs
  `name` and `description` frontmatter; Claude Code discovers it automatically.
- Agents live in `plugins/workbench/agents/`.
- The listing icon lives in `plugins/workbench/assets/`. Keep the editable
  SVG and its 1024px PNG export aligned when changing the mark.
- The README hero and social-preview artwork live in `assets/`. See the
  [asset guide](assets/README.md) for exporting and uploading the social card.
- Keep the root README's workflow table and the plugin's usage guide aligned
  with changes to the skills.
- Bump `plugins/workbench/.claude-plugin/plugin.json` whenever plugin content
  changes, including its documentation. CI enforces this on PRs.
- Keep `.claude-plugin/marketplace.json` at the repo root so marketplace
  installation continues to work.

## Validate

From the repo root:

```sh
claude plugin validate .
python3 -m compileall -q plugins
```

For changes to the lane or status helpers, also run their offline checks:

```sh
python3 tests/scripts/workbench-helpers_test.py
```

Skill evaluation records live under `tests/baselines/`. They document prior
runs; private-repo reports are kept out of this public repo. Changes to skill
behavior should be checked with representative prompts for the affected
workflow.

## Try the plugin locally

In Claude Code, add this checkout as a marketplace and install Workbench:

```text
/plugin marketplace add /absolute/path/to/toolshed
/plugin install workbench@toolshed
```

Use a disposable repo for workflows that create branches, push PRs, or merge.

## Releases

Releases are manual. Use `workbench-vX.Y.Z` tags for Workbench. The plugin
version in its manifest is the version users install from the marketplace.
See [migration and release-history notes](docs/migration.md) before changing
GitHub's Latest release.
