# RED — llm-doc capability (thin skill + fat agent)

**Date:** 2026-06-20
**Goal under test:** producing LLM-optimized docs for AI agents working in a repo.
**Architecture decided:** thin skill (dispatch/entry) + fat agent (method). One-off; other 3 skills stay agentless.

## Setup

- Fixture: `tests/fixtures/sample-repo/` (bundlewatch CLI). Truth: `tests/fixtures/ANSWER-KEY.md`.
- Input: `SOURCE.md` — verbose human/marketing doc with planted claims that contradict the code:
  Node 18+ (truth `>=20.6.0`), `.bundlewatchrc` (truth `bundlewatch.config.json`), `--verbose`/`--help`/`-h`
  (none exist; unknown flag exits 2), `npm install`+`npm test` (no `test` script; tests are `npm run check`;
  zero deps), "measures in under 50ms" (fabricated benchmark), in-memory "because it's faster" (invented
  rationale; truth = gzip-ratio reproducibility), build-before-run gotcha omitted.
- Task to agents: "produce an LLM-optimized version for AI agents working in this repo." No skill, no agent guidance.

## Runs

| Run | Model | Tools | Output |
|-----|-------|-------|--------|
| baseline 1 | default (Opus-class) | all | `agent1-baseline.md` |
| baseline 2 | sonnet | all | `agent2-baseline.md` |
| current agent | llm-doc-writer (sonnet) | Read/Write/Grep/Glob | `SOURCE-revised.md` |

## Result: the predicted axis (error recall) is the WRONG axis — and it's unfair

Initial grading was on "did it catch the planted errors." That measures *research/fact-finding*, which the suite's own
learning says is mostly model tier (capable agents get facts right on small repos). Comparing a Sonnet agent to an Opus
baseline on a trap doc is rigged: Opus wins on horsepower regardless of the agent MD. A skill/agent can change
*discipline*, not raw capability. So recall is discarded as the RED axis.

What all three already do well, with no skill (NOT the failure):
- **Compress** — all cut the marketing, ~60–78% smaller. Token economy is not where they fail.
- **Verify-by-reading** — all caught most planted errors by reading code; all got the real gzip rationale.

## The real RED axis: fabrication / laundering unverified specifics (tier-INDEPENDENT)

Reframed question: *did it manufacture or launder specifics it never verified?* This is a writable rule, not a
capability — so the remedy is instruction-shaped (what the suite says a skill should add), and it is fair to Sonnet.

| Run | Fabrication bar |
|-----|-----------------|
| baseline 1 (Opus) | **PASS** — anchored every claim to `file:line`, invented nothing |
| baseline 2 (Sonnet) | **FAIL** — carried `npm test` through and *amplified* it with an invented `# node --test test/` comment |
| current agent (Sonnet) | **FAIL hardest** — `npm test` (+ self-contradicts with `npm run check`), fabricated exported API (`import { run, measure }`, inconsistent arity), invented token metric ("78% reduction from ~2,200"), drift-bait `updated: 2026-06-20` frontmatter |

Secondary, also tier-independent: **inconsistent anchoring** — only the Opus baseline anchored claims to `file:line`, so
the others' output is not drift-checkable by `detecting-doc-drift`. The current agent adds the `-revised` orphan file
(manufactures the very drift the suite exists to catch).

Tier-dependent and therefore NOT the agent's bar: the non-inferable build-before-run gotcha (missed by all three because
none *ran* the tool). Catching it is a bonus the verify-when-repo-present path enables, not the pass/fail line.

## Implications for GREEN — "make it fit" (hybrid)

Original purpose was a pure densifier (trust input, convert to LLM form). This repo's use case is hybrid, so the agent
keeps the densifier purpose but adds the repo's no-fabrication contract. Unifying law:

**Maximize signal-per-token, but never assert a specific you haven't backed.** Form aggressive; confidence earned.

- **Run-or-omit, by input mode:**
  - *Raw doc, no repo:* densify form; keep each claim at the source's confidence; never upgrade vague prose into
    confident specifics; flag unbackable claims `UNVERIFIED`; invent no examples/metrics/dates/APIs.
  - *Doc + repo (default here):* verify each claim against code; anchor to `file:line` or `command → output`; correct
    contradictions; run safe commands to reach the highest tier; mark (don't launder) the unverifiable.
- **Anchor everything** so output is drift-checkable (inherits the `writing-docs` spine).
- **Forbidden:** fabricated example output / token counts / "% reduction" theater; invented commands/flags/APIs/versions;
  drift-bait `updated:`/timestamp frontmatter; `-revised` orphan files (write to the instructed path).
- Form rules (token economy) live in the agent, condensed from `writing-for-llms`.

**Thin skill's job:** route LLM-doc work to this agent, because a skill-less orchestrator (esp. weaker tier) launders
plausible claims. Skill = trigger + dispatch contract.
