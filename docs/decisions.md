# Decisions

> As of 2026-07-28 — entries are dated and appended, newest first; a superseded decision stays
> standing and is marked superseded by the entry that replaced it, so an old entry is a record of
> what was true then, not a claim about now.

## 2026-07-28 — a STALE fix preserves a soft-wrapped unit's physical shape (#126)
- Evidence: DRIFT-021 and DRIFT-022 in
  `tests/baselines/shadow-parity-gate-rerun/shadow-report.json` correctly identify stale passages
  and contain correct replacement prose, but each `fix` collapses a two- or four-line list item
  into one 206- or 362-character physical line. `drift.py` required `_one_line(fix)`, while the
  applier already splits replacement `text` on LF and can write any number of physical lines.
- Decided (contract): a STALE `fix` remains one string. It may contain LF-separated, non-empty
  physical lines only when its approved assertion unit already spans more than one source line;
  CR, NUL, blank physical lines, and a line break introduced into a single-line unit are
  `drift-verdict-invalid-fix`. The replacement may use a different number of physical lines than
  the preimage because a corrected passage can wrap differently, but it is still one logical
  assertion unit. `RULESET_VERSION` advances to 6 because a verdict the prior rules refused is now
  valid.
- Decided (method): `detecting-doc-drift` authors the complete replacement already wrapped to the
  target document's convention, including its list marker and continuation indentation.
  `fixing-docs` copies that string byte-verbatim into the edit plan's `text`; it does not reflow or
  reinterpret it. The engine validates the mechanical boundary, while the writing-docs bar owns
  the judgment of where Markdown should wrap.
- Rejected: applier-side reflow. Markdown links, emphasis, code spans, list indentation, and local
  column conventions make line breaking an authoring judgment. Giving that judgment to the
  applier would contradict its deterministic, refusal-based role and make applied bytes differ
  from the approved record.
- Verified: `tests/baselines/multiline-fix-red/` records the production RED failure and identical
  pre-/post-change pressure runs by fresh subagents. The drift suite replays DRIFT-021's actual
  two-line preimage with a three-line corrected fix, and the repository acceptance suite carries
  that same passage through audit, policy minting, edit-plan validation, and `apply_edit_plan()`.
  Tests also refuse CR, NUL, blank physical lines, and a multiline fix over a single-line unit.
- Code: `plugins/doc-lifecycle/engine/doclifecycle/drift.py`,
  `plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md`,
  `plugins/doc-lifecycle/skills/fixing-docs/SKILL.md`,
  `plugins/doc-lifecycle/engine/README.md`, `tests/engine/drift_test.py`,
  `tests/engine/acceptance/scenario_drift_test.py`,
  `tests/engine/acceptance/scenario_policy_test.py`,
  `tests/baselines/multiline-fix-red/`

## 2026-07-27 — a vendored copy needs a reader, or it doesn't get vendored (#77 follow-up)
- Evidence: `apply-upgrade.py`'s `SCRIPTS` table kept vendoring `plan-chunks.py`,
  `validate-bloat-output.py`, and `validate-drift-output.py` into every install's
  `.doc-lifecycle/wiring/`, on the stated rationale that "a model running either detecting skill
  reaches for them whichever lane invoked it." That doesn't hold against the current wiring:
  `doc-audit.yml` and `doc-apply.yml` call the engine CLI directly (never SKILL.md dispatch),
  `doc-apply.yml` doesn't even allowlist the `Skill` tool, and both detecting skills always
  resolve these scripts via `${CLAUDE_PLUGIN_ROOT}` — never a repo-relative path — so the
  vendored copy has zero readers in every path checked.
- Decided: stop vendoring them. Removed from `SCRIPTS`; this repo's own `.doc-lifecycle/wiring/`
  copies deleted; `SKILL.md`'s install steps and `CLAUDE.md`'s inventory no longer list them. The
  canonical scripts stay exactly where they were — owned by `detecting-doc-bloat` and
  `detecting-doc-drift`, unaffected.
- Closed here rather than deferred, because the deferral target went away: `copy_scripts()` only
  ever overwrote what `SCRIPTS` names, so nothing deleted a script that left the table — which
  would have stranded this decision's own three retired scripts in any repo that already vendored
  them. `prune_orphaned_scripts()` now deletes a `.py` directly under `.doc-lifecycle/wiring/`
  that the current wiring no longer names, and declares the deletion in `--report-written`.
  `stage-upgrade.py`'s `wiring/<name>.py` pattern already authorizes those paths, deletions
  included, so no consumer's pre-upgrade path authority refuses the prune.
- Not the cleanup of #77's own orphans: those sit at the pre-#133 addresses, and every `.py` in
  `.github/doc-sync/` leaves with the relocation's named set (#133 entry below). The prune is what
  keeps a *future* retirement from stranding a copy. #130 proposed a version-keyed `RETIRED` table
  for the same purpose and was closed as superseded — the relocation covers the paths it named,
  and this covers the general case. The three artifacts no upgrade lane can remove
  (`doc-sync.yml`, `doc-bloat.yml`, `last-stales.json`) are tracked as a manual cleanup in #139.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py`,
  `tests/scripts/apply-upgrade_test.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`, `CLAUDE.md`,
  `docs/guides/scheduling-doc-sync.md`

## 2026-07-27 — render-report.py sheds its legacy-lane subcommands (#77 follow-up)
- Evidence: #77 removed `doc-sync.yml` and `doc-bloat.yml` (and their gate/path-authority/distill-
  planner scripts) but kept `render-report.py` wholesale, since `bloat-triage` and the upgrade lane
  still call it — leaving 15 of its then-18 subcommands (`pre-summary`, `no-drift-summary`,
  `issue-body`, `blast-summary`, `pr-body`/`--prev-stales`, `pr-title`, `pr-summary`,
  `growth-backlog`, and the remaining `bloat-*`/`distill-merge-summary`) with no caller anywhere
  but historical `docs/plans/` records and their own tests, pending a decision on whether the new
  engine's lanes adopt any of them. (#127 later added a fourth live subcommand, `upgrade-notice` —
  kept; not part of this decision.)
- Decided: delete, adopt none. The new engine already owns this run surface under its own
  contract — `render-apply-summary.py` the apply lane's PR title/body/refusals,
  `render-audit-summary.py` the audit lane's — neither reuses `render-report.py`'s rendering, and
  there is no functional gap the retired subcommands would fill; keeping them would be two
  implementations of the same purpose, one of them dead.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py` (and its
  byte-identical `.doc-lifecycle/wiring/` copy), `tests/scripts/render-report_test.py`

## 2026-07-27 — the migration door reads both install layouts, and says which (#137)
- Evidence: the named limit the #133 entry below recorded, measured not reasoned. `apply-upgrade.py`'s
  relocation branch fires for a registry-free install too, and afterwards `migration-draft` read its
  inference inputs from a directory that was gone — `status: ok`, `from_version: null`, every source
  `present: false`, a registry still drafted but without the consumer's exclusions, their accepted
  waivers, or the preserved-state digests it would have inherited. Degraded inference that reads
  exactly like a clean one.
- Decided: the door reads both roots — keeping the old addresses beside the new ones rather than
  picking one, which is what `paths.py`'s `_WORKFLOW_PREFIXES` already does for classification. The
  four inputs (audit scope, waivers, lockfile, marker) are one address book per layout —
  `centralized` for `.doc-lifecycle/`, `legacy` for `.github/doc-sync/` — and the door reads
  whichever an install occupies. Repointing is still refused, for #133's reason: a genuinely
  pre-registry consumer is what this door exists for, and most of them have never relocated.
- Decided (the contract does not vary): `legacy-doc-sync-to-registry` spans both layouts. Neither had
  a registry, and where an install kept its state is not what the migration changes — so the layout
  is reported as a fact about the install rather than folded into the contract's name.
- Decided (two facts, not one enum): the payloads carry `install: {layout, registry}`. `layout` is
  where the state was found (`null` when neither address holds any of the four — a repository that
  never ran doc-sync, which the door still drafts for). `registry` is whether a file stands at the
  registry path. They are orthogonal because relocating and adopting the registry are different
  events in either order, so the three states the fix had to keep apart — pre-registry never
  relocated, relocated still pre-door, relocated already through the door — are three readings of
  the pair, and so is the fourth real one: `legacy` + `present`, which is what the door's own
  instructions produce between drafting a registry and dry-running it. A single enum would have
  fused questions with different remedies.
- Decided (it refuses rather than guesses): state standing under *both* layouts is
  `migration-split-install`, naming every path found under each — the question
  `apply-upgrade.py`'s `layout_problem` refuses to answer about an install's wiring, asked here
  about its state (different predicates: it looks at the directories, the door at the four files it
  reads). Reading either copy would silently drop the exclusions or acceptances in the other, which
  is the exact harm this issue was filed about, inverted; so it is refused on its own rather than
  reported beside findings a half-read config produced, which the door's exhaustive-problems habit
  would otherwise ask for. `sources` lists both layouts' addresses whichever one an install
  occupies, so a payload shows what was looked for and not only what was found.
- Decided (the artifact scan reads both roots, unlike the inputs): the asymmetry is deliberate.
  Two rival copies of the audit scope are a question about which is live; two old-world caches are
  two files to delete, so the closed-world scan covers every layout's state directory —
  #133's relocation leaves what it does not carry exactly where it is, and scanning only the layout
  the state was read at would stop naming those leftovers the moment an install relocated. The
  accounted-for names are per layout, because `.doc-lifecycle/` also holds `registry.json` and
  `evidence-tools.json`; a scan that kept the old list would have reported the registry as a
  leftover and told a consumer to delete the file the migration exists to land.
- Decided (a note, not a refusal): a draft against an install that already has a registry emits
  `migration-registry-already-landed`, naming the path. The skill's step 2 legitimately re-runs the
  draft to read each rule's `basis`, and that run is where the note lands — `--registry-only`
  prints the registry bytes and nothing else, by design, so the warning reaches the reviewer
  *before* a redirect rather than during one. Naming it in the payload is the door stating its own
  hazard rather than the skill prose carrying it alone.

## 2026-07-27 — doc-lifecycle install artifacts centralize under `.doc-lifecycle/` (#133)
- Evidence: an install's artifacts were scattered across three unrelated places — nine scripts and
  the vendored engine in `.github/doc-sync/`, the judgment files beside them, the sync marker loose
  at `.github/doc-sync-marker`, and `registry.json` already at `.doc-lifecycle/` because the new
  engine put it there. `.github/` is GitHub's directory, not a plugin's; nothing about that tree
  said which of its files a consumer is expected to edit. The ownership split was real and enforced
  in code — `apply-upgrade.py`'s table, `stage-upgrade.py`'s patterns — and invisible in the
  filesystem, so hand-editing a regenerated script looked reasonable right up until the next
  upgrade silently reverted it.
- Decided: one directory, three tiers, and the tier is the contract rather than a convention.
  `.doc-lifecycle/` root holds consumer judgment (`registry.json`, `audit-scope.json`,
  `drift-waivers.json`, `evidence-tools.json`) plus `installed-version` — the lockfile is
  plugin-owned but sits at the root because a human reads it to answer "what version am I on".
  `wiring/` holds the nine scripts and the vendored engine, regenerated wholesale by the upgrade
  lane and never hand-edited. `state/` holds what the lanes wrote. A reader now learns the
  ownership rule from `ls`, which is the only place it was missing.
- Decided: `.github/doc-sync-marker` becomes `.doc-lifecycle/state/sync-marker`. It is legacy state
  — #77 removed the last lane that read it — and it is carried rather than deleted because whose
  state it is decides that, and it is the consumer's. Renaming it into the state tier is what makes
  "machine-written" a tier with a member rather than an empty promise; a fresh install has none, so
  `state/` exists only in an install that came through the relocation.
- Decided: the workflow YAML stays in `.github/workflows/`. GitHub reads workflows from nowhere
  else, so this is the one exception the layout cannot absorb — and afterwards it is the only
  doc-lifecycle content under `.github/`, which is a cleaner boundary than the half-move that
  moving them would have produced.
- Decided (existing installs): `apply-upgrade.py` gained a relocation branch, entered when
  `.github/doc-sync/` exists and `.doc-lifecycle/wiring/` does not. The judgment files and the
  marker are carried byte-for-byte; the scripts, the engine, and the lockfile are written fresh at
  the new paths rather than moved, because the contract overwrites those unconditionally and moving
  bytes about to be replaced buys nothing.
- Decided (the closed-world rule): the relocation names a set — the judgment files, the lockfile,
  the marker, the old directory's `.py` files, its `engine/` — and carries or removes exactly that.
  Anything else a consumer left in the old directory is left exactly where it is and named on the
  run surface, and the old directory survives when it still holds one. A plugin leaving a directory
  does not get to sweep it, and the alternative — a recursive move — would silently relocate files
  the plugin never owned.
- Decided (it refuses rather than guesses): both layouts present is refused, because which of the
  two directories holds the live wiring is not knowable from the filesystem and picking one would
  discard whichever half a stopped relocation left behind. `wiring/` present without
  `.doc-lifecycle/installed-version` beside it is refused as a relocation that stopped partway,
  since the two are written in the same run. A vendored script whose bytes differ from the target
  release's is deliberately *not* one of these — that is what every real upgrade looks like.
- Decided (classification): the engine's path classifier takes `.doc-lifecycle/` as a whole prefix
  into the workflow class, keeping `.github/doc-sync/` beside it for installs that have not
  relocated. Taking the prefix rather than enumerating files closes a real gap: `registry.json` was
  previously protected only incidentally, by not wearing a documentation suffix, and an edit set
  naming it was refused for the right outcome by the wrong reason. The judgment files, the wiring,
  and the state are now one class because they share one property — no approved documentation edit
  may reach any of them.
- Decided (path authority): `stage-upgrade.py`'s widening is scoped by *direction*, not by path.
  The carried consumer state (`audit-scope.json`, `state/sync-marker`) is authorized as a create
  only — a write into a path holding nothing destroys nothing, and once it holds the consumer's
  judgment no upgrade may touch it again — and the old layout's named set is authorized as a
  removal only. So the widening buys exactly the one-time move and cannot be reused for anything
  after it, and "left in place and reported" is enforceable rather than merely intended.
- Decided (deliberately untouched): `migrate.py`'s legacy constants still point at
  `.github/doc-sync/`. The migration door reads a genuinely pre-registry install, which is a
  different scenario from this relocation and predates it; repointing those constants would make
  the door unable to find the state it exists to read. #133 names this a decision and its own
  testing section makes the door's suite a tripwire — "a change to it would be a signal that the
  migration door was repointed by mistake" — so this entry records the cost rather than paying it.
- Named limit (found in review, measured not reasoned): the relocation fires for a registry-free
  install too, and afterwards the migration door reads its inference inputs from a directory that
  is gone. `migration-draft` on such a repo returns `status: ok` with `from_version: null` and
  every source `present: false` — so the door still drafts a registry, but without the audit
  scope, the waivers, or the preserved-state digests it would have inherited. The two fixes
  available are both refused elsewhere: repointing the door is what the bullet above rules out, and
  leaving a registry-free install on the old layout means `apply-upgrade.py` writing to two
  addresses, which is the dual-path window #133 rejects outright. Filed rather than patched here.
  Closed by the #137 entry above, which took neither of those two: the door reads both layouts and
  reports which one it read.
- Named limit: an install predating this release cannot be relocated by the automated upgrade lane.
  That lane runs the *installed* copy of `stage-upgrade.py` — reviewed code the consumer already
  holds, which is the property the #127 entry below establishes — and a pre-#133 copy does not know
  the new layout, so it refuses the change set as unowned. Such an install relocates by re-running
  `scheduling-doc-sync` in Upgrade mode from a local checkout. This is the same shape as #127's own
  named limit: the wiring that upgrades a consumer is the wiring they already have.
- Follows from that limit, and worth stating because it is easy to assume otherwise: the *run
  surface* a pre-0.40.0 install renders is also its own. Both jobs copy the installed
  `*.py` out before anything runs, so an old install renders its old `refused` text and has no
  `blocked-relocation` status to render at all. The relocation guidance added to `refused` here
  reaches a 0.40.0-or-later install; what reaches an older one is the documentation — the skill's
  "Relocating a pre-0.40.0 install", the guide's upgrade section, and the release notes. #133's
  stories 7 and 9 ("the run surface says plainly that this was a relocation") are therefore
  satisfied going forward and not retroactively, and no test claims otherwise.
- Decided (where the leftovers are named): on the step log, not `$GITHUB_STEP_SUMMARY`. The
  leftovers are printed by `apply-upgrade.py`, which in the lane is the *target release's* code
  running in the uncredentialed job — text from an unreviewed release belongs in the log, not
  composed into the run summary a maintainer reads as this repository's own voice. The summary says
  where to look instead.
- Verified: `tests/scripts/apply-upgrade_test.py` (the relocation branch — what is carried, what is
  written fresh, what is removed, the leftovers left and reported, and both refusals);
  `tests/scripts/stage-upgrade_test.py` (the direction-scoped authority, including a modify at a
  create-only path); `tests/scripts/install-parity_test.py` (the dogfooded install byte-identical
  to what `apply-upgrade.py` lays down at the new paths, and that no shipped template or script
  still names the old directory — in either the joined spelling or the `os.path.join` one, which is
  how a default config path survived the move with its own docstring already updated).
  The classifier's widening is the `_WORKFLOW_PREFIXES` tuple in
  `plugins/doc-lifecycle/engine/doclifecycle/paths.py`; `tests/engine/paths_test.py`'s
  `FORBIDDEN_CLASSES` names every tier of the new spelling, the registry and a vendored
  `engine/README.md` included — the two files whose own suffix would otherwise class them as
  configuration and documentation.
- Verified (mutation): each entry of both safety-critical lists was deliberately broken in turn —
  dropped, narrowed to a subdirectory, misspelled without its leading dot, widened to reach the
  registry, and stripped of its direction check — and every one of the eleven mutations failed a
  test. A path list nothing fails on is a list that is not guarding.

## 2026-07-27 — publishing a tag is not a consumer's decision to run new code (#127)
- Evidence: `.github/workflows/doc-sync-upgrade.yml` before this change — one job holding
  `contents: write`, `pull-requests: write` and a push token, which on a weekly cron ran
  `upgrade-gate.py compare` (a 69-line semver comparison), cloned the newest release tag, and
  executed that clone's `apply-upgrade.py` from inside the credentialed job. Nobody in the
  consumer repository had read a line of that release when it ran, and the pull request it opened
  reviewed the *result* of an execution that had already happened. Filed out of #77, whose scope
  sentence named "self-executing upgrade logic" among the mutation paths to remove; #77's own PR
  closed the broad-staging half of that sentence and left this one.
- Decided (who decides): a version comparison detects, a human dispatches. The `schedule:` cron now
  reaches only a `detect` job that compares two numbers and stops — no clone, none of the release's
  code — and files one tracking issue naming the release, deduped on its exact title so a weekly
  check that keeps finding the same unreviewed release keeps quiet. Execution runs only under
  `workflow_dispatch` carrying a `target`, and the same tested gate that shape-checks the input
  refuses anything that is not strictly newer than the pin, so a dispatch can advance the pin and
  never rewind it. `issues: write` is the detecting job's only write scope, and it buys a
  notification.
- Decided (who holds what): the same trust split `doc-audit.yml`/`doc-apply.yml` already run.
  `regenerate` is the only job that runs the target release's code and it holds nothing — no token,
  no secret, `contents: read`, a checkout persisting no credential — and it runs `apply-upgrade.py`
  against a scratch copy of the wiring roots rather than the work tree. `land` holds the
  credentials and executes none of the release's code: every byte the release produced reaches it
  as data inside an artifact.
- Decided (and this is where the first draft was wrong, caught in review): both jobs copy
  `.github/doc-sync/*.py` out to `$RUNNER_TEMP/trusted/` before anything writes, and run every
  wiring script from there. The regeneration produces the release's own `stage-upgrade.py` and
  `render-report.py`, and `land`'s transfer legitimately lands them in `.github/doc-sync/` — so
  "the credentialed job runs only the install's own scripts" was true of the paths and false of
  the bytes: two steps after the transfer, `land` was invoking the release's code with the push
  token, which is the property this whole entry exists to establish. The claim is about *when* the
  copy was taken, never about which directory it sits in, and
  `upgrade-workflow_test.py::test_no_program_it_runs_can_have_been_overwritten_by_the_transfer` is
  what keeps it that way.
- Decided (what bounds the write): a new vendored script, `stage-upgrade.py`, is the upgrade lane's
  path authority — the inverse of `authorize-paths.py`, which denies exactly the wiring this one
  is about. It compares the scratch tree against the install, refuses the whole run if any
  difference lies outside what `apply-upgrade.py` owns (the marker, `audit-scope.json`, the
  registry, a workflow that is not `doc-*.yml`, a non-`.py` drop into `.github/doc-sync/`, a
  symlink, anything outside the wiring roots), and emits a manifest of `{status, path, sha256}`.
  The credentialed job re-derives that authority from the manifest rather than trusting it, checks
  every bundled file against its recorded digest, refuses a bundle carrying a file the manifest
  does not name, and stages by explicit pathspec. It is vendored — unlike `apply-upgrade.py`,
  which is not — precisely because the boundary has to be drawn by code the consumer already
  reviewed, so the vendored set goes eight → nine and the install's committed set fifteen →
  sixteen.
- Rejected: `workflow_dispatch`-only, dropping the schedule. Simplest, and it satisfies the same
  criterion, but consumers lose the "a new release exists" signal entirely and an install would
  sit unpatched until someone thought to look.
- Rejected: keeping the schedule as the trigger and relying on the split alone. The split closes
  the credential half, not the decision half: a compromised release would still execute in every
  consumer's runner on the next cron tick, and a job with `contents: read` on a public repo is not
  a job whose execution nobody needs to authorize.
- Still binds, from the 2026-07-07 deterministic-upgrade entry below: the lane runs no model, so
  its write scopes never sit behind a model process; `.github/doc-sync/installed-version` remains
  the pin and the workflow YAML carries no version, so a routine upgrade still never has to push a
  file under `.github/workflows/`. That entry's "the vendored set stays six" is superseded twice
  over — by the audit/apply lanes and now by `stage-upgrade.py` — but its reason for not vendoring
  `apply-upgrade.py` still holds and is now load-bearing: the target release's copy is what runs,
  which is exactly why it may not run credentialed.
- Named limit: a consumer's *first* upgrade to this release still runs the old single-job lane,
  because the wiring that upgrades them is the wiring they already have. There is no way around
  that from this side; it is the last run of the shape this entry retires.
- Named limit: `land` copies bytes the unreviewed release produced. That is what an upgrade is —
  the guarantee is that nothing from the release *executes* with credentials, that what lands is
  confined to the wiring, and that a person reads the diff as a pull request before it is merged.
- Supersedes, once it lands: #77's entry naming this as a "Known gap" is still on that issue's
  unmerged branch, so there is nothing here to mark yet. Whoever merges #77 should mark that
  paragraph superseded by this entry rather than leaving both standing as live gaps.
- Verified: `tests/scripts/stage-upgrade_test.py` (the authority, both directions — the manifest
  step's refusals, and the credentialed step re-deriving them from a manifest edited in between);
  `tests/scripts/upgrade-workflow_test.py` (the three-job split, dispatch-gated execution, no
  dispatch input in any `run:`, the credentialed job invoking nothing from the clone or scratch
  tree, no version literal in the YAML, a run-surface summary for every terminal state);
  `tests/scripts/upgrade-gate_test.py`'s `Normalize` (a target that is not three decimal
  components never becomes argv). `tests/scripts/workflow-permissions_test.py` lost its
  `BROAD_ADD_EXEMPT` set: no shipped write job stages broadly any more, and the exception that
  named this lane is gone with the `git add -A` it excused.
- Code: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync-upgrade.yml`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/stage-upgrade.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/upgrade-gate.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py`
## 2026-07-27 — the release gate is discovery, plus a guard on discovery (#77)
- Evidence: issue #57's distilled-decisions comment (2026-07-26): "Release gate is deterministic:
  all script suites + the repository-level acceptance fixture (extended with a registry case incl.
  closed-world finding, and auto-apply cases: policy mints for an eligible drift finding, and
  provably cannot mint for a bloat finding). RED/GREEN skill baselines remain the methodology for
  skill edits but never gate a release."
- Decided (nothing new was wired for any criterion but the last, and that is the finding): the
  acceptance seam, the adversarial corpus, the auto-apply can-mint/cannot-mint cases, the workflow
  permission checks, the template/dogfood equivalence test, and the migration dry run were already
  in the gate — each rides `release.yml`'s two discovery steps by virtue of matching a glob, which
  is what #99's discovery-driven design bought. Adding a second, hand-enumerated path to run them
  would have reintroduced exactly the list #99 removed.
- Decided (what was genuinely missing is a guard on discovery itself): discovery wires a suite the
  moment its file lands, but only if the file lands where the discovery step can see it. Verified
  empirically rather than reasoned about: `unittest discover` skips a subdirectory with no
  `__init__.py` without a word and reports OK, so a new engine suite in a new subdirectory is
  silently absent while CI stays green. A name the pattern misses, a directory no step reaches,
  and a glob narrowed in `release.yml` all fail the same way. `release-manifest.py` reads
  `release.yml` for the discovery steps CI actually runs, computes the set those steps really
  execute, and requires it to cover every suite in the tree. It derives the commands rather than
  restating them, so narrowing a glob moves the guard's own baseline and is caught, not obeyed.
- Decided (suite detection is structural, not name-based): a file is a suite when it declares a
  TestCase subclass carrying test methods. A rename is one of the ways a suite goes unwired, so a
  name-based guard would be blind to the case it exists for; the same rule correctly leaves
  `support.py` and `fixture.py`, which declare TestCase bases with no test methods, out.
- Decided (the manifest half): discovery cannot notice a suite that was deleted rather than
  unwired — a shrinking set is green. So each gate criterion #77 names is mapped to the suites
  that discharge it, and each must exist and be in the discovered set.
- Still binds: RED/GREEN skill baselines remain the methodology for skill edits and are
  demonstrably not part of the release gate. `tests/baselines/` and `tests/fixtures/` are declared
  non-gate roots, asserted in both directions — a suite under either is not required to be wired,
  and nothing under either may appear in the gate.
- Decided (a discovered suite is not yet a run suite), after an independent review of this guard
  found four more ways a suite goes quiet: `run-script-suites.py` runs each suite as `python3
  <path>`, so one without an `if __name__ == "__main__"` guard runs zero tests and reports PASS —
  discovered, counted, and inert, and invisible to both the runner and the first version of this
  guard. Demonstrated: a suite whose only test calls `self.fail()` was reported `PASS`. So the
  guard now also refuses an inert by-path suite, a file that does not parse (treating a
  SyntaxError as "not a suite" hides a file exactly when it is most broken), a suite anywhere in
  the repository rather than only under `tests/`, and a discovery step still present but gated
  `if: false`.
- Named limits, all three past what this shape can settle: the guard is itself discovered by the
  mechanism it guards, so `release.yml` runs it as its own step as well — that step, and the two
  discovery steps it reads, are the part no guard inside the tree can vouch for. It reads command
  *text*, so an indirection this scanner does not recognise reads as absent and a no-op wrapper
  reads as present. And suite detection is a single-module AST walk, so a TestCase reached through
  an imported base class not named `*TestCase`, or defined inside a conditional, is not
  recognised. Convention bounds those, not this file.
- Code: `.github/scripts/release-manifest.py`, `tests/scripts/release-manifest_test.py`,
  `.github/workflows/release.yml`

## 2026-07-27 — a dispatched record list is how an approval set is minted, never one (#77)
- Evidence: issue #57's distilled-decisions comment (2026-07-26), "Approval sets are untracked
  artifacts": "The applier refuses to run without a validated approval-set file; record-ID
  CLI/dispatch inputs are how one is minted, never a substitute." The superseded mechanism is
  `plan-distill.py`'s `--emit-prompt`, removed in this change: it selected every eligible record
  from the bloat report by lane filter, content-addressed the group, and rendered the record ids
  into a headless prompt that the legacy `fixing-doc-bloat` skill's group-executor mode read as
  "the human approval and your entire mandate". The prune lane did the same with a wildcard
  instead of a list — "apply EVERY record whose verdict is CUT, CONDENSE, or EXTRACT-AND-MOVE".
- Decided: the removal is not a tightening of that mechanism but a statement that it had no
  authority to tighten. An approval set is the sole authority the applier accepts, and it is an
  artifact — selected record digests bound to one report's lineage and to a mutation scope
  derived from the selection, with a digest that is required on the way in. A list of ids is
  refused by name (`approval-not-an-approval-set`, whose message for a list of digests reads
  "which is how an approval set is minted, never a substitute for one").
- Still binds, and this is the trust assumption the old shape lacked: no human appeared anywhere
  in the superseded loop. The audit engine's report produced the candidate set, a deterministic
  planner turned every eligible record in it into a "mandate", and a model applied it — the word
  "approved" appeared at every step and named no one. Nothing bound the list to the report it
  came from: no report digest, no lineage, no preimage, so a report moving under the dispatch was
  undetectable, and a mistaken or injected `RETIRE-DOC` record landed as a deletion whose
  authorization was its own id. Now a selection names record digests, `mint_approval_set` refuses
  before it mints, and every one of those refusals is re-run on read-back against the report the
  artifact names. Where no person selects, the minter is a named auto-apply policy whose
  selection derives from its own decisions and can never reach a bloat verdict, and change
  approval still lands everything.
- Superseded: the 2026-07-09 entry below (doc-bloat distill lane fan-out), whose "Still binds"
  recorded that `fixing-doc-bloat`'s group-executor mode treats the dispatch's record-id list as
  the human approval and the entire mandate. It stands as a record of what was true then.
- Code: `plugins/doc-lifecycle/engine/doclifecycle/approval.py`,
  `plugins/doc-lifecycle/engine/doclifecycle/policy.py`,
  `plugins/doc-lifecycle/engine/README.md`, `plugins/doc-lifecycle/skills/fixing-docs/SKILL.md`,
  `.github/workflows/doc-apply.yml`; removed: `plan-distill.py`, `doc-bloat.yml`

## 2026-07-27 — semantic approval and change approval are two acts, and a merge is only the second (#77)
- Evidence: issue #57's distilled-decisions comment (2026-07-26), "Two approvals": "semantic
  approval mints an approval set from selected record digests; change approval is accepting the
  actual diff (PR merge, or committing the staged interactive change). Only change approval lands
  anything." The superseded mechanism is both legacy lanes, removed in this change: `doc-bloat.yml`
  declared in its own header that each lane "edits directly and opens a DRAFT PR whose merge is
  the approval", and `doc-sync.yml` applied the model's patch and opened a pull request whose
  merge advanced the marker.
- Decided: one act was being asked to carry two different judgments, and they are now separate.
  Semantic approval — a person selecting record digests from one report — authorizes planning and
  application. Change approval — a person accepting the produced diff — is the only thing that
  lands anything. The applier never stages and never commits, so there is no path on which the
  second silently stands in for the first.
- Decided (the draft pull request goes with it): a draft was the legacy lane's way of saying "this
  is a proposal", which was needed precisely because nothing upstream had approved. The apply lane
  opens a real pull request, never a draft, because what it carries was already approved
  semantically — by a person, or by a named auto-apply policy for which pull-request review is the
  designated semantic review.
- Still binds, and this is the trust assumption the old shape lacked: nothing *bound* a legacy
  lane's landed diff to the report that justified it. The pull-request body did enumerate every
  record, and the report was uploaded as a run artifact, so a reviewer could read the record list —
  but the list travelled beside the diff, not in it. No report digest, no lineage, no approval-set
  identity rode in the change, so a reviewer could not verify that the diff in front of them was
  the one those records authorized, or that the list was complete. So a record that was wrong, a
  record nobody read, and a record somebody would have declined all landed identically, and an edit
  no record called for landed the same way. Now the approval set's digest and rendered summary
  travel in the change itself (`Doc-Lifecycle-Approval`, `Doc-Lifecycle-Report`,
  `Doc-Lifecycle-Approval-State`, `Doc-Lifecycle-Records`), the skipped records are listed and
  derived-checked so a short list hides nothing, and the artifact is never repository state.
- Superseded: the 2026-07-03 entry below (doc bloat nightly design), both halves — "the merge
  itself is the human approval gate", and "bloat output is always a draft PR". Also narrowed: the
  2026-07-02 entry's marker advancing on a merged sync pull request, whose lane is removed here.
  The 2026-07-26 Stage 0 entry (#59) is the partial predecessor: it bounded the blast radius with
  report-derived path authorization and no `git add -A` in a model lane, and left this semantic
  gap explicitly open.
- Code: `CONTEXT.md`, `plugins/doc-lifecycle/engine/doclifecycle/approval.py`,
  `plugins/doc-lifecycle/engine/doclifecycle/applier.py`, `.github/workflows/doc-apply.yml`;
  removed: `doc-sync.yml`, `doc-bloat.yml`, `authorize-paths.py`, `sync-gate.py`

## 2026-07-27 — a cached judgment is keyed by its whole lineage, not by content alone (#77)
- Evidence: issue #57's distilled-decisions comment (2026-07-26): segmentation is deterministic
  and "unit identity = content digest", so "finding digests, cache keys, and approval binding rest
  on reproducible identity" — content digests are the *unit's* identity, and lineage is what wraps
  them into a cache key. The superseded mechanism is `plan-chunks.py`'s `chunk_id()`, which
  content-addressed a chunk by sha256 over its members' `(path, content-sha256)` pairs and nothing
  else, and `doc-bloat.yml`'s resume step, which carried prior runs' chunk results forward on that
  identity ("content-addressed ids drop any whose docs changed"). What is removed here is the
  cross-run reuse, not the planner: `plan-chunks.py` survives as `detecting-doc-bloat`'s own
  bounded-chunk planner, where a content-addressed id is an id within one run and nothing carries
  a judgment across runs on it.
- Decided: a cached semantic result cannot outlive any input that could have changed the judgment
  it records, so the key folds all of them — document bytes, source-evidence bytes, the document
  inventory, the consumer's audit configuration, the registry, the ruleset version, the artifact
  schema version, the plugin version, and the repository and base-commit identity. Two keys
  differing in exactly one field hash to different slots, so changing any one is a miss and never
  a stale hit. A key match is not sufficient either: the stored entry is re-run through the landed
  report validator, not a parallel one, and there is no path that returns a stale or unverified
  payload.
- Still binds, and this is what the old key could not see: the chunk id omitted every input except
  the bytes. Upgrading the plugin left yesterday's verdicts — produced by the previous detection
  policy — served as today's findings, because the policy version was not in the key. The audit
  configuration that bounded and grouped the corpus was not an input to the digest at all — it
  reached an id only by way of which files ended up in a chunk and, for a policy scope, the id's
  one-letter prefix — so nothing in the key recorded which audit had planned that chunk, and any
  configuration change those two did not register left the id, and the result cached under it,
  standing. A chunk's
  verdicts depend on the corpus around it, and no inventory digest was in the key. And a carried
  result was pinned to no commit. The shape-only validation the legacy lane ran over a carried
  result could confirm the file parsed and named its chunk; it could not know the world had moved.
- Superseded: the 2026-07-07 entry below (bloat scale hardening), whose claim that content
  addressing means "cross-run resume never reuses a stale result" was true only for the single
  input the key carried. Consistent with the 2026-07-26 entry (#60): digests are taken over
  canonical JSON of meaning, so reformatting is not a change and changing a rule is.
- Also settled here: `.github/doc-sync/last-stales.json` is removed. The 2026-07-27 entry below
  (#75) already recorded that its recurrence keys are a location identity — a record's file, line
  number, and kind — which the new contract replaces with content digests, so it cannot be
  re-keyed. It retires with the lanes that read it.
- Code: `plugins/doc-lifecycle/engine/doclifecycle/cache.py`,
  `plugins/doc-lifecycle/engine/doclifecycle/report.py`,
  `plugins/doc-lifecycle/engine/README.md`, `tests/engine/acceptance/scenario_cache_test.py`;
  removed: `doc-bloat.yml`'s resume step, `last-stales.json`

## 2026-07-27 — a version comparison is not a review (#77)
- Evidence: issue #57's distilled-decisions comment (2026-07-26), "Still CI-driven": "Upgrade
  stays a reviewed version-bump PR." The mechanism this entry supersedes is the upgrade lane's
  authorization model: `upgrade-gate.py compare` is a semver comparison, and "a strictly newer
  release exists" was the entire authorization for cloning that release and running its own
  `apply-upgrade.py` against the consumer's workspace, in a job holding `contents: write` and a
  push token, before any human in that repository had read a line of it.
- Decided: the trust assumption is named rather than left implicit. Publishing a tag on this
  marketplace is not a consumer's decision to run new code, and a version number is not a
  reviewable artifact. What makes the upgrade safe is what the apply lane makes structural and
  the upgrade lane does not: refuse before anything exists, and execute nothing that was read.
- Rejected: retiring the upgrade lane with the legacy lanes. The distilled decisions keep it, and
  a consumer with no upgrade path is worse off — the vendored engine is distributed by exactly
  this route. What is superseded is the claim that a version gate is sufficient authority, not
  the lane.
- Also decided, and closed here: the lane stages an explicit path set. `apply-upgrade.py` reports
  the paths it wrote, and the credentialed step stages exactly those and refuses to commit when
  anything else in the working tree moved. This was the last `git add -A` in the repository, so
  `workflow-permissions_test.py`'s assertion that a write-scoped job never stages broadly now
  holds with no exemption — deleting that exemption is what proves it. Nothing here is a judgment
  about the diff; it is the same discipline the applier's whole-diff confinement enforces, which
  is that a write scope is not a licence to commit whatever happens to be on disk.
- Known gap, tracked as #127 and wired as blocking #77 — **superseded by the 2026-07-27 entry
  "publishing a tag is not a consumer's decision to run new code (#127)" above, which closed it.**
  Left standing as the record of what was true then. Stated plainly, and near the top rather
  than as a footnote, because this entry would otherwise read as a guarantee it does not carry:
  the lane still runs on a schedule, and still executes the target release's own upgrade logic
  from the freshly cloned checkout, in a job holding `contents: write` and a push token, before
  any human in the consumer's repository has read a line of it. So a reviewer sees a pull request
  describing an execution that already happened. It runs no model, so it carries no injection
  surface — which is why Stage 0 (#59) left it alone, and the exposure is supply-chain rather
  than prompt-borne. The fix is a trust split of the kind `doc-audit.yml`/`doc-apply.yml` already
  demonstrate, and it is real design work rather than a patch, which is why it is its own issue
  and not folded into a change that already removes two lanes.
- Superseded: the 2026-07-07 entry below (deterministic doc-sync upgrade), whose decision to run
  `apply-upgrade.py` "from the pinned target checkout … so the target version's own upgrade logic
  applies" stands as the mechanism and no longer stands as sufficient authorization. Its real win
  is untouched and still binds: the lane runs no model, so its write scopes never sit behind a
  model process. Also narrowed: the 2026-07-07 self-upgrade entry's "detection == regeneration",
  which is pre-review execution stated as a virtue.
- Code: `.github/workflows/doc-sync-upgrade.yml`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py`,
  `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/upgrade-gate.py`,
  `tests/scripts/workflow-permissions_test.py`, `.github/workflows/doc-apply.yml`

## 2026-07-27 — POLICY stays legacy pending skill migration (#77 follow-up)
- Evidence: found while implementing #77 and deliberately left alone there. `bloat.py`'s module
  docstring and the engine README both call the bulk verdict `POLICY` a departure from — and the
  `detecting-doc-bloat` skill's — "legacy contract", already gone from `doclifecycle.bloat`'s six
  verdicts. `detecting-doc-bloat/SKILL.md`, its `plan-chunks.py` (the `policy_scope` config key,
  the `POLICY_PROMPT` dispatch, the whole "policy chunk" mode), and
  `docs/guides/auditing-doc-bloat.md` (seven verdicts, a `POLICY` row) all still instruct and
  document it. No `bloat-audit` CLI command exists, and neither `bloat-plan` nor `context-index`
  is wired into any workflow — `doc-audit.yml` has cut over drift, not bloat; #77 retired the
  legacy *write* lanes (`doc-sync.yml`, `doc-bloat.yml`) but named `plan-chunks.py` and the bloat
  output validator as surviving with "non-legacy owners" — the two detecting skills' own
  read-only tooling (`HANDOFF.md`, 2026-07-27 entry) — not as migrated to the engine's verdict
  set.
- Decided (POLICY is retired in the target architecture, not in what ships today): the engine's
  scope mechanism (`enumerate_scope`, `bloat.SCOPE_VERDICTS` — an enumerable `set`/`glob`/`kind`
  rule on `RETIRE-DOC`, resolved from the corpus-wide context index) is the one correct successor
  to a hand-declared `policy_scope` directory, and no second bulk-verdict shape is wanted once the
  skill migrates. `bloat.py` and the engine README need no change — they already scope the claim
  correctly ("the legacy skill's `POLICY` verdict is deliberately absent").
- Decided (the live skill keeps `POLICY` until it migrates): `plan-chunks.py` has no
  context-index-driven scope mechanism of its own, so removing `POLICY` now would drop the only
  working bulk-directory-retirement path (e.g. pruning a whole `docs/superpowers`-style tree) with
  nothing to replace it — a functional regression dressed as a docs fix. `SKILL.md`,
  `plan-chunks.py`, and the guide instead each gained one explicit note that `POLICY` is this
  skill's own legacy shape, superseded in the engine, migrating in a future stage this entry does
  not schedule. `tests/scripts/validate-bloat-output_test.py` and `plan-chunks_test.py`'s
  `POLICY`-pinning assertions are correct as written — they pin the shape the live skill still
  produces — and are left unchanged.
- Rejected: stripping `POLICY` from the skill/planner/guide to match the engine outright. That
  reads as "make all four agree" on its face, but the engine's bulk-scope mechanism was never
  wired into `plan-chunks.py`, so agreement-by-deletion would ship a real capability loss, not a
  documentation fix.
- Still binds: when the bloat skill migrates to `doclifecycle.bloat` (not yet scheduled), `POLICY`
  and `policy_scope` retire from `plan-chunks.py`, `validate-bloat-output.py`, `SKILL.md`, and the
  guide together, in the same change that gives the skill a working replacement for bulk directory
  retirement.
- Code: `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md`,
  `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py`,
  `docs/guides/auditing-doc-bloat.md`

## 2026-07-27 — a fix that speaks for another document is a person's to approve (#123)
- Evidence: `docs/plans/2026-07-27-shadow-parity-gate-rerun.md`, G4 — DRIFT-023, the second
  shadow cycle's one false positive and #77's only blocker. A true sentence was called `STALE`
  because the document it pointed at had been superseded, and its `fix` repointed the sentence at
  the successor while asserting the successor "carries criteria and verdict". At the audited
  commit that file's Verdict section read "Not yet run". The record carries an exact preimage and
  an `evidence.source`, so `policy.py` would have minted for it with no human.
- Decided, and it is the mechanical half that carries the guarantee: `policy.py` refuses a record
  whose `fix` changes which documents the passage names — `policy-fix-names-other-document`. A
  preimage pins what a run read; a `fix` is what a model wrote, and a document the replacement
  adds or drops is one the record pins nothing from. A citation does not settle it: a pointer
  says one line was consulted, and what a document contains is the thing being asserted. Both
  directions, not just additions: a preimage that *mentions* a file has pinned the sentence and
  not the file, so an additions-only rule would admit a repointing that swapped which document
  the sentence is about (found by this PR's spec review, with a working bypass). The finding's own
  document is excluded, by its repository path and not its filename — rewriting a passage that
  names its own file speaks for nothing else, while a bare filename names no one document
  (seven files here are `SKILL.md`). Recognizing a file reference is `paths.path_references`,
  beside the classifier whose suffix tables it reuses, so one module answers "what is a path".
- Decided, as defense in depth and not as a guarantee: `detecting-doc-drift` now states that a
  `fix` naming a file is settled by opening that file, and `doc-audit.yml`'s prompt names
  fix-authoring among what it sends workers to that skill for. This addresses the wrong fix being
  *authored*, which the exclusion does not — but it is model behavior, so nothing rests on it.
- Rejected: the prompt change alone. It is the narrowest correction the gate's record suggested,
  and it has no hard guarantee — verifying it means re-running workers, and a worker that
  regressed would land the assertion unattended, which is the budget the criterion sets at zero.
- Rejected: a new record code for "pointer superseded". The most structural option and the
  biggest contract change: producers, validators, the applier's remedy table, and every consumer
  switching on the code. It also asks a model to classify its own finding into the class that
  refuses it, where the exclusion reads what the model wrote. Left available — the exclusion does
  not foreclose it.
- Named limits, both past what shape can settle and both left to the method rule: a document
  named without its suffix (`docs/plans/2026-07-27-rerun`) and one named in prose alone ("see the
  engine README"). And a fix that repoints is now a person's to approve even when the model got
  it right — one more record in the review queue, paid against a class whose error budget is zero.
- Verified: G4 re-measured on the recorded cycle's own report — 24 records, 12 eligible before,
  11 after, exactly one decision changed, the other 23 identical
  (`docs/plans/2026-07-27-shadow-parity-gate-rerun-addendum.md`, which states why no third live
  cycle was run). Eleven mutants of the guard, the comparison, the carve-out, and the recognizer,
  each killed — two of them only after review, which found a mutant the first round's tests let
  live and a bypass the first round's comparison allowed.
- Code: plugins/doc-lifecycle/engine/doclifecycle/policy.py,
  plugins/doc-lifecycle/engine/doclifecycle/paths.py,
  plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml,
  tests/engine/policy_test.py, tests/engine/paths_test.py

## 2026-07-27 — the audit lane declares tools without widening its grant (#118)
- Evidence: `docs/plans/2026-07-26-shadow-parity-gate.md`, "Cause B" — its second forcing
  condition, "the workers' tool set … did not include `gh`", which #115 left open. Six
  `UNVERIFIABLE` findings over `docs/agents/issue-tracker.md` were settleable with
  `gh <sub> --help`, and the model job's grant is
  `Skill,Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)`.
- Decided (the narrow option the issue asked to cost first, and it works): the lane may declare
  tools, and it reaches them through `scheduling-doc-sync/scripts/probe-evidence-tool.py` under
  the *existing* `Bash(python3 *)` allowance. The grant does not widen at all. What the probe
  can reach is enumerable in two directions — which programs (only those named in
  `.github/doc-sync/evidence-tools.json`, consumer-owned, seeded `{"tools": []}`, never
  overwritten by an upgrade) and how (only `<tool> <subcommand words> --help|--version`, exec'd
  directly with no shell, with credential-shaped variables stripped from its environment). The
  same config renders `drift-audit --evidence-command`, so the boundary the report publishes
  and the tools the model can run are one list rather than two that drift apart. This install
  declares `gh`.
- Rejected: adding `gh` to `--allowedTools`. Those patterns are prefix-matched, so `Bash(gh *)`
  is not a grant for `gh <sub> --help` — it is `gh api` and `gh pr list` too, i.e. GitHub API
  surface and network egress declared for a job kept deliberately token-free. The rejection is
  now a checked claim, not a convention: `tests/scripts/workflow-permissions_test.py` refuses
  any `--allowedTools` naming a Bash executable other than `git` or `python3`, across every
  shipped template and this repo's install.
- Rejected: leaving the lane tool-free. That was a legitimate outcome, and it stays the
  *default* for every consumer — an install that declares nothing renders no
  `--evidence-command`, exactly as before. But for this repository it would have preserved
  Cause B's six false findings permanently, including the real `STALE` they hid, on the very
  gate re-run (#117) that has to justify retiring the legacy lane.
- Named limit, not papered over: the probe reads a program's own interface and nothing else, so
  the one Cause B claim that needs `gh pr list --json bogus` to enumerate real field names
  (`authorAssociation`) is still not settleable here and stays honestly `UNVERIFIABLE`. Widening
  the probe to arbitrary flags would re-open exactly the surface the `--allowedTools` rejection
  above closed; the six `--help`-settleable claims are what this change buys.
- Still binds: `Bash(python3 *)` was already, in capability terms, local execution — which is
  why the workflow's own comment calls the tool list "ergonomics, not the boundary", and why the
  real boundary remains `contents: read`, no `GH_TOKEN`, and `persist-credentials: false`. This
  change does not enlarge that boundary; it makes one route through it enumerated, tested, and
  declared in the report's lineage instead of unavailable.
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/probe-evidence-tool.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md,
  tests/scripts/probe-evidence-tool_test.py, tests/scripts/workflow-permissions_test.py,
  tests/scripts/audit-workflow_test.py

## 2026-07-27 — the evidence boundary grows a second half: declared tools (#115)
- Evidence: `docs/plans/2026-07-26-shadow-parity-gate.md`, "Cause B" under criterion G4 — six
  false `UNVERIFIABLE` findings over `docs/agents/issue-tracker.md`, and one genuine `STALE`
  the same gap hid (`gh pr list --json …,authorAssociation,…`; `gh pr list --json bogus`
  enumerates the real fields and that is not one).
- Decided (of the design doc's three named directions, (a) — grow the boundary): a drift
  verdict's evidence may cite `command` instead of `source`, and `evidence_boundary` gains
  `commands`, the bare executable names a run declared it could run. Rejected (b), narrowing
  `detecting-doc-drift`'s method to stop sanctioning tier-2 tool evidence: the claims are
  genuinely checkable, and a method that refused to check them would convert six false
  findings into six permanently unanswerable ones — including the real drift. Rejected (c), a
  document kind for external-tooling claims: kind is the *truth obligation* a document carries,
  and `docs/agents/issue-tracker.md` owes exactly what every living document owes (currently
  true, assertions carry evidence); a fourth kind would have split the taxonomy along where the
  evidence lives rather than along what is owed, and a document mixing tool claims with repo
  claims would have had no kind at all.
- Decided (against the design doc's suggested output *digest*): the citation is the command
  plus the existing `observed` fact, not a hash of the tool's output. An external tool's output
  changes with its version, so a digest would expire on every upgrade of a program this
  repository does not pin — it would pin nothing durable while reading as though it did. It
  would also ask a model to compute a hash, which is the transcription failure #116 exists to
  fix. The cost is named rather than papered over: a `source` is pinned by `base_commit` and a
  `command` only to the environment that ran it, which is precisely why auto-apply refuses one.
- Not decided here (deliberately out of scope): Cause B named *two* forcing conditions, and this
  settles the first. The second — the audit lane's workers cannot run `gh` at all — is a
  trust-boundary question about a credentialed workflow (`--allowedTools` is prefix-matched, so
  there is no way to allow `gh <sub> --help` without allowing `gh api`), and it gets its own
  change: #118.
- Still binds (the guarantees the growth had to leave intact): the world stays closed —
  `commands` is empty by default, and a citation outside it is `drift-evidence-outside-boundary`,
  the same code and reason as a path outside the globs. The boundary is still lineage and still
  never opened: the engine executes nothing it declares. A citation must be one shell-free
  command line, so a report never presents a shell program as a single read-only command a
  reader re-runs. And auto-apply refuses a command-cited record by name
  (`policy-external-evidence`): mechanical means re-derivable from the commit, and this pointer
  is not.
- Code: plugins/doc-lifecycle/engine/doclifecycle/report.py,
  plugins/doc-lifecycle/engine/doclifecycle/drift.py,
  plugins/doc-lifecycle/engine/doclifecycle/policy.py,
  plugins/doc-lifecycle/engine/README.md, CONTEXT.md

## 2026-07-27 — this repo's registry, and what the migration leaves behind (#75)
- Evidence: `python3 -m doclifecycle migration-draft` and `migration-dry-run` against this
  repository, run through the `scheduling-doc-sync` migration door; issue #57's
  distilled-decisions comment (2026-07-26), "Classification lives in a registry".
- Decided (roots are widened past the inference): the drafted roots were `CLAUDE.md`,
  `CONTEXT.md`, `README.md`, and `docs`, which left every `plugins/**/*.md` file unaudited —
  and the plugin's skills are markdown that makes claims about this repo, which the legacy
  diff-scoped drift lane did audit (`.github/doc-sync/last-stales.json` records a STALE it
  found in `skills/scheduling-doc-sync/SKILL.md`). `plugins` is declared a fifth root, so the
  registry claims the product's own docs, under one broad `plugins/**/*.md → living` rule
  rather than the draft's nine per-directory globs: a new skill is then audited the day it
  lands, not the day someone remembers to add a rule for it.
- Decided (the remaining narrowing is ratified, not a gap): `migration-coverage-narrowed`
  reports the tracked `.md` files under no root, and what it names is `tests/baselines/`,
  `tests/fixtures/`, and `tests/docs-ab/` — recorded test evidence, where a RED baseline is
  supposed to stay wrong — plus `.github/`, which holds vendored copies rather than sources.
  They stay outside the roots.
- Decided (the legacy exclusions are not carried into the registry): `audit-scope.json`
  excluded those same `tests/` subtrees, but a registry `exclude` only prunes *within* a
  declared root, and `tests` is under none. Carrying them would be configuration that changes
  no coverage while sitting in every report's registry digest. This entry is the record of
  what was kept out.
- Decided (`docs/decisions.md` is narrative, not living): the draft inferred `living` because
  the file carried no `> As of` anchor. A decision log is narrative by design — honestly dated,
  never line-verified — and `writing-docs` scopes decision records out for exactly that reason.
  Classified `living` it would have had every superseded entry re-checked against today's code,
  which is the drift a superseded entry exists to record. The anchor is added at the top of this
  file to meet the obligation the kind carries.
- Decided (no waiver re-keying was needed): `drift-waivers.json` holds no waivers, so the dry
  run reports `rekeyed: []` and `needs_rewaiving: []`. Nothing was dropped because nothing was
  there; a future waiver re-keys through the same door.
- Decided (`last-stales.json` is kept, against the dry run's disposition): the dry run
  classifies it as a `cache` artifact, `carried: false` — its recurrence keys are a location
  identity (a record's file, line number, and kind), which the new contract replaces with content
  digests, so it cannot be re-keyed. It is
  nonetheless left in place rather than deleted, because the legacy read lanes still consume it
  and are still running. It retires with them (#77). Recorded here so the drop is stated, not
  silent.
- Code: `.doc-lifecycle/registry.json`

## 2026-07-27 — one fixing-docs door; apply discipline moves into the engine (#70)
- Evidence: issue #57's distilled-decisions comment (2026-07-26), "Engineering shape": skills go
  8 → 7, "`fixing-doc-drift` + `fixing-doc-bloat` merge into one `fixing-docs` door … with
  per-record-type guidance as internal routing; `references/apply-discipline.md` is superseded by
  the applier contract", and "`doc-distiller` emits edit plans … instead of writing files."
- Decided: the merge is a consequence of the applier (#69), not a cleanup — after minting, both
  bodies are the same flow (mint approval set → edit plan → applier → present the staged diff),
  and the record's finding code routes the remedy inside one skill via `RECORD_REMEDIES`.
- Decided (discipline is enforced, not restated): `references/apply-discipline.md` is deleted
  rather than repointed. Its five rules each have a mechanical owner now — the approval set is the
  authorized set, the confinement check is the blast radius, the preimage check is the anchor, the
  trailers are the evidence — and its §5 had gone actively wrong, telling the agent the evidence
  rides in a commit it produces, where the applier never stages and never commits.
- Decided (the distiller stops writing): `agents/doc-distiller.md` returns edit-plan operations
  and its tools drop `Write`/`Edit`. One record authorizes two paths, so residue for a third
  document is reported for its own approval rather than smuggled past a check that would refuse it.
- Still binds: a validated, current approval set is the only authority a write may rest on, and
  the applier is the only writer — an interactive skill has no exemption from either. Superseded:
  the 2026-07-03 entry below names `references/apply-discipline.md` as the owner of apply-only
  discipline; that owner is now the applier contract in `plugins/doc-lifecycle/engine/README.md`.
- Known gap, filed not fixed: `bloat.DESTINATION_VERDICTS` excludes `DISTILL`, so no record the
  bloat audit mints can carry a `destination` — `create-document` refuses
  `plan-target-not-record-target` and only the lossy `retire-document` half executes. A residue
  destination has to be its own concept, since bloat's destination check refuses any path the
  inventory does not already hold. Recorded in `tests/baselines/fixing-docs-merge-green/GREEN-results.md`.
- Code: `plugins/doc-lifecycle/skills/fixing-docs/SKILL.md`,
  `plugins/doc-lifecycle/agents/doc-distiller.md`,
  `plugins/doc-lifecycle/engine/doclifecycle/applier.py`
- Baselines: `tests/baselines/fixing-docs-merge-red/`, `tests/baselines/fixing-docs-merge-green/`

## 2026-07-26 — migration door: registry inference + dry-run upgrade (#74)
- Evidence: issue #57's distilled-decisions comment (2026-07-26), "Adoption / migration": infer
  a draft registry from existing state, "a human reviews the draft as a normal PR diff (glob
  rules, not per-file slog)", and "**Unclassified docs block the upgrade** (fail closed) — no
  'unclassified' dumping-ground bucket."
- Decided (the draft is globs, not files): `draft_registry()` emits one rule per directory
  carrying that directory's dominant classification, plus a per-file override only where a
  directory disagrees with itself. A per-file registry would be technically correct and
  unreviewable — nobody audits a thousand-line diff, so the door would produce rubber-stamped
  classification. Every rule carries the `basis` it was inferred from and the documents it
  claims, so a wrong rule is traceable to its evidence rather than argued about.
- Decided (roots come from evidence, not a sweep): top-level markdown files, the directory
  holding `docs/doc-scope.md`, and directories the waivers / `policy_scope` / audit-scope
  `include` reach into. `exclude` is deliberately *not* evidence — naming a subtree to keep it
  out is not a declaration that it is a root — and no inferable root is `migration-no-roots`
  rather than a guess. `--root` replaces inference outright.
- Decided (living is the default kind): precedence is anchor → policy scope → planning
  location → living, matching the legacy bloat planner so the door and the audit cannot disagree.
  Living last is the safe default: it owes the most, so a wrong guess over-audits rather than
  quietly exempting a document.
- Decided (a dry run resolves the half of finding identity it can): a legacy waiver re-keys
  cleanly when its quoted text lands on determinate assertion-capable units; the reported key is
  the **unit digest** (plural, with the `matched` count), not a finding digest. A finding digest
  also covers report lineage and the finding code, both bound when an audit runs — emitting one
  here would be a promise about a run nobody has made. The breadth bound is the audit's own
  `MAX_WAIVER_UNITS`, not a stricter one: calling anything past a single unit ambiguous would
  report waivers as broken that will keep working, overstating the cost this dry run exists to
  state accurately. Five named reasons cover the rest (not inventoried, carries no assertions,
  unreadable, claim not found, claim too broad), each with what to do.
- Decided (the draft's claims are re-derived, not assumed): a per-file override is still a glob,
  so a document named with `*` or `?` emits a rule that also claims its neighbours — and
  overrides sort last, so it wins silently. `registry.parse()` cannot catch it (the file is well
  formed), so every claim is re-checked through the parsed registry and a mismatch is
  `migration-draft-inconsistent`.
- Decided (old artifacts are rejected, never coerced): closed-world over `.github/doc-sync/` —
  anything the contract does not carry across and that is not a vendored script is an artifact
  of the old world — plus the two report names the legacy workflows write at the repo root. A
  name-based class (report / approval / cache) only picks which regeneration instruction the
  reader gets; the disposition is the same for all three, because none of them carry the lineage
  the new contract binds identity to.
- Decided (version-to-version, and it refuses rather than guesses): one contract,
  `legacy-doc-sync-to-registry`, spanning `installed-version` → `PLUGIN_VERSION`. Absent is a
  fresh install; unparseable and ahead-of-engine are refusals, using the upgrade gate's numeric
  comparison so the two agree about which install is older.
- Decided (the door never writes): both commands are read-only and the suites compare the whole
  tree byte for byte before and after, refusal paths included. The migration is a human landing
  a reviewed file; the dogfood migration itself is #75.
- Rejected: an `unclassified` kind or bucket for documents no rule claims. A bucket is how a
  corpus quietly stops being audited — the paths are named and the upgrade stops.
- Rejected: a second corpus walk inside the door. `registry.without_rules()` + the now-public
  `inventory.walk_root()` mean the documents a draft proposes rules for are exactly the ones the
  resulting inventory holds. `drift.load_waivers()` was made public for the same reason, and
  root evidence goes through `paths.repository_relative_problem()` rather than hand-trimmed
  strings, since path safety already has one owner.
- Rejected: a registry of version-keyed migration steps. There is exactly one migration — every
  pre-registry install looks alike, because none of them had a registry — so a step table would
  be structure for a need that does not exist yet. The contract is named and the versions it
  spans are reported; the second migration is what earns the table.

## 2026-07-26 — engine package + registry-driven closed-world inventory (#57 stage 1, #60)
- Evidence: issue #57's distilled-decisions comment (2026-07-26) commits to "one stdlib-only
  Python package … thin `python3 -m` CLI entrypoints wrap library functions, so library and
  command behavior cannot diverge", with classification living in a registry rather than in
  first-line markers. #60 is its first slice; the eight helper scripts are absorbed in later
  stages, not now.
- Decided (registry location): `.doc-lifecycle/registry.json`, a tool-owned dotdir at the
  consumer's repo root rather than a file per concern scattered across `docs/` and
  `.github/doc-sync/`. Later consumer state (waivers, markers, lockfile) moves under the same
  dir as its ticket lands.
- Decided (classification precedence): rule order, **last match wins** — the .gitignore mental
  model. Glob specificity is deliberately not consulted: order is visible in the file,
  specificity is not, so precedence stays reviewable in a diff.
- Decided (closed world's boundary): `roots` may not overlap or repeat, so a document belongs
  to exactly one root and cannot be inventoried twice; `extensions` (default `[".md"]`)
  declares what counts as a document, so coverage language can name exactly what it covered
  instead of hiding non-markdown docs; naming a directory in `exclude` excludes its subtree
  (a bare-directory no-op would be a silent coverage hole).
- Decided (identity): digests are taken over canonical JSON of *meaning*, not file bytes —
  reformatting a registry must not invalidate a report, while changing a rule must. Rule order
  is part of the registry digest; root/exclude/set/extension order is normalized away.
- Decided (failure shape): an unreadable, unparseable, or invalid registry — including a
  declared root that does not exist — returns a typed `Invalid` carrying every problem found
  in one pass, with no `documents` field at all. A partial inventory a reader could mistake for
  the corpus is worse than a refusal. The five-state result model arrives with the report
  contract (#62); this slice ships `ok`/`invalid` only.
- Decided (invocation): a `doc-lifecycle.py` launcher beside the package so a skill can run the
  engine from a plugin checkout with no PYTHONPATH; it and `python3 -m doclifecycle` both call
  `cli.main()` and hold no logic.
- Interim, not a second owner: the registry's path/glob hygiene checks and the walk's refusal to
  follow symlinks are needed before the path-authorization module (#67) exists, which becomes
  their single owner when it lands.
- Code: `plugins/doc-lifecycle/engine/` (package + launcher + `README.md`),
  `tests/engine/{inventory,cli}_test.py` + `support.py`, `.github/workflows/release.yml`
  ("Engine tests", discovery-based so a new suite wires itself), `CLAUDE.md`, `CONTEXT.md`.
- Source: https://github.com/aj604/toolshed/issues/60 (parent: #57)

## 2026-07-26 — Stage 0: model steps hold no repository write authority
- Evidence: issue #57's distilled decisions (2026-07-26) name the injection→mutation hole as the
  one thing that must not wait for the re-architecture: the scheduled lanes combined repository
  write permissions, a model process with broad tools, and `git add -A` staging, so a
  prompt-injected or simply mistaken run could turn a documentation workflow into a general
  repository mutation path. Issue #59 is that stage, landed on the legacy workflows.
- Decided (job split): every job invoking `anthropics/claude-code-action` now runs with
  `permissions: contents: read` (+ `id-token: write` for the OAuth exchange), checks out with
  `persist-credentials: false`, and carries no `GH_TOKEN`. Its output leaves as an artifact — the
  report, or a `git diff --binary --no-renames` patch of its edits. `doc-sync.yml` splits into
  plan/detect/fix/land; `doc-bloat.yml` splits its prune lane into `prune` (model) and
  `prune_land` (credentialed). The credentialed jobs (`land`, `prune_land`, `distill_merge`) run
  no model.
- Decided (the report is the authority): new `authorize-paths.py` derives the authorized path
  set from the validated report per lane — drift takes each STALE record's file; prune takes each
  record's `doc` plus `EXTRACT-AND-MOVE` targets; distill takes record docs, `POLICY` files,
  `MERGE-DOC` targets, and `docs/decisions.md`, and because the distiller *chooses* where residue
  lands and which inbound references it repoints, it authorizes the audited documentation scope
  rather than an exact list. Paths under `.git/`, `.github/workflows/`, or `.github/doc-sync/`,
  paths escaping the repo, and non-documentation files are never authorized — from a record or
  from a patch. The credentialed job stages `git add --pathspec-from-file=` that list and
  re-checks what actually landed.
- Still binds: a patch naming an unexpected path fails the run *before* anything is applied — no
  PR, nothing staged; patches are generated `--no-renames` (a rename record reports only its
  destination to `git apply --numstat`, so `authorize-paths.py` refuses one outright); the
  workflow-owned state files (marker, `last-stales.json`) are staged by the credentialed job
  under `--allow-workflow-state`, never reachable from a model patch; `tests/scripts/
  workflow-permissions_test.py` fails the release if a model job gains a write scope or a write
  job gains a model, and `install-parity_test.py` fails it if the dogfood install and the
  plugin's wiring diverge beyond the install's knobs.
- Consequence: this upgrade changes the workflow templates themselves, so consumers take the
  documented `blocked-workflows` path (patch artifact + fail-loud instructions) rather than an
  auto-landing upgrade PR — the Actions token cannot push `.github/workflows/`.
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync-upgrade.yml,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/authorize-paths.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md
- Source: https://github.com/aj604/toolshed/issues/59 (parent: #57)

## 2026-07-12 — grow-loop sensors + unowned-bucket owners (review findings 1,3,4,6)
- Evidence: 2026-07-12 architecture review — the shrink loops (drift, bloat) have sensors,
  gates, and cadence; the grow loop had only an in-session rule, and the buckets automation
  can't settle (UNVERIFIABLE puffery, recurring re-stales) had no disposition owner. Six
  findings verified against the repo; this release lands four (F1a, F6, F3, F4, F1b). F5
  (monthly full-audit drift lane) and F2 (narrative-doc claims in that audit) are deferred as
  a follow-up — the full-audit lane is the heavy piece and rides its own release.
- Decided (F1a first-rediscovery tally): the first-time answer exemption in `growing-docs`
  now costs one logged `- seen: <date> <occurrence>` line under the matching `docs/doc-scope.md`
  Deferred item; a live signal matching an item that already carries a `seen:` line **is** the
  second rediscovery. The log — not the conversation — is the cross-session memory the
  second-rediscovery rule needs.
- Decided (F6 direct narrative ask): `growing-docs` description now claims the direct
  "write an ADR/tutorial/walkthrough" ask (it owns the narrative template; writing-docs scopes
  those out), closing the routing gap on the door to the rich half of the ecosystem.
- Decided (F3 UNVERIFIABLE waiver): the detector stays pure (emits every UNVERIFIABLE);
  disposition is a run-surface concern. New consumer file `.github/doc-sync/drift-waivers.json`
  (`{file, claim}` exact-match identity — reworded → resurfaces, new authorship is a new
  decision) consumed by `render-report.py` pr-body/pr-title/no-drift-summary. A no-drift night
  now surfaces "N unverifiable claim(s) await disposition" (the previously-never-seen bucket).
  Seeded by the installer and by `apply-upgrade.py` (only-if-absent, never touched thereafter —
  audit-scope precedent). `detecting-doc-drift`'s dangling "human/bloat decision" handoff now
  cites the waiver flow instead of a bloat lens that never existed.
- Decided (F4 recurrence): `sync-gate.py stale-state` writes one run of STALE locations onto
  the PR branch (`.github/doc-sync/last-stales.json`) so it advances only when the fix merges;
  next run's `pr-body --prev-stales` tags a same-location re-stale (±3 lines, same kind) with a
  re-shape-don't-re-fix hint. The loop becomes adaptive without records carrying history.
- Decided (F1b growth surface): `render-report.py growth-backlog` renders `docs/doc-scope.md`
  Deferred items + `seen:` tallies on every weekly doc-bloat run (skip paths included), so the
  grow backlog is seen on the same cadence as the prune backlog. Tolerant parser: a missing
  file or empty section degrades to one quiet line, never a failed run.
- Still binds: detection is never disposition (drift emits, the pipeline waives); consumer
  state (`audit-scope.json`, `drift-waivers.json`, marker, `last-stales.json`) is never reset
  by an upgrade; the growing-docs STOP list and one-smallest-artifact rule bind the tally path.
- Code: plugins/doc-lifecycle/skills/growing-docs/SKILL.md,
  plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md,
  plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md,
  scheduling-doc-sync `scripts/{render-report,sync-gate,apply-upgrade}.py`,
  scheduling-doc-sync `doc-sync.yml`/`doc-bloat.yml`, the dogfooded `.github/` mirror, and
  `.github/doc-sync/drift-waivers.json`.
- Guarded by `tests/scripts/{render-report,sync-gate,apply-upgrade}_test.py`; growing-docs
  skill text re-GREENed in `skill-workspaces/` iteration-3 (with-skill 22/22 vs prior 21/22).
- Source: docs/plans/2026-07-12-review-findings-growth-and-lifecycle-design.md (retained —
  F5/F2 sections describe the deferred follow-up).

## 2026-07-09 — doc-bloat distill lane fan-out (apply-side scale)
- Evidence: career-compass run 28912881170 (2026-07-08) — the hardened sweep matrix (35 chunks)
  finished in ~9 minutes, but the distill lane took 250 of the run's 260 minutes: one uncapped
  headless invocation dispatching doc-distiller 56× sequentially in a single session, whose
  transcript re-ships every turn (cost quadratic in records) and outlives the prompt-cache TTL.
  On hundreds of planning docs the lane extrapolates to days.
- Decided: fan the distill lane out like the sweep. New `plan-distill.py` (scheduling-doc-sync
  `scripts/`, vendored — the set is now seven) plans the lane's actionable records into
  content-addressed groups: the lane mapping is imported from the co-located `sync-gate.py`
  (one owner), `DISTILL pending-implementation` is never planned, DISTILL-ready records group
  by artifact directory (the plan-time affinity proxy for distill-time targets — same-dir plans
  land residue in the same narrative docs, so same-target work rides one executor), and the
  mechanical verdicts (MERGE-DOC/RETIRE-DOC/POLICY) form one inline group. `--emit-prompt`
  renders each dispatch slice verbatim; each matrix job applies its group one-commit-per-record
  and exports a format-patch series plus a seam-validated sidecar; a deterministic merge job
  lands the series with `git am -3`, union-resolves `docs/decisions.md` append-append conflicts
  (append-only log), skips any other conflict loudly (per-record, never the lane), and opens the
  one draft PR with a not-landed banner (`render-report.py bloat-pr-body --merge`).
- Decided: NO turn caps anywhere on the apply side (owner call — an apply invocation is never
  truncated mid-judgment); the kill-switch is the job-level `timeout-minutes` (bounds hangs,
  not care). Retry is one fresh dispatch after a hard reset; there is no budget to escalate.
- Decided: no cross-run patch resume — a patch is a diff against a moving base. Convergence is
  re-detection: an unapplied record's artifact survives on main, the next sweep re-proposes it.
- Still binds: fixing-doc-bloat's group-executor mode treats the dispatch's record-id list as
  the human approval and the entire mandate — one commit per applied record, the sidecar at the
  named path, never push/PR/merge; `doc-distiller` is unchanged (the DISTILL method keeps its
  single owner, and one-commit-per-record is the merge's transport unit).
- Guarded by `tests/scripts/plan-distill_test.py` (lane selection, affinity grouping, ids,
  emit-prompt, sidecar seam, and the patch-merge engine incl. union resolution, against real
  git repos) and `render-report_test.py`'s wiring pins (script-borne distill lane, no
  `--max-turns` on its `claude_args`, merge job runs even when a group fails). `release.yml`
  CI now runs every `tests/scripts/*_test.py` suite (this also wired in the previously-missing
  plan-chunks and validate-bloat-output suites).
- Consequence (v0.10.0): the release rewrites `doc-bloat.yml` (and a comment in
  `doc-sync-upgrade.yml`), so existing installs' self-upgrade takes the blocked-workflows
  manual-apply path once (Actions token can't push `.github/workflows/`); the dogfood is
  hand-applied here. Script-only releases after this self-land as usual.
- Code: plugins/doc-lifecycle/skills/scheduling-doc-sync/ (SKILL.md, doc-bloat.yml,
  scripts/plan-distill.py, scripts/render-report.py, scripts/apply-upgrade.py),
  skills/fixing-doc-bloat/SKILL.md, skills/detecting-doc-bloat/SKILL.md (parallel-waves line);
  dogfood under .github/. Design: docs/plans/2026-07-09-bloat-distill-lane-fanout-design.md.

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
