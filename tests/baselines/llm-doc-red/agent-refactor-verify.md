# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget. Reads each artifact fully into memory and gzips the buffer; gzip ratio depends on entire content, so streaming would produce unreproducible measurements (`bin/cli.js:36-39`).

## Install / run

Node >=20.6.0 (`package.json:10`).

```
npm install
node bin/cli.js
```

`npm test` runs the unit suite (`node --test test/`), not the CLI.

## Config

Default config file: `bundlewatch.config.json` in cwd, or env `BUNDLEWATCH_CONFIG`. Override with `--config <path>`.

Schema (`bundlewatch.config.json`):
```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

Each entry: `path` (relative to cwd), `maxKb` (gzipped budget).

## Flags

| Flag | Effect |
|------|--------|
| `--config <path>` | Config file path |
| `--budget <kb>` | Override `maxKb` for all entries |
| `--json` | Machine-readable output |

Unknown flags → stderr + exit 2. There is no `--verbose`, `--help`, or `-h`; those flags exit 2 (`bin/cli.js:11`).

## Output

Human (default):
```
OK   dist/bundle.js  0.1kb / 5.0kb
```

JSON (`--json`):
```json
{"results":[{"path":"dist/bundle.js","actual":145,"budgetBytes":5120,"ok":true}],"failed":0}
```

Exit 0 = all pass. Exit 1 = at least one budget exceeded.

## Key exports (`bin/cli.js`)

- `measure(filePath) → number` — gzipped byte count of file
- `run(argv, cwd?) → 0|1` — full CLI run; returns exit code

## Build

`node scripts/build.js` — concatenates `src/*.js` → `dist/bundle.js`. `--lint-only` skips emit. This is a fixture stand-in; real projects use esbuild/rollup (`scripts/build.js:2`).

## Tests

```
node --test test/
```

Tests `src/budget.js` exports `overBudget(actualBytes, maxKb)` and `formatKb(bytes)` (`test/budget.test.js`).
