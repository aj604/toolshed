---
name: detecting-doc-drift
description: Use when auditing documentation against the code it describes, checking whether a README/CLAUDE.md/runbook is still accurate, or finding which doc passages a code change invalidates — and whenever drift detection is invoked programmatically (by a PR check, nightly sync, or doc-sync-automation) and must emit a structured, parseable result.
---

# Detecting Doc Drift

## Overview

**A doc is a set of claims about the repo; drift is a claim the repo no longer backs.**
This skill declares the *shape* of drift detection so it runs the same way every time and
can be **invoked programmatically to trigger updates** — not a one-off prose review.

Two non-negotiables make the output usable by automation:

1. **A verdict requires evidence.** Never mark a claim VERIFIED because doc and code "seem
   consistent." Verified means you ran the command, opened the line, or matched the grep.
2. **The result is structured, not prose.** Emit the declared record shape below. A human
   summary on top is fine; the structured block is the contract downstream tooling parses.

**REQUIRED SUB-SKILL:** Use **writing-docs** for any fix you propose — every `fix` must meet
its bar (real output, no aspirational claims, marked+anchored rationale). This skill finds
and classifies drift; writing-docs governs how the correction reads. **`fixing-doc-drift`**
consumes this skill's records and applies the fixes (an optional auto-trigger layer can wire
detect→fix to cron/PR).

## The engine (run these four steps, in order)

1. **Extract** each checkable claim from the doc, tagged by `kind` — one of exactly:
   `command`, `path`, `symbol`, `behavior`, `structure`, `value` (use these strings
   verbatim; automation switches on them). Pure prose is not a claim — **except** lines that
   *sound* factual but name no checkable thing ("robust", "production-ready", "reasonably
   fast", "handles most workloads"). Extract those too, kind `value`: they become
   `UNVERIFIABLE`. Do not skip them — an unbacked quality claim is the most common drift a
   human eye waves through.
2. **Verify** each claim against the repo at the appropriate tier (below).
3. **Classify** each: `VERIFIED` / `STALE` / `UNVERIFIABLE`.
4. **Emit** the structured result (the contract below), then **validate it mechanically**
   before handing it off: pipe it through `scripts/validate-drift-output.py` (reads the JSON
   on stdin or as a file arg). It enforces the enum/`fix`/`evidence`/summary rules and exits
   nonzero on any violation — don't emit a result it rejects. It checks *shape*, not whether a
   verdict is *right*; that judgment is still yours.

### Verification tiers + escalation rule

| Tier | Cost | Does | Catches |
|------|------|------|---------|
| 1 STATIC | seconds | grep/glob: path/symbol exists, command exists in Makefile/package.json, link resolves | renames, moves, deletions |
| 2 SHALLOW | moderate | read the cited line; run safe `--help`/`--version`/dry-run | changed flags, values, signatures |
| 3 DEEP | expensive | read implementing code; run the documented workflow where safe | behavior drift |

**Every claim starts at Tier 1.** Escalate a claim only when (a) Tier 1 flags suspicion,
(b) the claim's subject is in the diff (diff-scoped mode), or (c) a deep audit was
requested. This concentrates cost where drift is likely.

**Anchors: open the line, but judge the claim, not the line number.** A `file:line` anchor
is not evidence — open it. But the anchor is *metadata on a claim, never its own claim*: do
not extract "the exit is at line 14" as a separate record and grade its precision. Classify
the underlying claim on whether the *referenced construct* is there and the *stated value* is
right. An anchor that lands a few lines off the exact statement (points at the guard instead
of the `exit()` it guards) but still locates the right code is `VERIFIED`. **Never emit a
STALE record whose `fix` only changes a line number** — a line-number-only correction is not
drift. Mark `STALE` only when the value/behavior/symbol is wrong or the anchor points to a
construct that moved or no longer exists.

## The output contract (this is the "shape")

Emit one record per extracted claim — STALE and UNVERIFIABLE records are what automation acts
on; VERIFIED records prove coverage. Each record uses exactly these fields: `claim`,
`location` (`file:line`), `kind`, `tier`, `verdict`, `evidence`, `fix`.

Rules: `kind` is one of `command` / `path` / `symbol` / `behavior` / `structure` / `value`;
`verdict` is one of `VERIFIED` / `STALE` / `UNVERIFIABLE` — literal enum strings, no invented
values. `fix` is non-null only for `STALE`. `evidence` is mandatory for **every** verdict,
including VERIFIED (the grep/command/line that proves it). End with a one-line summary
automation can gate on: `summary: {verified: N, stale: N, unverifiable: N}`.

See **output-contract.md** for a worked three-record example (a STALE command, a STALE
behavior, an UNVERIFIABLE quality claim) with every field populated.

`scripts/validate-drift-output.py` enforces all of the above mechanically (run it on the
result — see step 4). Pass it `{"records": [...], "summary": {...}}` and it also checks the
summary counts against the records; pass a bare array and it recomputes the authoritative
summary for you.

## Modes

- **Full audit** (manual / nightly sweep): extract every claim across the target docs,
  Tier 1 by default, escalate per the rule. Emit the full record list, severity-ordered
  (wrong command/behavior before stale prose).
- **Diff-scoped** (PR check / what automation calls): input is a diff or commit range. For
  each changed file/symbol/value, **grep every doc for passages referencing it** — including
  command output blocks and examples, not just the obvious gotcha line — then verify those
  claims at Tier 3. Output only records for touched claims. Completeness is the metric: a
  changed symbol referenced in five docs must produce five records.

## Red flags — STOP

- Writing "looks consistent" / "should be fine" without opening the file → not a verdict.
- Trusting a `file:line` anchor instead of reading that line → anchors don't rot, values do.
- Emitting a prose report with no structured records → automation can't trigger on it.
- A VERIFIED record with an empty `evidence` field → unverified; go get the evidence.
- Diff-scoped run that checked the one obvious doc → grep ALL docs for the changed subject.
- Eyeballing a command table instead of grepping the Makefile/package.json for each target.
- Skipping a "robust"/"fast"/"production-ready" line because it's "just prose" → extract it
  as UNVERIFIABLE; that is the finding.
- A record with an invented `kind` (e.g. `schema_mismatch`) → use the six enum values only.
- Marking an anchor STALE for being off by a line, or emitting a `fix` that only changes a
  line number → not drift. The anchor is metadata, not its own claim.
