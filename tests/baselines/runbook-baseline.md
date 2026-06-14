# Runbook: bundlewatch CI failure

## What this tool does

`bundlewatch` (v0.3.1) is a small Node CLI that fails CI when a build artifact's
**gzipped** size exceeds a configured budget. It reads a config file listing
artifacts and their max sizes (in KB), gzips each artifact, and compares the
result against the budget. If any artifact is over, CI fails.

If you were paged, a CI build invoked `bundlewatch` and it exited non-zero. Your
job is to determine whether this is a **legitimate budget regression** (a real
bundle got bigger and someone needs to fix it) or a **tool/config error**
(missing artifact, bad config) and resolve or escalate accordingly.

- Entry point: `bin/cli.js`
- Config (default): `bundlewatch.config.json` at repo root
- Requires: Node `>=20.6.0` (uses native test runner, ESM)

## Reproduce locally (do this first)

```sh
# from the repo root
node --version            # confirm >= 20.6.0; mismatched Node causes spurious failures
node scripts/build.js     # produce the artifact (dist/bundle.js); see note below
node bin/cli.js           # run the check the way CI does
```

Important: `dist/` is git-ignored and not committed. The artifact must be
**built** before bundlewatch runs. In CI the build step runs first; locally you
must run `node scripts/build.js` yourself or you'll get a misleading "missing
file" failure that is not how CI actually failed.

Useful invocations:

```sh
node bin/cli.js --json            # machine-readable output, easier to read under pressure
node bin/cli.js --config <path>   # use a non-default config
node bin/cli.js --budget <kb>     # override budget for ALL entries (debugging only)
```

Config can also be pointed at via the `BUNDLEWATCH_CONFIG` env var. Precedence:
`--config` flag > `BUNDLEWATCH_CONFIG` > default `bundlewatch.config.json`.

There is no `--help` and no `--verbose`. Any unrecognized flag exits 2.

## Output format

Human (default), one line per artifact:

```
OK   dist/bundle.js  0.1kb / 5.0kb     <- gzipped actual / budget
FAIL dist/bundle.js  6.2kb / 5.0kb
```

JSON (`--json`):

```json
{"results":[{"path":"dist/bundle.js","actual":145,"budgetBytes":5120,"ok":true}],"failed":0}
```

`actual` and `budgetBytes` are in **bytes**. `failed` is the count of
over-budget artifacts.

## Exit codes and what they mean

| Exit | Meaning | Typical cause | Action |
|------|---------|---------------|--------|
| `0`  | All artifacts within budget | — | No action; build should be green |
| `1`  | At least one artifact over budget **OR an uncaught error** | Real regression, OR missing/unbuilt artifact, OR missing/malformed config | Read the output to disambiguate — see below |
| `2`  | Bad CLI usage | Unknown flag (e.g. `--verbose`), passed to the tool by the CI config | Fix the CI invocation |

Note the trap: exit `1` is overloaded. A genuine budget failure and a tool crash
both exit `1`. **Distinguish them by the output**, not the code.

## Failure modes and triage

### A. Legitimate budget regression
Output shows `FAIL <path>  <actual>kb / <budget>kb` with actual > budget, and the
process exits cleanly (no stack trace).

This means a real artifact grew past its budget. This is the tool doing its job.

Fix options (pick with the owning team):
1. Reduce the bundle size (remove a dependency, code-split, tree-shake) — preferred.
2. Raise the budget in `bundlewatch.config.json` by bumping the `maxKb` value for
   that entry, if the growth is intentional and acceptable. Commit the change and
   re-run CI.
3. As a temporary unblock you can override with `--budget <kb>` in the CI command,
   but this loosens the budget for *every* entry and should be reverted ASAP.

### B. Missing or unbuilt artifact
Output is a Node stack trace containing `Error: ENOENT ... open '.../dist/bundle.js'`
and exits `1` (no `OK`/`FAIL` lines printed).

Cause: the build step did not run, ran after bundlewatch, or failed silently, so
the artifact bundlewatch was told to measure does not exist.

Fix:
- Confirm the CI build step (`node scripts/build.js` / `npm run build`) runs and
  succeeds **before** the bundlewatch step.
- Check that the `path` values in `bundlewatch.config.json` match what the build
  actually emits.
- Reproduce locally with the "Reproduce locally" steps above.

### C. Missing or malformed config
Stack trace mentions the config path. `ENOENT` = config file not found (wrong
`--config`/`BUNDLEWATCH_CONFIG`/working directory). A `SyntaxError` / JSON parse
error = the config file is not valid JSON. Both exit `1`.

Fix:
- Verify `bundlewatch.config.json` exists at the working directory CI runs from,
  or that `--config` / `BUNDLEWATCH_CONFIG` points to the right path.
- Validate the JSON: `node -e "JSON.parse(require('fs').readFileSync('bundlewatch.config.json'))"`.
  The expected shape is `{ "budgets": [ { "path": "...", "maxKb": <number> } ] }`.

### D. Unknown flag (exit 2)
Output: `unknown flag: <flag>`. The CI step passed a flag bundlewatch doesn't
support (only `--config`, `--budget`, `--json` exist). Fix the CI invocation.

### E. Node version mismatch
If you see ESM/`node:test` syntax errors or unexpected behavior, check
`node --version` is `>=20.6.0`. CI runners on an older Node will misbehave.

## Quick decision flow

1. Open the CI log for the bundlewatch step.
2. Stack trace present? -> tool/config error -> case B or C. Not a real regression.
3. `unknown flag` -> case D, fix CI command.
4. `FAIL <path> Xkb / Ykb` line, no stack trace -> real regression -> case A.
5. Can't tell -> reproduce locally (build, then run) and compare.

## Escalation

- Real budget regression (case A): hand to the team that owns the artifact /
  the PR that triggered the failure. They decide shrink-vs-raise-budget.
- Config or CI-pipeline issue (cases B, C, D): hand to whoever owns the CI
  workflow / repo tooling.
- If you must unblock the pipeline urgently and the growth is deemed acceptable,
  raise `maxKb` in the config (case A, option 2) and open a follow-up to address it.

## Reference: files

- `bin/cli.js` — CLI entry, arg parsing, config load, measure loop, exit logic
- `src/budget.js` — pure helpers (`overBudget`, `formatKb`)
- `scripts/build.js` — produces `dist/bundle.js` (stand-in build); `--lint-only` skips emit
- `bundlewatch.config.json` — budget definitions
- `test/budget.test.js` — unit tests (`npm run check`)
