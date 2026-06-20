# GREEN + REFACTOR — llm-doc-writer agent (hybrid)

**Date:** 2026-06-20
**Axis under test (from RED reframe):** fabrication / laundering unverified specifics — tier-independent.
**Tier:** all runs on **Sonnet** (the agent's declared model), so results are comparable to the Sonnet RED failure.
Runs used the rewritten agent body as explicit instructions (registry copy is cached at the old version).

## GREEN

| Run | Mode | Output | Verdict |
|-----|------|--------|---------|
| green-verify | doc + repo | `agent-green-verify.md` | PASS (one residual) |
| green-densify | raw doc, no repo | `agent-green-densify.md` | PASS |

- **Densify-only:** kept source claims at source confidence, marked the "under 50ms" benchmark `UNVERIFIED`,
  invented nothing, no token theater, no `-revised`, no date frontmatter. Did NOT amplify with a fabricated comment
  (the exact Sonnet-RED failure: inventing `# node --test test/` for a non-existent `npm test`).
- **Verify:** caught and anchored every planted error; corrected `npm test → npm run check` (`package.json:14`); got
  the real correctness rationale; the `measure`/`run` "exported API" claim is REAL (`bin/cli.js:37,42`) and correctly
  anchored with right arity — not the fabricated API of the RED.
- **Residual (REFACTOR target):** green-verify invented example-output numbers (`1.2kb`, `actual:1234`) from the
  format instead of running the tool — the `writing-docs` "fabricated illustrative output" failure.

## Decisive comparison (same Sonnet tier)

- RED Sonnet (no rule): laundered `npm test`, fabricated API + token metric + `updated:` date → **FAIL**.
- GREEN Sonnet (with rule): no laundering, corrected with anchor, real API, no theater/date → **PASS**.

The variable that changed is the rule, not the model. This answers the fairness objection: the agent is graded on a
writable discipline, not on out-researching a stronger model.

## REFACTOR — closed the example-output loophole

Added to the agent: "Example output is a claim too — captured from a real run (`command → output`) or omitted;
placeholder numbers are fabricated output even when the format is anchored." Plus a verify-mode nudge to run the entry
point (surfaces gotchas; paste real output).

Re-test `agent-refactor-verify.md` (Sonnet, 18 tool calls — it ran the CLI):
- Example output now REAL: `OK dist/bundle.js 0.1kb / 5.0kb`, `{"actual":145,...}` captured from an actual run.
- No invented numbers anywhere; every claim anchored; no theater/orphan/date.
- Correctly did NOT assert the build-before-run gotcha: the fixture ships a committed `dist/`, so the CLI ran clean for
  the agent and an unobserved ENOENT would violate run-or-omit. (Gotcha is checkout-state/tier dependent — a bonus, not
  the pass line, per the RED reframe.)

**Verdict: GREEN+REFACTOR pass on the fair axis at the agent's own tier.** Agent is bulletproof against laundering and
fabrication; example-output channel closed.

## E2E — dispatch chain (closes the gap flagged at GREEN)

Tested the real chain with deployed components, no injected instructions:
1. Orchestrator invoked the deployed `writing-for-llms` skill → it returned the dispatch contract (what to pass).
2. Orchestrator dispatched `llm-doc-writer` **by type** with source + repo + output path (per the skill).
3. Agent loaded its **own** method from the registry — proving the deployed rewrite is live, not cached-old.

Result (`agent-e2e.md`, 14 tool calls): ran `node bin/cli.js --help` (→ exit 2) and `node --test test/` (2 pass);
anchored every claim to `file:line`; corrected all planted errors; real exported API with correct arity; example
output captured from real runs (`0.1kb`, `actual:145`); no token theater; wrote to the instructed path (no new
`-revised` orphan). Grades clean against `tests/fixtures/ANSWER-KEY.md`.

**Verdict: dispatch behavior PASS end-to-end.** The earlier "registry may be cached-old" caveat was unfounded — the
agent resolves fresh; the by-type dispatch ran the new method.

## Artifacts
- RED: `agent1-baseline.md` (Opus), `agent2-baseline.md` (Sonnet), `SOURCE-revised.md` (old agent).
- GREEN: `agent-green-verify.md`, `agent-green-densify.md`. REFACTOR: `agent-refactor-verify.md`.
- Input: `SOURCE.md`. Truth: `tests/fixtures/ANSWER-KEY.md`.
