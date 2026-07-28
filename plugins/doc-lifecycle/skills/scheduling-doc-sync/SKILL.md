---
name: scheduling-doc-sync
description: Use when wiring a repo for automated/unattended documentation audit — "set up doc sync", "automate drift detection", "schedule nightly doc checks", "keep docs in sync automatically" — installs the doc-lifecycle GitHub Actions (a scheduled read-only audit, a manual apply dispatch, a weekly upgrade check) instead of hand-rolling workflow YAML. Also the door for upgrading an existing install.
---

# Scheduling Doc Sync

## Overview

Installs the shipped automation into a target repo — **three workflows**:

- `doc-audit.yml` — the scheduled, read-only audit. Derives its scope from the registry, runs
  the audit engine, publishes a validated report as an artifact and a job summary. Writes
  nothing.
- `doc-apply.yml` — the manual apply dispatch. A reviewer names the record digests they approve
  from one audit run; the lane mints the approval set from that selection, plans, applies, and
  opens a pull request. The one lane that writes repository content.
- `doc-sync-upgrade.yml` — the self-upgrade lane, three jobs split by who decides and who holds
  credentials. Its weekly schedule only compares the installed version to the plugin's latest
  release and files one notice issue naming a newer one; regenerating the wiring runs solely on a
  `workflow_dispatch` carrying that version as `target`, and lands as a review PR.

**You install wiring; you do not re-derive it.** Orchestration lives in the shipped workflow
YAML; every lifecycle rule — scope, verdict contract, approval, application — lives in the
`doclifecycle` engine package (`plugins/doc-lifecycle/engine/README.md`), vendored into the
install and reached only through its public CLI. Every run-surface string lives in a shipped
script: `render-audit-summary.py` for the audit lane, `render-apply-summary.py` for the apply
lane, `render-report.py` for the upgrade lane; the upgrade lane's version comparison and the
shape-check on its dispatched target live in `upgrade-gate.py`, and which paths an upgrade may
write in `stage-upgrade.py`. Never inline audit or apply method into workflow YAML — that forks
the method from its one owner.

**The model holds no repository write authority.** Every job that invokes a model runs with
`permissions: contents: read` (plus `id-token: write` for the OAuth exchange only), checks out
with `persist-credentials: false`, carries no `GH_TOKEN`, and hands its work forward as an
artifact. The credentialed jobs run **no model**, and every one of them stages an explicit path
list — `git add --pathspec-from-file`, never `git add -A`, with no exception. The apply lane
stages the paths the engine's verified apply result emitted; the upgrade lane stages the path set
`stage-upgrade.py` authorized out of the regeneration's manifest, and refuses if git staged
anything else or left a change behind in the work tree.
`tests/scripts/workflow-permissions_test.py` fails the release if any of that slips. What none
of this establishes is that the *report* was honest — it is model output too; the pull request
the apply lane opens is where a person settles that.

**Installs are pinned, not floating.** Before each `claude-code-action` step, a
`Pin plugin marketplace` step reads the version from `.doc-lifecycle/installed-version` and
clones that release tag
(`VERSION=$(cat …/installed-version); git clone --depth 1 --branch "v${VERSION}" …/toolshed.git "$RUNNER_TEMP/toolshed-marketplace"`),
and the action step points `plugin_marketplaces` at that local path — so the skills a run
executes are frozen at the same version as the vendored wiring, and can't drift apart mid-week.
The version is read at runtime, NOT hardcoded in the workflow YAML, so the workflow files stay
byte-identical across versions — a routine upgrade changes only the lockfile, never a
`.github/workflows/` file (which the Actions token cannot push; see Upgrade mode). The upgrade
lane is the exception: its `regenerate` job clones the *target* release it is regenerating to —
the dispatched version, and only as `upgrade-gate.py normalize` re-emitted it — since
`installed-version` still holds the old version until the upgrade PR merges. Its scheduled job
clones nothing at all. Clone under `$RUNNER_TEMP`, never inside the work tree, or the exported
edit set captures it. Pin via the local checkout, NOT a
`plugin_marketplaces: …/toolshed.git#v<version>` ref — `claude-code-action`'s URL validator
requires the value end in `.git`, so a `#<ref>` fragment is rejected outright.
`doc-sync-upgrade.yml` is the only thing that advances the pin, and only via a reviewable PR.
The `plugins:` selector stays bare `doc-lifecycle@toolshed` (`claude-code-action` has no
`@version` selector there — `doc-lifecycle@toolshed@0.7.0` is invalid).

The three workflow templates are in this skill's base directory (announced when the skill
loads), and its own scripts one level down in `scripts/` — `upgrade-gate.py`,
`stage-upgrade.py`, `render-report.py`, `render-audit-summary.py`, `render-apply-summary.py`,
`probe-evidence-tool.py`. The chunk planner and the two output validators are copied from the
sibling skills that own them (install step 6). `scripts/apply-upgrade.py` is the deterministic
upgrade engine — the *target release's* copy of it is what the upgrade lane runs, so it is never
vendored into the install; `stage-upgrade.py` is vendored for the mirror-image reason, because it
is the code that bounds what that run may have written (see Upgrade mode).

## The audit lane (`doc-audit.yml`)

Two jobs, split by trust: `audit` (the model, `contents: read` + `id-token: write`, no
credential) calls the engine's own public CLI — `drift-plan` for a deterministic scope, then
`drift-audit` for the validated report; `publish` (no model, `contents: read` only, no write
scope at all — never `contents: write`, never a PR, never a commit) re-validates the report's
freshness against the live repository before rendering the run's job summary. It is still its
own job: the moment this lane needs any GitHub write to publish more than a job summary, that
write lands there, never beside the model. Every third-party action it invokes is pinned to an
immutable commit SHA (`tests/scripts/audit-workflow_test.py`).
`scripts/render-audit-summary.py` owns every string this lane puts on the run surface,
including the run that produced no report at all.

**Tier-2 tool evidence is declared, not granted.** A drift verdict may cite `evidence.command`
— a local tool it ran — instead of a repository path, but only for a tool the run declared
(`plugins/doc-lifecycle/engine/README.md`, "Lineage"). The declaration lives in
`.doc-lifecycle/evidence-tools.json` (`{"tools": []}` when seeded — tool-free until a consumer
adds to it), and `scripts/probe-evidence-tool.py` is both halves of the wiring: `declared
--flags` renders `drift-audit --evidence-command …`, and `run <tool> <words> --help` is how the
model reaches the tool, refusing any undeclared program and any invocation that is not a
`--help`/`--version` read. It runs under the model step's existing `Bash(python3 *)` allowance,
so the tool grant stays `Skill,Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)` — widening it
instead was rejected in aj604/toolshed#118, because those patterns are prefix-matched and
naming `gh` would grant `gh api` in a job deliberately given no credential
(`tests/scripts/workflow-permissions_test.py` refuses any other executable).

**Installed only into a repo that has been through the migration door.** This template requires
a landed `.doc-lifecycle/registry.json` (the document model's classification manifest), which no
consumer has until it runs the migration door ("Migration to the registry contract", below), and
it is closed-world over that registry, so it would fail on every run without one. That file's
presence is exactly what switches this lane on: `apply-upgrade.py`'s `adopted_registry()` reads
it, and only then does Upgrade mode render `doc-audit.yml`'s `{{AUDIT_CRON}}`, copy
`render-audit-summary.py`, and vendor the engine (see Upgrade mode's ownership table). Never
hand-install it ahead of that door.

## The apply lane (`doc-apply.yml`)

A reviewer reads a `doc-audit.yml` run's report, picks the record digests they approve, and
dispatches this workflow with `report_run_id`, `report_digest`, `records`, and `base`. The named
subset **is** the semantic approval — the workflow mints the approval set from it
(`mint-approval`) — and merging the pull request it opens is change approval of the actual diff.

Three jobs, split by trust: `revalidate` (deterministic, `contents: read` + `actions: read`, no
write scope) binds the downloaded report artifact to the dispatched digest, re-validates it
against the requested base, and mints the approval set; `plan` (the only model, `contents: read`
+ `id-token: write`, no GH_TOKEN, `persist-credentials: false`) authors an edit plan and nothing
else; `apply` (`contents: write` + `pull-requests: write`, no model) runs `apply-plan`, stages
exactly the paths the verified result emitted, commits with the engine's approval trailers,
pushes a branch named for the approval digest, and opens a real pull request — never a draft.

A stale report refuses at revalidation naming the lineage field that moved, and `apply` runs only
on both other jobs succeeding, so nothing is created. Dispatch inputs reach no shell: they travel
through `env:` or an action's `with:`, and the record selection is validated to be sha256 digests
before it becomes argv. `scripts/render-apply-summary.py` owns this lane's run surface — every
refusal, the staged path list, and the PR title, body, and commit message
(`tests/scripts/render-apply-summary_test.py`, `tests/scripts/apply-workflow_test.py`).

**Installed on the same condition `doc-audit.yml` is**: it needs a landed
`.doc-lifecycle/registry.json`, the vendored engine, and `render-apply-summary.py` in
`.doc-lifecycle/wiring/`, so Upgrade mode installs it for exactly the repos that carry a registry.
It has no knob — manual dispatch carries no schedule to preserve.

## The install layout

Everything the plugin installs lives under `.doc-lifecycle/`, in three tiers split by who owns
the bytes:

    .doc-lifecycle/
      registry.json  audit-scope.json  drift-waivers.json  evidence-tools.json   consumer judgment
      installed-version                                                          version lockfile
      wiring/    upgrade-gate.py stage-upgrade.py render-report.py               plugin-owned
                 render-audit-summary.py render-apply-summary.py
                 probe-evidence-tool.py plan-chunks.py
                 validate-drift-output.py validate-bloat-output.py
                 engine/                                                         vendored wholesale
      state/     sync-marker                                                     machine-written

The judgment files at the root are the ones a consumer edits and no upgrade rewrites.
`wiring/` is regenerated wholesale by the upgrade lane — a hand edit there survives until the
next upgrade and no longer. `state/` holds what the lanes wrote: only the carried `sync-marker`
today, which a fresh install does not have, so the directory exists only in an install that came
through the relocation (Upgrade mode).

The three workflow files stay in `.github/workflows/` — GitHub reads workflows only from there —
and are the only doc-lifecycle content left under `.github/`.

## Preflight (run all; report failures, don't silently skip)

1. Target repo has a GitHub remote: `git remote get-url origin`. No remote → stop; this
   pipeline is a GitHub Action. (A non-GitHub repo wants a different trigger — tell the user.)
2. `gh auth status` succeeds.
3. Auth secret: `gh secret list` shows `CLAUDE_CODE_OAUTH_TOKEN` (preferred — created by Claude
   Code's `/install-github-app`, no key-pasting) or `ANTHROPIC_API_KEY`. The workflows pass
   both to `anthropics/claude-code-action`; either alone works. If neither: **warn, don't
   block** — offer `/install-github-app`, or `gh secret set ANTHROPIC_API_KEY` with the user
   pasting the value; a lane fails red on its first model call without one.
4. Actions may create PRs:
   `gh api repos/{owner}/{repo}/actions/permissions/workflow --jq .can_approve_pull_request_reviews`
   must be `true` — GitHub blocks Actions-created PRs by default, and the workflow-level
   `permissions:` block cannot override it (the PR step fails with "GitHub Actions is not
   permitted to create or approve pull requests"). If `false`: **warn, don't block** — offer
   `gh api -X PUT repos/{owner}/{repo}/actions/permissions/workflow -F can_approve_pull_request_reviews=true`
   (needs repo admin; also in Settings → Actions → General).

## Install

1. Confirm the knobs with the user (defaults are fine unattended):
   - audit cron: default `0 1 * * *` (01:00 UTC daily); replaces `{{AUDIT_CRON}}` in doc-audit.yml
   - upgrade cron: default `0 2 * * 1` (02:00 UTC Mondays); replaces `{{UPGRADE_CRON}}` in
     doc-sync-upgrade.yml

   `doc-apply.yml` has no knob — manual dispatch carries no schedule to set. The plugin version
   is NOT a knob either — it's read from the plugin manifest, not chosen (next step).
2. Resolve the version being installed: `jq -r .version "$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json"`
   (the bare semver — no `v` prefix).
3. Confirm `.doc-lifecycle/registry.json` is landed. The audit and apply lanes are closed-world
   over it and fail on every run without one. Absent → stop and run Migration mode (below), or
   **bootstrapping-docs**' registry step for a repo with no docs yet; never hand-install ahead
   of that door.
4. Copy the three workflow templates, replacing the literal placeholders in each:
   - `doc-audit.yml` → `.github/workflows/doc-audit.yml`: `{{AUDIT_CRON}}`.
   - `doc-apply.yml` → `.github/workflows/doc-apply.yml`: no placeholder to replace.
   - `doc-sync-upgrade.yml` → `.github/workflows/doc-sync-upgrade.yml`: `{{UPGRADE_CRON}}`.
   The workflow YAML carries NO version placeholder — each `Pin plugin marketplace` step reads
   `.doc-lifecycle/installed-version` at runtime (written in step 11) and clones that tag, so
   the workflow files are version-agnostic (Overview). The version from step 2 lands only in
   that lockfile.
5. Copy this skill's scripts into `.doc-lifecycle/wiring/`: `scripts/upgrade-gate.py`,
   `scripts/stage-upgrade.py`, `scripts/render-report.py`, `scripts/render-audit-summary.py`,
   `scripts/render-apply-summary.py`, `scripts/probe-evidence-tool.py` (the version-comparison
   gate, the upgrade lane's path authority, and each lane's run-surface rendering — run from the
   repo, unit-tested upstream).
6. Copy the sibling skills' scripts into `.doc-lifecycle/wiring/`:
   `../detecting-doc-bloat/scripts/plan-chunks.py`,
   `../detecting-doc-bloat/scripts/validate-bloat-output.py`, and
   `../detecting-doc-drift/scripts/validate-drift-output.py`.
7. Vendor the engine: copy `$CLAUDE_PLUGIN_ROOT/engine/` wholesale to `.doc-lifecycle/wiring/engine/`.
   It is one package whose modules import each other, so a partially-refreshed tree is a version
   that was never tested — copy all of it, never a subset. `.doc-lifecycle/wiring/engine/doc-lifecycle.py`
   is what both lanes invoke.
8. Seed the audit scope — **only if absent**: write `.doc-lifecycle/audit-scope.json` with the
   starter `{"exclude": [], "include": []}` (empty arrays — a valid no-op default the human
   tunes). `plan-chunks.py` reads it to pick which docs a large bloat audit covers (exclude/
   include globs) and how to chunk them — the optional `policy_scope` (directories of ephemeral
   artifacts, each swept as one POLICY record) and `chunking` (`max_docs` / `max_lines` /
   `max_chunks`) keys are documented in that script's docstring; Migration mode reads the same
   file to infer documentation roots. An existing file is a tuned config — never overwrite it.
9. Seed the drift waivers — **only if absent**: write `.doc-lifecycle/drift-waivers.json`
   with the starter `{"waivers": []}`. This is the UNVERIFIABLE disposition record: an entry
   `{"file": <doc>, "claim": <quoted claim text>, "reason": ..., "date": ...}` annotates the
   matching assertion as accepted when the engine is given `drift-audit --waivers`, and
   Migration mode re-keys these onto assertion-unit identity. Matching is containment on the
   quoted fragment, bounded at both ends (`MIN_WAIVER_CLAIM`, `MAX_WAIVER_UNITS` in
   `doclifecycle/drift.py`), so rewording a waived line puts it back on the surface — new
   authorship is a new decision. An existing file is accumulated human judgment — never
   overwrite it.
10. Seed the declared evidence tools — **only if absent**: write
    `.doc-lifecycle/evidence-tools.json` with `{"tools": []}`. Tool-free is the honest default;
    a consumer adds the bare executable names the audit lane's verdicts may cite (audit lane,
    above). An existing file is a declared boundary — never overwrite it.
11. Write the version lockfile: `.doc-lifecycle/installed-version` = the bare version from
    step 2. Unlike the seeded state files, this tracks the wiring version and must equal the pin,
    so on a fresh install always write it. `doc-sync-upgrade.yml` reads it to decide whether a
    newer release exists; it advances only when an upgrade PR merges.
12. Tell the user, concretely:
    - the sixteen files to commit, plus the vendored `engine/` tree: the three workflows under
      `.github/workflows/` (`doc-audit.yml`, `doc-apply.yml`, `doc-sync-upgrade.yml`); the nine
      scripts under `.doc-lifecycle/wiring/` (`upgrade-gate.py`, `stage-upgrade.py`,
      `render-report.py`, `render-audit-summary.py`,
      `render-apply-summary.py`, `probe-evidence-tool.py`, `plan-chunks.py`,
      `validate-drift-output.py`, `validate-bloat-output.py`); and, at `.doc-lifecycle/`, the
      three seeded state files (`audit-scope.json`, `drift-waivers.json`, `evidence-tools.json`)
      and `installed-version`. `.doc-lifecycle/state/` stays empty on a fresh install — the
      marker it holds arrives only from a relocation;
    - the audit lane runs on its cron and writes nothing — it publishes a validated report as
      the `audit-report` artifact and renders the run's job summary, whatever the outcome;
    - applying is a deliberate second step: read that run's report, then
      `gh workflow run doc-apply -f report_run_id=<id> -f report_digest=<digest> -f records="<digests>" -f base=main`
      — the digests you name are the approval, and the PR it opens is what a merge approves;
    - the weekly upgrade check only detects: when a newer plugin release ships it files one notice
      issue naming it (one open notice per release, so a repeat check stays quiet), and when the
      install is already current or ahead of releases it self-explains and stops. It clones
      nothing and runs none of the release's code;
    - upgrading is a separate, human decision: read the release, then
      `gh workflow run doc-sync-upgrade -f target=<X.Y.Z>`, which regenerates the wiring and opens
      a `doc-sync/upgrade` PR whose merge advances the pin;
    - run them now with `gh workflow run doc-audit` and `gh workflow run doc-sync-upgrade` (the
      latter with no `target` — the detecting half);
    - to upgrade from a local checkout instead, re-run this skill (see Upgrade mode — consumer
      state and knobs preserved; wiring + pin + lockfile refreshed).

## Upgrade mode

Run by `doc-sync-upgrade.yml`'s `regenerate` job when a human dispatches that workflow with a
`target` (or by a human forcing an upgrade from a local checkout). It regenerates the vendored
wiring at the new version while leaving every consumer-owned value alone. **It is not a fresh
install** — skip the Preflight (secrets and PR-permissions are already in place) and do not
re-seed the state files.

**A version comparison detects; it never authorizes execution.** Upgrading means running the
*target release's* own `apply-upgrade.py`, which nobody in the consumer repository has read at the
moment it runs, so the schedule reaches only the `detect` job: it compares two numbers, files one
notice issue naming the release (`render-report.py upgrade-notice` renders its title and body and
decides nothing; `upgrade-gate.py notice` reads that title back and dedupes on it, so a repeat
check keeps quiet), and stops — cloning nothing, running none of the release's code, and
holding `issues: write` as its whole write scope. Execution happens only under
`workflow_dispatch` carrying a `target`, and `upgrade-gate.py` both shape-checks that input to
strict X.Y.Z before it names a git ref and refuses a target that is not strictly newer than the
pin. A dispatch advances the pin; it never rewinds it.

**The regeneration is deterministic — `scripts/apply-upgrade.py`, no model.** The workflow YAML
is version-agnostic, so an upgrade is pure mechanics (re-copy the scripts, re-render the
templates with the consumer's preserved knobs, replace the vendored engine, bump the lockfile),
and a tested script owns it — the upgrade lane makes no model call, and needs no model auth. The
workflow runs it from the target release's own checkout, in the job that holds no credential; a
human forcing an upgrade runs the same script against their checkout with
`--plugin-root "$CLAUDE_PLUGIN_ROOT"`:

    apply-upgrade.py --plugin-root <doc-lifecycle plugin dir> --repo <install root> --target <version>
                     [--report-written <file>]

The script writes files only; git/PR is the workflow's job (below). `--report-written` declares
each repo-relative path *as it writes it* — the rendered workflows, the copied scripts,
`installed-version`, the files it actually seeded, and the vendored engine as a directory path
(`copy_engine` empties the destination first, so a deletion has to be stageable). **The lane does
not read it**: a declaration by the release being landed is not evidence about that release, so
what gets staged comes from `stage-upgrade.py` comparing trees the lane controls. The flag remains
for a human forcing an upgrade from a checkout they took themselves. Never re-implement the
script's file ops by hand.

Ownership is the whole game — total on wiring, idempotent on state (this table is the contract
`apply-upgrade.py` implements):

| File | Owner | Upgrade behavior |
|------|-------|------------------|
| `doc-sync-upgrade.yml` | plugin (wiring) | **Regenerate** from the new template, re-injecting the consumer's existing knob (below), not the template default. No version to re-pin — the Pin steps read `installed-version` at runtime. |
| `.doc-lifecycle/wiring/*.py` (the six always-installed scripts) | plugin (wiring) | **Overwrite** from the new version. |
| `.doc-lifecycle/installed-version` | version state | **Set** to `<target>` (bare semver). This is what advances the pin; on a version-only release it's the *only* file that changes. |
| `.doc-lifecycle/audit-scope.json` | consumer (tuned config) | **Never touch.** A relocation carries it to this path once, and no upgrade rewrites it afterwards. |
| `.doc-lifecycle/drift-waivers.json` | consumer (accepted-claim record) | **Never touch.** Seed `{"waivers": []}` only if absent (pre-0.11 installs lack it). |
| `.doc-lifecycle/state/sync-marker` | legacy state | **Never touch.** No lane reads it. A relocation carries it here byte-for-byte, once; every upgrade after that leaves it alone (`stage-upgrade.py` authorizes it as a create only). |
| `doc-audit.yml`, `doc-apply.yml` | plugin (wiring) | **Regenerate**, knobs preserved — but only for an install holding `.doc-lifecycle/registry.json`. An install without one is left exactly as it was. |
| `.doc-lifecycle/wiring/render-audit-summary.py`, `render-apply-summary.py`, `probe-evidence-tool.py` | plugin (wiring) | **Overwrite**, on the same registry condition. |
| `.doc-lifecycle/evidence-tools.json` | consumer (declared tools) | **Never touch.** Seed `{"tools": []}` only if absent, on the same registry condition — tool-free is what a consumer opts out of, never what an upgrade hands them. |
| `.doc-lifecycle/wiring/engine/` | plugin (wiring) | **Replace wholesale**, on the same registry condition — the destination is emptied first, so a module deleted upstream stops being importable. Never edited in place. |
| `.doc-lifecycle/registry.json` | consumer (classification) | **Never touch.** Migration mode produces it; this mode only reads whether it exists. |

**Knobs are preserved, not reset** — `apply-upgrade.py` reads each install-time value out of the
currently-installed workflow and substitutes it back into the new template:
- `doc-sync-upgrade.yml`: its `cron:` → `{{UPGRADE_CRON}}`. A missing file (an install predating
  self-upgrade) is the one place it seeds a default (`0 2 * * 1`) and warns on stderr.
- `doc-audit.yml` (registry installs only): its `cron:` → `{{AUDIT_CRON}}`. Absent on an install
  that adopted the registry before this lane existed, so it seeds `0 1 * * *` and warns, the same
  shape `doc-sync-upgrade.yml` uses. `doc-apply.yml` has no knob.

A knob it can't extract fails the run red rather than default-guessing.

### Relocating a pre-0.40.0 install

An install from before 0.40.0 keeps its wiring at `.github/doc-sync/` with the marker loose beside
it as `.github/doc-sync-marker`. `apply-upgrade.py` relocates it — once — when that directory is
present and `.doc-lifecycle/wiring/` is not:

- **Carried byte-for-byte:** `audit-scope.json`, `drift-waivers.json`, `evidence-tools.json` to
  `.doc-lifecycle/`, and the marker to `.doc-lifecycle/state/sync-marker`. The registry does not
  move — the engine already writes it at `.doc-lifecycle/registry.json`.
- **Written fresh, not moved:** the scripts under `wiring/`, the vendored engine, and the
  lockfile. The contract overwrites those unconditionally, so moving bytes about to be replaced
  would buy nothing.
- **Removed:** exactly the paths named above plus the old directory's `.py` files and its
  `engine/`. A file in the old directory outside that named set is **left exactly where it is**
  and reported on the run surface — the plugin does not sweep a directory on its way out, so the
  old directory survives when it still holds one.

It refuses rather than guesses in two shapes: both layouts present (which of the two holds the
live wiring is not knowable from the filesystem), and `wiring/` present without
`.doc-lifecycle/installed-version` beside it (a relocation that stopped partway).

**An install predating 0.40.0 cannot be relocated by the automated upgrade lane.** That lane runs
the *installed* copy of `stage-upgrade.py` — reviewed code the consumer already holds — and a
copy from before this release does not know the new layout, so it refuses the change set as
unowned. Relocate such an install by re-running this skill in Upgrade mode from a local checkout,
which runs the target release's `apply-upgrade.py` directly.

**The job that runs the release's code holds nothing, and the job that holds credentials runs
nothing the release wrote.** `regenerate` has `contents: read`, no `GH_TOKEN`, no secret, and a
checkout persisting no credential; it copies the wiring roots (`.github/`, `.doc-lifecycle/`) into
a scratch tree under `$RUNNER_TEMP` and runs the clone's `apply-upgrade.py` against that copy.
`land` holds `contents: write` + `pull-requests: write` — every byte the release produced reaches
it as data inside the `doc-sync-upgrade-bundle` artifact.

Both jobs first copy `.doc-lifecycle/wiring/*.py` to `$RUNNER_TEMP/trusted/` and run every wiring
script from there. This is the step the split rests on, and the easy one to get wrong: the
regeneration writes the release's own `stage-upgrade.py` and `render-report.py`, and `land`'s
transfer legitimately lands them in `.doc-lifecycle/wiring/` — so a step invoking one out of the work
tree afterwards runs the release's code with `land`'s push token, the split defeated two steps
after it was drawn. "The install's tooling, not the release's" is a claim about *when the copy was
taken*, never about which directory it sits in.

**`stage-upgrade.py` is the authority between the two jobs.** `manifest` derives what changed by
comparing the scratch tree against the install and refuses the whole run if any difference lies
outside what `apply-upgrade.py` owns (the marker, `audit-scope.json`, the registry, a workflow
that is not `doc-*.yml`, a non-`.py` drop into `.doc-lifecycle/wiring/`, a symlink, anything outside
the wiring roots), emitting `{status, path, sha256}` entries plus the changed files. `apply`
re-derives that same authority from the manifest instead of trusting that `manifest` already
did — the two run in different trust domains with an artifact in between — checks every bundled
file against its recorded digest, refuses a bundle carrying a file the manifest does not name, and
prints the staging list. `verify` then checks what git actually staged against that list. All
three run from that pre-transfer copy.

**Do not commit or open the PR in upgrade mode** — the workflow's `land` job owns git: it
transfers the manifest's path set into its own checkout, stages exactly that set by pathspec,
opens the `doc-sync/upgrade` PR (or self-explains a no-op), and the merge is what advances
`installed-version`. A difference outside the wiring ends the run before any of that, at the
`refused` status, which names every offending path and states that nothing was staged and no pull
request opened — a regeneration that reached past the wiring is a bug to fix upstream, never
something to sweep into the commit. Anything git staged beyond the authorized set, or left behind
in the work tree, fails the `verify` check the same way. Regenerating never leaves an install
floating on `main`: the new wiring is pinned to `<target>` end to end.

**Workflow-file changes can't self-land.** The Actions `GITHUB_TOKEN` cannot push files under
`.github/workflows/` (GitHub blocks it; the `workflows` permission is not grantable to it).
Because the Pin steps read `installed-version` at runtime, a *version-only* upgrade touches only
that lockfile (+ the scripts and the vendored engine) and the PR opens normally. But an upgrade
whose new templates change the workflow YAML itself can't be pushed by the workflow — the
`land` job's `Open the upgrade pull request` step detects a changed `.github/workflows/` file,
writes the diff to the
`doc-sync-upgrade-patch` artifact, and fails loud with `git apply` instructions
(`render-report.py upgrade-summary --status blocked-workflows`). A human applies that patch with
a `workflow`-scoped credential. This is rare and expected; don't try to "fix" it by widening the
token — the restriction is GitHub's.

## Migration to the registry contract

A one-time, guided, **interactive** run — not Upgrade mode, which is deterministic and
model-free. An install predating the registry has no `.doc-lifecycle/registry.json`, and the
audit is closed-world, so it needs one before it can run at all. The engine owns every decision
here; this skill only sequences it. Both commands are **read-only** — the migration is the human
landing a file, never the door.

    ENGINE="$CLAUDE_PLUGIN_ROOT/engine/doc-lifecycle.py"

1. **Draft.** `mkdir -p .doc-lifecycle && python3 "$ENGINE" migration-draft --repo .
   --registry-only > .doc-lifecycle/registry.json`. It infers roots and kinds from
   `audit-scope.json`, the waivers, `docs/doc-scope.md`, `> As of` markers (the first line, or
   the first non-blank line under the title), and
   directory conventions. `--root <path>` (repeatable) replaces inference for a repo whose docs
   sit somewhere unconventional. A refused draft prints **nothing** and exits 1 — an empty
   registry file means read stderr, not that there was nothing to infer.
2. **Review the diff, as globs.** The draft is one rule per directory plus per-file overrides —
   a short diff, deliberately. Run `python3 "$ENGINE" migration-draft --repo .` (no
   `--registry-only`) to see each rule's `basis` and the documents it claims before judging it.
   Edit the file; don't argue with the inference.
3. **Dry-run.** `python3 "$ENGINE" migration-dry-run --repo .`. Read the obligations per kind,
   the waivers that re-keyed, and the ones that need re-waiving. **Exit 1 means blocked** — most
   often a document under a declared root that no rule claims, named in the output. Add a rule or
   an exclude *to the registry file* and re-run this step; the loop is edit → dry-run, never back
   through step 1, which would overwrite your edits with the inference again — a draft run once a
   registry is landed says so itself, in `migration-registry-already-landed`. There is no
   unclassified bucket.
4. **Re-waive.** Rewrite each `needs_rewaiving` entry against what the document says now. Its
   `message` states which of the five reasons applies.
5. **Delete the rejected artifacts.** The dry run's `artifacts` names every old report, cache, or
   approval found and how to regenerate it. Delete them; never edit one into the new shape.
6. **Land it** as a normal PR: the registry, the rewritten waivers, the deletions.

### Migration rules (these govern the six steps above, not the install below)

- **Never hand-write the registry from scratch** when an install predating it exists — the draft
  is what makes the review a diff instead of a per-file slog.
- **Never bypass a block.** A blocked dry run is the closed-world rule doing its job.
- **This mode moves no consumer state.** `audit-scope.json`, `drift-waivers.json`, and the
  sync marker stay untouched; `installed-version` is advanced by `apply-upgrade.py` in Upgrade
  mode, not here. The dry run's `preserved` states each of those files' digest and disposition,
  so nothing about consumer state is left to memory.
- **Both commands find that state wherever this install keeps it** — `.doc-lifecycle/`, or
  `.github/doc-sync/` on an install that has not run the relocating upgrade. Each payload's
  `install.layout` says which it read, and `install.registry` says whether a registry is already
  landed; don't pass `--waivers` or `--installed-version` to "help" it. State standing under
  *both* layouts exits 1 with `migration-split-install` — keep whichever copy holds your
  decisions, remove the other, and re-run. Never merge the two by hand into one.
- Fresh installs run steps 1–3 too (the door is also **bootstrapping-docs**' registry step) —
  with no prior state it infers from markers and directory conventions alone, and reports
  `from_version: null`.

## Rules

- **Runs as a GitHub Action** (`schedule` + `workflow_dispatch`), not a Claude scheduled task
  (ties to one user's account) or a local git/session hook (only fires while someone's working).
- **The model never holds repository write authority.** A model job's `permissions:` stays
  `contents: read` (+ `id-token: write`), its checkout sets `persist-credentials: false`, and it
  carries no `GH_TOKEN`. Its output leaves as an artifact; a credentialed, model-free job is what
  writes. Never widen a model job's token "so it can push", and never move a
  `claude-code-action` step into a job holding a write scope —
  `tests/scripts/workflow-permissions_test.py` fails the release if either happens.
- **PR-only output.** Never configure a lane to commit doc edits directly to the default branch —
  not even if asked ("PRs are annoying"). The reviewable pull request *is* the product. The audit
  lane writes nothing at all; the apply and upgrade lanes each land only through a PR a human
  merges, and neither opens a draft.
- **Semantic approval is a person naming record digests.** `doc-apply.yml` is
  `workflow_dispatch` only, and it applies exactly the records that dispatch named. Never wire a
  schedule, a label, or a bot into its trigger, and never widen the selection inside the lane.
- **Both engine lanes need a landed registry.** `.doc-lifecycle/registry.json` is what switches
  `doc-audit.yml` and `doc-apply.yml` on. Installing them without it ships wiring that fails on
  every run.
- **Installs are pinned; only the upgrade workflow advances the pin.** Every model step is
  preceded by a `Pin plugin marketplace` step that clones `…/toolshed.git` at `v<version>` to a
  local path, and `plugin_marketplaces` points there — so the skills a run executes are frozen at
  the vendored wiring's version. (`claude-code-action` rejects a `plugin_marketplaces` git URL
  carrying a `#<ref>` fragment; its validator requires the value end in `.git`, so the pin lives
  in the checkout, not the URL.) `installed-version` is the lockfile — it advances only when a
  `doc-sync/upgrade` PR merges. Never ship an unpinned marketplace checkout (bare `main`), and
  never version the `plugins:` selector (`@version` there is unsupported).
- **Upgrading is a human's dispatch, never a version comparison's conclusion.** A newer release is
  a notice issue, not a mandate: the schedule detects and stops, and the target release's code
  runs only under `workflow_dispatch` naming a `target`, in a job holding `contents: read`, no
  token and no secret — while the job holding `contents: write` runs only
  `.doc-lifecycle/wiring/*.py` from its own checkout, taken before the release wrote anything. Never route the schedule into
  the regenerating job, never give the detecting job a scope beyond `issues: write`, and never
  move the release's `apply-upgrade.py` into the credentialed one
  (`tests/scripts/upgrade-workflow_test.py`).
- **Don't customize the installed YAML beyond the audit-cron and upgrade-cron knobs.** Real
  changes belong upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade.
- **Staging is an explicit path list, never `git add -A` — no exceptions.** Both credentialed
  jobs stage `--pathspec-from-file`: the apply lane the paths the engine's verified apply result
  emitted, the upgrade lane the paths `stage-upgrade.py` authorized out of the regeneration's
  manifest. Each then
  re-checks what landed, and a stray path stops the run before anything is committed or pushed.
  `workflow-permissions_test.py` asserts this over every shipped template with no exemption list.
- **The report is a build artifact, never repo content.** The audit lane uploads
  `drift-report.json` and its cost sidecar as artifacts; don't let a hand edit reintroduce either
  as a committed file.
- **Typed engine exits are outcomes, not crashes.** `drift-audit` exits 1 (invalid) and 4
  (partial) are each a legitimate typed report, as are `validate-report`'s 1/3/4. The lanes
  capture them with `|| code=$?` and render each on the run surface — the runner's shell is
  `bash -e`, so a bare `$?` read after the call would never run on the exits that matter. Never
  "simplify" that back to a plain call, and never add `continue-on-error` to hide one.
- **Upgrade preserves consumer state.** Overwrite the yml, the scripts, and the vendored engine
  freely; `audit-scope.json`, `drift-waivers.json`, `evidence-tools.json`, and the registry are
  state, not wiring. See Upgrade mode.

## Red flags — STOP

- Writing audit or apply method inside a workflow prompt → invoke the skills by name and the
  engine by its CLI contract.
- Installing `doc-audit.yml` or `doc-apply.yml` into a repo with no `.doc-lifecycle/registry.json`
  → closed-world; every run fails. Run Migration mode first.
- Overwriting an existing `.doc-lifecycle/audit-scope.json`, `drift-waivers.json`, or
  `evidence-tools.json` with the empty starter → consumer state, not wiring; seed only when absent.
- Adding a direct-commit mode, or dropping the upgrade lane's open-PR gate "to simplify" → the
  gates are the product; see the design doc in aj604/toolshed.
- Committing `drift-report.json` as repo content → artifact hygiene, not history.
- Giving a model job `contents: write`, a `GH_TOKEN`, or a credential-persisting checkout "so it
  can just push" → that is the mutation path the job split closes.
- Replacing either credentialed job's `git add --pathspec-from-file` with a trusting `git add -A`,
  or dropping the leftover check that follows it → what may be written is bounded by the approval
  set in one lane and by the declared written set in the other, and a broad add hands a stray file
  the same authority as an approved edit.
- Opening the apply lane's PR as a draft, or splicing a `github.event.inputs.*` value into a
  `run:` block → the PR is the change approval, and dispatch inputs reach argv only after
  validation (`tests/scripts/apply-workflow_test.py`).
- Naming another executable in a `--allowedTools` grant → those patterns are prefix-matched, so
  `gh` grants `gh api` in a job deliberately given no credential. Declare the tool in
  `evidence-tools.json` and reach it through `probe-evidence-tool.py` instead.
- Dropping the `Pin plugin marketplace` clone step, or pointing `plugin_marketplaces` at
  `…/toolshed.git` (bare `main`) → an unpinned install that floats and drifts from the frozen
  wiring. Pin it via the local checkout of the release tag.
- Reaching for `plugin_marketplaces: …/toolshed.git#v<version>` → `claude-code-action` rejects it
  ("Invalid marketplace URL format"); its validator requires the URL end in `.git`. Pin via the
  local checkout instead.
- Writing `plugins: doc-lifecycle@toolshed@<version>` → the `@version` selector is unsupported;
  pin via the local checkout of the release tag only.
- Resetting `.doc-lifecycle/installed-version`, or overwriting a seeded state file, during an
  upgrade → upgrade preserves consumer state; only wiring + the pin + the lockfile change.
- Making the scheduled upgrade check clone the release or run its `apply-upgrade.py` "so upgrades
  land unattended", or moving that execution into the credentialed `land` job → that is
  pre-review execution of unreviewed code, which the three-job split exists to close. The
  schedule detects; a dispatch authorizes.
- Running `stage-upgrade.py` (or any other check) out of the clone, out of `$RUNNER_TEMP/scratch`,
  or out of `.doc-lifecycle/wiring/` after `land`'s transfer, or landing the bundle with a trusting
  `cp -a` + `git add -A` → the boundary is only worth what the code drawing it is, so both jobs
  run every wiring script from the copy taken before anything wrote, and `apply` re-derives the
  authority from the manifest instead of trusting `manifest` already did.
- Staging an upgrade from `apply-upgrade.py --report-written` inside the lane → that is the
  release being landed declaring what it wrote, which is not evidence about that release. Derive
  the set with `stage-upgrade.py manifest`, from trees the lane controls; the flag is for a human
  running the upgrade against a checkout they took themselves.
- Splicing `inputs.target` straight into the `git clone` (or any other `run:` line) → the
  dispatched value reaches a shell only as `upgrade-gate.py normalize` re-emitted it, and the same
  gate is what refuses a target that would rewind the pin.
