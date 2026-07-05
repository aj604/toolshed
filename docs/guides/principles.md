# Docs as checkable claims — how doc-lifecycle thinks

> As of 2026-07-05 (doc-lifecycle 0.6.2 @ e5201b8; skill files under `plugins/doc-lifecycle/skills/`)

Five minutes here explains every skill in the plugin. Each principle below names the
skill file that enforces it, so none of this is aspiration — you can go read the rule.

## 1. A repo-tracking doc is a set of claims

A README, runbook, or CLAUDE.md exists to be *true of the repo as it is now*. So every
line is one of two things (`skills/writing-docs/SKILL.md`):

- a **verifiable claim** — a command, path, symbol, behavior, or structure you can check
  against the code today;
- a **rationale claim** — the "why", allowed only in a marked section and anchored to a
  `file:line`, commit, or date, so its relevance can be audited later.

Anything else — invented example output, an aspirational "supports X", prose the reader
could infer from one obvious file — gets cut. Tutorials and design narratives are exempt
by design (this guide is one); fabrication inside them still isn't.

## 2. Docs fail on two axes, and each axis gets its own auditor

- **Drift** — the doc is *wrong*: the Makefile target was renamed, the exit code changed.
  `detecting-doc-drift` extracts each claim and verifies it against the code, with
  evidence on every verdict — including `VERIFIED`; "looks consistent" is not a verdict.
- **Bloat** — the doc is *accurate but past its useful form*: four sentences carrying one
  fact, two docs holding the same setup block, a design doc whose decisions already live
  in the code. `detecting-doc-bloat` judges every passage against that bar and proposes
  what to cut, condense, move, merge, or distill — with cited evidence.

Claims make both audits possible. You can't mechanically check "the architecture is
elegant"; you can check "reset state = `make reset`".

## 3. Nothing edits your docs without your approval

Both detectors are **read-only**. They emit structured records — a verdict from a fixed
enum, cited evidence — and stop. The fixers apply only what a report authorizes, and
nothing else: `fixing-doc-drift` takes the drift report you hand it as its whole mandate,
landing each `STALE` record's drafted fix at its location and never touching a passage
the report didn't flag; `fixing-doc-bloat` is gated harder still — every bloat record
carries an ID, you approve a subset of IDs, and exactly those records get applied. No
"while I'm here" cleanups, no rewording the proposal text. That discipline has one
written owner, `plugins/doc-lifecycle/references/apply-discipline.md`, which both fixers
cite. A fix that also lands its author's opinions stops being reviewable; this one stays
reviewable by construction.

## 4. Automation is a graduation, not a default

Installing the plugin schedules **nothing**. The skills run when you ask, in your
session, with you approving. Unattended operation exists — a nightly drift sync and a
weekly bloat sweep as GitHub Actions — but only after you explicitly install it via
`scheduling-doc-sync`, and it keeps the same shape: its output is **pull requests, never
direct commits to your default branch** (`skills/scheduling-doc-sync/SKILL.md` forbids a
direct-commit mode outright; the only direct push is a marker bump on a no-drift night).
Past its blast-radius cap the nightly files a labeled issue instead of an oversized PR,
and the bloat sweep only ever opens **draft** PRs.

Run the loops by hand first. When the record shapes are familiar and the approvals feel
routine, [turn on the schedule](scheduling-doc-sync.md) — that ordering is the intended
onboarding path, not a suggestion.

## Where to start

- Repo with no docs → [Starting docs from scratch](starting-docs-from-scratch.md)
- Docs that might no longer be true → the drift loop: [What an audit hands you](../../README.md#what-an-audit-hands-you)
- Docs that have grown heavy → [Auditing and fixing bloat](auditing-doc-bloat.md)
- Loops familiar, want them unattended → [Turning on the nightly](scheduling-doc-sync.md)
