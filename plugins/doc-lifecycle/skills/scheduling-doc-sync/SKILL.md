---
name: scheduling-doc-sync
description: Use when wiring a repo for automated/unattended documentation drift sync — "set up doc sync", "automate drift detection", "schedule nightly doc checks", "keep docs in sync automatically" — installs the doc-lifecycle nightly GitHub Action (detect → gate → fix → evidence PR) instead of hand-rolling workflow YAML. Also the door for upgrading an existing install.
---

# Scheduling Doc Sync

## Overview

Installs the shipped nightly pipeline into a target repo. **You install wiring; you do not
re-derive it.** Orchestration lives in the shipped `doc-sync.yml`; every gate decision lives in
the shipped `sync-gate.py`; doc judgment lives in `detecting-doc-drift` / `fixing-doc-drift`,
which the workflow invokes headlessly by name. Never inline detection or fixing method into
workflow YAML — that forks the method from its one owner.

All shipped files are in this skill's base directory (announced when the skill loads).

## Preflight (run all; report failures, don't silently skip)

1. Target repo has a GitHub remote: `git remote get-url origin`. No remote → stop; this
   pipeline is a GitHub Action. (A non-GitHub repo wants a different trigger — tell the user.)
2. `gh auth status` succeeds.
3. `gh secret list` shows `ANTHROPIC_API_KEY`. If absent: **warn, don't block** — offer to run
   `gh secret set ANTHROPIC_API_KEY` with the user pasting the value; the workflow fails red on
   its first model call without it.
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

1. Confirm the two knobs with the user (defaults are fine unattended):
   - cron: default `0 3 * * *` (03:00 UTC nightly)
   - blast-radius cap: default `10` (matches fixing-doc-drift's default of ~10 passages)
2. Copy `doc-sync.yml` → `.github/workflows/doc-sync.yml`, replacing the literal placeholders
   `{{CRON_SCHEDULE}}` and `{{BLAST_RADIUS_CAP}}` with the chosen values.
3. Copy `scripts/sync-gate.py` → `.github/doc-sync/sync-gate.py`.
4. Copy `../detecting-doc-drift/scripts/validate-drift-output.py` → `.github/doc-sync/validate-drift-output.py`
   (the workflow's mechanical contract check runs from the repo, not the plugin cache).
5. Seed the marker — **only if absent**:
   `test -f .github/doc-sync-marker || git rev-parse HEAD > .github/doc-sync-marker`
   An existing marker means an existing install: this is an upgrade, and resetting the marker
   would silently skip every commit since the last sync. Never reset it.
6. Tell the user, concretely:
   - the four files to commit;
   - first night: diff from the seeded marker; no drift → marker-only commit, drift → PR on
     `doc-sync/nightly` with evidence, over-cap → a `doc-sync` issue;
   - run it now with `gh workflow run doc-sync`;
   - upgrades: re-run this skill (marker preserved; template/scripts refreshed).

## Rules

- **PR-only output.** Never configure the pipeline to commit doc edits directly to the default
  branch — not even if asked ("PRs are annoying"). The reviewable evidence-PR *is* the product;
  a direct-commit pipeline is an unreviewable one. The only direct push the pipeline makes is
  the marker-only commit on a no-drift run.
- **Upgrade preserves the marker** (step 5). Overwrite the yml and scripts freely; the marker
  is state, not wiring.
- **Don't customize the installed YAML beyond the two knobs.** Real changes belong upstream in
  the plugin (aj604/toolshed) so every install gets them on next upgrade.
- **The drift report is a build artifact, never repo content.** The shipped workflow already
  removes it before the marker-only commit and moves it out of the working tree before the PR
  commit's `git add -A` — don't "simplify" that by dropping the artifact-upload step or letting
  a hand edit reintroduce `drift-report.json`/`pr-body.md` into a commit.

## Red flags — STOP

- Writing detection or fixing instructions inside a workflow prompt → invoke the skills by name.
- `git rev-parse HEAD > .github/doc-sync-marker` when the file already exists → upgrade, keep it.
- Adding a direct-commit mode, or dropping the cap/pending-work gates "to simplify" → the gates
  are the product; see the design doc in aj604/toolshed.
- Committing `drift-report.json` or `pr-body.md` as repo content → artifact hygiene, not history.
