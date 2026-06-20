# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget.

## Setup

**Requires:** Node >= 20.6.0 (`package.json:10`)

```bash
npm install
npm run check   # runs node --test test/
```

No `npm test` script exists. The test command is `check` (`package.json:14`).

## CLI flags

`bin/cli.js:6-11` — only these flags are supported; unknown flags exit 2:

| Flag | Argument | Effect |
|------|----------|--------|
| `--config` | `<path>` | Path to config JSON. Default: `bundlewatch.config.json`, overridden by env `BUNDLEWATCH_CONFIG` |
| `--budget` | `<kb>` | Override gzipped budget (kb) for all entries |
| `--json` | — | Emit machine-readable JSON instead of human text |

There is no `--verbose` and no `--help`/`-h`. (`cli.js:11`)

## Config

Default config file: `bundlewatch.config.json` (not `.bundlewatchrc`). Override via `--config <path>` or env `BUNDLEWATCH_CONFIG`. (`cli.js:27-29`)

Shape (`bundlewatch.config.json:1-5`):
```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

Each entry in `budgets`: `path` (relative to cwd), `maxKb` (gzipped budget in kilobytes).

## Output

**Human (default):**
```
OK   dist/bundle.js  1.2kb / 5.0kb
FAIL dist/bundle.js  6.1kb / 5.0kb
```
Format: `cli.js:56-59`

**JSON (`--json`):**
```json
{"results":[{"path":"dist/bundle.js","actual":1234,"budgetBytes":5120,"ok":true}],"failed":0}
```
Format: `cli.js:53`

Exit 0 if all pass; exit 1 if any fail. (`cli.js:61`)

## How it works

`measure(filePath)` reads the artifact fully into memory and returns `gzipSync(buffer).length`. (`cli.js:37-39`)

In-memory approach is chosen for **correctness**, not speed: gzip ratio depends on the entire content, so a streamed partial measurement would report a size CI cannot reproduce. (`cli.js:34-36`)

## Exported API

`bin/cli.js` exports two functions (ESM, `package.json:8`):

- `measure(filePath) → number` — gzipped byte length of a file
- `run(argv, cwd?) → 0 | 1` — parse flags, load config, measure all entries, write output, return exit code

## Build

```bash
npm run build   # writes dist/bundle.js from src/*.js
npm run lint    # syntax check only, no emit
```

`scripts/build.js` concatenates `src/*.js` → `dist/bundle.js`. (`scripts/build.js:1-3`)
