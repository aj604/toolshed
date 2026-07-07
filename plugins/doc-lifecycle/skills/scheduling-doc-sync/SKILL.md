---
name: scheduling-doc-sync
description: Use when wiring a repo for automated/unattended documentation drift sync — "set up doc sync", "automate drift detection", "schedule nightly doc checks", "keep docs in sync automatically" — installs the doc-lifecycle nightly GitHub Action (detect → gate → fix → evidence PR) instead of hand-rolling workflow YAML. Also the door for upgrading an existing install.
---

# Scheduling Doc Sync

## Overview

Installs the shipped automation into a target repo — **two workflows**: the nightly drift
sync (`doc-sync.yml`) and the weekly chunked doc-bloat sweep (`doc-bloat.yml`: deterministic
chunk plan → matrix detect → assemble → two draft-PR lanes). **You install wiring; you do not
re-derive it.** Orchestration lives in the shipped workflow YAML; every gate decision lives in
the shipped `sync-gate.py`; every run-surface string (summaries, notices, issue/PR bodies) lives
in the shipped `render-report.py`; chunk planning lives in `plan-chunks.py`; doc judgment lives
in `detecting-doc-drift` / `fixing-doc-drift` / `detecting-doc-bloat` / `fixing-doc-bloat`,
which the workflows invoke headlessly by name. Never inline detection or fixing method into
workflow YAML — that forks the method from its one owner.

The workflow templates and gate/render scripts are in this skill's base directory (announced
when the skill loads); the chunk planner and the two output validators are copied from the
sibling skills that own them (install steps 3–4).

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
2. Copy `doc-sync.yml` → `.github/workflows/doc-sync.yml`, replacing the literal placeholders
   `{{CRON_SCHEDULE}}` and `{{BLAST_RADIUS_CAP}}` with the chosen values. Copy `doc-bloat.yml` →
   `.github/workflows/doc-bloat.yml`, replacing `{{BLOAT_CRON}}`.
3. Copy `scripts/sync-gate.py` → `.github/doc-sync/sync-gate.py`,
   `scripts/render-report.py` → `.github/doc-sync/render-report.py`, and
   `../detecting-doc-bloat/scripts/plan-chunks.py` → `.github/doc-sync/plan-chunks.py`
   (gate decisions, run-surface rendering, and doc-bloat's deterministic chunk planning all
   run from the repo, unit-tested upstream — for both `doc-sync.yml` and `doc-bloat.yml`).
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
7. Tell the user, concretely:
   - the nine files to commit (`doc-sync.yml`, `doc-bloat.yml`, `sync-gate.py`,
     `render-report.py`, `plan-chunks.py`, `validate-drift-output.py`,
     `validate-bloat-output.py`, the seeded `audit-scope.json`, and the seeded
     `doc-sync-marker`);
   - first night: diff from the seeded marker; no drift → marker-only commit, drift → PR on
     `doc-sync/nightly` with evidence, over-cap → a `doc-sync` issue;
   - the weekly bloat sweep opens up to two **draft** PRs (`doc-bloat/prune`, `doc-bloat/distill`);
     a lane with no findings, or whose PR is already open, is skipped with a self-explaining run
     summary;
   - run them now with `gh workflow run doc-sync` and `gh workflow run doc-bloat`;
   - upgrades: re-run this skill (marker preserved; template/scripts refreshed);
   - **sync PRs carry no CI checks** (pushed via `GITHUB_TOKEN`, which never retriggers CI);
     mint a GitHub App token (`actions/create-github-app-token`) instead if CI-on-doc-PRs matters.

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
- **Upgrade preserves the marker** (step 6). Overwrite the yml and scripts freely; the marker
  is state, not wiring.
- **Don't customize the installed YAML beyond the cron/cap/bloat-cron knobs.** Real changes belong
  upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade.
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
