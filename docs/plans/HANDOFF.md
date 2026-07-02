# Documentation Skills Suite — Handoff

**Last updated:** 2026-06-14
**HEAD at handoff:** `a8fb6d3`
**Repo:** `toolshed` (git, branch `main`)

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
| 4 | fixing-doc-drift (the human-invoked fix step) | ✅ done (GREEN+REFACTOR) | `fixing-doc-drift/` | yes |
| 5 | auto-trigger layer (cron/PR) | ✅ done | `scheduling-doc-sync/` | — |

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

## Update 2026-06-20 — llm-doc-writer agent + writing-for-llms refactor

Reshaped the LLM-doc capability into **thin skill + fat agent** (Avery's architecture: method lives in the
agent MD; the skill is a thin dispatch/entry point). Scoped as a one-off — the other 3 skills stay agentless.

- **`llm-doc-writer` agent** rewritten from a pure densifier (trusted input, no Bash, "use provided info only",
  token-count theater, `-revised` orphans) into a **hybrid**: *maximize signal-per-token, never assert a specific
  you haven't backed.* Densify-only when given raw text; densify + verify + anchor when given a repo. Gained `Bash`.
- **`writing-for-llms` skill** slimmed to a dispatcher (triggers + what to pass + contract). Method has one home
  (the agent), so it isn't duplicated across the two context windows — net less main-context cost than the old fat skill.
- **Tested RED → GREEN → REFACTOR at Sonnet tier** (the agent's own model). RED reframe matters: grading on
  planted-error *recall* is tier-dependent and unfair (Opus wins on horsepower); the real, writable, tier-independent
  axis is **fabrication / laundering unverified specifics**. Same Sonnet model: without the rule it laundered a false
  `npm test` and fabricated an API; with the rule it didn't. Records: `tests/baselines/llm-doc-red/`.
- **Dispatch chain tested E2E:** orchestrator invoked the deployed `writing-for-llms` skill → dispatched
  `llm-doc-writer` by type → agent loaded its own method from the registry (deploy is live, not cached) → produced a
  clean, anchored, verified doc (`agent-e2e.md`). See `GREEN-results.md` "E2E".
- **Deployed:** `~/.claude/agents/llm-doc-writer.md`, `~/.claude/skills/writing-for-llms/SKILL.md` (reload to pick up).

## Update 2026-06-20 (later) — `writing-for-llms` merged into `writing-docs` (one door)

Reversed the earlier "thin skill + fat agent, one-off" split. The thin `writing-for-llms` skill
was an intermediary door; the `llm-doc-writer` **agent** (the fat part) stays. Rationale: a user
shouldn't have to pick between two doc skills — `writing-docs` is now the single door that routes
by audience (human standard vs. + density) and by job weight (inline vs. dispatch a generalist /
the `llm-doc-writer` agent). The contract is hoisted into the door you already open.

- **Built test-first** (RED → GREEN → REFACTOR). Records: `tests/baselines/writing-docs-merge-red/`.
  RED axis (tier-independent, writable): the two-door ecosystem dead-ends the agent — it grabs
  `writing-docs` (which named CLAUDE.md), "feels complete, ends the search," never reaches the
  density discipline or dispatches `llm-doc-writer`; and the deferred density bar was under-applied
  (a baseline *added* inferable facts). Output-density was the WRONG axis (capability masks it —
  same lesson as the llm-doc RED).
- **GREEN:** merged door dispatched `llm-doc-writer` and withheld the inferable facts the baseline
  added. **REFACTOR:** confirmed no over-dispatch on one-line edits ("size gates inline-vs-dispatch;
  audience only picks the executor"). GREEN-2 caveat: the fix is real only once `writing-for-llms`
  is gone from the repo AND `~/.claude/skills` — an unrecommended-but-present door still competes.
- **Changes:** `writing-docs` SKILL.md (description absorbs the LLM triggers; "One bar, every
  reader — then route" router) + `agent-context.md`; `writing-for-llms/` deleted; dangling refs
  fixed in `CLAUDE.md`, `README.md`, `bootstrapping-docs/SKILL.md`, `PITCH.md`, this design doc.
- **Deployed:** merged `~/.claude/skills/writing-docs/`; removed `~/.claude/skills/writing-for-llms/`.

## Update 2026-06-20 (later still) — `fixing-doc-drift` built (the fix step)

The "skill 4" fix step is built — but as **`fixing-doc-drift`**, a human-invoked apply step, not
the auto `doc-sync-automation`. It consumes `detecting-doc-drift`'s structured records and lands
the fixes. The `auto` (cron/PR triggers, PR packaging, idempotency) is deliberately deferred to
non-skill wiring (now "skill 5" in the table, ⬜).

- **Built test-first** (RED → GREEN → REFACTOR), records: `tests/baselines/fixing-drift-red/`.
  Reused the `drift-red` fixture; the fixer's input is the exact record set `detecting-doc-drift`
  emits (`drift-report.json`). RED axis (tier-independent, writable): **over-reach** — given a
  report, a baseline (Sonnet) *deleted* the UNVERIFIABLE line, conflating "sync to the report"
  with "apply the full writing-docs cleanup." Opus held the line by restraint → made it a written
  rule. GREEN: same Sonnet, with the skill, preserved the line and stayed scoped. REFACTOR: held
  under authority pressure ("just regenerate the whole doc").
- **The skill is thin apply-discipline:** act only on STALE fixes; never delete (flag UNVERIFIABLE);
  no "while I'm here"; land the drafted fix as-is and dispatch `writing-docs` only for structural
  rewrites; blast-radius stop; evidence travels with the change.
- **Lifecycle now complete:** bootstrap → write → detect → fix. Refs wired in `detecting-doc-drift`
  SKILL.md, `README.md`, `PITCH.md`, `marketplace.json` tagline, and the design doc.
- **Deployed:** `~/.claude/skills/fixing-doc-drift/`.

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

## Update 2026-07-02 — auto-trigger layer shipped (`scheduling-doc-sync`)

Item 5 built as a skill + shipped wiring, per `2026-07-02-doc-sync-automation-design.md`:
nightly GitHub Action template (`doc-sync.yml`, orchestration only) + unit-tested gate
(`sync-gate.py`, decision matrix in `tests/scripts/sync-gate_test.py`) + installer skill
(preflight, knob substitution, marker seeding — never resets an existing marker). Built
test-first: RED = baseline agent hand-rolls the wiring (records in
`tests/baselines/doc-sync-setup-red/`); REFACTOR pressure = holds PR-only against
"commit straight to main". Lifecycle: bootstrap → write → detect → fix → **schedule**.
