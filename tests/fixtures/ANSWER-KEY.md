# Fixture answer key (grading reference — NOT visible to agents documenting the repo)

Ground truth for `sample-repo` (bundlewatch CLI). Baseline/skilled doc output is
graded against these facts. Each is mechanically verifiable.

## Verifiable claims (the truth)

| Claim | Truth | How to verify |
|-------|-------|---------------|
| Run tests | `npm run check` (runs `node --test test/`) | package.json scripts; **there is no `npm test`** |
| Build | `npm run build` → emits `dist/bundle.js` | `npm run build` |
| Lint | `npm run lint` | package.json scripts |
| Node version | `>=20.6.0` required | package.json engines |
| CLI flags | `--config <path>`, `--budget <kb>`, `--json` only | bin/cli.js parseArgs |
| No `--verbose`, no `--help` | unknown flag exits 2 | `node bin/cli.js --verbose; echo $?` → 2 |
| Default config file | `bundlewatch.config.json` | bin/cli.js loadConfig |
| Config override | env `BUNDLEWATCH_CONFIG` or `--config` | bin/cli.js loadConfig |
| Exit codes | 0 within budget, 1 over budget, 2 bad flag | run CLI |
| Install deps | none (zero dependencies) | package.json has no deps |

## Gotcha (non-inferable, must be documented)

You **must** `npm run build` before running the CLI — it measures `dist/bundle.js`,
which does not exist until built. Running first throws ENOENT.

## Rationale claim (the "why" — should be anchored, not invented)

`bin/cli.js measure()` reads each artifact fully into memory and gzips the whole
buffer instead of streaming. **Why:** budgets are defined on gzipped size, gzip
ratio depends on the entire content, so a streamed/partial measure would report a
size CI couldn't reproduce. Anchor: comment above `measure()` in bin/cli.js.

## Traps (predicted baseline failures)

- Writing `npm test` (plausible, WRONG — script doesn't exist).
- Inventing `--verbose` / `--help` / `-h` flags (plausible, WRONG).
- Omitting the build-before-run gotcha (invisible unless you actually run it).
- Omitting Node >=20.6.0.
- Marketing prose ("blazing-fast", "zero-config", "powerful").
- Inventing a rationale for the in-memory read, or stating it with no anchor.
- Misplacing agent-facing build/test commands into prose-heavy README sections,
  or dumping human onboarding narrative into CLAUDE.md.
