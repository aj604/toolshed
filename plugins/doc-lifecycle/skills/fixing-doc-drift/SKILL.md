---
name: fixing-doc-drift
description: Use when applying a drift report (detecting-doc-drift output) to the docs — syncing documentation to code after drift is found, landing fixes from a structured STALE/VERIFIED/UNVERIFIABLE record set, or whenever tempted to "clean up", reword, or delete doc passages the report did not flag.
---

# Fixing Doc Drift

## Overview

**The drift report is your mandate — not the doc's overall quality.** You apply the fixes the
report authorized and nothing else. A sync that also "improves" the doc stops being reviewable:
a human can no longer tell an evidence-backed correction from your opinion.

**Violating the letter of the report is violating the spirit of the sync.**

Input: a `detecting-doc-drift` drift report — `STALE` / `VERIFIED` / `UNVERIFIABLE` records,
each with `evidence`; `STALE` records carry a single-line `location` (`file:line`) and a `fix`
that is the complete replacement text for that line — the drift-report contract guarantees the
shape. This skill *applies* it; it does not re-audit.
**REQUIRED SUB-SKILL:** use **writing-docs** for any fix that needs real rewriting (a paragraph),
not a string-swap.

## The rules (these address what agents get wrong)

### 1. Act only on STALE records

Apply each `STALE` record's `fix` at its `location`. `VERIFIED` and `UNVERIFIABLE` are **not
action items**: VERIFIED records prove coverage; UNVERIFIABLE records are surfaced for human
review, not edit targets. VERIFIED passages stay **byte-identical** (sole exception: a line
shared with a STALE claim — Rule 5 owns that case).

### 2. Never delete — flag instead

Do not delete any passage, including vague or unverifiable prose. `UNVERIFIABLE` means *"a human
should decide"*, not *"cut it."* Cutting unverifiable lines is a deliberate **writing-docs**
cleanup, never a silent side effect of a drift sync.

### 3. No "while I'm here"

Spot a real problem the report didn't flag? **Surface it to the human; do not edit it.** An
out-of-scope fix — however correct — breaks the one-to-one map between the report and the diff,
which is the only thing that makes the sync reviewable.

### 4. Confirm the anchor before you write

Before applying a `fix`, read the line at its `location` and confirm it still contains the
record's `claim` (detection tolerates a few lines of anchor drift — search the nearby lines if
the exact line moved). Claim not found → the doc changed after the report was cut: **do not
apply the fix, do not guess a placement** — stop and re-run `detecting-doc-drift` for a fresh
report. Applying blind overwrites the wrong line. Two `STALE` records targeting one `location`
is the same stop: two full-line replacements cannot both hold, so the report is contradictory —
re-run detection rather than picking one.

### 5. Land the fix as-is; rewrite only when needed

The record's `fix` is the full-line replacement for its `location` — the drift-report contract
guarantees the shape, and it already meets the writing-docs bar: **apply it verbatim, and stop
at its boundary.** A `fix` that re-emits a whole line — including clauses the report didn't
single out — is still in scope: the report drafted that scope, you are *placing* it, not
extending it. When a `STALE` and a `VERIFIED` claim share one `location`, the `STALE` `fix` is
the full-line replacement, and "byte-identical" (Rule 1) protects the VERIFIED claim's surviving
substring — it is not a competing whole-line rule. Only when a fix is *structural* (a paragraph,
not a string) dispatch **writing-docs**, which routes audience/density itself.

### 6. Blast-radius stop

If the report crosses the cap (default: **~10 STALE records, or more than a third of the
report's records STALE**) or the doc is wholesale-wrong, **stop and escalate** — open an issue /
tell the human. Wholesale regeneration is a red flag, not a fix: do not emit a giant rewrite.

### 7. Evidence travels with the change

The commit / PR body maps each edit to its record's `evidence` (`file:line` or command output).
A reviewer confirms the sync by diffing against the report, not by re-deriving it.

## Red flags — STOP

- About to delete a line the report marked `UNVERIFIABLE` → flag it, don't cut it.
- Editing a passage with no matching `STALE` record → out of scope; surface instead.
- "The doc contract says cut unverifiable prose, so I'll delete it" → that's a writing-docs
  cleanup, not this sync. Not your mandate here.
- The line at `location` no longer carries the record's claim → the report is stale; re-run
  detection, don't guess a placement.
- Rewording or restructuring a `VERIFIED` passage to "read better" → it stays byte-identical.
- The report flags most of the doc and you're about to rewrite it all → blast-radius stop.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The unverifiable line violates the doc contract — delete it" | Deletion is a content call outside the sync. Flag it; a human decides. |
| "While I'm here I'll fix this other wrong line I noticed" | Not in the report = not reviewable against the report. Surface it. |
| "I'll tidy this VERIFIED passage too" | VERIFIED stays byte-identical, or the diff stops mapping to evidence. |
| "The whole doc is stale — easier to just regenerate it" | Blast-radius stop. Escalate; don't bury 30 edits in one unreviewable change. |
