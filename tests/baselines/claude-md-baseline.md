# CLAUDE.md

## Project

`bundlewatch` — a CLI that fails CI when a build artifact exceeds its gzipped size budget. Pure Node.js, no runtime dependencies.

## Requirements

- Node.js `>=20.6.0` (uses the built-in `node --test` runner and ESM).
- This is an ESM project (`"type": "module"`). Use `import`/`export`, not `require`. Reference Node built-ins with the `node:` prefix (e.g. `import { readFileSync } from "node:fs"`).
- No dependencies and no lockfile; `npm install` is not needed to run anything.

## Commands

| Task | Command |
|------|---------|
| Run tests | `npm run check` (runs `node --test test/`) |
| Build artifact | `npm run build` (writes `dist/bundle.js`) |
| Lint / syntax check | `npm run lint` (build in `--lint-only` mode, no output emitted) |
| Run the CLI | `node bin/cli.js` or `npx bundlewatch` |

There is no separate test/lint tooling (no Jest, ESLint, Prettier, TypeScript). "Lint" is just the build script run with `--lint-only`.

## Layout

- `bin/cli.js` — CLI entry point and core logic (`parseArgs`, `loadConfig`, `measure`, `run`). Exports `measure`/`run` for tests; runs `process.exit(run(...))` only when invoked directly.
- `src/budget.js` — pure helpers (`overBudget`, `formatKb`).
- `scripts/build.js` — stand-in build that concatenates `src/*.js` into `dist/bundle.js`. A real project would call esbuild/rollup here.
- `test/budget.test.js` — node:test + node:assert/strict tests for `src/budget.js`.
- `bundlewatch.config.json` — default config: a `budgets` array of `{ path, maxKb }` entries.
- `dist/` and `node_modules/` are gitignored. `dist/` is a build output — build before running the CLI against it.

## How it works

`run(argv, cwd)` loads the config, then for each budget entry measures the artifact's **gzipped** size and compares it to `maxKb * 1024`. Returns exit code `0` if all pass, `1` if any artifact is over budget. Human output by default; `--json` for machine-readable output.

CLI flags (parsing is intentionally minimal; unknown flags exit `2`):
- `--config <path>` — config JSON path. Default `bundlewatch.config.json`, overridable via env `BUNDLEWATCH_CONFIG`; `--config` takes precedence over the env var.
- `--budget <kb>` — override the budget (kb) for all entries.
- `--json` — emit JSON instead of human-readable text.

There is deliberately no `--verbose` and no `--help`.

## Conventions and gotchas

- Budgets are measured against **gzipped** size, not raw bytes. Artifacts are read fully into memory and gzipped whole (not streamed) on purpose: gzip ratio depends on full content, so a partial measurement would not be reproducible in CI. Keep it this way.
- Exit codes are part of the contract: `0` = within budget, `1` = over budget, `2` = bad/unknown flag. Preserve these.
- Keep `measure` and `run` exported so tests can import them without spawning a process.
- The CLI must run with zero dependencies — don't add npm packages without a strong reason.
- When adding tests, follow the existing style: `node:test` `test()` blocks with `node:assert/strict`. Run them with `npm run check`.
