# CLAUDE.md

bundlewatch: CLI that fails CI when a build artifact exceeds its gzipped size budget.

## Commands

| Task | Command |
|------|---------|
| Build the artifact (`dist/bundle.js`) | `npm run build` |
| Run tests | `npm run check` (not `npm test`) |
| Lint (syntax check, no emit) | `npm run lint` |
| Run the budget check | `node bin/cli.js` |

## Gotchas

- Build before running the CLI. `node bin/cli.js` reads `dist/bundle.js` (gitignored, not committed); with no `dist/` it crashes with an unhandled ENOENT, not a clean error. Run `npm run build` first.
- `npm run check` does **not** build. Tests import `src/budget.js` directly, so they pass without `dist/`; only the CLI needs the build.
- CLI exit codes are the contract for CI: `0` all within budget, `1` something over budget, `2` unknown flag (`bin/cli.js:21`, `:61`).
- Config resolution order (`bin/cli.js:28`): `--config <path>` > `$BUNDLEWATCH_CONFIG` > `bundlewatch.config.json`.
- Flags are only `--config`, `--budget <kb>`, `--json`; there is intentionally no `--help`/`--verbose`, and any unknown flag exits 2 (`bin/cli.js:6-11`).

## Conventions

- Requires Node `>=20.6.0` (`package.json` engines); tests use the built-in `node --test` runner and `node:assert/strict` — no test framework dependency.

## Design notes

> **Why (as of `bin/cli.js:32-36`):** `measure()` reads each artifact fully into memory and gzips the whole buffer instead of streaming, because budgets are defined against gzipped size and the gzip ratio depends on the entire content — a partial/streamed measurement would report a size CI could not reproduce. Acceptable because artifacts are build outputs in the low MBs.
> **Why (as of `scripts/build.js:1-3`):** `build.js` just concatenates `src/*.js` into `dist/bundle.js` as a stand-in so the CLI has something to measure; a real project would invoke esbuild/rollup here.
