# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. It is almost entirely
Markdown; the executable code published is the engine package
(`plugins/doc-lifecycle/engine/doclifecycle/`, stdlib-only — the single owner the #57
re-architecture is absorbing the helper scripts into; see its `README.md`) plus thirteen skill
helper scripts
(`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`,
`plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py` and
`.../detecting-doc-bloat/scripts/plan-chunks.py`, plus
`scheduling-doc-sync`'s `scripts/sync-gate.py`, `scripts/upgrade-gate.py`, `scripts/render-report.py`,
`scripts/plan-distill.py` (doc-bloat's distill-lane planner + deterministic patch merge),
`scripts/authorize-paths.py` (the path authority the credentialed workflow jobs enforce over a
model's edit set),
`scripts/apply-upgrade.py` (the deterministic upgrade engine — run from the pinned checkout by
the upgrade lane, not vendored into installs), `scripts/render-audit-summary.py` (the new
engine's read-only audit lane's run-surface rendering — #71),
`scripts/render-apply-summary.py` (the new engine's apply lane's run surface — its refusals, its
staged path list, and the PR title, body, and commit message that carry the approval set's digest
and summary — #72),
`scripts/probe-evidence-tool.py` (the audit lane's declared-tool probe — it renders
`drift-audit --evidence-command` from `evidence-tools.json` and runs each declared tool only as
a `--help`/`--version` read, under the model step's existing `Bash(python3 *)` grant rather than
a wider one, #118), and
`scripts/compare-shadow-lanes.py` (the shadow-mode parity comparison between the legacy lane
and the new one, #76 — transitional, leaves with the legacy lane in #77), all `python3`, no deps)
plus the GitHub Actions templates the scheduling skill installs
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`, `doc-bloat.yml`, and
`doc-sync-upgrade.yml`), `doc-audit.yml` (the new engine's audit lane template, landed by #71
alongside the other three), and `doc-apply.yml` (the new engine's manual apply dispatch — the one
lane that writes, #72); both are installed here as of #75, and Upgrade mode installs them only
into a repo holding `.doc-lifecycle/registry.json`. The sample
repos under `tests/fixtures/` are the only other runnable
code, besides the dogfooded doc-sync install under `.github/` (`doc-sync/sync-gate.py`,
`doc-sync/upgrade-gate.py`, `doc-sync/render-report.py`,
`doc-sync/plan-chunks.py`, `doc-sync/plan-distill.py`, `doc-sync/authorize-paths.py`,
`doc-sync/validate-drift-output.py`, `doc-sync/validate-bloat-output.py`,
`doc-sync/render-audit-summary.py`, `doc-sync/render-apply-summary.py`,
`doc-sync/probe-evidence-tool.py`,
`doc-sync/engine/` (the `doclifecycle` package vendored wholesale from
`plugins/doc-lifecycle/engine/`, byte-identical to it — the only copy the new lanes run, never
edited in place),
`doc-sync/audit-scope.json` (doc-bloat full-audit scope config), `doc-sync/drift-waivers.json`
(accepted-UNVERIFIABLE waivers the sync run surfaces consume),
`doc-sync/evidence-tools.json` (the local tools the audit lane may cite — `gh` here),
`doc-sync/installed-version`
(the plugin-version lockfile the upgrade workflow reads), `workflows/doc-sync.yml`,
`workflows/doc-bloat.yml`, `workflows/doc-sync-upgrade.yml`, `workflows/doc-audit.yml`,
`workflows/doc-apply.yml`; the two legacy lanes are `if: false` at their entry job here,
disabled by #75 ahead of #77 removing them from the templates), the classification registry
(`.doc-lifecycle/registry.json` — five roots, closed-world), the ci+release workflow
(`workflows/release.yml`), that workflow's own test-suite runner
(`.github/scripts/run-script-suites.py`, #99 — discovery-driven, so a new
`tests/scripts/*_test.py` suite needs no hand-wiring), the shadow-mode parity gate's harness
(`tests/baselines/shadow-parity-gate/shadow-cycle.py`, #76 — recorded scaffolding, retired with
the legacy lane in #77; its `digest` and `merge` subcommands are the gate's own instruments and
are pinned by `tests/scripts/shadow-cycle_test.py`), and that gate's second-cycle worker
orchestrator (`tests/baselines/shadow-parity-gate-rerun/fanout.py`, #117 — kept because it
carries the worker prompt the verdict makes claims about).

## Layout (pointers, not descriptions)

- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there.
- `plugins/doc-lifecycle/` — the one published plugin. `.claude-plugin/plugin.json` is its
  manifest; `skills/`, `agents/`, and `engine/` hold its contents.
- `CONTEXT.md` — the ubiquitous language for the #57 re-architecture (component, contract, and
  document-model terms, each with an _Avoid_ list). Use its vocabulary in engine code and tests.
- `docs/` — `plans/` (design docs + `HANDOFF.md`), `guides/` (narrative user guides). Not published.
- `tests/` — `fixtures/` (runnable sample repos), `baselines/` (RED/GREEN skill-test records,
  plus `shadow-parity-gate/`, the #76 gate's first-cycle run evidence and its harness, and
  `shadow-parity-gate-rerun/`, #117's second cycle — the FAIL both cycles reached is recorded in
  `docs/plans/2026-07-27-shadow-parity-gate-rerun.md`, which #77 cites),
  `scripts/` (helper-script suites), `engine/` (engine suites). Not published.

## Working on the plugin

- **Add a skill:** create `plugins/doc-lifecycle/skills/<name>/SKILL.md` with `name` and
  `description` frontmatter. Skills are auto-discovered — `plugin.json` does not enumerate them
  (`plugins/doc-lifecycle/.claude-plugin/plugin.json`).
- **Add a plugin:** new `plugins/<name>/` dir with `.claude-plugin/plugin.json`, then add an entry
  to the `plugins` array in `.claude-plugin/marketplace.json`.
- **Before committing a manifest:** `marketplace.json` and every `plugin.json` must be valid JSON.
- **Test the marketplace locally:** `/plugin marketplace add /path/to/toolshed` (the repo root).

## Conventions

- **Skills are built test-first** (RED → GREEN → REFACTOR with subagents) via the
  `superpowers:writing-skills` methodology; test records live under `tests/baselines/`, one dir
  per test milestone (see the directory for the current set), plus the original writing-docs
  records loose at the root.
- The bloat lane's RED/GREEN baselines are retained at
  `tests/baselines/bloat-red/` and `tests/baselines/bloat-fixing-red/` (recorded against
  `detecting-doc-bloat` and the since-merged `fixing-doc-bloat`), the 2026-07-06
  rearchitecture's at `tests/baselines/bloat-rearch-red/` / `bloat-rearch-green/`, the
  2026-07-07 scale hardening's at `tests/baselines/bloat-scale-red/` / `bloat-scale-green/`,
  the 2026-07-09 distill-lane fan-out's at `tests/baselines/distill-fanout-red/` /
  `distill-fanout-green/`, and the fix-skill merge's at
  `tests/baselines/fixing-docs-merge-red/` / `fixing-docs-merge-green/`;
  method, status, and resume notes: `docs/plans/HANDOFF.md`; design: `docs/decisions.md`
  (2026-06-09 suite entry; 2026-06-20 `docs/reference/` shape; 2026-07-06 rearchitecture
  entry; 2026-07-07 scale-hardening entry; 2026-07-09 distill-fan-out entry).
- Apply discipline has one owner, the applier contract in
  `plugins/doc-lifecycle/engine/README.md` ("Approval sets" and "The applier"), cited (not
  restated) by `fixing-docs` — the single fix door for drift and bloat records alike.
- **The helper scripts have unit tests** (stdlib `unittest`, no deps) at
  `tests/scripts/<script-name>_test.py`; run the matching test after touching a script or its
  output contract — `sync-gate_test.py`/`render-report_test.py` also cover `doc-bloat.yml`'s
  gate/render wiring, since both workflows share the two scripts. `upgrade-gate_test.py` covers the
  `doc-sync-upgrade.yml` version-comparison gate, and `apply-upgrade_test.py` covers that workflow's
  deterministic wiring-regeneration engine (knob preservation, script overwrite, fail-loud on
  unextractable knobs). `plan-distill_test.py` covers the distill lane's grouping, dispatch
  rendering, sidecar seam, and patch-merge engine; `authorize-paths_test.py` covers the per-lane
  path authority the credentialed jobs enforce over a model's edit set. Three suites cover the
  wiring itself rather than one script: `workflow-permissions_test.py` (model jobs read-only and
  token-free, write jobs model-free and staging explicit paths, and no `--allowedTools` grant
  naming a Bash executable beyond `git`/`python3` — those patterns are prefix-matched, #118),
  `install-parity_test.py`
  (the dogfooded `.github/` install is byte-identical to what `apply-upgrade.py` would lay down
  from the plugin with this install's knobs, plus a whole-tree comparison of the vendored engine
  and a recorded allowlist of this install's legacy-lane divergence, `LEGACY_LANES_DISABLED`),
  and `engine-capability_test.py` (the engine's
  applier module grants no shell, git, exec, or network capability). `render-audit-summary_test.py` covers the new
  engine's audit lane's run-surface rendering (every report result state, plus the
  report-never-produced case, and cost/turn observability); `audit-workflow_test.py` adds
  `doc-audit.yml`-specific static checks (SHA-pinned third-party actions, no direct branch
  commits; no step reading `$?` or calling the engine CLI with later logic depending on it,
  anywhere `bash -e`'s inherited abort would already have skipped that read or logic — #107)
  plus an execution-based regression suite for the freshness-revalidation step (run under a
  real `bash -e` against a stubbed engine CLI: a stale/partial verdict must reach the
  published report, never laundered as the original's status, and an empty/absent
  revalidated payload must not fail the step outright) and static guards on how this lane
  reaches Tier-2 tool evidence (#118: the model grant unchanged, `--evidence-command` rendered
  by `probe-evidence-tool.py` rather than typed into the YAML);
  `probe-evidence-tool_test.py` covers that script itself (the declared list and its rendered
  flags, the refusals for an undeclared tool or a non-`--help`/`--version` invocation, and the
  credential scrub). Both suites sit alongside what `workflow-permissions_test.py` already
  covers generically for every `scheduling-doc-sync/*.yml` template. `render-apply-summary_test.py` covers the apply lane's
  run surface (every refusal, the staged path list, and the rendered PR body, title, and commit
  message), and `apply-workflow_test.py` adds `doc-apply.yml`'s static checks (three-job trust
  split, no dispatch input in any `run:` block, staging confined to the apply result's paths, a
  real PR rather than a draft). `compare-shadow-lanes_test.py` covers the shadow-mode
  parity comparison (assertion correspondence across two commits, coverage and cost deltas,
  auto-apply-eligibility split, determinism). `release.yml`'s CI runs every
  `tests/scripts/*_test.py` suite.
- **The engine's tests live at `tests/engine/*_test.py`** and are found by discovery
  (`python3 -m unittest discover -s tests/engine -p '*_test.py'`), which is how `release.yml`'s
  "Engine tests" step runs them — a new suite is wired by landing the file, with no list to
  update. They test only the two public seams (the library function, and `python3 -m
  doclifecycle` as a subprocess); confirm new seams before adding a suite at one.
- Sync PR bodies/titles render via `render-report.py`'s `pr-body`/`pr-title` subcommands, never
  inline YAML `jq` — keeping the logic unit-tested and the CI YAML allowlist thin.
- **Docs in this repo follow the contract the plugin enforces:** every line is a claim verifiable
  against the repo (the `writing-docs` skill — one door for both human and agent docs; it carries
  the agent-density bar inline and dispatches the `llm-doc-writer` agent for heavy agent-facing jobs).
- **This repo's `docs/` stays flat** (`plans/`, plus `guides/` — durable narrative user guides,
  each carrying growing-docs' `> As of` first-line anchor, never planning artifacts) — a
  single-unit marketplace; the
  `docs/reference/` convention the plugin prescribes for larger repos
  (`plugins/doc-lifecycle/skills/bootstrapping-docs/repo-shape.md`) does not apply here —
  don't add one.

## Gotchas

- **`tests/fixtures/taskflow` needs `make setup` (plain `npm install`) after checkout**, then
  `make migrate` before `make dev` — migrate creates `.taskflow-state.json`, and api and worker
  refuse to start without it (`tests/fixtures/taskflow/Makefile:7`, comment). `make test`
  (`node --test packages/*/test/`) does not need migrate; only `@taskflow/shared` has tests
  (`Makefile:21`, comment).

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

This repo uses the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout. See `docs/agents/domain.md`.
