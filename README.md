# toolshed

A personal [Claude Code](https://code.claude.com/docs/en/plugins) plugin marketplace.

```
/plugin marketplace add aj604/toolshed
/plugin install workbench@toolshed
```

## Plugins

| Plugin | What it is |
|---|---|
| [`workbench`](plugins/workbench/) | An SDLC toolkit: `orchestrate-issues` (drive a GitHub issue dependency graph to completion with background agents), `enhance` (pick and ship one autonomous improvement), `incremental-enhancement-lanes` (parallel stacks of improvement PRs for human review), and `commit-to-pr` (commit, push, and open or update a PR). Its workflows use git and the GitHub CLI; the lane helper also requires Python 3.10+. |

## Retired: doc-lifecycle

`doc-lifecycle` (evidence-backed doc drift detection and fixes) is decommissioned and its
source is no longer on `main`. The last release considered working is
[`v0.11.1`](https://github.com/aj604/toolshed/tree/v0.11.1); later versions' tags remain in
git history. If you installed it, remove it with `/plugin uninstall doc-lifecycle@toolshed`; a
repo that installed its scheduled lanes should also delete `.doc-lifecycle/` and its `doc-*.yml`
workflows.

## License

[MIT](LICENSE)
