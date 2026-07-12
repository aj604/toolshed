# Docs A/B experiment — does doc quality move agent task performance?

Design approved 2026-07-11. Tests the plugin's three load-bearing premises against
measured agent behavior instead of authored conviction: the premises, the corpus that
encodes them, and the plugin that implements them share one author, so this experiment
is the first external grounding in the stack.

## Hypotheses

- **H1 (hydration):** plugin-shaped docs beat no docs on task success and cost (tokens/turns).
- **H2 (density):** plugin-shaped beats bloated even though both contain the same true facts —
  isolates signal density from fact presence.
- **H3 (drift severity):** stale docs perform worse than *no* docs — misleading beats-absent
  ("wrong answers, not slow degradation").

Expected pattern, stated before running: hydration/density move the **cost** metrics more
than success (agents can recover ground truth from `tests/fixtures/taskflow`'s Makefile and
sources), while staleness moves **success** — false claims send agents down wrong paths that
reading code wouldn't. H3 failing (stale ≈ none) would itself be a finding: it would argue
drift is a cost problem, not a correctness one, and weaken the case for the nightly lane's
priority over the weekly one.

## Fixture

`tests/fixtures/taskflow` — 3-unit workspace repo, ships doc-less, with planted gradeable
gotchas recorded in `tests/fixtures/taskflow-ANSWER-KEY.md`: `make setup → make migrate →
make dev` ordering (api/worker exit 3 without `.taskflow-state.json`), `make test` not
`npm test`, `DATABASE_URL` required (api exits 1), worker needs state schema 3 (exits 4),
Node `>=20.6.0`, PORT optional default 8080.

## Variants (the only cell-to-cell difference is the docs in the workspace)

| Variant | Content | Isolates |
|---------|---------|----------|
| `none` | stock fixture, no docs | baseline |
| `plugin-shaped` | hand-authored CLAUDE.md + README to the answer key's "what good looks like" (~25 dense lines) | hydration (vs none) |
| `bloated` | the **same true facts** buried in a ~300-line completeness catalog (per-file descriptions, helper signatures, route tables, restated package.json, boilerplate) — every fact in `plugin-shaped` is present and true here | density (vs plugin-shaped) |
| `stale` | same shape/length as plugin-shaped with planted false claims mapping to the fixture's real traps: `npm test`, `DB_URL`, "migrate no longer required", wrong default port | drift (vs none) |

Variants are hand-authored (deterministic, reviewable), not skill-generated. Bloated content
must be TRUE — false filler would contaminate it with the stale condition.

## Task battery (~5 tasks; each solvable without docs, so docs move cost/success, not feasibility)

1. **run-tests** — run the suite, report the pass count → trips `make test` vs `npm test`.
2. **start-api** — start the API, hit an endpoint, save the response → trips setup order +
   `DATABASE_URL` + migrate gotcha.
3. **add-helper** — add a helper to `@taskflow/shared` with tests, suite green → graded by
   re-running the suite mechanically.
4. **run-worker** — process one task through the worker, capture output → trips migrate +
   schema-3/exit-4.
5. **orientation-quiz** — write `answers.json` (test command, required env, setup order, node
   version) → pure hydration probe; its token count approximates tokens-to-orientation.

## Instrument

Per run: fresh workspace copy (fixture + variant docs + `git init` + pre-installed
node_modules from a per-variant template), then headless
`claude -p "<task>" --output-format json --max-turns 25` with a pinned model
(`claude-sonnet-5`), a restricted tool allowlist (Bash/Read/Write/Edit/Glob/Grep — no
Task, no web), and **profile isolation** so no user-level CLAUDE.md, memory, or plugins
contaminate the cell (`--setting-sources` restriction, falling back to a scratch
`CLAUDE_CONFIG_DIR`; smoke test validates whichever the installed CLI supports). The JSON
result supplies `num_turns`, token usage, `total_cost_usd`, `duration_ms`.

Scale: 4 variants × 5 tasks × 3 trials = 60 runs. Smoke test first (2 runs: cheapest task,
`none` + `plugin-shaped`), report measured per-run cost and projected matrix cost, pause
for go-ahead.

## Grading

Two layers, per the skill-workspaces harness pattern:
1. `collect-facts.py` — mechanical checks per run (does `answers.json` name `make test`;
   does the suite pass post-hoc; does the saved API response parse; exit codes).
2. Fresh grader agents (never the executor) score judgment assertions against
   `GRADING-NOTES.md`'s answer key; one grader per run, with the mechanical facts as input.

## Layout

- Committed: `tests/docs-ab/` — `variants/`, `tasks.json`, `run-experiment.py`,
  `collect-facts.py`, `analyze.py`, `GRADING-NOTES.md`.
- Run outputs: `skill-workspaces/docs-ab/` (gitignored, like the skill-creator harness).
- `analyze.py` renders the variant×task matrix (success rate, median tokens/turns/cost)
  plus the three hypothesis comparisons.

## Out of scope

- Skill-generated variants (a follow-up could compare hand-authored vs bootstrapping-docs
  output).
- Multi-repo generalization; this is one fixture, results are directional.
- Statistical significance claims beyond per-cell variance at n=3.
