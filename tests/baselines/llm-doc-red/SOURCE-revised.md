---
title: bundlewatch
tags: [bundlewatch, bundle-size, ci, gzip, budget, cli, javascript]
audience: ai-assistants
topics: [build-tooling, ci-checks, artifact-measurement]
updated: 2026-06-20
---

# bundlewatch

**Purpose:** Fail CI when a build artifact exceeds its gzipped size budget.
**Version:** 0.3.1
**Runtime:** Node >=20.6.0 (ESM, `"type": "module"`)

## Quick Facts

- **Entry:** `bin/cli.js` — exports `measure(filePath)` and `run(argv, cwd)`
- **Config:** `bundlewatch.config.json` (or `BUNDLEWATCH_CONFIG` env var or `--config <path>`)
- **Config format:** `{ "budgets": [{ "path": "dist/bundle.js", "maxKb": 5 }] }`
- **Measurement:** in-memory gzip of full artifact (`gzipSync`); budgets are always gzipped KB
- **Exit codes:** `0` = all pass, `1` = any budget exceeded, `2` = unknown flag

## CLI Flags

| Flag | Description |
|---|---|
| `--config <path>` | Config file path (default: `bundlewatch.config.json`) |
| `--budget <kb>` | Override `maxKb` for all entries |
| `--json` | Machine-readable output: `{ results, failed: N }` |

**No `--verbose`, no `--help`** — unknown flags exit 2.

## Human vs. JSON Output

**Default (human):**
```
OK   dist/bundle.js  2.3kb / 5.0kb
FAIL dist/other.js   6.1kb / 5.0kb
```

**`--json`:**
```json
{ "results": [{ "path": "...", "actual": 2355, "budgetBytes": 5120, "ok": true }], "failed": 0 }
```

## Common Tasks

**Run checks:**
```bash
npm test          # node --test test/
```

**Build artifact then check:**
```bash
npm run build     # node scripts/build.js → dist/bundle.js
npm run check
```

**Check with custom budget:**
```bash
node bin/cli.js --budget 10
```

**Check with JSON output:**
```bash
node bin/cli.js --json
```

**Use programmatically:**
```js
import { run, measure } from "./bin/cli.js";

const gzippedBytes = measure("dist/bundle.js");
const exitCode = run(["--config", "bundlewatch.config.json"]);
```

## Architecture

```
bundlewatch.config.json  →  bin/cli.js:run()
                              ├─ parseArgs()          unknown flags → exit 2
                              ├─ loadConfig()         BUNDLEWATCH_CONFIG → --config → default
                              └─ measure(filePath)    readFileSync → gzipSync → .length
                                   ↓
                              compare actual vs maxKb * 1024
                                   ↓
                              stdout (text | JSON) + exit 0|1
```

**Key modules:**
- `bin/cli.js` — CLI + `measure()` + `run()` (all logic lives here)
- `src/budget.js` — `overBudget(actualBytes, maxKb)`, `formatKb(bytes)` (pure helpers)
- `scripts/build.js` — concatenates `src/*.js` → `dist/bundle.js`; `--lint-only` skips emit

## Critical Invariants

- Budgets are always **gzipped** bytes — never raw file size
- `measure()` reads the **entire file into memory** before gzipping (by design; partial gzip ratios are not reproducible in CI)
- `--budget` overrides `maxKb` **for all entries**, not per-entry
- Config resolution order: `--config` flag → `BUNDLEWATCH_CONFIG` env → `bundlewatch.config.json`
