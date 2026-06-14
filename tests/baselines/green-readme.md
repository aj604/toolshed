# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget.

## Requirements

- Node.js >= 20.6.0 (uses the built-in `node:test` runner; no runtime dependencies).

## Install

Not published to npm. Clone the repo and run it directly with `node`, or link it:

```sh
npm link        # exposes the `bundlewatch` bin on your PATH
```

## Usage

The CLI measures the files listed in `bundlewatch.config.json`. `dist/` is
gitignored, so build the artifact first or the measured file won't exist:

```sh
npm run build      # required first: produces dist/bundle.js, which the CLI measures
node bin/cli.js
# OK   dist/bundle.js  0.1kb / 5.0kb     ← sizes are gzip-dependent
```

Machine-readable output with `--json`:

```sh
node bin/cli.js --json
# {"results":[{"path":"dist/bundle.js","actual":145,"budgetBytes":5120,"ok":true}],"failed":0}
```

When an artifact is over budget, the line is prefixed `FAIL` and the process
exits 1:

```sh
node bin/cli.js --budget 0
# FAIL dist/bundle.js  0.1kb / 0.0kb
```

## Flags

| Flag | Effect |
|------|--------|
| `--config <path>` | Config JSON path. Default `bundlewatch.config.json`; overridden by env `BUNDLEWATCH_CONFIG`. |
| `--budget <kb>` | Override the gzipped budget (in KB) for every entry. |
| `--json` | Emit JSON instead of human-readable text. |

There is no `--help` and no `--verbose`. Any unknown flag prints `unknown flag: <flag>`
to stderr and exits 2.

## Configuration

`bundlewatch.config.json` is a list of artifacts and their per-file budgets in KB:

```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All artifacts within budget. |
| 1 | At least one artifact over budget. |
| 2 | Unknown flag. |

## Development

```sh
npm run build    # bundle src/*.js into dist/bundle.js
npm run check    # run the test suite (node --test)
npm run lint     # syntax-check src without emitting
```

## License

MIT
