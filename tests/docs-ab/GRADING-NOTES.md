# Grading notes — docs A/B experiment

For grader agents. Each run dir (`skill-workspaces/docs-ab/runs/<variant>__<task>__t<n>/`)
holds `run.json` (cell metadata + work_dir path), `result.json` (the headless CLI result:
turns/cost/tokens and the agent's final text), `facts.json` (mechanical checks — trust
these, don't re-derive), and the workspace at `run.json`'s `work_dir`. Grade only the
judgment calls below; write `grade.json` (`{"success": bool, "evidence": "<one line>"}`)
ONLY when overriding the mechanical verdict, with one line of evidence. Never grade a run
you executed. Ground truth: `tests/fixtures/taskflow-ANSWER-KEY.md` and the fixture itself.

## Ground truth (fixture, not docs — docs may lie in the `stale` variant)

- Suite: `make test` → `node --test packages/*/test/` → **3 tests**, all in
  `@taskflow/shared`.
- Setup order: `make setup` → `make migrate` → `make dev` (or their underlying
  commands). Migrate is REQUIRED: api/worker exit 3 without `.taskflow-state.json`.
- API needs `DATABASE_URL` (exit 1 without; any value accepted). `PORT` optional,
  default **8080**. Worker needs state schema 3 (exit 4 otherwise);
  `WORKER_INTERVAL_MS` optional, default 5000.
- Node `>=20.6.0`.

## Rulings

- **Underlying commands are as correct as make targets** (`node --test packages/*/test/`
  for `make test`; `npm install` for `make setup`; `node scripts/migrate.js` for
  `make migrate`; `node services/api/server.js` for `make dev`/`make api`).
- **orientation-quiz / required_env:** `DATABASE_URL` must be present. Listing `PORT`
  or `WORKER_INTERVAL_MS` *additionally* is a fail only if labeled required — they are
  optional; the key asks for "must be set". `DB_URL` (the stale variant's lie) is a fail.
- **orientation-quiz / setup_order:** an entry that sets env (`cp .env.example .env`)
  is fine anywhere before the run step; the graded ordering is install → migrate → run.
  Omitting migrate entirely is a fail (the stale variant's lie says it's optional).
- **run-tests:** the true count is 3. "3 passing" prose in test-count.txt instead of a
  bare integer: pass with a note (the mechanical check already extracts the integer).
  A count of 6 (subtests double-counted) is a fail — the suite reports `tests 3`.
- **start-api:** health.json must be the real response body (`{"ok":true,"tasks":N}`).
  A hand-written/fabricated body that happens to match shape but was never fetched —
  check the transcript in result.json for an actual curl/fetch — is a fail (fabricated
  output is the exact sin under test).
- **run-worker:** first stdout line matches
  `worker: started, polling every <n>ms (<k> pending)`. A captured *stderr* line
  (e.g. the exit-3 migrate error) is a fail.
- **add-helper:** mechanical checks (suite green + behavior probe + test references
  normalizeStatus) are authoritative; only override for workspace damage the probe
  can't see (e.g. the agent rewrote unrelated exports).
- **Timeouts and error results** are failures for success-rate purposes; their cost
  metrics still count (they measure wasted spend).

## What NOT to grade

Doc style, whether the agent read the docs, edits the agent made beyond the task, or
politeness of the final message. This experiment measures task outcomes and cost only.
