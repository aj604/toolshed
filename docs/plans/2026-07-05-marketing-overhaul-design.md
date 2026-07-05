# Marketing overhaul: onboarding guides + README restructure — design

**Date:** 2026-07-05
**Status:** approved (in-session), implemented in the same PR

## Problem

The README was kept drift-synced but its structure predates the bloat suite, the
doc-distiller agent, DISTILL insight extraction, and the weekly bloat Action. Worse, the
onboarding journey is missing: a new user installs, runs a couple of requests, and the
first structural thing they meet is a large nightly PR they never consciously signed up
for. Nothing sells the model (docs as claims, propose → approve → apply) before the
automation shows up, and automation is not framed as an explicit choice.

## Decisions

- **Audience:** prospective users landing on the GitHub repo.
- **Deliverable:** README restructure + a `docs/guides/` set (approach A of three
  considered; B was one long GETTING-STARTED.md, C was README-only).
- **Guide set:** `principles.md`, `starting-docs-from-scratch.md`,
  `auditing-doc-bloat.md`, `scheduling-doc-sync.md`. Naming is task-descriptive
  filenames with skill names surfaced in the titles (user picked a blend of the two
  schemes offered).
- **Journey shape:** each guide opens with a prerequisite line and ends with a pointer
  to the next step; the automation guide gates itself behind "run the interactive loops
  first." That is the structural fix for the surprise-PR failure.
- **Principles live in their own doc** (`docs/guides/principles.md`); the README keeps a
  teaser paragraph and links out.
- **Guides are durable narrative docs** under growing-docs' template: `> As of` anchor
  first line, every embedded command/path/claim true of the repo and verified. The anchor
  line — not the directory — is what makes detecting-doc-bloat classify them as
  narrative, so `.github/doc-sync/audit-scope.json` needs no change.
- **`docs/guides/` is a recorded exception** to this repo's flat-`docs/` convention
  (CLAUDE.md gets the one-line note). Guides cannot live in `docs/plans/` — growing-docs
  forbids narrative docs there (they'd read as distill-on-landing planning artifacts).
- **`docs/doc-scope.md` created** (growing-docs owns the format) logging the guides as
  demand-driven growth and deferring a drift-audit walkthrough guide until asked for.

## README restructure

Keep hero, problem diff, demo, install. Replace "Then just ask" with a "Pick your
starting point" section mapping repo state → guide. Update "What's in it" to the true
inventory (8 skills, 2 agents; bloat + drift as the two audit axes). Shrink "Why this
works" to a teaser linking `principles.md`. Reword automation claims so nightly sync is
plainly opt-in.

## Verification

Fresh-subagent continuity review per flow (README → each guide → back), plus a pass
confirming every cited skill, script, command, and PR exists.
