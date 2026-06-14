# CLAUDE.md

Guidance for AI agents working in this repository.

## What this is

`bundlewatch` is a tiny, zero-dependency CLI that fails CI when a build
artifact exceeds its gzipped size budget. You give it a config listing
artifact paths and per-artifact size limits (in KB); it gzips each artifact,
compares the gzipped byte count against the budget, prints a report, and exits
non-zero if any artifact is over budget.

It is pure ESM (`"type": "module"`), uses only Node built-ins (`node:fs`,
`node:zlib`, `node:path`, `node:url`), and requires **Node >= 20.6.0**.

## Layout

| Path | Role |
| --- | --- |
| `bin/cli.js` | CLI entry point and core logic (arg parsing, config load, measure, run loop, reporting). Has a shebang and is the `bundlewatch` bin. |
| `src/budget.js` | Pure helpers `overBudget(actualBytes, maxKb)` and `formatKb(bytes)`. |
| `scripts/build.js` | Stand-in "build": concatenates `src/*.js` into `dist/bundle.js`. Supports `--lint-only`. |
| `test/budget.test.js` | Node test runner tests for `src/budget.js`. |
| `bundlewatch.config.json` | Default config: a `budgets` array of `{ path, maxKb }`. |
| `dist/` | Build output (`bundle.js`). Gitignored. |

## Commands

```sh
npm run build      # node scripts/build.js  -> writes dist/bundle.js
npm run lint       # node scripts/build.js --lint-only  (syntax check, no emit)
npm run check      # node --test test/  (runs the test suite)
```

There is no separate test framework or linter dependency. `check` uses Node's
built-in test runner; `lint` is just the build script's syntax pass over
`src/*.js`. No install step is needed beyond Node itself (no runtime deps).

### Running the CLI

```sh
node bin/cli.js                       # uses ./bundlewatch.config.json
node bin/cli.js --config path.json    # explicit config path
node bin/cli.js --budget 5            # override budget (KB) for ALL entries
node bin/cli.js --json                # machine-readable JSON output
```

Typical CI flow: `npm run build` then `node bin/cli.js`.

Config can also be pointed at via the `BUNDLEWATCH_CONFIG` env var. Precedence:
`--config` flag > `BUNDLEWATCH_CONFIG` > `bundlewatch.config.json`.

### Exit codes

- `0` — all artifacts within budget
- `1` — at least one artifact over budget
- `2` — unknown CLI flag (arg-parse error)

### Output

Human mode prints one line per artifact:

```
OK   dist/bundle.js  1.2kb / 5.0kb
FAIL dist/big.js  9.8kb / 5.0kb
```

JSON mode emits `{ results, failed }` where `results` is the per-artifact
records (`path`, `actual`, `budgetBytes`, `ok`) and `failed` is the count of
over-budget entries.

## Conventions

- **ESM only.** Use `import`/`export`. No `require`, no CommonJS.
- **No dependencies.** Stick to Node built-ins; do not add packages. Keeping the
  dependency tree empty is a deliberate property of the tool.
- **Node built-in `node:` import specifiers** (e.g. `node:fs`, not `fs`).
- **Two-space indentation, double-quoted strings, semicolons** — match existing
  files.
- Functions that are independently useful are exported even when the CLI invokes
  them in-process (`measure`, `run` in `cli.js`; helpers in `src/budget.js`),
  which is what makes them testable.
- The CLI is invoked-as-main guarded: `if (import.meta.url === \`file://${process.argv[1]}\`)`, so importing `cli.js` does not run it.

## Design reasoning

- **Budgets are measured against gzipped size, and the whole artifact is read
  into memory and gzipped as one buffer** (`measure` in `bin/cli.js`) rather than
  streamed. Gzip ratio depends on the entire content, so a partial/streamed
  measurement would report a size CI could not reproduce. The code accepts the
  memory cost on purpose: artifacts are build outputs in the low MBs, never
  arbitrary user input. Preserve this — do not "optimize" it into streaming.
- **Arg parsing is intentionally minimal.** Only `--config`, `--budget`, and
  `--json` are supported. There is deliberately no `--verbose` and no `--help`;
  any unknown flag exits `2`. Don't add flags casually; the strictness is a
  feature (typos fail loudly in CI).
- **`--budget` overrides every entry's `maxKb`.** It is a global override, not a
  per-artifact one. The per-artifact limits live in the config's `budgets` array.
- **`scripts/build.js` is a placeholder bundler.** It just concatenates
  `src/*.js` with a `// <filename>` banner so the CLI has something to measure.
  Real projects would swap in esbuild/rollup here. `--lint-only` runs the same
  read/parse pass without emitting `dist/`, which is how `npm run lint` gets a
  cheap syntax check for free.

## Notes / gotchas for editors

- `src/budget.js` (`overBudget`, `formatKb`) is currently exercised only by the
  tests; `bin/cli.js` re-implements the equivalent comparison and KB formatting
  inline rather than importing those helpers. If you change budget/formatting
  logic, update both places (or refactor the CLI to import from `src/budget.js`)
  so behavior and tests stay in sync.
- `dist/` is gitignored and produced by the build; never hand-edit
  `dist/bundle.js`.
- Tests live in `test/` and run via `node --test`; add new tests as
  `test/*.test.js` using `node:test` + `node:assert/strict`.
- Config shape is `{ "budgets": [ { "path": string, "maxKb": number } ] }`.
- Requires Node >= 20.6.0 (declared in `engines`); features like the stable test
  runner and `import.meta` usage assume a modern Node.
