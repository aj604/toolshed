---
name: fixing-doc-bloat
description: Use when applying a human-approved subset of a detecting-doc-bloat report — landing approved cuts/condenses/moves/merges/retirements and dispatching approved distillations — or whenever tempted to act on bloat findings a human has not approved by record ID. Approval is the mandate; nothing else is.
---

# Fixing Doc Bloat

## Overview

**The approved subset is your mandate — not the report's other findings, not the doc's
overall bulk.** You apply exactly the records the human approved by ID and nothing else. A
bloat fix that also "cleans up" an obvious-but-unapproved finding stops being reviewable: a
human can no longer tell an approved cut from your opinion of what should have been approved.

**Acting on an unapproved record is violating the approval, even when the record is right.**

Input: a validator-passing `detecting-doc-bloat` report (`"schema": 2`, `records` with `id` /
`doc` / `location` / `verdict` / `evidence` / `proposal` / `status` / `files`) **plus an explicit
approval** — `{"approved": [ids]}` from issue triage, or the human's in-session ID list. The
approved records are the action items; **every other record in the report is context, not a
to-do.** This skill *applies* the approved subset; it does not re-audit or re-classify.

**REQUIRED SUB-SKILL:** use **writing-docs** for any landing that needs real writing — an
`EXTRACT-AND-MOVE` `text` or `MERGE-DOC` remainder that must read densely in its new home,
not a string-swap.

**Discipline spine:** the generic apply rules — authorized-records-only, no while-I'm-here,
anchor-confirm, blast-radius, evidence-travels — are owned by
`${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md`. Read it; this skill adds only the
bloat-specific application below. The routing table, stops, red flags, and rationalization
table here are in force unchanged.

## Headless (group executor)

When the weekly workflow dispatches you as a matrix group executor, your approved subset
arrived **verbatim in the dispatch prompt** — the record IDs (with verdict and doc) plus the
report path. That list is the human approval and your entire mandate: apply exactly those
records by the routing table, nothing else. Make **one commit per applied record, in the
order listed** — the workflow transports your work as a per-record patch series, so an
uncommitted landing does not exist and a multi-record commit cannot be merged record-by-record.
A record you cannot apply is reported as skipped or failed with its stated reason — never a
stopper for its siblings. Done means the per-record commits plus the group result object
(`{"group", "applied", "skipped", "failed"}` — every listed id in exactly one array) written
to the exact path the dispatch names; then stop. You never open the distill manifest, never
push, never open a PR, and never merge — orchestration, retries, the merge, and the draft PR
are the workflow's, not yours.

## The routing table (the bloat-specific rules)

Apply each **approved** record by its verdict. For the passage verdicts, `location` is the
passage's **anchor** (its first line) and the record's `evidence` opens with the passage's
full extent — `file:start-end` (`file:start` if one line). **The edit's mandate is the
passage that span delimits, anchored at `location`** — not mechanically the anchor line.
The doc verdicts carry `location: null` and act on the whole doc.

| Verdict | Applied as |
|---|---|
| `CUT` | delete the passage the record's evidence delimits, anchored at `location` (anchor-confirm first, per spine §3). On a boundary line the passage shares with unflagged text, delete only the passage's own text — the neighboring sentence's words stay |
| `CONDENSE` | replace the passage the record's evidence delimits — every line of its span — with `proposal`, **byte-verbatim** — the report drafted that text to the writing-docs bar; you place it, you do not touch it |
| `EXTRACT-AND-MOVE` | land `proposal.text` in `proposal.target` (writing-docs bar), delete the source passage the record's evidence delimits — **one commit** |
| `RETIRE-DOC` | delete the doc; **approval of this ID is the deletion authorization** — no second confirmation needed |
| `MERGE-DOC` | move the content not already in `proposal.target` into it, then delete the merged doc — **one commit** |
| `DISTILL` (`status: "ready"` only) | dispatch **doc-lifecycle:doc-distiller** with the record (its ID, the artifact path in `doc`, and its `evidence`); the distiller authors the claims/insights/decision entry post-approval and stages one commit, which you then commit. `pending-implementation` is **never actionable** — skip it with a note even if it was approved |
| `POLICY` | apply the record's `proposal` policy to **exactly the paths in `files`** — for a retirement-class policy, `git rm` those files in one commit. The `files` array is the complete mandate: never widen to the directory's current contents, never skip a listed path silently. A policy you cannot apply mechanically as stated → stop, surface it. Approval of this ID is the deletion authorization |

### Boundary rule — an approved edit's blast radius is that record's own location/proposal

The single boundary that RED broke: an approved record's edit reaches **only** its own
`location` and its own `proposal`. A different record sitting one paragraph away — approved or
not — is a separate action item. **Never fold an adjacent record's content into an approved
record's edit**, even when the two are about the same subject and the report already wrote the
adjacent record's text for you. If record X is approved and record Y is not, Y's line stays
exactly as it is; the fact that X's fix touches nearby lines does not extend X's mandate to
cover Y. Absorbing Y into X's diff is applying an unapproved record — a spine §1 violation —
no matter which record's commit it hides in.

### CONDENSE text lands as given — never blended, never augmented

A `CONDENSE` `proposal` is complete, writing-docs-bar text. **Land it as-is, at its own
boundary; stop at its final character.** Do not merge a neighboring record's rationale into a
CONDENSE line "so it reads fuller," do not append a fact the proposal didn't state, and do not
restate the same fact in an adjacent sentence — a bloat fix that *adds* redundancy has failed
at its own job. If you believe a CONDENSE proposal is incomplete, that is feedback for the
human, not a license to rewrite it. "Applied verbatim" must be literally true of the bytes you
wrote. The same hands-off rule covers everything the distiller lands: what it staged is what
you commit — never re-edited, never "rounded out."

### DISTILL is the distiller's job — dispatch, never inline

For an approved `DISTILL ready` record, **dispatch the `doc-lifecycle:doc-distiller` agent**
with that one record; do not distill the artifact yourself. The distiller owns the method
(single owner), and since contract v2 it also **authors the residue** — records carry no
payload: post-approval, the distiller re-verifies the landing, runs the per-section insight
walk, drafts claims (each verified against the code it cites), drafts artifact-true anchored
insights (creating the target narrative doc with its `> As of` line if absent), appends **one**
entry to `docs/decisions.md` (creating it with an `# Decisions` heading if absent — the
decision log is a repo-level file, **not** a CLAUDE.md subsection), completes the `Source:`
line with the artifact's real last-commit SHA, repoints the artifact's inbound references, and
`git rm`s the artifact — all **staged as one commit, which you then commit.** The distiller
stages; the dispatcher commits. Match your dispatch input to its contract: hand it the record
(ID, artifact path, evidence) **plus the report path** — the distiller deduplicates its
landings against sibling records (e.g. an `EXTRACT-AND-MOVE` aimed at the same target), which
it can only do if it can see them; expect back the residue as drafted, the claims and insights
landed (with `target:line`), any that failed verification, duplicates skipped with the
colliding record, references repointed, the log entry as written, and the staged file list —
the drafted residue is what the approving human sees in the draft PR.

**Distiller failure handling:** if the distiller reports a claim failed verification, that
claim is simply not landed — **surface the failure to the human; never redraft the claim
yourself** to force it through. Land what verified, report what didn't. If the distiller
reports a collision (a `DISTILL` claim and a sibling `EXTRACT` record aimed near-duplicate
text at one target), it already deduped its side and landed the line once — **pass its
collision note through to the human; never re-edit the landed result** to "reconcile" it.

## Bloat-specific stops

- **Approved ID not in the report** → stop. The inputs disagree; the approval references a
  record that isn't there. Do not guess which record was meant.
- **DISTILL approved but `status: "pending-implementation"`** → skip it, note it. There is no
  landed code to verify claims against, so nothing is actionable. Approval cannot make an
  unverifiable future-design into an edit.
- **Distiller reports failed claims, or refuses because the landing re-verify failed** → land
  what verified, surface the failures. Never redraft its claims yourself to force one through.
- **POLICY approved but a `files` entry no longer exists** → apply the rest, note the missing
  path — never widen the edit to the directory's current contents to "compensate".
- **A doc-level verdict (`RETIRE-DOC` / `MERGE-DOC`) and a passage verdict both approved for
  the same doc** → apply the passage edits first, the doc-level delete/merge last. Deleting the
  doc first would strand the passage edits.

## Red flags — STOP

- About to apply a record that isn't in the approval — "the CUT is unapproved but obviously
  right" → unapproved = not your mandate; surface it, don't apply it.
- Folding an adjacent (approved or unapproved) record's content into an approved record's edit
  → that adjacent record is a separate action item; its boundary is its own.
- Editing only the single line at `location` when the evidence span is multi-line, or deleting
  a whole boundary line that also carries unflagged text → the mandate is the span'd passage
  exactly: all of it, nothing beside it.
- Rewording, extending, or blending a `CONDENSE` proposal, or re-editing text the distiller
  landed → it lands byte-verbatim at its own boundary; adding to it re-introduces the bloat
  you're removing.
- Distilling the artifact inline instead of dispatching the distiller → the distiller owns the
  method; inlining it drops the re-verify / dedup / decision-log / single-commit shape.
- Putting the decision entry anywhere but `docs/decisions.md` (e.g. a CLAUDE.md subsection) →
  the decision log is a repo-level file; the distiller owns it.
- Redrafting a claim the distiller failed to verify, or re-editing a landed result it flagged
  for collision → surface it; don't launder or reconcile.
- Applying a `POLICY` record to files beyond its `files` array ("two new artifacts appeared —
  same class, I'll retire them too") → the array is the mandate; new files are a finding for
  the next sweep.
- Approving IDs yourself, or treating your presented summary as the approval → only the human's
  ID list is the mandate.
- Splitting an `EXTRACT-AND-MOVE`, `MERGE-DOC`, or `DISTILL` across commits → the move and the
  deletion ride one commit, or the diff stops reading "moved, not lost."
- Pushing, opening a PR, or folding several records into one commit as a group executor → one
  commit per record, the group result file, stop; the merge and the draft PR are the workflow's.
- Applying `DISTILL pending-implementation` because it was approved → skip + note; approval
  can't make unverifiable claims verifiable.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The CUT is unapproved but trivial / obviously right" | Unapproved = not your mandate. Surface it; the human decides. |
| "This unapproved record is right next to my approved edit — I'll just include it" | Its boundary is its own location/proposal, not your approved record's. Absorbing it is applying an unapproved record. |
| "`location` names one line, so I'll only touch that line" | `location` is the anchor; the evidence's opening `file:start-end` span is the mandate. A CONDENSE of a nine-line passage replaces nine lines. |
| "The proposal reads thin — I'll round it out with the adjacent claim" | Land it byte-verbatim, stop at its boundary. Blending it in adds redundancy and breaks "applied as given." |
| "I'll just distill inline — dispatching is overhead" | The distiller owns the method (single owner). Inlining drops re-verify, dedup, the decision log, and the single-commit shape. |
| "The decision entry fits fine in CLAUDE.md" | The decision log is `docs/decisions.md`, a repo-level file the distiller owns. |
| "Pending artifact, but the human approved it" | Approval can't make unverifiable claims verifiable. Skip + note. |
| "The distiller couldn't verify a claim, but it's clearly true — I'll patch it in" | Land only what verified; surface the failure. Redrafting its claims launders an unchecked one. |
| "The policy obviously covers the new files in that directory too" | The approved `files` array is the mandate — filter-selected provenance, not a standing license over the directory. |
