# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget.

`bundlewatch` gzips your build output, compares the result against a size budget
you define, and exits non-zero when any artifact is too big. Wire it into CI to
catch accidental bundle bloat before it ships.

## Requirements

- Node.js >= 20.6.0

## Installation

Install from the project directory (or as a dependency in your own project):

```sh
npm install --save-dev bundlewatch
```

This exposes a `bundlewatch` command. You can also run it directly with `npx bundlewatch`.

## Configuration

Create a `bundlewatch.config.json` in your project root listing the artifacts to
check and their maximum **gzipped** size in kilobytes:

```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

Each entry's `path` is resolved relative to the current working directory.

## Usage

Build your artifact, then run the check:

```sh
bundlewatch
```

Example output:

```
OK   dist/bundle.js  3.2kb / 5.0kb
```

The command exits `0` when every artifact is within budget and `1` when one or
more exceed it (`FAIL` lines), making it CI-friendly.

### Options

| Flag | Description |
| --- | --- |
| `--config <path>` | Path to the config JSON. Defaults to `bundlewatch.config.json`, or the `BUNDLEWATCH_CONFIG` environment variable if set. |
| `--budget <kb>` | Override the gzipped budget (in KB) for all entries. |
| `--json` | Emit machine-readable JSON instead of human-readable text. |

There is intentionally no `--help` or `--verbose`. Unknown flags exit with code `2`.

The `--json` output looks like:

```json
{"results":[{"path":"dist/bundle.js","actual":3277,"budgetBytes":5120,"ok":true}],"failed":0}
```

### Example: CI

```sh
npm run build
bundlewatch
```

## npm scripts

This repo includes a tiny stand-in build (it concatenates `src/*.js` into
`dist/bundle.js`) so there's an artifact to measure. Real projects would replace
it with their own bundler (esbuild, rollup, etc.).

| Script | What it does |
| --- | --- |
| `npm run build` | Produces `dist/bundle.js`. |
| `npm run lint` | Runs the build's syntax check without emitting output. |
| `npm run check` | Runs the test suite. |

## Running the tests

```sh
npm run check
```

This runs the suite via the built-in Node test runner (`node --test test/`); no
extra test framework is required.

## License

MIT
