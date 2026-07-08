---
name: scheduling-doc-sync
description: Use when wiring a repo for automated/unattended documentation drift sync — "set up doc sync", "automate drift detection", "schedule nightly doc checks", "keep docs in sync automatically" — installs the doc-lifecycle nightly GitHub Action (detect → gate → fix → evidence PR) instead of hand-rolling workflow YAML. Also the door for upgrading an existing install.
---

# Scheduling Doc Sync

## Overview

Installs the shipped automation into a target repo — **three workflows**: the nightly drift
sync (`doc-sync.yml`), the weekly chunked doc-bloat sweep (`doc-bloat.yml`: deterministic
chunk plan → matrix detect → assemble → two draft-PR lanes), and the weekly self-upgrade
(`doc-sync-upgrade.yml`: compare installed version to the plugin's latest release → regenerate
the wiring at a newer one → open a review PR). **You install wiring; you do not re-derive it.**
Orchestration lives in the shipped workflow YAML; every gate decision lives in the shipped
`sync-gate.py` / `upgrade-gate.py`; every run-surface string (summaries, notices, issue/PR
bodies) lives in the shipped `render-report.py`; chunk planning lives in `plan-chunks.py`; doc
judgment lives in `detecting-doc-drift` / `fixing-doc-drift` / `detecting-doc-bloat` /
`fixing-doc-bloat`, which the workflows invoke headlessly by name. Never inline detection or
fixing method into workflow YAML — that forks the method from its one owner.

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
`$RUNNER_TEMP`, never inside the work tree, or the PR steps' `git add -A` captures it.
Pin via the local checkout, NOT a `plugin_marketplaces: …/toolshed.git#v<version>` ref —
`claude-code-action`'s URL validator requires the value end in `.git`, so a `#<ref>` fragment is
rejected outright. `doc-sync-upgrade.yml` is the only thing that advances the pin, and only via a
reviewable PR. The `plugins:` selector stays bare `doc-lifecycle@toolshed` (`claude-code-action`
has no `@version` selector there — `doc-lifecycle@toolshed@0.7.0` is invalid).

The three workflow templates and the gate/render scripts (`sync-gate.py`, `upgrade-gate.py`,
`render-report.py`) are in this skill's base directory (announced when the skill loads); the
chunk planner and the two output validators are copied from the sibling skills that own them
(install steps 3–4).

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
   - upgrade cron: default `0 5 * * 1` (05:00 UTC Mondays); replaces `{{UPGRADE_CRON}}` in
     doc-sync-upgrade.yml. The plugin version is NOT a knob — it's read from the plugin manifest,
     not chosen (next step).
2. Resolve the version being installed: `jq -r .version "$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json"`
   (the bare semver, e.g. `0.7.0`). Copy the three workflow templates, replacing the literal
   placeholders in each:
   - `doc-sync.yml` → `.github/workflows/doc-sync.yml`: `{{CRON_SCHEDULE}}` and `{{BLAST_RADIUS_CAP}}`.
   - `doc-bloat.yml` → `.github/workflows/doc-bloat.yml`: `{{BLOAT_CRON}}`.
   - `doc-sync-upgrade.yml` → `.github/workflows/doc-sync-upgrade.yml`: `{{UPGRADE_CRON}}`.
   The workflow YAML carries NO version placeholder — each `Pin plugin marketplace` step reads
   `.github/doc-sync/installed-version` at runtime (written in step 7) and clones that tag, so the
   workflow files are version-agnostic (Overview). The version from step 2 lands only in that
   lockfile.
3. Copy `scripts/sync-gate.py` → `.github/doc-sync/sync-gate.py`,
   `scripts/upgrade-gate.py` → `.github/doc-sync/upgrade-gate.py`,
   `scripts/render-report.py` → `.github/doc-sync/render-report.py`, and
   `../detecting-doc-bloat/scripts/plan-chunks.py` → `.github/doc-sync/plan-chunks.py`
   (gate decisions, the version-comparison gate, run-surface rendering, and doc-bloat's
   deterministic chunk planning all run from the repo, unit-tested upstream — across all three
   workflows).
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
6. Seed the marker — **only if absent**:
   `test -f .github/doc-sync-marker || git rev-parse HEAD > .github/doc-sync-marker`
   An existing marker means an existing install: this is an upgrade, and resetting the marker
   would silently skip every commit since the last sync. Never reset it.
7. Write the version lockfile: `.github/doc-sync/installed-version` = the bare version from step 2
   (e.g. `0.7.0`). Unlike the marker/audit-scope, this tracks the wiring version and must equal
   the pin, so on a fresh install always write it. `doc-sync-upgrade.yml` reads it to decide
   whether a newer release exists; it advances only when an upgrade PR merges.
8. Tell the user, concretely:
   - the twelve files to commit (`doc-sync.yml`, `doc-bloat.yml`, `doc-sync-upgrade.yml`,
     `sync-gate.py`, `upgrade-gate.py`, `render-report.py`, `plan-chunks.py`,
     `validate-drift-output.py`, `validate-bloat-output.py`, the seeded `audit-scope.json`, the
     seeded `doc-sync-marker`, and `installed-version`);
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

Dispatched headlessly by `doc-sync-upgrade.yml` (or run by a human forcing an upgrade) once a
newer plugin release exists. It regenerates the vendored wiring at the new version while leaving
every consumer-owned value alone. **It is not a fresh install** — skip the Preflight (secrets,
labels, PR-permissions are already in place) and do not re-seed the marker or audit-scope.

Ownership is the whole game — total on wiring, idempotent on state:

| File | Owner | Upgrade behavior |
|------|-------|------------------|
| `doc-sync.yml`, `doc-bloat.yml`, `doc-sync-upgrade.yml` | plugin (wiring) | **Regenerate** from the new templates, but re-inject the consumer's existing knobs (below), not the template defaults. No version to re-pin — the Pin steps read `installed-version` at runtime. |
| `.github/doc-sync/*.py` (all six scripts) | plugin (wiring) | **Overwrite** from the new version. |
| `.github/doc-sync/installed-version` | version state | **Set** to `<target>` (bare semver). This is what advances the pin; on a version-only release it's the *only* file that changes. |
| `.github/doc-sync-marker` | sync state | **Never touch.** |
| `.github/doc-sync/audit-scope.json` | consumer (tuned config) | **Never touch.** |

**Preserve the knobs — read them out of the installed files, never reset to defaults.** Before
overwriting a workflow, extract its current value and substitute *that* back in:
- `doc-sync.yml`: the `cron:` under `schedule` → `{{CRON_SCHEDULE}}`; the `CAP:` env → `{{BLAST_RADIUS_CAP}}`.
- `doc-bloat.yml`: its `cron:` → `{{BLOAT_CRON}}`.
- `doc-sync-upgrade.yml`: its `cron:` → `{{UPGRADE_CRON}}`. If this file is absent (an install
  predating self-upgrade), add it with the default upgrade cron and note it in the PR body.

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
- **Upgrade preserves the marker** (step 6) and the version lockfile discipline. Overwrite the
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
- **The drift report is a build artifact, never repo content.** The shipped workflow already
  removes it before the marker-only commit and moves it out of the working tree before the PR
  commit's `git add -A` — don't "simplify" that by dropping the artifact-upload step or letting
  a hand edit reintroduce `drift-report.json`/`pr-body.md` into a commit.
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
- Dropping the `Pin plugin marketplace` clone step, or pointing `plugin_marketplaces` at
  `…/toolshed.git` (bare `main`) → an unpinned install that floats and drifts from the frozen
  wiring. Pin it via the local checkout of the release tag.
- Reaching for `plugin_marketplaces: …/toolshed.git#v<version>` → `claude-code-action` rejects it
  ("Invalid marketplace URL format"); its validator requires the URL end in `.git`. Pin via the
  local checkout instead.
- Writing `plugins: doc-lifecycle@toolshed@<version>` → the `@version` selector is unsupported;
  pin via the `#v<version>` ref on `plugin_marketplaces` only.
- Resetting `.github/doc-sync/installed-version`, or overwriting the marker/audit-scope, during an
  upgrade → upgrade preserves consumer state; only wiring + the pin + the lockfile change.
