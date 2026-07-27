---
name: scheduling-doc-sync
description: Use when wiring a repo for automated/unattended documentation drift sync — "set up doc sync", "automate drift detection", "schedule nightly doc checks", "keep docs in sync automatically" — installs the doc-lifecycle nightly GitHub Action (detect → gate → fix → evidence PR) instead of hand-rolling workflow YAML. Also the door for upgrading an existing install.
---

# Scheduling Doc Sync

## Overview

Installs the shipped automation into a target repo — **three workflows**: the nightly drift
sync (`doc-sync.yml`), the weekly chunked doc-bloat sweep (`doc-bloat.yml`: deterministic
chunk plan → matrix detect → assemble → prune lane + fanned-out distill lane, each a draft
PR), and the weekly self-upgrade
(`doc-sync-upgrade.yml`: compare installed version to the plugin's latest release → regenerate
the wiring at a newer one → open a review PR). **You install wiring; you do not re-derive it.**
Orchestration lives in the shipped workflow YAML; every gate decision lives in the shipped
`sync-gate.py` / `upgrade-gate.py`; every run-surface string (summaries, notices, issue/PR
bodies) lives in the shipped `render-report.py`; chunk planning lives in `plan-chunks.py`;
distill-lane planning, dispatch rendering, and the deterministic patch merge live in
`plan-distill.py`; the path authority for a model's edit set lives in `authorize-paths.py`; doc
judgment lives in `detecting-doc-drift` / `fixing-doc-drift` / `detecting-doc-bloat` /
`fixing-doc-bloat`, which the workflows invoke headlessly by name. Never inline detection or
fixing method into workflow YAML — that forks the method from its one owner.

**The model holds no repository write authority.** Every job that invokes a model runs with
`permissions: contents: read` (plus `id-token: write` for the OAuth exchange only), checks out
with `persist-credentials: false`, and hands its work forward as an artifact — a report, or a
`git diff --binary --no-renames` patch of its edits. The credentialed jobs (`land`,
`prune_land`, `distill_merge`) run **no model**: they derive the authorized path set from the
validated report (`authorize-paths.py expected`), check every path the patch names against it
(`authorize-paths.py check`), apply, and stage that explicit list —
`git add --pathspec-from-file=`, never `git add -A`. A patch naming any other path fails the
run before anything is applied: no PR, nothing staged. This is the boundary; the model step's
`--allowedTools` list is ergonomics, not security. `distill_merge` is the one lane that
cannot stage by pathspec — it transports per-record commits so the PR stays reviewable
record by record — so it checks twice instead: every path in every group patch before the
first `git am`, and every path in the landed diff after the last. What none of this
establishes is that the *report* was honest — it is model output too; PR review is the
backstop until the approval-set stage lands.

**Installs are pinned, not floating.** Before each `claude-code-action` step, a
`Pin plugin marketplace` step reads the version from `.github/doc-sync/installed-version` and
clones that release tag
(`VERSION=$(cat …/installed-version); git clone --depth 1 --branch "v${VERSION}" …/toolshed.git "$RUNNER_TEMP/toolshed-marketplace"`),
and the action step points `plugin_marketplaces` at that local path — so the skills a run
executes are frozen at the same version as the vendored wiring, and can't drift apart mid-week.
The version is read at runtime, NOT hardcoded in the workflow YAML, so the nightly workflow files
stay byte-identical across versions — a routine upgrade changes only the lockfile, never a
`.github/workflows/` file (which the Actions token cannot push; see Upgrade mode). The upgrade
lane is the exception: it clones the *target* release it's regenerating to (`steps.versions.latest`),
since `installed-version` still holds the old version until the skill advances it. Clone under
`$RUNNER_TEMP`, never inside the work tree, or the exported edit set captures it.
Pin via the local checkout, NOT a `plugin_marketplaces: …/toolshed.git#v<version>` ref —
`claude-code-action`'s URL validator requires the value end in `.git`, so a `#<ref>` fragment is
rejected outright. `doc-sync-upgrade.yml` is the only thing that advances the pin, and only via a
reviewable PR. The `plugins:` selector stays bare `doc-lifecycle@toolshed` (`claude-code-action`
has no `@version` selector there — `doc-lifecycle@toolshed@0.7.0` is invalid).

The three workflow templates and this skill's own scripts (`sync-gate.py`, `upgrade-gate.py`,
`render-report.py`, `plan-distill.py`, `authorize-paths.py`) are in its base directory
(announced when the skill loads); the chunk planner and the two output validators are copied
from the sibling skills that own them (install steps 3–4). `apply-upgrade.py` (also in the base directory) is the deterministic upgrade
engine — run from the pinned checkout by the upgrade lane, never vendored into the install (see
Upgrade mode).

## The new engine's audit lane (`doc-audit.yml`, aj604/toolshed#57)

`doc-audit.yml` (base directory, alongside the three templates above) is a **fourth, separate**
template: the re-architecture's read-only scheduled audit, rebuilt on the `doclifecycle` engine
package rather than the eight legacy scripts. It runs *alongside* `doc-sync.yml`, not instead of
it — the two coexist until the shadow-mode parity gate (aj604/toolshed#76) clears the way to
retire the legacy lane (aj604/toolshed#77). Its own script, `scripts/render-audit-summary.py`,
owns that lane's run-surface rendering exactly as `render-report.py` owns the legacy lane's.

Structurally it is the same two-job trust split as every other lane here — `audit` (the model,
`contents: read` + `id-token: write`, no credential) and `publish` (no model, `contents: read` +
`issues: write` only — never `contents: write`, never a PR, never a direct commit) — but calls
the engine's own public CLI (`drift-plan`, `drift-audit`, `validate-report`) instead of the
legacy `sync-gate.py`/`render-report.py`/`validate-drift-output.py` trio, and every third-party
action it invokes is pinned to an immutable commit SHA (a stricter bar than the legacy
templates currently meet — see `tests/scripts/audit-workflow_test.py`).

**Not yet wired into Install/Upgrade above.** This template requires a landed
`.doc-lifecycle/registry.json` (the new document model's classification manifest), which no
consumer has until it runs the migration door (aj604/toolshed#74 — "Migration to the registry
contract", below); installing this lane into a
repo's `.github/` — vendoring the `doclifecycle` engine package, copying
`render-audit-summary.py`, and rendering the `{{AUDIT_CRON}}` knob — is aj604/toolshed#75's job.
Until then this file is the reviewable template only; don't hand-install it ahead of that door.

## Preflight (run all; report failures, don't silently skip)

1. Target repo has a GitHub remote: `git remote get-url origin`. No remote → stop; this
   pipeline is a GitHub Action. (A non-GitHub repo wants a different trigger — tell the user.)
2. `gh auth status` succeeds.
3. Auth secret: `gh secret list` shows `CLAUDE_CODE_OAUTH_TOKEN` (preferred — created by Claude
   Code's `/install-github-app`, no key-pasting) or `ANTHROPIC_API_KEY`. The workflow passes
   both to `anthropics/claude-code-action`; either alone works. If neither: **warn, don't
   block** — offer `/install-github-app`, or `gh secret set ANTHROPIC_API_KEY` with the user
   pasting the value; the workflow fails red on its first model call without one.
4. `gh label create doc-sync --force` (idempotent) — the pipeline files blast-radius issues
   under this label, and `gh issue create --label` fails if it doesn't exist.
5. Actions may create PRs:
   `gh api repos/{owner}/{repo}/actions/permissions/workflow --jq .can_approve_pull_request_reviews`
   must be `true` — GitHub blocks Actions-created PRs by default, and the workflow-level
   `permissions:` block cannot override it (the PR step fails with "GitHub Actions is not
   permitted to create or approve pull requests"). If `false`: **warn, don't block** — offer
   `gh api -X PUT repos/{owner}/{repo}/actions/permissions/workflow -F can_approve_pull_request_reviews=true`
   (needs repo admin; also in Settings → Actions → General).

## Install

1. Confirm the knobs with the user (defaults are fine unattended):
   - cron: default `0 3 * * *` (03:00 UTC nightly)
   - blast-radius cap: default `10` (matches fixing-doc-drift's default of ~10 passages)
   - bloat cron: default `0 4 * * 1` (04:00 UTC Mondays); replaces `{{BLOAT_CRON}}` in doc-bloat.yml
   - upgrade cron: default `0 2 * * 1` (02:00 UTC Mondays); replaces `{{UPGRADE_CRON}}` in
     doc-sync-upgrade.yml. Earliest of the three (before the 03:00 nightly sync and 04:00 bloat
     sweep) so the weekly version-bump check is the first run of its day. The plugin version is
     NOT a knob — it's read from the plugin manifest, not chosen (next step).
2. Resolve the version being installed: `jq -r .version "$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json"`
   (the bare semver, e.g. `0.7.0`). Copy the three workflow templates, replacing the literal
   placeholders in each:
   - `doc-sync.yml` → `.github/workflows/doc-sync.yml`: `{{CRON_SCHEDULE}}` and `{{BLAST_RADIUS_CAP}}`.
   - `doc-bloat.yml` → `.github/workflows/doc-bloat.yml`: `{{BLOAT_CRON}}`.
   - `doc-sync-upgrade.yml` → `.github/workflows/doc-sync-upgrade.yml`: `{{UPGRADE_CRON}}`.
   The workflow YAML carries NO version placeholder — each `Pin plugin marketplace` step reads
   `.github/doc-sync/installed-version` at runtime (written in step 8) and clones that tag, so the
   workflow files are version-agnostic (Overview). The version from step 2 lands only in that
   lockfile.
3. Copy `scripts/sync-gate.py` → `.github/doc-sync/sync-gate.py`,
   `scripts/upgrade-gate.py` → `.github/doc-sync/upgrade-gate.py`,
   `scripts/render-report.py` → `.github/doc-sync/render-report.py`,
   `scripts/plan-distill.py` → `.github/doc-sync/plan-distill.py`,
   `scripts/authorize-paths.py` → `.github/doc-sync/authorize-paths.py`, and
   `../detecting-doc-bloat/scripts/plan-chunks.py` → `.github/doc-sync/plan-chunks.py`
   (gate decisions, the version-comparison gate, run-surface rendering, doc-bloat's
   deterministic chunk planning, the distill lane's planning + patch merge, and the
   credentialed jobs' path authority all run from the repo, unit-tested upstream — across all
   three workflows).
4. Copy `../detecting-doc-drift/scripts/validate-drift-output.py` → `.github/doc-sync/validate-drift-output.py`
   and `../detecting-doc-bloat/scripts/validate-bloat-output.py` → `.github/doc-sync/validate-bloat-output.py`
   (each workflow's mechanical contract check runs from the repo, not the plugin cache).
5. Seed the audit scope — **only if absent**: write `.github/doc-sync/audit-scope.json` with the
   starter `{"exclude": [], "include": []}` (empty arrays — a valid no-op default the human tunes).
   This is the doc-bloat full-audit scope config `plan-chunks.py` reads to pick which docs the
   weekly sweep audits (exclude/include globs) and how to chunk them — the optional
   `policy_scope` (directories of ephemeral artifacts, each swept as one POLICY record) and
   `chunking` (`max_docs` / `max_lines` / `max_chunks`) keys are documented in that script's
   docstring. An existing file is a tuned config — never overwrite it.
6. Seed the drift waivers — **only if absent**: write `.github/doc-sync/drift-waivers.json`
   with the starter `{"waivers": []}`. This is the UNVERIFIABLE disposition record: the nightly
   surfaces every unverifiable claim (on the sync PR, or on the run summary of a no-drift
   night) until a human either rewords the doc line or accepts it here as
   `{"file": <doc>, "claim": <exact line text>, "reason": ..., "date": ...}` — waived claims
   stop resurfacing. Matching is exact claim text, so rewording a waived line puts it back on
   the surface (new authorship is a new decision). An existing file is accumulated human
   judgment — never overwrite it.
7. Seed the marker — **only if absent**:
   `test -f .github/doc-sync-marker || git rev-parse HEAD > .github/doc-sync-marker`
   An existing marker means an existing install: this is an upgrade, and resetting the marker
   would silently skip every commit since the last sync. Never reset it.
8. Write the version lockfile: `.github/doc-sync/installed-version` = the bare version from step 2
   (e.g. `0.7.0`). Unlike the marker/audit-scope, this tracks the wiring version and must equal
   the pin, so on a fresh install always write it. `doc-sync-upgrade.yml` reads it to decide
   whether a newer release exists; it advances only when an upgrade PR merges.
9. Tell the user, concretely:
   - the fifteen files to commit (`doc-sync.yml`, `doc-bloat.yml`, `doc-sync-upgrade.yml`,
     `sync-gate.py`, `upgrade-gate.py`, `render-report.py`, `plan-chunks.py`, `plan-distill.py`,
     `authorize-paths.py`, `validate-drift-output.py`, `validate-bloat-output.py`, the seeded
     `audit-scope.json`, the seeded `drift-waivers.json`, the seeded `doc-sync-marker`, and
     `installed-version`);
   - first night: diff from the seeded marker; no drift → marker-only commit, drift → PR on
     `doc-sync/nightly` with evidence, over-cap → a `doc-sync` issue;
   - the weekly bloat sweep opens up to two **draft** PRs (`doc-bloat/prune`, `doc-bloat/distill`);
     a lane with no findings, or whose PR is already open, is skipped with a self-explaining run
     summary;
   - the weekly upgrade check opens a `doc-sync/upgrade` PR only when a newer plugin release
     ships; when the install is already current (or ahead of releases) it self-explains and stops;
   - run them now with `gh workflow run doc-sync`, `gh workflow run doc-bloat`, and
     `gh workflow run doc-sync-upgrade`;
   - upgrades happen automatically via `doc-sync-upgrade.yml`; to force one, re-run this skill
     (see Upgrade mode — marker/audit-scope/knobs preserved; wiring + pin + lockfile refreshed);
   - **sync PRs carry no CI checks** (pushed via `GITHUB_TOKEN`, which never retriggers CI);
     mint a GitHub App token (`actions/create-github-app-token`) instead if CI-on-doc-PRs matters.

## Upgrade mode

Run by `doc-sync-upgrade.yml` once a newer plugin release exists (or by a human forcing an
upgrade). It regenerates the vendored wiring at the new version while leaving every
consumer-owned value alone. **It is not a fresh install** — skip the Preflight (secrets, labels,
PR-permissions are already in place) and do not re-seed the marker or audit-scope.

**The regeneration is deterministic — `scripts/apply-upgrade.py`, no model.** Once the workflow
YAML went version-agnostic, an upgrade is pure mechanics (re-copy the eight scripts, re-render the
three templates with the consumer's preserved knobs, bump the lockfile), so a tested script owns
it and the upgrade lane makes no model call — and needs no model auth. The workflow runs it from
the pinned target checkout; a human forcing an upgrade runs the same script against their checkout
with `--plugin-root "$CLAUDE_PLUGIN_ROOT"`:

    apply-upgrade.py --plugin-root <doc-lifecycle plugin dir> --repo <install root> --target <version>

The script writes files only; git/PR is the workflow's job (below). Never re-implement its file
ops by hand.

Ownership is the whole game — total on wiring, idempotent on state (this table is the contract
`apply-upgrade.py` implements):

| File | Owner | Upgrade behavior |
|------|-------|------------------|
| `doc-sync.yml`, `doc-bloat.yml`, `doc-sync-upgrade.yml` | plugin (wiring) | **Regenerate** from the new templates, but re-inject the consumer's existing knobs (below), not the template defaults. No version to re-pin — the Pin steps read `installed-version` at runtime. |
| `.github/doc-sync/*.py` (all eight scripts) | plugin (wiring) | **Overwrite** from the new version. |
| `.github/doc-sync/installed-version` | version state | **Set** to `<target>` (bare semver). This is what advances the pin; on a version-only release it's the *only* file that changes. |
| `.github/doc-sync-marker` | sync state | **Never touch.** |
| `.github/doc-sync/audit-scope.json` | consumer (tuned config) | **Never touch.** |
| `.github/doc-sync/drift-waivers.json` | consumer (accepted-claim record) | **Never touch.** Seed `{"waivers": []}` only if absent (pre-0.11 installs lack it). |

**Knobs are preserved, not reset** — `apply-upgrade.py` reads each install-time value out of the
currently-installed workflow and substitutes it back into the new template:
- `doc-sync.yml`: the `cron:` under `schedule` → `{{CRON_SCHEDULE}}`; the `CAP:` env → `{{BLAST_RADIUS_CAP}}`.
- `doc-bloat.yml`: its `cron:` → `{{BLOAT_CRON}}`.
- `doc-sync-upgrade.yml`: its `cron:` → `{{UPGRADE_CRON}}`.
A knob it can't extract fails the run red rather than default-guessing; the one exception is a
missing `doc-sync-upgrade.yml` (an install predating self-upgrade), where it seeds the default
upgrade cron (`0 2 * * 1`) and warns on stderr.

**Do not commit or open the PR in upgrade mode** — the workflow owns git: it diffs the working
tree, opens the `doc-sync/upgrade` PR (or self-explains a no-op), and the merge is what advances
`installed-version`. Regenerating never leaves an install floating on `main`: the new wiring is
pinned to `<target>` end to end.

**Workflow-file changes can't self-land.** The Actions `GITHUB_TOKEN` cannot push files under
`.github/workflows/` (GitHub blocks it; the `workflows` permission is not grantable to it).
Because the Pin steps read `installed-version` at runtime, a *version-only* upgrade touches only
that lockfile (+ the scripts) and the PR opens normally. But an upgrade whose new templates change
the workflow YAML itself can't be pushed by the workflow — the `Open upgrade PR` step detects a
changed `.github/workflows/` file, writes the diff to the `doc-sync-upgrade-patch` artifact, and
fails loud with `git apply` instructions (`render-report.py upgrade-summary --status
blocked-workflows`). A human applies that patch with a `workflow`-scoped credential. This is rare
and expected; don't try to "fix" it by widening the token — the restriction is GitHub's.

## Migration to the registry contract

A one-time, guided, **interactive** run — not Upgrade mode, which is deterministic and
model-free. An install predating the registry has no `.doc-lifecycle/registry.json`, and the new
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
   through step 1, which would overwrite your edits with the inference again. There is no
   unclassified bucket.
4. **Re-waive.** Rewrite each `needs_rewaiving` entry against what the document says now. Its
   `message` states which of the five reasons applies.
5. **Delete the rejected artifacts.** The dry run's `artifacts` names every old report, cache, or
   approval found and how to regenerate it. Delete them; never edit one into the new shape.
6. **Land it** as a normal PR: the registry, the rewritten waivers, the deletions.

### Migration rules (these govern the six steps above, not the install below)

- **Never hand-write the registry from scratch** when a legacy install exists — the draft is what
  makes the review a diff instead of a per-file slog.
- **Never bypass a block.** A blocked dry run is the closed-world rule doing its job.
- **This mode moves no consumer state.** `audit-scope.json`, `drift-waivers.json`, and the marker
  stay untouched; `installed-version` is advanced by `apply-upgrade.py` in Upgrade mode, not
  here. The dry run's `preserved` states each of those files' digest and disposition, so nothing
  about consumer state is left to memory.
- Fresh installs run steps 1–3 too (the door is also **bootstrapping-docs**' registry step) —
  with no legacy state it infers from markers and directory conventions alone, and reports
  `from_version: null`.

## Rules

- **Runs as a GitHub Action** (`schedule` + `workflow_dispatch`), not a Claude scheduled task
  (ties to one user's account) or a local git/session hook (only fires while someone's working).
- **Idempotency is marker-based, not model discipline.** `.github/doc-sync-marker` advances only
  on a clean-run (no-drift) direct commit or a merged sync PR; a blast-radius cap escalates to a
  labeled issue instead of accumulating into one giant PR.
- **PR-only output.** Never configure the pipeline to commit doc edits directly to the default
  branch — not even if asked ("PRs are annoying"). The reviewable evidence-PR *is* the product;
  a direct-commit pipeline is an unreviewable one. The only direct push the pipeline makes is
  the marker-only commit on a no-drift run.
- **Upgrade preserves the marker** (step 7) and the version lockfile discipline. Overwrite the
  yml and scripts freely; the marker and `audit-scope.json` are state, not wiring. See Upgrade mode.
- **Installs are pinned; only the upgrade workflow advances the pin.** Every model step is
  preceded by a `Pin plugin marketplace` step that clones `…/toolshed.git` at `v<version>` to a
  local path, and `plugin_marketplaces` points there — so the skills a run executes are frozen at
  the vendored wiring's version. (`claude-code-action` rejects a `plugin_marketplaces` git URL
  carrying a `#<ref>` fragment; its validator requires the value end in `.git`, so the pin lives
  in the checkout, not the URL.) `installed-version` is the lockfile — it advances only when a
  `doc-sync/upgrade` PR merges, exactly like the marker. Never ship an unpinned marketplace
  checkout (bare `main`), and never version the `plugins:` selector (`@version` there is
  unsupported).
- **Don't customize the installed YAML beyond the cron/cap/bloat-cron/upgrade-cron knobs.** Real
  changes belong upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade.
- **The model never holds repository write authority.** A model job's `permissions:` stays
  `contents: read` (+ `id-token: write`), its checkout sets `persist-credentials: false`, and it
  carries no `GH_TOKEN`. Its output leaves as an artifact; a credentialed, model-free job
  authorizes that artifact's paths against the report (`authorize-paths.py`) and stages exactly
  them. Never widen a model job's token "so it can push", and never move a `claude-code-action`
  step into a job holding a write scope — `tests/scripts/workflow-permissions_test.py` fails the
  release if either happens.
- **Staging is an explicit path list, never `git add -A`.** The credentialed jobs stage
  `--pathspec-from-file` the authorized list and re-check what landed. A broad add would hand a
  model's stray file the same authority as an approved doc edit.
- **The drift report is a build artifact, never repo content.** The shipped workflow already
  removes it before the marker-only commit and before the edit-set export, and renders the PR
  body from a copy under `$RUNNER_TEMP` — don't "simplify" that by dropping the artifact-upload
  step or letting a hand edit reintroduce `drift-report.json`/`pr-body.md` into a commit.
- **Mechanical gate failures fail the job red, never silently.** A malformed `drift-report.json`
  makes `validate-drift-output.py` exit nonzero, and the workflow's validate step carries no
  `continue-on-error` — don't add one.
- **The weekly bloat sweep splits findings into two lanes by verdict:** `prune`
  (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`, passage-level) and `distill` (`MERGE-DOC`/`RETIRE-DOC`/
  `POLICY`, or `DISTILL` with `status: ready`, doc-level). A `DISTILL` record still
  `pending-implementation` belongs to neither lane and is never opened as a PR.
- **`doc-bloat.yml` is a separate sibling workflow from `doc-sync.yml`, each with its own
  concurrency group** — drift's marker-based detect-fix model and bloat's marker-less
  detect-propose model would tangle if combined. Bloat output is always a **draft PR**, never
  auto-merged or direct-committed.

## Red flags — STOP

- Writing detection or fixing instructions inside a workflow prompt → invoke the skills by name.
- `git rev-parse HEAD > .github/doc-sync-marker` when the file already exists → upgrade, keep it.
- Overwriting an existing `.github/doc-sync/audit-scope.json` with the empty starter → it's a tuned
  config, not wiring; seed it only when absent.
- Adding a direct-commit mode, or dropping the cap/pending-work gates "to simplify" → the gates
  are the product; see the design doc in aj604/toolshed.
- Committing `drift-report.json` or `pr-body.md` as repo content → artifact hygiene, not history.
- Giving a model job `contents: write`, a `GH_TOKEN`, or a credential-persisting checkout "so the
  fix step can just push" → that is the mutation path the job split closes; the fix leaves as a
  patch artifact.
- Replacing the `authorize-paths.py` check with a trusting `git apply` + `git add -A`, or
  generating the edit-set patch without `--no-renames` → a rename reports only its destination to
  the check, so the source path would go unexamined.
- Dropping the `Pin plugin marketplace` clone step, or pointing `plugin_marketplaces` at
  `…/toolshed.git` (bare `main`) → an unpinned install that floats and drifts from the frozen
  wiring. Pin it via the local checkout of the release tag.
- Reaching for `plugin_marketplaces: …/toolshed.git#v<version>` → `claude-code-action` rejects it
  ("Invalid marketplace URL format"); its validator requires the URL end in `.git`. Pin via the
  local checkout instead.
- Writing `plugins: doc-lifecycle@toolshed@<version>` → the `@version` selector is unsupported;
  pin via the local checkout of the release tag only.
- Resetting `.github/doc-sync/installed-version`, or overwriting the marker/audit-scope, during an
  upgrade → upgrade preserves consumer state; only wiring + the pin + the lockfile change.
