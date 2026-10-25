# Migration and release history

The `toolshed` marketplace now publishes **Workbench**. Its repository and
marketplace name remain `aj604/toolshed` and `toolshed`, so the installation
commands are:

```text
/plugin marketplace add aj604/toolshed
/plugin install workbench@toolshed
```

## Retired plugin: doc-lifecycle

`doc-lifecycle`, the documentation-drift plugin previously published here, is
decommissioned. Its source, engine, tests, local install, and scheduled lane
workflows were removed from `main`. Workbench is a separate plugin with skills
for agent-driven development.

If you installed the retired plugin:

1. Uninstall it in Claude Code:

   ```text
   /plugin uninstall doc-lifecycle@toolshed
   ```

2. In repos where you installed its scheduled lanes, remove `.doc-lifecycle/`
   and the `doc-*.yml` workflows belonging to that install under
   `.github/workflows/`.
3. Install Workbench using the commands above.

The last release considered working is
[`v0.11.1`](https://github.com/aj604/toolshed/tree/v0.11.1). Earlier source and
later historical tags remain available in git history.

## Release naming

Bare `vX.Y.Z` tags and the existing GitHub Releases belong to doc-lifecycle.
Use **`workbench-vX.Y.Z`** for any Workbench release.

Installed doc-lifecycle upgrade lanes read GitHub's Latest release. Preserve
that pointer when publishing a Workbench release: publish it without marking
it Latest (`gh release create … --latest=false`). Workbench installation uses
the marketplace and the version in `plugins/workbench/.claude-plugin/plugin.json`.
