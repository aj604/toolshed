# Decisions

## 2026-07-07 — deterministic doc-sync upgrade (no model for a version bump)
- Follows the version-agnostic entry below. With the workflow YAML version-agnostic (Pin steps read
  `installed-version` at runtime), an upgrade carries no doc-judgment: re-copy the six vendored
  scripts, re-render the three templates with the consumer's preserved knobs, bump the lockfile. The
  headless `claude-code-action` step that did this was a model call to do `cp` + four regexes.
- Decided: replace it with a tested, deterministic `apply-upgrade.py` (scheduling-doc-sync's
  `scripts/`). `doc-sync-upgrade.yml`'s regenerate step now runs it from the pinned target checkout
  (`--plugin-root <checkout>/plugins/doc-lifecycle --repo $GITHUB_WORKSPACE --target <latest>`) — so
  the target version's own upgrade logic applies, matching the prior "run the skill at the target
  version" intent. The script writes files only; the workflow keeps owning git/PR and the
  blocked-workflows fallback (`git diff` is still the divergence signal). It is NOT vendored into
  installs — it only runs in the upgrade lane, which always has the checkout — so the vendored set
  stays six.
- Consequence: the upgrade lane makes no model call, so it needs no model auth — dropped
  `id-token: write` and the secret refs from `doc-sync-upgrade.yml`. Knob extraction that fails (a
  hand-mangled installed file) fails the run red rather than default-guessing; a missing
  `doc-sync-upgrade.yml` (a pre-self-upgrade install) is the one exception — seeds the default
  upgrade cron and warns on stderr. The skill's Upgrade mode now delegates to the script (single
  owner); a human forcing an upgrade runs the same script with `--plugin-root "$CLAUDE_PLUGIN_ROOT"`.
- Also moved the default upgrade cron `0 5 * * 1` → `0 2 * * 1`, so the weekly version-bump check is
  the first of the three scheduled runs (before the 03:00 nightly sync and the 04:00 Monday bloat
  sweep).
- Consequence (v0.9.4, this change): it rewrites `doc-sync-upgrade.yml`, so existing installs still
  on the model-based upgrade template take the 0.9.3→0.9.4 step as a one-time manual apply (the
  Actions token can't push `.github/workflows/`; blocked-workflows path). The dogfood is hand-applied
  here, so its own self-upgrade to 0.9.4 re-renders identical workflows and self-lands as an
  installed-version-only bump. Upgrades after 0.9.4 that don't touch the templates self-land.
- Guarded by `tests/scripts/apply-upgrade_test.py` (in release CI): knob preservation, placeholder-
  free render (GitHub `${{ }}` expressions untouched), six-script overwrite, marker/audit-scope
  untouched, absent-upgrade.yml default, and nonzero exit on unextractable knobs / missing sources.
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/ (SKILL.md, doc-sync-upgrade.yml,
  scripts/apply-upgrade.py), tests/scripts/apply-upgrade_test.py, .github/workflows/release.yml;
  dogfood under .github/ (workflows/doc-sync-upgrade.yml).

## 2026-07-07 — version-agnostic pins + upgrade workflow-file fallback
- Follows the local-checkout entry below. Once the marketplace pin worked, the toolshed dogfood
  upgrade got to its push and hit the next wall (run 28909022925): GitHub refuses to let the
  Actions `GITHUB_TOKEN` create/update files under `.github/workflows/` — "refusing to allow a
  GitHub App to create or update workflow … without `workflows` permission" — and that permission
  is not grantable to the default token via the `permissions:` block. The upgrade lane's whole job
  is to regenerate the workflow YAMLs, so it always tripped this.
- Decided (chosen over an elevated PAT): make the nightly workflow files **version-agnostic**. The
  `Pin plugin marketplace` steps in `doc-sync.yml`/`doc-bloat.yml` read the version from
  `.github/doc-sync/installed-version` at runtime (`VERSION=$(cat …); git clone --branch
  "v${VERSION}"`) instead of a hardcoded `v<version>`. So a routine version bump changes only the
  lockfile (+ scripts) — never a `.github/workflows/` file — and the default token pushes it
  fine. `installed-version` becomes the single source of truth for the pin (kills the per-step
  version duplication). The upgrade lane still clones the *target* (`steps.versions.latest`), since
  the lockfile holds the old version until the skill advances it.
- Fallback for the rarer case (an upgrade whose new templates change the workflow YAML itself):
  the `Open upgrade PR` step detects a changed `.github/workflows/` path, writes the diff to the
  `doc-sync-upgrade-patch` artifact, and fails loud with `git apply` instructions via
  `render-report.py upgrade-summary --status blocked-workflows`. A human applies it with a
  `workflow`-scoped credential. No new secret is required for the common path.
- Consequence: the 0.9.2→0.9.3 upgrade (this change) IS a workflow-template change, so existing
  installs (career-compass, the dogfood) take it as a one-time manual apply; version-only upgrades
  after 0.9.3 self-land.
- Guarded by the new `render-report_test.py` case for `blocked-workflows`.
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/ (SKILL.md, doc-sync.yml, doc-bloat.yml,
  doc-sync-upgrade.yml, scripts/render-report.py); dogfood under .github/ (the three workflows,
  doc-sync/render-report.py, doc-sync/installed-version → 0.9.3); tests/scripts/render-report_test.py.

## 2026-07-07 — marketplace pin moves from URL ref to local checkout
- Amends the self-upgrade entry below ("Pin lives ONLY in the `#v<version>` ref"). The moving
  `anthropics/claude-code-action@v1` tag tightened its marketplace-URL validator to
  `/^https:\/\/…+\.git$/` — the value must END in `.git` — so a `…/toolshed.git#v<version>`
  ref-pin is now rejected outright ("Invalid marketplace URL format"), before Claude runs. It
  broke every doc-sync workflow at the model step (career-compass upgrade run 28908054944; the
  same `#ref` had worked in live runs ~24h earlier, so the action's `@v1` moved under us).
- Decided: pin via a **local checkout of the release tag**, not a URL ref. Each model step is
  preceded by a `Pin plugin marketplace at v<version>` step that
  `git clone --depth 1 --branch v<version> …/toolshed.git "$RUNNER_TEMP/toolshed-marketplace"`,
  and the `claude-code-action` step points `plugin_marketplaces` at that local path (the
  validator passes local paths straight through). Same version freeze; clone under
  `$RUNNER_TEMP`, outside the work tree, so the PR steps' `git add -A` never captures it. The
  `plugins:` selector stays bare (unchanged). This is also a known-good pattern — the E2E
  install used a `git clone --branch` + local-path marketplace add before the URL-ref form
  existed (`tests/baselines/doc-sync-setup-red/E2E-results.md`).
- Consequence: installs cannot self-heal through their own upgrade workflow — its
  `doc-sync-upgrade.yml` carries the same broken pin and dies before the skill runs, and the
  last released version (`0.9.1`) still has the URL-ref templates. Recovering an existing install
  requires a one-time hand-patch of its workflows to the checkout form.
- Guarded by `tests/scripts/marketplace-pin_test.py` (in release CI): no shipped
  `plugin_marketplaces` value may be an `https://` URL not ending in `.git`.
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/ (SKILL.md, doc-sync.yml, doc-bloat.yml,
  doc-sync-upgrade.yml, scripts/render-report.py); dogfood under .github/ (the three workflows +
  doc-sync/render-report.py); tests/scripts/marketplace-pin_test.py.

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
## 2026-07-07 — bloat scale hardening (provisioned executors, budgets, convergent runs)
- Decided: The headless sweep lane is provisioned, budgeted, and convergent — the dispatch
  prompt carries the chunk slice verbatim (rendered by `plan-chunks.py --emit-prompt`, never
  YAML templating, and the executor never opens the manifest), `Skill` joins the sweep
  allowlist (the 2026-07-07 career-compass run 28860529836 showed every invocation burning
  1–2 permission denials and 14–18 turns against a flat `--max-turns 15`), turn caps are
  planner-computed per chunk (12 + 2/doc, 4/planning-doc, +1 per 600 lines, clamp [20,40];
  policy flat 20) with retry classification at the seam (`sync-gate.py bloat-retry`:
  `error_max_turns` escalates ceil(1.5×) cap 60, anything else retries fresh), chunk ids are
  content-addressed over (path, content-sha256) so cross-run resume never reuses a stale
  result, and assembly is gap-tolerant (`--allow-partial` in CI): unswept chunks land in the
  report's `unswept` list, render as a loud PR banner and run-summary line, and the next
  sweep resumes exactly them.
- Still binds: full per-doc audit depth (no triage-first mode; chunk splitting rejected —
  the failing chunks are single docs); a twice-failed chunk costs its own docs, never the
  report; the workflow ceiling (60) is the kill switch, the planner budget is work sizing —
  two roles, never one number; gaps are always loud (a "nothing to propose" summary with
  silent unswept chunks is the named failure).
- Code: plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py,
  plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml,
  plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md
- Source: docs/plans/2026-07-07-bloat-scale-hardening-design.md

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
  result is exactly one POLICY record whose files equal the dispatched chunk's list ("CI
  never passes `--allow-partial`" bound here until 2026-07-07 — superseded by the
  scale-hardening entry above: CI now passes it, with gaps recorded in the report's
  `unswept` list); doc enumeration and chunk planning go through `plan-chunks.py` (this
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
