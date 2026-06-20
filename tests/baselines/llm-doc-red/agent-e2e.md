# bundlewatch

Fails CI when a build artifact exceeds its gzipped size budget.
(`package.json:4`)

## Requirements

- Node `>=20.6.0` (`package.json:9–11`)
- No install step — no `dependencies` in `package.json`

## Run

```bash
# run checks (reads bundlewatch.config.json by default)
node bin/cli.js

# run tests
node --test test/
```

(`package.json:13–15` — the scripts are `build`, `check`, and `lint`; there is no `npm test` script)

## CLI flags

| Flag | Argument | Effect |
|------|----------|--------|
| `--config` | `<path>` | Path to config JSON. Defaults to `BUNDLEWATCH_CONFIG` env var, then `bundlewatch.config.json`. |
| `--budget` | `<kb>` | Override `maxKb` for all budget entries. |
| `--json` | — | Emit machine-readable JSON instead of human text. |

Unknown flags exit `2`. `--verbose` and `--help` do not exist — both exit `2`.
(`bin/cli.js:6–11`)

## Config

Default file: `bundlewatch.config.json` at the working directory.
Override: `--config <path>` or env `BUNDLEWATCH_CONFIG`.

Schema (`bundlewatch.config.json`):
```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

Each budget entry: `path` (relative to cwd) + `maxKb` (gzipped threshold in kilobytes).

## Output

Human text (default):
```
OK   dist/bundle.js  0.1kb / 5.0kb
```

JSON (`--json`):
```json
{"results":[{"path":"dist/bundle.js","actual":145,"budgetBytes":5120,"ok":true}],"failed":0}
```

`failed` is a count. Exit code: `0` all pass, `1` any fail.
(`bin/cli.js:51–62`)

## How measurement works

Each artifact is read fully into memory, then `gzipSync`'d. Budgets are compared against the gzipped byte count. In-memory (not streaming) because gzip ratio depends on the full buffer — a partial measurement would produce a size CI cannot reproduce.
(`bin/cli.js:32–39`)

## Exported API

```js
import { measure, run } from "./bin/cli.js";

measure(filePath)           // → gzipped byte count (number)
run(argv, cwd?)             // → exit code (0 | 1)
```

(`bin/cli.js:37–62`)
