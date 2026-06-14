# Documentation Skills Suite — Handoff

**Last updated:** 2026-06-14
**HEAD at handoff:** `a8fb6d3`
**Repo:** `/Users/averyjones/Repos/skills` (git, branch `main`)

## What this project is

Building a suite of 4 documentation skills with the `superpowers:writing-skills` TDD
methodology (RED → GREEN → REFACTOR with subagents). Full design and rationale:
`docs/plans/2026-06-09-documentation-skills-suite-design.md` (read this first to resume).

Lifecycle the suite covers: **bootstrap → write → detect drift → auto-sync.**

## Status

| # | Skill | State | In repo | Deployed to `~/.claude/skills` |
|---|-------|-------|---------|-------------------------------|
| 1 | writing-docs | ✅ done (GREEN+REFACTOR) | `writing-docs/` | yes |
| 2 | bootstrapping-docs | ✅ done (GREEN+REFACTOR) | `bootstrapping-docs/` | yes |
| 3 | detecting-doc-drift | ✅ done (GREEN+REFACTOR) | `detecting-doc-drift/` | yes |
| 4 | doc-sync-automation | ⬜ not started — NEXT | — | — |

Build order is sequential: 3 needs 1+2 working (it rewrites via writing-docs standards);
4 needs 3 working (it wires 3 into cron/PR triggers).

### Skill 3 outcome (important — reshaped the skill)

RED did **not** fail on recall: 12 baseline agents across full-audit + diff-scoped modes and
2 model tiers all detected planted drift well (Opus perfectly with evidence; Haiku caught all
behavioral drift). Capable agents are naturally strong *verifiers* — unlike the *generation*
failures skills 1–2 targeted. Per Avery's steer ("the point is to declare the shape of this;
it will be invoked programmatically and trigger updates"), the real, universal RED was on a
different axis: **all 12 agents emitted free-form prose, not a machine-actionable result** an
automation could parse to trigger updates. So skill 3 is a **procedural/contract skill**: it
declares the deterministic extract→verify(tiered)→classify→**emit structured records** shape
(fixed `kind`/`verdict` enums, evidence mandatory, two modes). GREEN+REFACTOR were run on
**Haiku** (the realistic automation runner): closed loopholes = prose output, skipped
UNVERIFIABLE, invented `kind`s, and anchor/line-number over-flagging. Full record:
`tests/baselines/drift-red/{RED-findings,GREEN-results}.md`.

**This sets up skill 4 (doc-sync-automation):** it consumes skill 3's structured output —
diff-scoped mode is "what automation calls" — and adds the wiring/guardrails (triggers,
blast-radius cap, idempotency, never-delete, evidence-in-PR). The drift *contract* now lives
in skill 3; skill 4 is genuinely thin wiring on top, as the design intended.

## How to resume (next session)

1. Read `docs/plans/2026-06-09-documentation-skills-suite-design.md` — especially the
   `detecting-doc-drift` section (tiered verification engine, two modes) and the
   `writing-docs strategy` section (verifiability spine, two claim classes).
2. Invoke `superpowers:writing-skills`; create TodoWrite items for its checklist.
3. Build `detecting-doc-drift` via RED → GREEN → REFACTOR (see "Next skill" below).

## Next skill: detecting-doc-drift

**What it is** (from the design): docs make verifiable claims; drift = a claim the repo no
longer backs. Engine = extract claims → verify (tiered) → classify VERIFIED/STALE/
UNVERIFIABLE → fix or report. Two modes: full audit (manual sweep) and diff-scoped (what
automation calls). Three verification tiers (static grep → safe commands → deep
read/execute) with an escalation rule so cost concentrates where drift is likely.

**RED setup is easy here — reuse the existing fixtures.** Both fixtures are runnable and
already have correct baseline docs to mutate:
- `tests/fixtures/sample-repo/` (bundlewatch CLI) + answer key `tests/fixtures/ANSWER-KEY.md`
- `tests/fixtures/taskflow/` (3-component workspace) + `tests/fixtures/taskflow-ANSWER-KEY.md`
- Known-good docs to plant drift into: `tests/baselines/bootstrap-green/agent1/` and
  `agent2/` (accurate CLAUDE.md/AGENTS.md/README for taskflow).

**Suggested RED:** take a known-good doc, plant N stale claims (rename a command, change a
flag, alter an exit code, break a `file:line` anchor, change a documented number), then ask
baseline agents (no skill) "are these docs accurate?" Measure: planted-drift recall +
false-VERIFIED rate (claims passed without evidence). Predicted failures to confirm:
evidence-free "looks consistent" passes; missing drift that needs running code; no tiering
(either over-verifies everything or under-verifies).

## Key learnings (carry forward — these shaped skills 1 and 2)

- **Capable agents (Opus) get the FACTS right on small repos.** They read package.json/
  Makefile and get commands, flags, and gotchas correct without a skill. Each skill's value
  is therefore the *discipline agents lack naturally*, not fact-finding. Write skills to the
  OBSERVED baseline failures, not the predicted ones.
- **writing-docs** observed failures: fabricated "illustrative" example output (invented
  numbers); rationale stated as timeless prose with no anchor; aspirational install steps;
  inferable-content bloat. Spine = verifiability; "every example/output is a claim, run-or-omit".
- **bootstrapping-docs** observed failure: completeness-chasing (full API refs, helper-sig
  catalogs, trees) with no scope/stop signal — even though all gotchas were found. Skill =
  scope discipline: minimal high-leverage set, agent-file-first, STOP list, deferred note.
- **Fixtures must be big enough to make the failure show.** sample-repo (tiny) was fine for
  writing-docs but couldn't surface completeness-chasing; taskflow (multi-component) was
  built for that. detecting-doc-drift likely needs enough claim variety to exercise all 3
  tiers — both fixtures together should suffice.
- **GREEN/REFACTOR pattern that worked:** re-run the exact RED scenario with the skill, then
  one pressure test pushing toward the core failure. Both skills hit the "bulletproof
  signature" (agent refuses under pressure, cites the skill, names the temptation).
- **Deploy step:** copy skill dir to `~/.claude/skills/<name>/` so it loads in new sessions.

## Repo layout

```
docs/plans/
  2026-06-09-documentation-skills-suite-design.md   # full design + writing-docs strategy
  HANDOFF.md                                         # this file
writing-docs/            SKILL.md + readme.md, runbooks.md, agent-context.md
bootstrapping-docs/      SKILL.md
tests/fixtures/
  sample-repo/           bundlewatch CLI fixture (runnable)
  ANSWER-KEY.md          grading key for sample-repo
  taskflow/              3-component workspace fixture (runnable; run `make setup` first)
  taskflow-ANSWER-KEY.md grading key for taskflow
tests/baselines/         RED/GREEN test records + findings for skills 1 and 2
```

## Conventions used in this project

- One skill at a time; fully test + deploy + commit before starting the next (writing-skills
  Iron Law: no skill without a failing test first; no untested edits).
- Each skill: build/extend fixture → RED baselines (commit) → write skill + GREEN (verify)
  → REFACTOR pressure test → deploy + commit. Test records live under `tests/baselines/`.
- Fixtures are committed runnable; `.taskflow-state.json` and `node_modules/` are gitignored
  (run `make setup` in taskflow after checkout to relink workspaces).
- Commits co-authored; design/skills committed as they pass.

## Not yet decided (deferred to implementation)

- detecting-doc-drift: exact claim-extraction format; how tiers are surfaced to the user.
- doc-sync-automation: blast-radius cap N; where the nightly cron runs (cloud routine vs
  GitHub Action); per-repo trigger config. See design doc "Open items".
