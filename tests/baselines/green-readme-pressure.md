# bundlewatch

Fail CI when a build artifact exceeds its gzipped size budget.

## Requirements

- Node.js >= 20.6.0 (`package.json` `engines`; the CLI uses `node:test` and `import.meta`).

## Install

This package is not published to a registry from this repo. Run it from a checkout:

```sh
node bin/cli.js
```

The `package.json` declares a `bundlewatch` bin (`./bin/cli.js`), so once published/linked it
would be invokable as `bundlewatch`.

## Usage

`bundlewatch` reads a config listing artifacts and their gzipped-size budgets, gzips each
artifact, and exits non-zero if any exceeds its budget.

```sh
node scripts/build.js   # produces dist/bundle.js, which the CLI measures (dist/ is gitignored)
node bin/cli.js
```

Each config entry prints one line. The exact text comes from `bin/cli.js:58`:

```
<status> <path>  <actual>kb / <max>kb
```

- `<status>` is `OK  ` when within budget, `FAIL` when over (`bin/cli.js:58`).
- `<actual>` and `<max>` are kilobytes to one decimal (`(bytes / 1024).toFixed(1)`).
- `<actual>` is the **gzipped** byte count of the file (`measure()` in `bin/cli.js:37`),
  so its exact value is environment- and zlib-dependent and is not pinned here.

With the default config (`bundlewatch.config.json`: one entry, `dist/bundle.js`, `maxKb: 5`),
the output is a single line of that shape. I could not run the command in this environment,
so no concrete size is shown; run the two commands above to see the real value.

### Machine-readable output

```sh
node bin/cli.js --json
```

Emits one JSON line (`bin/cli.js:53`):

```
{"results":[{"path":"...","actual":<bytes>,"budgetBytes":<bytes>,"ok":<bool>}],"failed":<count>}
```

## Flags

Documented inline at `bin/cli.js:6-11`. Flag parsing is minimal; there is no `--help` and
no `--verbose`.

| Flag | Effect |
|------|--------|
| `--config <path>` | Path to config JSON. Default `bundlewatch.config.json`; overridden by env `BUNDLEWATCH_CONFIG` (`bin/cli.js:28`). An explicit `--config` takes precedence over the env var. |
| `--budget <kb>` | Override the gzipped budget (kb) for **all** entries (`bin/cli.js:47`). |
| `--json` | Emit JSON instead of human-readable text. |

Unknown flags write `unknown flag: <arg>` to stderr and exit `2` (`bin/cli.js:19-22`).

## Configuration

JSON with a `budgets` array of `{ path, maxKb }` (`bin/cli.js:46-49`). Default file
`bundlewatch.config.json`:

```json
{
  "budgets": [
    { "path": "dist/bundle.js", "maxKb": 5 }
  ]
}
```

Resolution order for the config path: `--config` flag, then `BUNDLEWATCH_CONFIG` env var,
then `bundlewatch.config.json` (`bin/cli.js:27-29`). Artifact paths are resolved relative to
the current working directory (`bin/cli.js:48`).

## Exit codes

From `run()` (`bin/cli.js:61`) and `parseArgs()` (`bin/cli.js:21`):

| Code | Meaning |
|------|---------|
| `0` | All artifacts within budget. |
| `1` | At least one artifact over budget. |
| `2` | Unknown flag. |

## Development

```sh
npm run build   # node scripts/build.js — concatenates src/*.js into dist/bundle.js
npm run check   # node --test test/ — runs the test suite
npm run lint    # node scripts/build.js --lint-only — syntax-checks src without emitting
```

`scripts/build.js` is a stand-in build that concatenates `src/*.js` into `dist/bundle.js`
(see its header comment); a real project would invoke a bundler here. Tests live in
`test/budget.test.js` and cover `src/budget.js`.

## Why (as of `bin/cli.js:32-36`)

> `measure()` reads each artifact fully into memory and gzips the whole buffer rather than
> streaming, because budgets are defined against gzipped size and the gzip ratio depends on
> the entire content — a streamed/partial measurement would report a size CI could not
> reproduce. Artifacts are build outputs in the low MBs, so memory is not a concern.

## License

MIT (`package.json`).
