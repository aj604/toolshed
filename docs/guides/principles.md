# Docs as checkable claims — how doc-lifecycle thinks

> As of 2026-07-29 (doc-lifecycle 0.44.0; skill files under `plugins/doc-lifecycle/skills/`, applier contract in `plugins/doc-lifecycle/engine/README.md`)

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
enum, cited evidence — and stop. One skill applies them, `fixing-docs`, and only what you
authorized: every record carries an ID, you approve a subset of IDs, and that selection is
minted into an **approval set** — the artifact the applier treats as its sole authority, a
report on its own being worth nothing. Drift and bloat land through the same door and the
same gate: each approved `STALE` record's drafted fix at the unit it names (`location` is
a display string the engine derives for readers; the unit digest is what anchors the edit),
and each approved bloat record's span and nothing beside it. No "while I'm here" cleanups, no rewording the
proposal text. That discipline has one written owner, the applier contract in
`plugins/doc-lifecycle/engine/README.md` (its "Approval sets" and "The applier" sections),
which `fixing-docs` cites. A fix that also lands its author's opinions stops being
reviewable; this one stays reviewable by construction.

## 4. Automation is a graduation, not a default

Installing the plugin schedules **nothing**. The skills run when you ask, in your
session, with you approving. Unattended operation exists — but only after you explicitly
install it via `scheduling-doc-sync`, as three GitHub Actions with the write authority
split out of the schedule: a **nightly drift audit** that holds `contents: read`, no
credential, and opens no PR, no commit, no issue — it stops at a published report; a
**manual apply dispatch**, never scheduled, that a person triggers by naming the record
digests they approve, and which opens one **real pull request** (never a draft) for you
to merge; and a **weekly self-upgrade check** that compares your installed version to the
plugin's latest release and, when one is available, files a notice issue naming it — the
schedule never opens a PR on its own. A PR only appears once a person dispatches the same
workflow by hand naming the target version; that dispatch clones the target release,
regenerates the wiring, and opens the review PR (see [scheduling-doc-sync.md](scheduling-doc-sync.md)).
There is no scheduled bloat sweep — bloat auditing stays interactive
(`docs/guides/auditing-doc-bloat.md`).
Merging is still the only thing that lands anything; the schedule can only ever propose.

Run the loops by hand first. When the record shapes are familiar and the approvals feel
routine, [turn on the schedule](scheduling-doc-sync.md) — that ordering is the intended
onboarding path, not a suggestion.

## Where to start

- Repo with no docs → [Starting docs from scratch](starting-docs-from-scratch.md)
- Docs that might no longer be true → the drift loop: [What an audit hands you](../../README.md#what-an-audit-hands-you)
- Docs that have grown heavy → [Auditing and fixing bloat](auditing-doc-bloat.md)
- Loops familiar, want them unattended → [Turning on the nightly](scheduling-doc-sync.md)
