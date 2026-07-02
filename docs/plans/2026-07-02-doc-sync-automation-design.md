# doc-sync-automation — Design

**Date:** 2026-07-02
**Status:** Approved (brainstorm with Avery, 2026-07-02)
**Fills:** item 5 in `HANDOFF.md` ("auto-trigger layer (cron/PR) — deferred, non-skill wiring");
"Skill 4: doc-sync-automation" sketch in `2026-06-09-documentation-skills-suite-design.md`.

## Problem

The lifecycle is built — bootstrap → write → detect (`detecting-doc-drift`, machine-parseable
records) → fix (`fixing-doc-drift`) — but nothing runs it unattended. A user who wants nightly
drift-sync must assemble the wiring themselves: pick a trigger, chain the two skills, invent
marker/idempotency mechanics, and rediscover the guardrails. Ship that assembly as a first-class
part of the `doc-lifecycle` plugin instead.

## Decision: GitHub Action runner, installed by a skill

Chosen over a Claude scheduled task (tied to one user's account, not the repo) and over local
git/session hooks (only fire while someone is working; noisy). A GitHub Action lives with the
repo, works for teams, and needs no laptop awake at 3am. Cost: requires a GitHub remote and an
`ANTHROPIC_API_KEY` repo secret.

Orchestration lives **only** in the shipped workflow; doc judgment lives only in the published
skills the workflow invokes headlessly. The installer only installs. (Single-owner rule: no
method duplicated into YAML prompt text.)

## Components

```
plugins/doc-lifecycle/skills/scheduling-doc-sync/
  SKILL.md            # installer skill — "set up doc sync", "automate drift detection"
  doc-sync.yml        # workflow template installed into target repos
  scripts/sync-gate.py  # deterministic gate decisions (unit-tested, stdlib-only)
```

### `scheduling-doc-sync` (installer skill)

Run once per target repo, interactively. Preflight + install, no doc judgment:

1. Preflight: GitHub remote exists; `gh` authenticated; warn (don't block) if it can't confirm
   an `ANTHROPIC_API_KEY` secret — offer to run `gh secret set`.
2. Copy `doc-sync.yml` to `.github/workflows/`, substituting two knobs: cron time (default
   03:00 UTC) and blast-radius cap (default ~10 stale passages, matching the fixer's cap).
3. Seed the sync marker at current `HEAD`.
4. State exactly what to commit and what the first night will do.

Template is copied into target repos, so upgrades don't propagate — SKILL.md tells users to
re-run the installer to upgrade.

### `doc-sync.yml` (the nightly pipeline)

Triggers: `schedule` (cron) + `workflow_dispatch` ("run it now"; also how E2E tests fire it).
A `pull_request` mode is **out of scope for v1** — the `on:` block carries a comment marking
the seam. Installs the doc-lifecycle plugin from this marketplace in CI so the invoked skills
are the published ones.

## Data flow (one nightly run)

1. **Diff range.** Read `.github/doc-sync-marker` (last-synced SHA); range = `marker..HEAD`
   on the default branch. Empty range → exit green, zero model calls.
2. **Pending-work check.** Open PR on branch `doc-sync/nightly`, or open issue labeled
   `doc-sync` → exit without detecting; previous findings await a human.
3. **Detect.** Headless Claude runs `detecting-doc-drift` in diff-scoped mode over the range →
   `drift-report.json`.
4. **Mechanical gate** (no model): `validate-drift-output.py` rejects malformed output → job
   fails red (contract bug, not drift). Then on the summary:
   - `stale == 0` → advance marker to HEAD via marker-only direct commit; exit green.
   - `stale > cap` → open a `doc-sync`-labeled issue listing the records; marker unchanged.
   - else → proceed.
5. **Fix.** Headless Claude runs `fixing-doc-drift` on the report (its own rules govern:
   STALE-only, never delete, no while-I'm-here).
6. **PR.** Branch `doc-sync/nightly`, one commit = doc edits + marker advanced to detected
   HEAD. PR body maps each edit to its record's `evidence`. **Merging the PR is what advances
   the marker** — unmerged/closed PR means the range is re-checked later (safe default).

Idempotency is marker mechanics, not model discipline: the marker advances only via a clean
run's direct commit or a merged PR; step 2 prevents pile-up in between.

## Error handling & permissions

Posture: **fail loud, never half-apply.**

- Malformed detect output → job red; raw output uploaded as artifact; marker untouched.
- Fix step dies mid-run → nothing pushed, no branch, marker untouched; next night retries the
  identical SHA-pinned range.
- `gh pr create` fails → job red with the error verbatim; pushed branch survives for manual PR.
- Missing/expired API key → first model call fails red; the standard Action-failure email is
  the notification channel (no custom notifier).

Workflow `permissions`: `contents: write, pull-requests: write, issues: write` — nothing else.
Headless steps pin `--allowedTools`: detect = read/grep/read-only bash; fix adds file edits.
The only default-branch push is the marker-only commit on a clean run; if branch protection
forbids that, the workflow carries the marker forward inside the next PR instead (staler
ranges, still correct).

## Guardrails carried from the suite design

Never rewrite what the diff didn't invalidate; never delete (flag only); blast-radius cap →
issue, not giant PR; idempotent re-runs; every rewritten claim cites evidence in the PR body.
The first three are enforced by `fixing-doc-drift` (already pressure-tested); the cap and
idempotency are enforced mechanically by the gate.

## Testing

- **Installer skill: RED → GREEN → REFACTOR** (writing-skills methodology; records to
  `tests/baselines/doc-sync-setup-red/`). RED axis (predicted, writable, tier-independent):
  baseline agent asked to "set up automated nightly doc sync" hand-rolls a workflow —
  re-invents detection in YAML prompt text, no marker/idempotency, direct-commits to main, no
  blast-radius stop. GREEN: with the skill → installs the shipped template, preflights, seeds
  marker. REFACTOR pressure: "commit straight to main, PRs are annoying" — hold the PR-only line.
- **Gate decisions: unit-tested script.** The branchy logic (empty range / pending work /
  stale==0 / stale>cap / proceed; when the marker may advance) lives in `sync-gate.py`
  (stdlib-only), tested by `tests/scripts/sync-gate_test.py` covering the decision matrix.
  YAML calls it and obeys exit codes. This becomes the repo's second published executable —
  update CLAUDE.md's "only executable code" line accordingly.
- **One real E2E before release:** push a fixture (reuse `drift-red` planted-drift docs) to a
  scratch GitHub repo, fire `workflow_dispatch`, verify detect → gate → fix → PR with evidence
  body end-to-end.
- `claude plugin validate` before tagging, as always.

## Out of scope (v1)

- `pull_request` trigger mode (comment-vs-commit policy, fork permissions, CI latency).
- Any notification channel beyond GitHub's own Action-failure email and the PR/issue itself.
- Multi-repo fleet management; the installer is one repo at a time.
