# CLAUDE.md

This repo is a **Claude Code plugin marketplace**, not an application. It is almost entirely
Markdown; the executable code published is the engine package
(`plugins/doc-lifecycle/engine/doclifecycle/`, stdlib-only — the single owner the #57
re-architecture absorbed the helper scripts into; see its `README.md`) plus thirteen skill
helper scripts
(`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`,
`plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py` and
`.../detecting-doc-bloat/scripts/plan-chunks.py`, plus
`scheduling-doc-sync`'s `scripts/upgrade-gate.py` (the upgrade lane's semver comparison, plus the
strict X.Y.Z shape-check a dispatched upgrade target passes before it names a git ref),
`scripts/stage-upgrade.py` (that lane's path authority, #127 — it derives what a regeneration
wrote by comparing the scratch tree against the install, refuses the run whole if any difference
lies outside what `apply-upgrade.py` owns, and is vendored precisely because both upgrade jobs
must run it from a copy of the install's own tooling taken before the regeneration wrote the
release's copy of it),
`scripts/render-report.py` (the upgrade lane's run surface — its only consumer;
`detecting-doc-bloat` now summarizes its report by hand rather than through a subcommand here),
`scripts/render-audit-summary.py` (the audit lanes' run-surface rendering — #71/#144),
`scripts/render-apply-summary.py` (the apply lane's run surface — its refusals, its
staged path list, and the PR title, body, and commit message that carry the approval set's digest
and summary — #72),
`scripts/probe-evidence-tool.py` (the audit lane's declared-tool probe — it renders
`drift-audit --evidence-command` from `evidence-tools.json` and runs each declared tool only as
a `--help`/`--version` read, under the model step's existing `Bash(python3 *)` grant rather than
a wider one, #118),
`scripts/verify-apply-bytes.py` (both apply lanes' byte verification at the two git boundaries the
engine cannot see, #191 — it takes the applier's certified postimage manifest and compares the
staged index and then the commit tree against it, refusing when git holds anything else and
naming the commit the push carries so the pushed tree is the verified one), and
`scripts/bloat-cadence.py` (the scheduled bloat lane's trusted prompt renderer and
schema-bound action-output collector — it validates chunk returns, selects one retry, and runs
from the release-pinned marketplace rather than being vendored), and
`scripts/check-repo-integrity.py` (the repository-integrity gate both read-only audit lanes run
between the model step and any assembly — HEAD, staged, tracked, and untracked surfaces, with an
`--allow` list holding exactly the artifacts a lane declared it would write into the work tree;
un-vendored because it judges the checkout and so must not live in it, #185), and
`scripts/apply-upgrade.py` (the deterministic upgrade engine — the *target release's* own copy is
what the upgrade lane runs, in the one job holding no credential, and it stays deliberately
un-vendored) — all under `scheduling-doc-sync/scripts/`, not the
skill's base directory, which holds only the templates; all `python3`, no deps)
plus the five GitHub Actions templates the scheduling skill installs
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml` — the read-only scheduled
drift audit, #71; `doc-bloat-audit.yml` — the weekly read-only, budgeted Task fan-out whose
typed completion gaps come from the report, #144; `doc-apply.yml` — the manual apply dispatch,
the human-selected apply lane, #72;
`doc-policy-apply.yml` — the successful-scheduled-audit-chained policy lane whose three jobs keep
the model repository-credential-free and open a real review PR for the mechanical subset selected
by the standing consumer policy, #143; and
`doc-sync-upgrade.yml` — the model-free upgrade lane, whose weekly schedule only detects a newer
release and files a notice issue, while a human dispatch naming the target is what regenerates the
wiring and opens the version-bump PR, #127). #77 removed the legacy
`doc-sync.yml` / `doc-bloat.yml` write lanes and their gate/path-authority/distill-planner
scripts, so an install is exactly those five templates; `apply-upgrade.py` installs the four
engine lanes only into a repo holding `.doc-lifecycle/registry.json`, and the upgrade lane
everywhere. The sample repos under `tests/fixtures/` are the other runnable
code that matters, alongside the dogfooded install under `.doc-lifecycle/` (#133 centralized it
there out of `.github/doc-sync/`; three tiers by owner — consumer judgment at the root,
plugin-regenerated wiring under `wiring/`, machine-written state under `state/`):
`wiring/upgrade-gate.py`,
`wiring/stage-upgrade.py`,
`wiring/render-report.py`, `wiring/render-audit-summary.py`,
`wiring/render-apply-summary.py`, `wiring/probe-evidence-tool.py`,
`wiring/verify-apply-bytes.py` — the chunk planner and the
two output validators are NOT vendored here; both detecting skills always dispatch their own
copy via `${CLAUDE_PLUGIN_ROOT}`, so a copy under `wiring/` would have no reader
(aj604/toolshed#77 follow-up), and `check-repo-integrity.py` is not vendored either — both audit
lanes run it from the release-pinned marketplace clone, because a gate that judges the checkout
must not be a file inside the checkout it judges (#185),
`wiring/engine/` (the `doclifecycle` package vendored wholesale from
`plugins/doc-lifecycle/engine/`, byte-identical to it — the only copy the lanes run, never
edited in place),
`registry.json` (the classification registry — five roots, closed-world),
`audit-scope.json` (bloat-audit scope config, and one of Migration mode's inference
inputs), `drift-waivers.json`
(accepted-UNVERIFIABLE claims — `drift-audit --waivers` annotates against it, and Migration
mode re-keys it; no installed lane passes that flag today),
`evidence-tools.json` (the local tools the audit lane may cite — `gh` here),
`auto-apply-policy.json` (this consumer's standing authorization for mechanical stale-passage
and narrative-anchor refresh records; upgrades preserve it and never seed one),
`installed-version`
(the plugin-version lockfile the upgrade workflow reads), and `state/sync-marker`, which survives
as legacy state no lane reads — carried across the relocation byte-for-byte because whose state it
is decides that. The five lane workflows stay in `.github/workflows/` (`doc-audit.yml`,
`doc-bloat-audit.yml`, `doc-apply.yml`, `doc-policy-apply.yml`, `doc-sync-upgrade.yml`) because
GitHub reads workflows only from there, and are
the only doc-lifecycle content left under `.github/`. Also runnable: the ci+release workflow
(`.github/workflows/release.yml`), that workflow's own test-suite runner
(`.github/scripts/run-script-suites.py`, #99 — discovery-driven, so a new
`tests/scripts/*_test.py` suite needs no hand-wiring), the release manifest guard
(`.github/scripts/release-manifest.py`, #77 — it reads `release.yml` for the discovery steps CI
actually runs, computes the suites those steps really execute, and fails when a suite in the tree
is not among them: a `tests/engine` subdirectory missing `__init__.py`, a name the pattern
misses, a directory nothing discovers, or a glob narrowed in `release.yml`. It also carries the
release manifest mapping each release criterion to the suites that discharge it — #77's original
criteria plus #158's primary human lifecycle transaction — and declares `tests/baselines/` and
`tests/fixtures/` non-gate roots — the RED/GREEN skill baselines are retained methodology,
demonstrably outside the release gate), and the shadow-mode parity
gate's second-cycle worker orchestrator
(`tests/baselines/shadow-parity-gate-rerun/fanout.py`, #117 — kept because it carries the worker
prompt the verdict makes claims about). The rest of the tree's Python is one-off tooling wired
into no lane and no CI step: `assets/demo/make_cast.py` (the README demo's generator),
`tests/docs-ab/` (the A/B harness), `tests/baselines/fixing-docs-merge-red/build_report.py`.

## Layout (pointers, not descriptions)

- `.claude-plugin/marketplace.json` — marketplace manifest, lists plugins. **Must stay at repo
  root**: `/plugin marketplace add <owner>/<repo>` only finds `marketplace.json` there.
- `plugins/doc-lifecycle/` — the one published plugin. `.claude-plugin/plugin.json` is its
  manifest; `skills/`, `agents/`, and `engine/` hold its contents.
- `.doc-lifecycle/` — this repo's own install of the plugin (#133). Judgment files and
  `installed-version` at the root are hand-edited; `wiring/` is regenerated wholesale by the
  upgrade lane, so an edit there is reverted on the next upgrade; `state/` is machine-written.
  Its lane workflows live in `.github/workflows/` — GitHub's requirement, and the only
  doc-lifecycle content under `.github/`.
- `CONTEXT.md` — the ubiquitous language for the #57 re-architecture (component, contract, and
  document-model terms, each with an _Avoid_ list). Use its vocabulary in engine code and tests.
- `docs/` — `plans/` (design docs + `HANDOFF.md`), `guides/` (narrative user guides). Not published.
- `tests/` — `fixtures/` (runnable sample repos), `baselines/` (RED/GREEN skill-test records,
  plus `shadow-parity-gate/`, the #76 gate's first-cycle run evidence, and
  `shadow-parity-gate-rerun/`, #117's second cycle — the FAIL both cycles reached is recorded in
  `docs/plans/2026-07-27-shadow-parity-gate-rerun.md`, which #77 cites; the gate's harness left
  with the legacy lane in #77, the run evidence stayed),
  `scripts/` (helper-script suites), `engine/` (engine suites), `docs-ab/` (the doc-form A/B
  harness — tooling, not a suite). Neither `baselines/` nor
  `fixtures/` gates a release — `release-manifest.py` declares both non-gate roots. Not published.

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
  `tests/baselines/fixing-docs-merge-red/` / `fixing-docs-merge-green/`; the policy lane's retained
  test-first record is at `tests/baselines/policy-lane-red/`, and the scheduled bloat cadence's
  at `tests/baselines/scheduling-bloat-cadence-red/`;
  method, status, and resume notes: `docs/plans/HANDOFF.md`; design: `docs/decisions.md`
  (2026-06-09 suite entry; 2026-06-20 `docs/reference/` shape; 2026-07-06 rearchitecture
  entry; 2026-07-07 scale-hardening entry; 2026-07-09 distill-fan-out entry).
- Apply discipline has one owner, the applier contract in
  `plugins/doc-lifecycle/engine/README.md` ("Approval sets" and "The applier"), cited (not
  restated) by `fixing-docs` — the single fix door for drift and bloat records alike.
- **The helper scripts have unit tests** (stdlib `unittest`, no deps) at
  `tests/scripts/<script-name>_test.py`; run the matching test after touching a script or its
  output contract. `upgrade-gate_test.py` covers the
  `doc-sync-upgrade.yml` version-comparison gate, its `normalize` shape-check (a dispatched
  target that is not three decimal components never becomes argv), and its `notice` dedupe (one
  open notice issue per release), `stage-upgrade_test.py` that
  lane's path authority in both directions (the manifest step's refusals, and the credentialed
  step re-deriving them from a manifest edited in between), `render-report_test.py` that lane's
  run-surface strings, and
  `apply-upgrade_test.py` that workflow's
  deterministic wiring-regeneration engine (knob preservation, script overwrite, fail-loud on
  unextractable knobs). Three suites cover the
  wiring itself rather than one script: `workflow-permissions_test.py` (model jobs read-only and
  token-free; every write job model-free and staging an explicit path list, with no `git add -A`
  exemption left — #127 replaced the upgrade lane's last broad add with the path set
  `stage-upgrade.py` authorizes from the manifest; and no `--allowedTools`
  grant naming a Bash executable beyond `git`/`python3`, since those patterns are prefix-matched,
  #118),
  `install-parity_test.py`
  (the dogfooded install (`.doc-lifecycle/` plus the five lane workflows under `.github/workflows/`) is byte-identical to what `apply-upgrade.py` would lay down
  from the plugin with this install's knobs, plus a whole-tree comparison of the vendored engine),
  and `engine-capability_test.py` (the engine's
  applier module grants no shell, git, exec, or network capability). `render-audit-summary_test.py` covers the
  audit lane's run-surface rendering (every report result state, plus the
  report-never-produced case, the integrity-refused case — which outranks any report on
  disk — and cost/turn observability); `audit-workflow_test.py` adds
  `doc-audit.yml`-specific static checks (SHA-pinned third-party actions, no direct branch
  commits; no step reading `$?` or calling the engine CLI with later logic depending on it,
  anywhere `bash -e`'s inherited abort would already have skipped that read or logic — #107)
  plus an execution-based regression suite for the freshness-revalidation step (run under a
  real `bash -e` against a stubbed engine CLI: a stale/partial verdict must reach the
  published report, never laundered as the original's status, and an empty/absent
  revalidated payload must not fail the step outright) and static guards on how this lane
  reaches Tier-2 tool evidence (#118: the model grant unchanged, `--evidence-command` rendered
  by `probe-evidence-tool.py` rather than typed into the YAML) and on the repository-integrity
  gate (#185: it stands between the model and `drift-audit`, exempts exactly `verdicts.json`,
  and its verdict reaches the run surface);
  `check-repo-integrity_test.py` covers the gate itself against real git repositories — the
  dirtied non-document evidence source both lanes must refuse, every mutation surface named
  exhaustively, the allowlist exempting nothing but its own untracked path, and the
  fresh-checkout scenario that shows why the refusal has to be terminal (a later checkout of
  the same commit is clean, so nothing downstream can re-derive the failure);
  `bloat-audit-workflow_test.py` guards the sibling bloat cadence (#144): registry/public-plan
  preflight before fan-out, the two SHA-pinned model actions' exact `Task,Read,Grep,Glob`
  boundary, trusted structured-output extraction and one-retry selection, one budgeted fresh
  Task per chunk, out-of-tree artifacts, the same shared integrity gate before
  #152 completion assembly, and a report-derived typed partial summary (the unswept sidecar is
  never the authority); `bloat-cadence_test.py` executes the supported action-output seam,
  invalid-return retry selection, and post-retry partial truth;
  `probe-evidence-tool_test.py` covers that script itself (the declared list and its rendered
  flags, the refusals for an undeclared tool or a non-`--help`/`--version` invocation, and the
  credential scrub). Both suites sit alongside what `workflow-permissions_test.py` already
  covers generically for every `scheduling-doc-sync/*.yml` template. `render-apply-summary_test.py` covers the apply lane's
  run surface (every refusal, the staged path list, and the rendered PR body, title, and commit
  message), and `apply-workflow_test.py` adds `doc-apply.yml`'s static checks (three-job trust
  split, no dispatch input in any `run:` block, staging confined to the apply result's paths, a
  real PR rather than a draft). `verify-apply-bytes_test.py` covers the byte verification both
  apply lanes run past that surface, executed against real temporary git repositories (an
  approved path mutated between the apply and the staging, index normalization by a `clean`
  filter, a hook rewriting and re-staging after the index was verified, a deletion checked as
  absence at both boundaries, and a refusal leaving no commit id for the push to name), and
  `apply-lane-parity_test.py` is what holds selection and trigger to being the only differences
  between the two lanes — every `run:` block of their credentialed jobs must be byte-identical
  (#191). `policy-workflow_test.py` covers the audit-chained policy lane:
  completed-run artifact binding, revalidation before `policy-eligibility`/`policy-mint`,
  absent/no-eligible clean stops, the same trust split and staging confinement, real-PR-only
  delivery, dogfood policy configuration, and both user-facing opt-in docs.
  `upgrade-workflow_test.py` does the same for `doc-sync-upgrade.yml`
  (#127: its own three-job split, execution reachable only by dispatch and never by the schedule,
  neither job invoking a wiring script the regeneration could have overwritten, no dispatch input
  in any `run:` block, no version literal in the YAML, and a run-surface summary for every terminal
  state). `release-manifest_test.py` covers the release manifest guard by
  mutation — synthetic repositories in which a suite is genuinely unwired, each of which the
  guard must name — plus a run against this repository. `release.yml`'s CI runs every
  `tests/scripts/*_test.py` suite, and the guard is what catches a suite discovery silently
  stopped running.
- **The engine's tests live at `tests/engine/*_test.py`** and are found by discovery
  (`python3 -m unittest discover -s tests/engine -p '*_test.py'`), which is how `release.yml`'s
  "Engine tests" step runs them — a new suite is wired by landing the file, with no list to
  update. They test only the two public seams (the library function, and `python3 -m
  doclifecycle` as a subprocess); confirm new seams before adding a suite at one.
- Every run-surface string — job summaries, PR bodies, PR titles, commit messages — renders via
  a tested script (`render-audit-summary.py` for the audit lane, `render-apply-summary.py` for
  the apply lane, `render-report.py` for the upgrade lane), never inline YAML `jq` — keeping the
  logic unit-tested and the CI YAML allowlist thin.
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
