# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget. (`package.json`)

- Node `>=20.6.0`, ESM (`"type": "module"`). (`package.json`)
- Entry: `bin/cli.js` (bin name `bundlewatch`). Core logic: `run()` / `measure()` in `bin/cli.js`; helpers in `src/budget.js`.
- Exit codes: `0` all within budget · `1` one or more over budget · `2` unknown flag.

## Commands

| Command | Effect | Source |
|---|---|---|
| `npm run build` | Concatenate `src/*.js` → `dist/bundle.js` | `scripts/build.js` |
| `npm run lint` | Syntax check, no emit (`build.js --lint-only`) | `package.json`, `scripts/build.js` |
| `npm run check` | Run tests (`node --test test/`) | `package.json` |
| `node bin/cli.js [flags]` | Measure artifacts vs budgets | `bin/cli.js` |

There is no `test` or `start` script. (`package.json:12`)

## CLI flags

| Flag | Meaning |
|---|---|
| `--config <path>` | Config JSON path |
| `--budget <kb>` | Override gzipped budget (kb) for every entry |
| `--json` | Emit JSON instead of human text |

Parsing is exhaustive: any other arg (including `--help`, `-h`, `--verbose`) prints `unknown flag: <arg>` to stderr and exits 2. No `--help`/`--verbose` exist. (`bin/cli.js:11-23`)

## Config

Required JSON file with a `budgets` array of `{ path, maxKb }`. (`bundlewatch.config.json`, `bin/cli.js:46-47`)

```json
{ "budgets": [ { "path": "dist/bundle.js", "maxKb": 5 } ] }
```

Resolution order for config path: `--config` → env `BUNDLEWATCH_CONFIG` → default `bundlewatch.config.json`. (`bin/cli.js:28`)

Not zero-config: `run()` throws if the config file is absent (no try/catch around `loadConfig`). (`bin/cli.js:27-30,43-44`)

## Output

Human (default): one line per artifact — `OK  <path>  <kb>kb / <max>kb` or `FAIL ...` (1 decimal). (`bin/cli.js:55-59`)

JSON (`--json`): `{ results: [{ path, actual, budgetBytes, ok }], failed: <count> }`. (`bin/cli.js:52-53`)

## Behavior notes

- Budgets are **gzipped** bytes. `measure()` reads the whole file and `gzipSync`s the full buffer (no streaming) so CI gets a reproducible size. (`bin/cli.js:32-40`)
- `--budget` overrides per-entry `maxKb` for all entries via `opts.budget ?? entry.maxKb`. (`bin/cli.js:47`)
- Artifact paths resolve against `cwd`; config path resolves against process cwd. (`bin/cli.js:29,48`)
- `src/budget.js` (`overBudget`, `formatKb`) is exercised only by tests, not imported by `cli.js`. (`test/budget.test.js`, `bin/cli.js`)
