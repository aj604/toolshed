# Documentation Skills Suite — Handoff

**Last updated:** 2026-07-03
**HEAD at handoff:** `8b9700a` + review fixes + bloat/distillation suite merge (see `git log`)
**Repo:** `toolshed` (git)

## What this project is

Built a suite of documentation skills with the `superpowers:writing-skills` TDD
methodology (RED → GREEN → REFACTOR with subagents). Full design and rationale:
`docs/plans/2026-06-09-documentation-skills-suite-design.md` (read this first to resume).

Lifecycle the suite covers: **bootstrap → write → grow → detect → fix.**

## Status

| # | Skill | State | In repo (under `plugins/doc-lifecycle/skills/`) | Deployed to `~/.claude/skills` |
|---|-------|-------|---------|-------------------------------|
| 1 | writing-docs | ✅ done (GREEN+REFACTOR) | `writing-docs/` | yes |
| 2 | bootstrapping-docs | ✅ done (GREEN+REFACTOR) | `bootstrapping-docs/` | yes |
| 3 | detecting-doc-drift | ✅ done (GREEN+REFACTOR) | `detecting-doc-drift/` | yes |
| 4 | fixing-doc-drift (the human-invoked fix step) | ✅ done (GREEN+REFACTOR) | `fixing-doc-drift/` | yes |
| 5 | auto-trigger layer (cron/PR) | ✅ done | `scheduling-doc-sync/` | yes |
| 6 | growing-docs (demand-driven growth) | ✅ done (GREEN; REFACTOR no-op + review fixes) | `growing-docs/` | no (not yet re-deployed) |
| 7 | detecting-doc-bloat | ✅ done (GREEN; tier boundary documented) | `detecting-doc-bloat/` | no |
| 8 | fixing-doc-bloat | ✅ done (GREEN, independently graded) | `fixing-doc-bloat/` | no |
| 9 | doc-distiller (agent, dispatched by fixing-doc-bloat) | ✅ done (GREEN, independently graded) | `agents/doc-distiller.md` | no |

### Skill 6 outcome (2026-07-03)

Added after Avery's steer that the suite was too aggressive about not creating docs, with
no path back from bootstrapping's permanent deferral. Design:
`docs/plans/2026-07-02-growing-docs-design.md`. RED (6 agents, 3 scenarios ×2) showed the
predicted "won't document" failure did NOT materialize — capable agents document well when
a false claim gives them a drift path; what actually failed: no pure-gap path (drift only
audits existing claims), demand signals never named, bootstrap's deferred note chat-only
with no owner, and the narrative carve-out a dead-end resolved by per-agent improvisation
(0/2 staleness anchors). GREEN 6/6; records `tests/baselines/growing-red|green/`.
Companion edits: bootstrapping-docs now exits by writing `docs/doc-scope.md` (format
single-owned by growing-docs) and handing growth over; writing-docs Rule 5 gained its
positive twin and the carve-out now routes to growing-docs; repo-shape.md Rule 7 updated
(continuity review caught it still prescribing the old deferred-note ending).

Skill 6 follow-ups (from code review, 2026-07-03):
- **Natural-triggering check after re-deploy** — GREEN agents were pointed at the SKILL.md
  files (plugin cache served pre-edit versions), so description-based routing was never
  exercised; run one demand-signal prompt against the installed plugin.
- **Nightly promotion-signal flagging** — design's out-of-scope note: the doc-sync nightly
  could flag `docs/doc-scope.md` items whose promote-when signal has fired. Narrative-doc
  `> As of` anchors are a hook for this; today's drift skills don't audit narrative docs.

Build order is sequential: 3 needs 1+2 working (it rewrites via writing-docs standards);
4 needs 3 working (it consumes 3's structured drift report and applies the fixes). The
cron/PR trigger wiring is row 5: `scheduling-doc-sync`. Rows 7–9 are a separate pair
(bloat/distillation, the value axis) built after row 5; they share `fixing-doc-drift`'s
apply-discipline spine (see the "spine extraction" update below) but not its build
dependency chain.

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

**This sets up skill 4** (then planned as `doc-sync-automation`; shipped as `fixing-doc-drift`
plus the auto-trigger layer, deferred until 2026-07-02 — see the updates below): it consumes skill 3's
structured output — diff-scoped mode is "what automation calls" — and adds the wiring/guardrails (triggers,
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
  fixed in `CLAUDE.md`, `README.md`, `bootstrapping-docs/SKILL.md`, this design doc.
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
  SKILL.md, `README.md`, `marketplace.json` tagline, and the design doc.
- **Deployed:** `~/.claude/skills/fixing-doc-drift/`.

## Update 2026-07-02 — handoff reconciled to shipped state

Resume notes, lifecycle line, dependency notes, and the repo-layout tree below were brought in
line with what actually shipped: all four skills + the `llm-doc-writer` agent done, auto-trigger
layer deferred (shipped later the same day — see "Row 5 shipped" above).

## How to resume (next session)

All five skills plus the `llm-doc-writer` agent are done (GREEN+REFACTOR), deployed, and ship
in `plugins/doc-lifecycle/`. There is no skill left to build.

## Row 5 shipped: auto-trigger layer (`scheduling-doc-sync`, 2026-07-02)

Built as an installer skill + shipped wiring — nightly GitHub Action calling
`detecting-doc-drift` in diff-scoped mode, gating through `sync-gate.py`, handing the report
to `fixing-doc-drift`, opening an evidence PR (blast-radius cap escalates to an issue;
marker-based idempotency). Built test-first after all (RED axis existed: hand-rolled wiring);
records in `tests/baselines/doc-sync-setup-red/`, incl. live E2E. Design:
`2026-07-02-doc-sync-automation-design.md`. PR #10 (2026-07-03) moved the detect/fix steps onto
`anthropics/claude-code-action@v1` and extracted run-surface rendering to a shipped
`render-report.py`; targeted re-GREEN of the affected install/upgrade scenario:
`tests/baselines/doc-sync-action-regreen/`.

## Rows 7–9: bloat/distillation suite (2026-07-03)

Second pair on the drift pair's shape, covering the **value axis** (drift covers
accuracy): `detecting-doc-bloat` (contract skill, read-only, emits `CUT` /
`CONDENSE` / `EXTRACT-AND-MOVE` / `RETIRE-DOC` / `MERGE-DOC` / `DISTILL` records)
and `fixing-doc-bloat` (applies a human-approved record-ID subset; dispatches the
new `doc-distiller` agent for `DISTILL` records). Design:
`docs/plans/2026-07-03-doc-bloat-and-distillation-design.md`; plan:
`docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md`. Test records:
`tests/baselines/bloat-red/` (detecting) and `tests/baselines/bloat-fixing-red/`
(fixing + distiller). Not yet deployed to `~/.claude` (see status table).

**Spine extraction + re-GREEN of `fixing-doc-drift`:** the apply-only rules common
to both fix skills (authorized-records-only, no "while I'm here", evidence
travels with the change, etc.) were extracted into
`plugins/doc-lifecycle/references/apply-discipline.md`, the single owner both
`fixing-doc-drift` and `fixing-doc-bloat` cite instead of each restating them.
`fixing-doc-drift`'s SKILL.md was edited to cite the spine; it was targeted
re-GREENed afterward (`tests/baselines/fixing-drift-red/REGREEN-after-spine-extraction.md`)
per the re-GREEN convention (behavior-affecting edits to a shipped GREEN skill
get a targeted re-verify note in that skill's baseline dir).

**Tier boundary (detecting-doc-bloat, full-audit completeness):** four Haiku
runs against the bloat fixture each missed exactly one of six planted findings,
rotating which one; a Sonnet run on the identical fixture and skill text hit
6/6. Recorded as a capacity limit, not a teaching gap:
`tests/baselines/bloat-red/GREEN-results.md` ("Tier boundary (measured,
final)"). Operational consequence for future scheduling wiring: a full-audit
invocation at automation tier should run on Sonnet (or run Haiku repeatedly and
union the records); Haiku is adequate for diff-scoped/single-doc checks.

**Audience-split precision guard (post-GREEN, user steer):** `detecting-doc-bloat`
gained a guard against flagging CLAUDE.md/AGENTS.md lines as redundant merely
because README states the same fact — cross-audience duplication (human doc vs.
agent doc) is deliberate placement, not bloat; dedup verdicts require
same-audience overlap. Added after GREEN shipped, then targeted-re-verified
(6/6, no regression) per the re-GREEN convention:
`tests/baselines/bloat-red/GREEN-results.md` ("Post-GREEN edit").

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
  built for that. detecting-doc-drift reused both (see "Skill 3 outcome" above).
- **GREEN/REFACTOR pattern that worked:** re-run the exact RED scenario with the skill, then
  one pressure test pushing toward the core failure. Both skills hit the "bulletproof
  signature" (agent refuses under pressure, cites the skill, names the temptation).
- **Deploy step:** copy skill dir to `~/.claude/skills/<name>/` so it loads in new sessions.

## Repo layout

```
.claude-plugin/
  marketplace.json       # marketplace manifest (must stay at repo root)
plugins/doc-lifecycle/
  .claude-plugin/plugin.json
  skills/
    writing-docs/        SKILL.md + readme.md, runbooks.md, agent-context.md
    bootstrapping-docs/  SKILL.md + repo-shape.md
    detecting-doc-drift/ SKILL.md + output-contract.md, scripts/validate-drift-output.py
    fixing-doc-drift/    SKILL.md
  agents/
    llm-doc-writer.md
docs/plans/
  2026-06-09-documentation-skills-suite-design.md   # full design + writing-docs strategy
  2026-06-20-reference-doc-containment-design.md    # the docs/reference/ shape
  HANDOFF.md                                         # this file
tests/
  fixtures/
    sample-repo/           bundlewatch CLI fixture (runnable)
    ANSWER-KEY.md          grading key for sample-repo
    taskflow/              3-component workspace fixture (runnable; run `make setup` first)
    taskflow-ANSWER-KEY.md grading key for taskflow
  baselines/             RED/GREEN test records for all five skills + the llm-doc-writer agent
  scripts/               validate-drift-output_test.py (unit tests for the helper script)
```

## Conventions used in this project

- One skill at a time; fully test + deploy + commit before starting the next (writing-skills
  Iron Law: no skill without a failing test first; no untested edits).
- Each skill: build/extend fixture → RED baselines (commit) → write skill + GREEN (verify)
  → REFACTOR pressure test → deploy + commit. Test records live under `tests/baselines/`.
- Fixtures are committed runnable; `.taskflow-state.json` and `node_modules/` are gitignored
  (run `make setup` — plain `npm install` — in taskflow after checkout).
- Commits co-authored; design/skills committed as they pass.

## Not yet decided (deferred to the auto-trigger layer)

**HEAD at handoff:** `db561b3`
**Repo:** `toolshed` (git)

## What this project is

Built a suite of 5 documentation skills with the `superpowers:writing-skills` TDD
