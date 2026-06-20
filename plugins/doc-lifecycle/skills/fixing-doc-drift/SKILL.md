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

Input: a `detecting-doc-drift` record set — `STALE` / `VERIFIED` / `UNVERIFIABLE`, each with
`evidence`; `STALE` records carry a drafted `fix`. This skill *applies* it; it does not re-audit.
**REQUIRED SUB-SKILL:** use **writing-docs** for any fix that needs real rewriting (a paragraph),
not a string-swap.

## The rules (these address what agents get wrong)

### 1. Act only on STALE records

Apply each `STALE` record's `fix` at its `location`. `VERIFIED` and `UNVERIFIABLE` are **not
action items** — they prove coverage / flag a smell, they are not work. VERIFIED passages stay
**byte-identical**.

### 2. Never delete — flag instead

Do not delete any passage, including vague or unverifiable prose. `UNVERIFIABLE` means *"a human
should decide"*, not *"cut it."* Cutting unverifiable lines is a deliberate **writing-docs**
cleanup, never a silent side effect of a drift sync.

### 3. No "while I'm here"

Spot a real problem the report didn't flag? **Surface it to the human; do not edit it.** An
out-of-scope fix — however correct — breaks the one-to-one map between the report and the diff,
which is the only thing that makes the sync reviewable.

### 4. Land the fix as-is; rewrite only when needed

The `fix` already meets the writing-docs bar — apply it verbatim. Only when a fix is *structural*
(a paragraph, not a string) dispatch **writing-docs**, which routes audience/density itself.

### 5. Blast-radius stop

If STALE records exceed the cap (default: **~10 passages, or a third of the doc**) or the doc is
wholesale-wrong, **stop and escalate** — open an issue / tell the human. Do not emit a giant
rewrite.

### 6. Evidence travels with the change

The commit / PR body maps each edit to its record's `evidence` (`file:line` or command output).
A reviewer confirms the sync by diffing against the report, not by re-deriving it.

## Red flags — STOP

- About to delete a line the report marked `UNVERIFIABLE` → flag it, don't cut it.
- Editing a passage with no matching `STALE` record → out of scope; surface instead.
- "The doc contract says cut unverifiable prose, so I'll delete it" → that's a writing-docs
  cleanup, not this sync. Not your mandate here.
- Rewording or restructuring a `VERIFIED` passage to "read better" → it stays byte-identical.
- The report flags most of the doc and you're about to rewrite it all → blast-radius stop.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The unverifiable line violates the doc contract — delete it" | Deletion is a content call outside the sync. Flag it; a human decides. |
| "While I'm here I'll fix this other wrong line I noticed" | Not in the report = not reviewable against the report. Surface it. |
| "I'll tidy this VERIFIED passage too" | VERIFIED stays byte-identical, or the diff stops mapping to evidence. |
| "The whole doc is stale — easier to just regenerate it" | Blast-radius stop. Escalate; don't bury 30 edits in one unreviewable change. |
