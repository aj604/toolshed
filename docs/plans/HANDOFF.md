# Documentation Skills Suite — Handoff

**Last updated:** 2026-07-09
**HEAD at handoff:** doc-bloat distill lane fanned out (plan → matrix → deterministic merge — see `git log`)
**Repo:** `toolshed` (git)

## Latest milestone (2026-07-09): distill-lane fan-out (apply-side scale)

The career-compass bootstrap run (28912881170) proved the 07-07 hardening: 35 sweep chunks in
~9 minutes — and exposed the next wall: the distill lane's single uncapped invocation took 250
minutes applying 56 DISTILL records serially. Rebuilt the lane per
`docs/plans/2026-07-09-bloat-distill-lane-fanout-design.md` (durable decisions:
`docs/decisions.md` 2026-07-09 entry): `plan-distill.py` groups the lane's records
(artifact-directory affinity, inline group for mechanical verdicts), a matrix job per group
applies one-commit-per-record with no turn cap (owner call; job timeout is the kill-switch),
and a deterministic merge job lands the patch series (decisions.md conflicts union-resolved,
anything else dropped loudly to the PR's not-landed banner; convergence is re-detection, not
patch resume). Skill-text RED/GREEN: `tests/baselines/distill-fanout-red/` /
`distill-fanout-green/`. Plugin bumped to 0.10.0.
**Pending follow-up (post-release):** career-compass picks the change up via its weekly
upgrade lane — which will take the **blocked-workflows manual-apply path** (this release
regenerates `doc-bloat.yml` and `doc-sync-upgrade.yml`, and the Actions token can't push
`.github/workflows/`; the run attaches the patch artifact) — or by re-running
scheduling-doc-sync locally. Success bar = a bootstrap-scale distill lane in minutes with
per-record gaps bannered, never a multi-hour serial job.

## Prior milestone (2026-07-06): detecting-doc-bloat rearchitecture

Rebuilt detecting-doc-bloat per
`docs/plans/2026-07-06-detecting-doc-bloat-rearchitecture-design.md` (plan:
`...-rearchitecture-plan.md`; durable decisions: `docs/decisions.md` 2026-07-06 entry).
Full writing-skills TDD as a new skill: RED `tests/baselines/bloat-rearch-red/`
(all five scenarios FAIL — the v1 text taught detect-time payload authoring and
inline mega-sweeps; runners recovered only via validator archaeology), GREEN
`tests/baselines/bloat-rearch-green/`. Contract is now v2 (`"schema": 2`, POLICY
verdict, `files` provenance, no payloads — the doc-distiller authors residue
post-approval). `list-docs.py` retired, absorbed by `plan-chunks.py`.
**Pending follow-up (post-release):** re-install scheduling-doc-sync on
career-compass (`claude plugin update doc-lifecycle@toolshed`, re-run the
scheduling skill to refresh `.github/doc-sync/` + workflows), then a
`workflow_dispatch` doc-bloat run. Success bar (design §Testing): valid v2
report; no permission-denial storm; minutes, not tens of minutes; the
superpowers swarm collapsed to one POLICY record.

## What this project is

Built a suite of documentation skills with the `superpowers:writing-skills` TDD
methodology (RED → GREEN → REFACTOR with subagents). Full design and rationale:
`docs/decisions.md` (the 2026-06-09 entry has the durable decisions; the design doc itself was retired).

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
`docs/decisions.md` (2026-07-02 growing-docs entry). RED (6 agents, 3 scenarios ×2) showed the
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
non-skill wiring (later shipped as row 5 in the table — see "Row 5 shipped" below).

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
layer deferred (shipped later the same day — see "Row 5 shipped" below).

## How to resume (next session)

All eight skills plus the `llm-doc-writer` and `doc-distiller` agents are built and GREEN
(per-row state in the status table) and ship in `plugins/doc-lifecycle/`. With the
bloat/distillation suite (rows 7–9) landed, no designed skill is left to build; open items
are the "Skill 6 follow-ups" above and the not-yet-deployed rows in the status table.

## Row 5 shipped: auto-trigger layer (`scheduling-doc-sync`, 2026-07-02)

Shipped as installer skill + Actions wiring (decisions + still-binding constraints: `docs/decisions.md` 2026-07-02 doc-sync entries); PR #10 (2026-07-03) moved detect/fix onto `anthropics/claude-code-action@v1` and extracted rendering to `render-report.py`; records: `tests/baselines/doc-sync-setup-red/` (incl. live E2E), `tests/baselines/doc-sync-action-regreen/`.

## Rows 7–9: bloat/distillation suite (2026-07-03)

Bloat/distillation pair + `doc-distiller`, on the drift pair's shape (decisions + still-binding constraints: `docs/decisions.md` 2026-07-03 doc-bloat entries); records: `tests/baselines/bloat-red/`, `tests/baselines/bloat-fixing-red/`; not yet deployed to `~/.claude` (see status table).

**Spine extraction:** apply-only rules single-owned at `plugins/doc-lifecycle/references/apply-discipline.md`, cited by both fix skills (`docs/decisions.md` 2026-07-03 design entry); `fixing-doc-drift` targeted re-GREEN per the re-GREEN convention (behavior-affecting edits to a shipped GREEN skill get a targeted re-verify note in its baseline dir): `tests/baselines/fixing-drift-red/REGREEN-after-spine-extraction.md`.

**Tier boundary (detecting-doc-bloat, full-audit completeness):** four Haiku
runs against the bloat fixture each missed exactly one of six planted findings,
rotating which one; a Sonnet run on the identical fixture and skill text hit
6/6. Recorded as a capacity limit, not a teaching gap:
`tests/baselines/bloat-red/GREEN-results.md` ("Tier boundary (measured,
final)"). Operational consequence for future scheduling wiring: a full-audit
invocation at automation tier should run on Sonnet (or run Haiku repeatedly and
union the records); Haiku is adequate for diff-scoped/single-doc checks.

**Audience-split precision guard (post-GREEN, user steer):** dedup verdicts require same-audience overlap — README-vs-CLAUDE.md duplication is deliberate placement (`detecting-doc-bloat/SKILL.md`); targeted re-verified 6/6: `tests/baselines/bloat-red/GREEN-results.md` ("Post-GREEN edit").

**Passage-span contract (post-GREEN, review fast-follow):** passage extent is normative — a passage verdict's `evidence` opens `file:start-end` with start = `location` (`detecting-doc-bloat/SKILL.md`; `validate-bloat-output.py` `check_evidence_span`); both skills targeted re-verified: `tests/baselines/bloat-red/GREEN-results.md`, `tests/baselines/bloat-fixing-red/GREEN-results.md` ("Post-GREEN edit — passage-span…").

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

Repo layout: see CLAUDE.md's Layout section for top-level shape; run `ls -R plugins/doc-lifecycle/ tests/` for current file-level detail (this hand-maintained tree drifts easily — already stale for `list-docs.py`, `doc-bloat.yml`, and three `docs/plans/` files).

## Conventions used in this project

- One skill at a time; fully test + deploy + commit before starting the next (writing-skills
  Iron Law: no skill without a failing test first; no untested edits).
- Each skill: build/extend fixture → RED baselines (commit) → write skill + GREEN (verify)
  → REFACTOR pressure test → deploy + commit. Test records live under `tests/baselines/`.
- Fixtures are committed runnable; `.taskflow-state.json` and `node_modules/` are gitignored —
  setup/migrate gotchas are owned by CLAUDE.md's Gotchas section, not restated here.
- Commits co-authored; design/skills committed as they pass.
