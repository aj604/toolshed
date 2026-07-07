# Decisions

## 2026-07-07 — doc-sync self-upgrade (pinned wiring + upgrade PR)
- Decided: installs are pinned, not floating. Every `claude-code-action` step pins
  `plugin_marketplaces` to the install-time release tag (`…/toolshed.git#v<version>`), so the
  skills a run executes are frozen at the same version as the vendored wiring — closing the
  drift where the skills floated at `main` while the committed wiring stayed frozen (the
  2026-07-07 RED doc-bloat runs). Pin lives ONLY in the `#v<version>` ref; the `plugins:`
  selector stays bare (`claude-code-action` has no `@version` selector — both RED baseline
  agents guessed `doc-lifecycle@toolshed@<v>` and both were wrong). A third installed workflow
  `doc-sync-upgrade.yml` is the only thing that advances the pin: weekly it compares
  `.github/doc-sync/installed-version` (the bare-semver lockfile) against the plugin's latest
  release via the tested `upgrade-gate.py` (`upgrade|current|ahead`, exit 2 on malformed), and
  on a newer release re-runs `scheduling-doc-sync` headlessly in upgrade mode to regenerate the
  wiring and open a `doc-sync/upgrade` review PR. Detection == regeneration: `git diff` after
  the re-copy is the divergence signal, no separate compare-shipped-vs-vendored logic.
- Still binds: upgrade mode preserves consumer state (marker, `audit-scope.json`) and re-injects
  the install-time knobs (cron/cap/bloat-cron/upgrade-cron) rather than resetting to template
  defaults; the model regenerates files but the workflow owns git/PR (same split as the drift
  lane); run-surface strings live in `render-report.py` (`upgrade-summary`, `upgrade-pr-body`),
  gate decisions in `upgrade-gate.py` — never inline YAML. `installed-version` advances only on a
  merged upgrade PR, like the marker. Built test-first (`tests/baselines/upgrade-red/`).
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/ (SKILL.md, doc-sync.yml, doc-bloat.yml,
  doc-sync-upgrade.yml, scripts/upgrade-gate.py, scripts/render-report.py),
  tests/scripts/upgrade-gate_test.py, tests/scripts/render-report_test.py; dogfood under
  .github/ (workflows/doc-sync-upgrade.yml, the pinned doc-sync.yml/doc-bloat.yml,
  doc-sync/installed-version, doc-sync/upgrade-gate.py). Fuller design:
  docs/superpowers/specs/2026-07-07-doc-sync-self-upgrade-design.md.

## 2026-07-06 — detecting-doc-bloat rearchitecture (harness, chunked sweeps, contract v2)
- Decided: DISTILL payload authoring moved from detect time to post-approval distill time —
  detection emits classification + landed-code evidence only; the doc-distiller authors the
  claims/insights/decision entry after a human approves the record ID (speculative →
  approval-gated; the single biggest cost lever, per career-compass run 28833711517). Added the
  bulk `POLICY` verdict with a mandatory `files` provenance array; ephemeral-artifact
  directories are declared config (`policy_scope` in audit-scope.json), selected by filter,
  never summarized file-by-file by the model. Budgets are structural, not prose: per-chunk
  `--max-turns 15` (a flail detector), seam validation where each chunk is produced with one
  fresh re-dispatch, chunk results as checkpoint, assembly that refuses partial results by
  name; the run-level `chunking.max_chunks` ceiling defaults to off — refusing legitimate
  large runs is worse than pricing them visibly. One skill with progressive disclosure
  (thin router + references/) rather than multiple skills; subagent dispatch is the
  interactive chunk executor and the workflow matrix is the headless one — same manifest,
  same validator seam either way.
- Still binds: the report contract is v2 (`"schema": 2`, eight record fields, seven verdicts,
  no payloads) and the validator rejects v1 shapes with a regenerate error; a policy chunk's
  result is exactly one POLICY record whose files equal the manifest list; CI never passes
  `--allow-partial`; doc enumeration and chunk planning go through `plan-chunks.py` (this
  supersedes the 2026-07-03 entry's "goes through `list-docs.py`" — that helper is absorbed
  and retired), and the 2026-07-03/04 entries' two-lane split now routes `POLICY` to the
  distill lane.
- Code: plugins/doc-lifecycle/skills/detecting-doc-bloat/ (SKILL.md, references/,
  scripts/plan-chunks.py, scripts/validate-bloat-output.py),
  plugins/doc-lifecycle/agents/doc-distiller.md,
  plugins/doc-lifecycle/skills/fixing-doc-bloat/SKILL.md,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/ (doc-bloat.yml, SKILL.md,
  scripts/sync-gate.py, scripts/render-report.py)
- Source: docs/plans/2026-07-06-detecting-doc-bloat-rearchitecture-design.md (retained;
  implementation plan: docs/plans/2026-07-06-detecting-doc-bloat-rearchitecture-plan.md)

## 2026-06-09 — Documentation skills suite design
- Decided: Activity-centered suite — one skill per documentation activity, doc-type knowledge
  in per-artifact reference files — designing four skills (bootstrapping-docs, writing-docs,
  detecting-doc-drift, doc-sync-automation; its 2026-06-20 updates add `fixing-doc-drift` and
  merge writing-for-llms into `writing-docs`, dispatching `llm-doc-writer`) on a verifiability
  spine with two claim classes (verifiable / marked+anchored rationale), rather than a single
  monolithic doc-writing skill or a Diátaxis-page-per-type split; ADRs explicitly out of scope
  (YAGNI). The suite has since grown to 8 skills and two agents on the same contract (the
  2026-07-02/03 entries below).
- Still binds: every doc-lifecycle skill's job maps to exactly one documentation activity; the
  verifiability contract (verifiable claim or marked+anchored rationale claim) is shared
  across the suite, not owned by any single skill.
- Code: `plugins/doc-lifecycle/skills/`, `plugins/doc-lifecycle/agents/`
- Source: docs/plans/2026-06-09-documentation-skills-suite-design.md @ 09f4300 (removed in this commit)

## 2026-07-03 — Doc bloat and distillation plan
- Decided: Built `detecting-doc-bloat`/`fixing-doc-bloat` as a matched RED→GREEN pair per the
  writing-skills methodology, mirroring `detecting-doc-drift`/`fixing-doc-drift`'s build process.
- Still binds: RED/GREEN baselines are retained under `tests/baselines/` rather than discarded
  once the skill goes green.
- Code: `tests/baselines/bloat-red/`, `tests/baselines/bloat-fixing-red/`
- Source: docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md @ 09f4300 (removed in this commit)

## 2026-07-03 — Doc bloat and distillation design
- Decided: Added `detecting-doc-bloat`/`fixing-doc-bloat` as a second skill pair mirroring
  `detecting-doc-drift`/`fixing-doc-drift`'s shape (contract-emitting detector + human-gated
  applier), covering the value axis (drift covers accuracy). `DISTILL` retires a landed
  planning artifact by extracting its durable decisions into living docs plus one
  decision-log entry, then deleting it — chosen over keeping design docs verbatim forever or
  per-line-cutting them.
- Still binds: the apply-only discipline for fix skills has one owner
  (`plugins/doc-lifecycle/references/apply-discipline.md`); `DISTILL`'s two-status model
  (`pending-implementation` forbids payload, `ready` requires verified claims + one
  decision-log entry) is closed.
- Code: `plugins/doc-lifecycle/references/apply-discipline.md`,
  `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
- Source: docs/plans/2026-07-03-doc-bloat-and-distillation-design.md @ 09f4300 (removed in this commit)

## 2026-07-02 — Doc-sync automation plan
- Decided: Doc-sync automation was built test-first, with RED/GREEN/E2E records under
  `tests/baselines/doc-sync-setup-red/`.
- Still binds: mechanical gate failures (a malformed `drift-report.json`) fail the sync-gate job
  red rather than degrading silently — `validate-drift-output.py` exits nonzero on shape errors
  and the workflow's validate step carries no `continue-on-error`. The shipped `doc-sync.yml` has
  since moved past this plan's literal task steps (e.g. onto `anthropics/claude-code-action@v1`,
  per `docs/plans/HANDOFF.md`'s Row 5 note) — the plan's own code blocks are retired as stale
  procedure, not current truth.
- Code: `.github/workflows/doc-sync.yml`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`
- Source: docs/plans/2026-07-02-doc-sync-automation-plan.md @ 09f4300 (removed in this commit)

## 2026-07-02 — Doc-sync automation design
- Decided: Chose a GitHub Action runner over a Claude scheduled task (ties to one user's
  account) or local git/session hooks (fire only while someone works), with marker-based
  idempotency and a blast-radius cap that escalates to an issue rather than one giant PR;
  posture is fail loud, never half-apply.
- Still binds: nightly sync runs as a GitHub Action (`schedule` + `workflow_dispatch`);
  `.github/doc-sync-marker` advances only on a clean-run direct commit or a merged sync PR;
  a blast-radius cap escalates to a labeled issue instead of one giant PR.
- Code: `.github/workflows/doc-sync.yml`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`
- Source: docs/plans/2026-07-02-doc-sync-automation-design.md @ 09f4300 (removed in this commit)

## 2026-07-03/04 — Doc bloat nightly plan
- Decided: `doc-bloat.yml` built test-first (`sync-gate_test.py`, `render-report_test.py`
  extended with bloat-* cases) as a sibling to `doc-sync.yml`, sharing `sync-gate.py`/
  `render-report.py` rather than forking new scripts; already exercised for real (PR #23,
  merged 2026-07-04).
- Still binds: the weekly bloat sweep splits findings into two lanes by verdict — `prune`
  (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`, passage-level) and `distill` (`MERGE-DOC`/`RETIRE-DOC`, or
  `DISTILL` with `status: ready`, doc-level); a `DISTILL` `pending-implementation` record belongs
  to neither lane and is never opened as a PR.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`
- Source: docs/plans/2026-07-03-doc-bloat-nightly-plan.md @ 09f4300 (removed in this commit)

## 2026-07-03 — Doc bloat nightly design
- Decided: Bloat sweep output is a proposal (draft PR), never an auto-fix, because a bloat
  verdict is a judgment call, not a mechanically-checkable correction; the merge itself is the
  human approval gate — chosen over drift's detect→fix pipeline shape.
- Still binds: `doc-bloat.yml` stays a separate sibling workflow from `doc-sync.yml`, each with
  its own concurrency group, because drift's marker-based detect-fix model and bloat's
  marker-less detect-propose model would tangle if combined; bloat output is always a draft PR,
  never auto-merged or direct-committed, and a lane is skipped if its own draft PR is already
  open.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`
- Source: docs/plans/2026-07-03-doc-bloat-nightly-design.md @ 09f4300 (removed in this commit)

## 2026-07-03 — doc-sync PR body tightening plan
- Decided: PR-body/title rendering moved from inline YAML `jq` (as originally planned) into
  tested Python (`render-report.py`), the same pattern later reused for the bloat lanes.
- Still binds: any future PR-body/title change belongs in `render-report.py`, with a
  `render-report_test.py` case, never inline YAML.
- Code: `.github/doc-sync/render-report.py`, `tests/scripts/render-report_test.py`
- Source: docs/plans/2026-07-03-doc-sync-pr-body-tightening-plan.md @ 09f4300 (removed in this commit)

## 2026-07-03 — doc-sync PR body tightening design
- Decided: Tightened doc-sync PR bodies to two compact tables (Fixed/Flagged) with a
  singular/plural, flagged-count-bearing title, and tightened drift evidence to a one-line
  pointer+fact bar — both changes reduce PR review noise without changing what's checked.
- Still binds: drift evidence stays a one-line pointer+fact bar (no history, no restated
  command output, no reasoning narrative — the verdict carries the conclusion, evidence
  carries only what proves it); sync PR bodies render as two tables (Fixed/Flagged) with a
  counts-bearing singular/plural title, no raw-report `<details>` block.
- Code: `.github/doc-sync/render-report.py`, `plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`
- Source: docs/plans/2026-07-03-doc-sync-pr-body-tightening-design.md @ 09f4300 (removed in this commit)

## 2026-07-03 — Doc bloat inventory tool design
- Decided: Replaced ad-hoc find/ls doc enumeration with a tested `list-docs.py` helper
  (git-ls-files-based, config-driven via `audit-scope.json`), keeping the CI allowlist thin and
  inventory logic unit-tested (`tests/scripts/list-docs_test.py`) rather than improvised per
  invocation.
- Still binds: doc enumeration for the bloat audit goes through `list-docs.py` and
  `audit-scope.json`'s include/exclude globs, never a hand-rolled `find`/`ls` in CI YAML.
- Code: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/list-docs.py`,
  `.github/doc-sync/audit-scope.json`
- Source: docs/plans/2026-07-03-doc-bloat-inventory-tool-design.md @ 09f4300 (removed in this commit)

## 2026-06-20 — Reference-doc containment design
- Decided: `bootstrapping-docs`' `docs/reference/` containment convention marked "implemented"
  after all five concrete edits landed in `repo-shape.md`/`SKILL.md`, including demoting the
  standing "Not yet documented" section to a one-time bootstrap-exit record (`docs/doc-scope.md`,
  owned by `growing-docs`).
- Still binds: the convention (for repos that opt in) contains the whole agent doc set in one
  subtree, never scattered at `docs/` root; `architecture.md` is the sole cross-unit doc and must
  not re-describe any single unit. This repo itself opts out (see CLAUDE.md).
- Code: `plugins/doc-lifecycle/skills/bootstrapping-docs/repo-shape.md`,
  `plugins/doc-lifecycle/skills/bootstrapping-docs/SKILL.md`
- Source: docs/plans/2026-06-20-reference-doc-containment-design.md @ 09f4300 (removed in this commit)

## 2026-07-04 — Durable narrative docs + DISTILL insight extraction
- Decided: Added a third doc kind — the durable narrative doc, marked by growing-docs' first-line
  `> As of <date> (<anchors>)` anchor (the marker classifies, not the directory) and homed in
  `docs/reference/` (plain `docs/` until that tree exists, never `docs/plans/`); grew the
  `DISTILL ready` payload an optional anchored `insights` channel with a mandatory per-section
  insight walk; made the always-loaded file a router, not a repository (single owner:
  `writing-docs/agent-context.md`), with unprompted-critical as a scope test.
- Still binds: an anchored doc is never a planning artifact to distill, wherever it sits; every
  `ready` record's evidence states its insight-walk outcome (`insight sweep: none — …` when dry);
  a `ready` payload must carry at least one claim or one insight; anything landing content in
  CLAUDE.md/AGENTS.md — extraction, claim, or merge — must clear the router rule.
- Code: plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md,
  plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py,
  plugins/doc-lifecycle/agents/doc-distiller.md,
  plugins/doc-lifecycle/skills/writing-docs/agent-context.md
- Source: docs/plans/2026-07-04-durable-narrative-docs-design.md @ d695e25 (removed in this commit)

## 2026-07-02 — Growing docs (demand-driven expansion) design
- Decided: Added `growing-docs` as a distinct sibling skill rather than extending
  `bootstrapping-docs` (the two trigger contexts — 'repo has no docs' vs 'docs exist but a demand
  signal fired' — would fire for neither in one description); growth is demand-triggered via the
  second-rediscovery rule, one signal → one smallest artifact; `bootstrapping-docs` now exits by
  writing `docs/doc-scope.md`, whose format `growing-docs` single-owns.
- Still binds: growth requires a nameable demand signal (never milestones or scheduled review);
  narrative docs (walkthrough/tutorial/ADR) carry the required `> As of` first-line anchor and
  stay outside writing-docs' claim bar; bootstrapping-docs' STOP list binds growth too;
  `docs/doc-scope.md` is read on demand, never a standing section in an always-loaded file.
- Code: plugins/doc-lifecycle/skills/growing-docs/SKILL.md,
  plugins/doc-lifecycle/skills/bootstrapping-docs/SKILL.md,
  plugins/doc-lifecycle/skills/writing-docs/SKILL.md
- Source: docs/plans/2026-07-02-growing-docs-design.md @ b9e6f97 (removed in this commit)
