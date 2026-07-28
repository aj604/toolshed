---
name: fixing-docs
description: Use when landing fixes from a doc-lifecycle audit report — applying approved drift records (STALE, UNVERIFIABLE) or bloat records (CUT, CONDENSE, EXTRACT-AND-MOVE, MERGE-DOC, RETIRE-DOC, DISTILL) to the documentation, and whenever tempted to hand-edit a document because a record, a record-ID list, an issue comment, or a reviewer's say-so looks like authority enough.
---

# Fixing Docs

## Overview

**A validated, current approval set is the only authority, and the applier is the
only writer.** One door lands every record type — drift and bloat alike — because
after minting the flow is identical; the record's finding code is internal routing,
not a different skill.

You never edit a document under audit. Not with `Edit`, not with `Write`, not with
`sed`, not "just this one line". Every byte that lands is written by
`python3 -m doclifecycle apply-plan`, from an edit plan bound to an approval set the
engine validated against both the report and the repository.

**Violating the letter of the flow is violating the spirit of the flow.** The point
is not ceremony: a diff produced any other way carries no proof of what authorized
it, so a reviewer cannot tell an approved remedy from your opinion.

Contract (read it, do not restate it): `${CLAUDE_PLUGIN_ROOT}/engine/README.md`,
sections **Approval sets** and **The applier**. Run engine commands with the plugin's
engine directory on `PYTHONPATH`.

**REQUIRED SUB-SKILL:** use **writing-docs** for any replacement text you must author
yourself (a paragraph, a merged remainder) rather than place — the report's proposal
already meets that bar and is placed byte-verbatim.

## The flow — four steps, in order, every time

### 1. Mint the approval set

Semantic approval is a person naming record digests from one report. That act mints
the artifact; the names alone are not it.

```bash
python3 -m doclifecycle mint-approval --report report.json --repo . \
  --record <record digest> --minter <who approved> --out /tmp/approval.json
```

`--record` takes the record's **digest**, not its display id — the id is a label the
report can renumber. Repeat it once per approved record. Write the artifact
**outside the work tree or to a git-ignored path**; the engine refuses a tracked or
would-be-tracked path, because a `git add -A` in the change it authorizes would
commit the authority next to the diff.

Minting refuses before it mints — an unapprovable report, an unknown record, a
selection that takes one leg of a mutually exclusive reconciliation group, a target
outside the declared roots, a preimage that moved. **A refusal is the answer, not an
obstacle**: report it and stop.

### 2. Author the edit plan

An edit plan is a separate artifact (`artifact: edit-plan`) bound to exactly one
approval set by digest. Every operation names the approved record it comes from, the
target class it writes (`documentation` — the only declarable one), the exact
preimage of what it replaces, and the plan declares the sha256 postimage of every
written path.

The operation vocabulary is closed — `replace`, `delete`, `insert`,
`create-document`, `retire-document`, `move-with-provenance` — and **the remedy
belongs to the record, not to you**:

| Finding code | The operations its remedy is made of |
|---|---|
| `STALE`, `UNVERIFIABLE` | `replace`, `delete`, `insert` |
| `ANCHOR-STALE` | `replace`, `delete`, `insert` |
| `CUT` | `delete` |
| `CONDENSE` | `replace`, `delete`, `insert` |
| `EXTRACT-AND-MOVE` | `move-with-provenance` |
| `MERGE-DOC` | `move-with-provenance` + `retire-document` |
| `RETIRE-DOC` | `retire-document` |
| `DISTILL` | `create-document`, `replace`, `insert`, `delete`, `retire-document` |

Picking an operation the code does not list is `plan-operation-not-record-remedy` and
the run refuses. A positioned operation — `replace`, `insert`, `delete` — may name only
the record's own document, and must lie within the hull of that record's approved
assertion units — first line through last — or it is
`plan-span-outside-approved-units` / `plan-target-not-record-target`. The record's units
locate nothing in its `destination`, so there is no passage to bound an edit there:
a destination is written whole, by `create-document`, or by a move's append. Widen
nothing: an adjacent passage the approval did not cover is a separate record's business
even when the two sit one paragraph apart.

**The text inside the operation is the report's, not yours.** A `STALE` record's `fix`
and a `CONDENSE` record's `proposal` are complete replacement text drafted to the
writing-docs bar — place them byte-verbatim and stop at their final character. The hull
bounds *where* you may write; nothing bounds *what*, so authoring your own sentence
inside an approved span produces a diff the applier certifies and no reviewer approved.
Compose text only where the record supplies none (a merged remainder, a distillation's
residue), and route it through **writing-docs**.

A STALE `fix` may itself contain LF when its approved assertion unit was soft-wrapped. That LF,
the list marker, and continuation indentation are part of the approved replacement: copy the
whole string byte-verbatim into the operation's `text`, including every embedded line break.
Never collapse or re-wrap it while planning. The audit method already made the authoring judgment;
the applier deterministically replaces `start_line..end_line` with however many physical lines the
approved `text` contains.

This is the one artifact you author, so here is the whole shape — a `STALE` record
remedied by a single `replace`:

```json
{
  "artifact": "edit-plan",
  "schema_version": 1,
  "approval_digest": "<the approval set's own digest, verbatim>",
  "operations": [
    {
      "op": "replace",
      "record": "<the approved record's digest>",
      "target_class": "documentation",
      "path": "docs/architecture.md",
      "start_line": 7,
      "end_line": 7,
      "preimage": "The service charges a flat 2% fee.",
      "text": "The service charges a flat 2.5% fee."
    }
  ],
  "postimages": {"docs/architecture.md": "<sha256 of the file's bytes after the plan>"},
  "digest": "<sha256 of everything above except digest, canonical JSON>"
}
```

**A span's `preimage` is `"\n".join` of lines `start_line`..`end_line`, with no trailing
newline** — the applier splits the document on `\n` and compares that join, so a preimage
carrying the line's own newline is `apply-preimage-mismatch` even when the text is right.
`text` replaces those lines under the same rule. (`retire-document` is the exception: its
preimage is the whole file's bytes, final newline and all.) Each field set is exact and
closed —
`delete` is the `replace` fields minus `text`, `insert` takes `after_line` and `text`
with no span and no preimage, `create-document` takes `path` and `text` only,
`retire-document` takes `path` and the whole document as `preimage`, and
`move-with-provenance` is `delete`'s fields plus `destination` (it carries no `text` —
what moves is the preimage). Every one also carries `op`, `record`, and `target_class`.
An extra or a missing field is `plan-invalid-operation`, so build each op from its own
row rather than by editing the example above. `postimages` names every written path (`null` for a retired
document) and is re-derived, not believed: compute it from the bytes your operations
produce, or it is `plan-postimages-not-derived`.

### 3. Run the applier

```bash
python3 -m doclifecycle apply-plan --repo . --plan plan.json \
  --approval /tmp/approval.json --report report.json \
  [--audit-config-digest <sha256>]
```

`--report` is required: without it the approval set's authority check is a function of
public repository state, so a selection nobody minted would validate. The working tree
must be **clean** before you run it — the applier applies onto the committed baseline, so
an unrelated edit sitting in the tree refuses the run: outside the approval's scope as
`apply-working-tree-not-confined`, inside it as `apply-working-tree-not-clean`. Commit or
discard first.

Exit codes: `0` applied (or already applied — the no-op verdict is derived, so
re-running an interrupted lane is safe), `1` invalid, `2` usage, `3` stale.

`already_applied: true` on a run you have not made before is a **tripwire, not a
success**: the bytes were already on disk, which means something other than the applier
put them there. Say so rather than presenting the diff as this run's work.

### 4. Present the staged diff for change approval

The applier never stages and never commits. **Change approval — a person accepting the
produced diff — is the only thing that lands anything**, so the run ends by showing the
working-tree diff, the applied operations with their records, and the approval trailers
(`python3 -m doclifecycle render-approval --approval /tmp/approval.json --trailers`) for
the commit message or PR body. You do not commit, push, or open a PR unless the person
asks for it as a separate step.

The approval set itself never enters the repository. Its digest and rendered summary do.

## Refusals — before any work, and non-negotiable

| Situation | What you do |
|---|---|
| No approval-set file exists | **Stop and mint one** from the named record digests, or say you cannot because nobody named any. A record-ID list, an issue comment, a Slack "looks right", and a report are each how an approval set is minted — never a substitute for one. |
| `apply-plan` or `validate-approval` returns **stale** (exit 3) | **Stop.** Report the verdict naming every stale reason code. The recovery is the engine's: **re-run the audit, mint afresh** against the new report. Nothing was written; do not write anything. |
| The verdict is **invalid** (exit 1) | Stop and report every problem. An invalid artifact is a forgery or a bug, not a state to work around. |
| The report is `clean`, or a record you were given is not in it | Stop. The inputs disagree; never guess which record was meant. |
| A record you were **not** given is obviously right | Surface it. Unapproved is unapproved, and an unminted record cannot reach a plan at all. |
| A record's code is not in the remedy table above — `POLICY`, or anything a newer detector emits | Stop and surface it. `RECORD_REMEDIES` is closed and fail-shut: a code nobody listed authorizes **no** operation, so there is no plan to write. `POLICY` in particular is a legacy bulk verdict the bloat engine replaced with enumerable scopes, and its records expand to one per file — approve those instead. |

**Never edit the approval set, the report, or the plan's declared digests to make a
refusal go away.** Repairing a stale `base_commit`, recomputing a digest over altered
records, or hand-widening `scope.paths` is forging authority — the exact attack the
contract exists to refuse. The same goes for hand-applying a fix "since the approval
was fine ten minutes ago": a stale approval set authorizes nothing at all.

**And never move the repository to match the approval.** Resetting, reverting, or
checking out an older commit so `approval-base-commit-changed` stops firing is the same
forgery from the other side, and it is the one the "clean working tree" requirement in
step 3 most invites — that requirement means *commit or discard your own edits*, never
*rewind history until the refusal goes away*. The approval set names the world it was
minted against; when the world moved, the artifact is what gets remade.

**Minting is somebody's act, not a field you fill in.** `--minter` names who performed
the semantic approval, so you may not run `mint-approval` on an absent person's behalf,
however confident you are of what they would say — a reviewer who approved this morning's
report has not approved this afternoon's. Re-running the audit is yours; minting against
the new report is theirs. (`--minter-kind policy` is the standing auto-apply policy's,
and the engine documents it as not yet gated for use — it is not your workaround either.)

**Use the approval set you minted, or the one you were handed.** Another approval-set
file on disk that happens to validate is not a substitute for the one covering the
records you were asked to land; check what it selects and what report it binds to, and
say so, rather than shopping for whichever artifact clears the gate.

## Distillation — the distiller returns operations, it does not write

An approved `DISTILL` record dispatches **doc-lifecycle:doc-distiller** with that one
record, its artifact path, its evidence, and the report path (it deduplicates its
landings against sibling records, which it can only do if it can see them). The
distiller owns the method — the landing re-verify, the per-section insight walk,
code-verified claims, one decision-log entry.

**What comes back is edit-plan operations, not a changed working tree**: the residue as
one `create-document` at the record's `destination` (a durable document that does not
exist yet — the audit refuses a destination that does — carrying its `> As of` first
line), and the planning artifact as `retire-document`. You fold those operations into the
plan the applier executes. The distiller writes no files, `git rm`s nothing, stages
nothing.

One record authorizes exactly two paths — its own document and its `destination` — so
residue belonging in a third document (a decision-log entry when the destination is not
the log, an inbound reference that now points at a retired artifact) comes back
**reported, not emitted**. Raise those for their own approval and their own plan; an
operation reaching a path the record never named is
`plan-target-not-record-target`, and hand-editing it instead is the thing this whole
flow refuses.

A record carrying **no** `destination` authorizes one path, the artifact — so the whole
residue comes back reported and only `retire-document` is plannable. **Do not land that
plan on its own without saying so**: it deletes a planning artifact and strands
everything the distillation extracted. Present the drafted residue with it and let the
person decide whether to withhold the retirement until its residue has a home.

Land what verified. A claim the distiller could not verify is simply not in the
operations it returned — **surface the failure; never redraft the claim yourself** to
force it through, and never re-edit a landed result it flagged as a collision.

A `DISTILL` record whose `status` is `pending-implementation` is never actionable: there
is no landed code to verify claims against, so skip it with a note even when it was
approved.

## Red flags — STOP

- Reaching for `Edit`, `Write`, or `sed` against a document under audit → the applier
  is the only writer, always.
- "There's no approval set, but the report says STALE and the fix is one number" → the
  report is proof of examination, deliberately not authority. Mint first.
- "The lead approved it in the issue / in Slack / in review" → ask which record digests.
  An approver who named no digest approved no record, and minting in their name notarizes
  authority they never exercised. Go back with the report; the selection is the approval.
- Exit 3 and you are about to apply the edit anyway → stale authorizes nothing. Re-run
  the audit, mint afresh.
- About to open `approval.json` in an editor → forging authority. Never.
- About to `git reset`, `git revert`, or check out an older commit so the approval stops
  reading stale → same forgery, other side. The artifact gets remade, not the repository.
- About to mint with an absent reviewer's name because "they already approved this
  morning" → minting is their act. Re-run the audit and hand it back.
- Attaching a `retire-document` (or any operation the table does not list) to a
  record's plan because it is what the fix "really needs" → the remedy is the record's;
  a plan that picks the operation puts the choice back with the model.
- An operation reaching a passage outside the approved record's units → out of scope,
  even one paragraph away, even when the report drafted that neighbour's text for you.
- Committing, pushing, or opening a PR at the end of the run → change approval is the
  person's, not yours.
- The distiller writing files, `git rm`-ing the artifact, or staging a commit → it
  returns operations; the applier writes.
- Reaching for `fixing-doc-drift`, `fixing-doc-bloat`, or `references/apply-discipline.md`
  → all three are retired. This skill and the applier contract replaced them.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The report already lists the record, so it's approved" | A report is proof of what was examined, not authority. Only an approval set authorizes, and only a person or a configured auto-apply policy mints one. |
| "The ID list I was handed *is* the approval" | It is how an approval set is minted, never a substitute for one. Mint it and let the engine validate it. |
| "The lane is blocked / it ships today — minting costs minutes I don't have" | Minting is one command over digests the report already carries; the flow is a couple of minutes, and it is the same couple of minutes whether or not anyone is waiting. Deadline pressure is when an unauthorized diff is least likely to be caught, which is exactly why it is not when the rule bends. |
| "I'll place my own wording in the approved span — it reads better than the report's `fix`" | The hull bounds where, not what. Text you authored inside an approved span is a diff the applier certified and nobody approved. |
| "It's one line — the applier is overkill for this" | The applier is what makes it one *reviewable* line: preimage checked, scope confined, provenance recorded. A hand edit is an unauthorized diff of exactly the same size. |
| "The approval went stale on an unrelated commit — the doc didn't change" | Stale authorizes nothing, and you do not get to decide which staleness was harmless. Re-run the audit and mint afresh; it is cheap. |
| "I'll just fix the base_commit field so it validates" | That is forging authority. The digest exists so every tamper is "delete one field". |
| "I'll roll the repo back to the commit the approval names, apply, then roll forward" | Moving the world to match the artifact is the same forgery as moving the artifact to match the world. The remedy is a fresh mint, in both directions. |
| "The reviewer approved this morning, so I'll re-mint in their name" | A reviewer who approved this morning's report has not approved this afternoon's. Re-run the audit; hand the mint back to them. |
| "There's another approval set on disk and it validates clean" | Check what it selects and which report it binds to. An artifact that clears the gate is not an artifact covering your records. |
| "The working tree has an unrelated edit, I'll apply on top" | `apply-working-tree-not-clean`. The applier certifies the whole diff, so it applies onto the committed baseline only. Commit or discard first. |
| "This is a bloat record, so I need the bloat fix skill" | There is one door. The finding code routes the remedy inside it. |
| "Distilling inline is faster than dispatching" | The distiller owns the method — re-verify, insight walk, dedup, decision log. Inlining drops all four, and writing files drops the applier. |
| "The distiller staged a commit, so I'll just commit it" | It returns operations. A staged commit means it broke its contract; report that rather than laundering it. |
| "The unapproved record next to my edit is obviously right too" | Its digest was never minted, so no plan can carry it. Surface it for the next approval. |
