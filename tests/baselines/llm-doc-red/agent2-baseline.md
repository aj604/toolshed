# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget. Node >=20.6, ESM.

## Quick reference

| Flag | Default | Description |
|------|---------|-------------|
| `--config <path>` | `bundlewatch.config.json` (or `$BUNDLEWATCH_CONFIG`) | Config file path |
| `--budget <kb>` | per-entry `maxKb` | Override budget for all entries |
| `--json` | false | Machine-readable output |

Unknown flags → exit 2. No `--verbose`, no `--help`.

## Config (`bundlewatch.config.json`)

```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

Each entry: `path` (relative to cwd) + `maxKb` (gzipped budget in KB).

## Run

```bash
npm install
npm test                        # runs node --test test/
node bin/cli.js                 # default config
node bin/cli.js --config ci.json --json
node bin/cli.js --budget 10     # override all budgets to 10kb
```

## Output

Human (default):
```
OK   dist/bundle.js  3.2kb / 5.0kb
FAIL dist/vendor.js  6.1kb / 5.0kb
```

JSON (`--json`):
```json
{"results":[{"path":"dist/bundle.js","actual":3277,"budgetBytes":5120,"ok":true}],"failed":0}
```

Exit 0 = all pass. Exit 1 = any budget exceeded.

## How measurement works

Each artifact is read fully into memory, then `gzipSync`'d. Budgets are against gzipped size. In-memory (not streamed) ensures reproducible CI measurements.

## Key files

| File | Purpose |
|------|---------|
| `bin/cli.js` | CLI entry — `parseArgs`, `loadConfig`, `measure`, `run` |
| `src/budget.js` | `overBudget(actualBytes, maxKb)`, `formatKb(bytes)` |
| `bundlewatch.config.json` | Default config (single entry example) |
| `scripts/build.js` | Build + optional lint-only mode |
