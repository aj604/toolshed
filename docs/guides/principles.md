# Docs as checkable claims — how doc-lifecycle thinks

> As of 2026-07-30 (doc-lifecycle 0.45.0; skill files under `plugins/doc-lifecycle/skills/`, applier contract in `plugins/doc-lifecycle/engine/README.md`)

Five minutes here explains every skill in the plugin. Each principle below names the
skill file that enforces it, so none of this is aspiration — you can go read the rule.

## 1. A repo-tracking doc is a set of claims

A README, runbook, or CLAUDE.md exists to be *true of the repo as it is now*. So every
assertion unit has one of four classes (`skills/writing-docs/SKILL.md`):

- **factual** — a command, path, symbol, behavior, structure, or value checked against
  current evidence;
- **normative** — a rule checked against a current governing source or owner judgment;
- **rationale** — the "why", checked for coherence with current evidence;
- **non-assertive** — connective prose or signposting, the only class that takes no judgment.

Classification never waives a living truth obligation. The first three classes are always
`VERIFIED`, `STALE`, or `UNVERIFIABLE`; only non-assertive prose remains unjudged.

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

Both audit lanes are **read-only**. They emit structured records — a verdict from a fixed
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
install it via `scheduling-doc-sync`, as five GitHub Actions:

- `doc-audit.yml`, a **nightly drift audit** that is read-only and stops at a published report;
- `doc-bloat-audit.yml`, a **weekly bloat audit** that is also read-only and stops at a
  published report, with incomplete coverage stated explicitly;
- `doc-apply.yml`, a **manual apply dispatch** that opens one real pull request for the record
  digests a person approved;
- `doc-policy-apply.yml`, an optional audit-chained lane that can open a review PR only for the
  engine's closed eligible drift subset under an explicitly committed policy; and
- `doc-sync-upgrade.yml`, whose **weekly self-upgrade check** may file one notice issue, while
  running release code and opening an upgrade PR still require a human dispatch.

Scheduled bloat findings still require a person to approve record IDs through `fixing-docs`;
the weekly bloat lane never applies, branches, or opens a pull request. See
[scheduling-doc-sync.md](scheduling-doc-sync.md) for the full trust split and
[auditing-doc-bloat.md](auditing-doc-bloat.md) for review and application.
Merging is still the only thing that lands anything; the schedule can only ever propose.

Run the loops by hand first. When the record shapes are familiar and the approvals feel
routine, [turn on the schedule](scheduling-doc-sync.md) — that ordering is the intended
onboarding path, not a suggestion.

## Where to start

- Repo with no docs → [Starting docs from scratch](starting-docs-from-scratch.md)
- Docs that might no longer be true → the drift loop: [What an audit hands you](../../README.md#what-an-audit-hands-you)
- Docs that have grown heavy → [Auditing and fixing bloat](auditing-doc-bloat.md)
- Loops familiar, want them unattended → [Turning on the nightly](scheduling-doc-sync.md)
