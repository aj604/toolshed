# bundlewatch

> Fail CI when a build artifact exceeds its gzipped size budget.

`bundlewatch` is a tiny, zero-dependency CLI that measures the **gzipped** size of your build outputs and compares each against a budget you define. If anything is over budget, it exits non-zero so your CI pipeline fails loudly — before a bloated bundle ever ships.

- **Gzipped, not raw.** Budgets are checked against gzipped size, because that's what your users actually download.
- **Zero dependencies.** Pure Node.js standard library (`fs`, `zlib`, `path`). Nothing to audit, nothing to update.
- **CI-native.** Exit code `0` on pass, `1` on budget failure, `2` on bad usage. Plain-text output for humans, `--json` for machines.

## Requirements

- Node.js `>= 20.6.0`

## Installation

```bash
npm install --save-dev bundlewatch
```

Or run it ad hoc without installing:

```bash
npx bundlewatch
```

## Configuration

Create a `bundlewatch.config.json` in your project root. Each entry pairs a file `path` with its budget in kilobytes (`maxKb`), measured **after gzip**:

```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

You can list as many artifacts as you like:

```json
{
  "budgets": [
    { "path": "dist/app.js", "maxKb": 120 },
    { "path": "dist/vendor.js", "maxKb": 250 },
    { "path": "dist/styles.css", "maxKb": 30 }
  ]
}
```

## Usage

Run it from your project root after building:

```bash
bundlewatch
```

### Example output

When everything fits:

```text
OK   dist/bundle.js  0.2kb / 5.0kb
```

When an artifact blows its budget, the offending line is marked `FAIL` and the process exits with code `1`:

```text
OK   dist/app.js     118.4kb / 120.0kb
FAIL dist/vendor.js  274.9kb / 250.0kb
OK   dist/styles.css 12.1kb / 30.0kb
```

```bash
$ bundlewatch; echo "exit: $?"
...
exit: 1
```

### JSON output

For dashboards, bots, or further processing, use `--json`:

```bash
bundlewatch --json
```

```json
{"results":[{"path":"dist/bundle.js","actual":155,"budgetBytes":5120,"ok":true}],"failed":0}
```

`actual` and `budgetBytes` are both in bytes; `failed` is the count of over-budget entries.

## Options

| Flag | Description |
| --- | --- |
| `--config <path>` | Path to the config JSON. Defaults to `bundlewatch.config.json`, overridable via the `BUNDLEWATCH_CONFIG` environment variable. |
| `--budget <kb>` | Override the gzipped budget (in kilobytes) for **all** entries, ignoring each entry's `maxKb`. |
| `--json` | Emit machine-readable JSON instead of human-readable text. |

Flag parsing is intentionally minimal: there is no `--verbose` and no `--help`. **Any unknown flag exits with code `2`.**

### Configuration precedence

The config file is resolved in this order:

1. `--config <path>` (explicit flag)
2. `BUNDLEWATCH_CONFIG` environment variable
3. `bundlewatch.config.json` in the current directory

### Examples

Check against a config in a non-standard location:

```bash
bundlewatch --config config/size-budgets.json
```

Apply a single budget to every artifact (handy for quick experiments):

```bash
bundlewatch --budget 200
```

Point at a config via environment variable (useful in CI):

```bash
BUNDLEWATCH_CONFIG=ci/budgets.json bundlewatch --json
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | All artifacts are within budget. |
| `1` | One or more artifacts exceeded their budget. |
| `2` | Usage error (e.g., an unknown flag). |

## Use in CI

Because `bundlewatch` exits non-zero on failure, it drops straight into any CI pipeline. Build first, then check:

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]
jobs:
  size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run build
      - run: npx bundlewatch
```

If any bundle exceeds its budget, the step fails and the pull request is blocked.

## Why gzipped size?

Budgets are defined against **gzipped** size because that's the number that matters to your users over the wire. `bundlewatch` reads each artifact fully into memory and gzips the entire buffer rather than streaming a partial measurement — the gzip ratio depends on the whole file, so a partial read would report a size CI could not reproduce. Build artifacts are small (low megabytes at most), so correctness wins over micro-optimizing memory.

## API

The CLI is also importable as an ES module if you want to embed size checks in your own scripts:

```js
import { measure, overBudget, formatKb, run } from "bundlewatch";

const bytes = measure("dist/bundle.js");   // gzipped size in bytes
overBudget(bytes, 5);                       // true if over a 5kb budget
formatKb(bytes);                            // e.g. "0.2kb"

// Run the full check programmatically; returns the process exit code (0 or 1)
const code = run(["--json"]);
```

## Development

```bash
npm run build   # bundle src/*.js into dist/bundle.js
npm run lint    # syntax-check sources without emitting
npm run check   # run the test suite (node --test)
```

## License

MIT
