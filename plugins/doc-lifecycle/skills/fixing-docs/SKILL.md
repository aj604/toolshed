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
| `CUT` | `delete` |
| `CONDENSE` | `replace`, `delete`, `insert` |
| `EXTRACT-AND-MOVE` | `move-with-provenance` |
| `MERGE-DOC` | `move-with-provenance` + `retire-document` |
| `RETIRE-DOC` | `retire-document` |
| `DISTILL` | `create-document`, `replace`, `insert`, `delete`, `retire-document` |

Picking an operation the code does not list is `plan-operation-not-record-remedy` and
the run refuses. A positioned operation on the record's own document must also lie
within the hull of that record's approved assertion units — first line through last —
or it is `plan-span-outside-approved-units`. Widen nothing: an adjacent passage the
approval did not cover is a separate record's business even when the two sit one
paragraph apart.

### 3. Run the applier

```bash
python3 -m doclifecycle apply-plan --repo . --plan plan.json \
  --approval /tmp/approval.json --report report.json \
  [--audit-config-digest <sha256>]
```

`--report` is required: without it the approval set's authority check is a function of
public repository state, so a selection nobody minted would validate. The working tree
must be **clean** before you run it — the applier applies onto the committed baseline,
and an unrelated edit sitting in the tree is `apply-working-tree-not-clean`. Commit or
discard first.

Exit codes: `0` applied (or already applied — the no-op verdict is derived, so
re-running an interrupted lane is safe), `1` invalid, `2` usage, `3` stale.

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

**Never edit the approval set, the report, or the plan's declared digests to make a
refusal go away.** Repairing a stale `base_commit`, recomputing a digest over altered
records, or hand-widening `scope.paths` is forging authority — the exact attack the
contract exists to refuse. The same goes for hand-applying a fix "since the approval
was fine ten minutes ago": a stale approval set authorizes nothing at all.

## Distillation — the distiller returns operations, it does not write

An approved `DISTILL` record dispatches **doc-lifecycle:doc-distiller** with that one
record, its artifact path, its evidence, and the report path (it deduplicates its
landings against sibling records, which it can only do if it can see them). The
distiller owns the method — the landing re-verify, the per-section insight walk,
code-verified claims, one decision-log entry.

**What comes back is edit-plan operations, not a changed working tree**: the residue as
`create-document` text (a durable document that does not exist yet, carrying its
`> As of` first line) or `insert`/`replace` into the record's `destination`, and the
planning artifact as `retire-document`. You fold those operations into the plan the
applier executes. The distiller writes no files, `git rm`s nothing, stages nothing.

One record authorizes exactly two paths — its own document and its `destination` — so
residue belonging in a third document (a decision-log entry when the destination is not
the log, an inbound reference that now points at a retired artifact) comes back
**reported, not emitted**. Raise those for their own approval and their own plan; an
operation reaching a path the record never named is
`plan-target-not-record-target`, and hand-editing it instead is the thing this whole
flow refuses.

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
- "The lead approved it in the issue / in Slack / in review" → that is how an approval
  set is minted. Mint it, with them named as minter.
- Exit 3 and you are about to apply the edit anyway → stale authorizes nothing. Re-run
  the audit, mint afresh.
- About to open `approval.json` in an editor → forging authority. Never.
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
| "It's one line — the applier is overkill for this" | The applier is what makes it one *reviewable* line: preimage checked, scope confined, provenance recorded. A hand edit is an unauthorized diff of exactly the same size. |
| "The approval went stale on an unrelated commit — the doc didn't change" | Stale authorizes nothing, and you do not get to decide which staleness was harmless. Re-run the audit and mint afresh; it is cheap. |
| "I'll just fix the base_commit field so it validates" | That is forging authority. The digest exists so every tamper is "delete one field". |
| "The working tree has an unrelated edit, I'll apply on top" | `apply-working-tree-not-clean`. The applier certifies the whole diff, so it applies onto the committed baseline only. Commit or discard first. |
| "This is a bloat record, so I need the bloat fix skill" | There is one door. The finding code routes the remedy inside it. |
| "Distilling inline is faster than dispatching" | The distiller owns the method — re-verify, insight walk, dedup, decision log. Inlining drops all four, and writing files drops the applier. |
| "The distiller staged a commit, so I'll just commit it" | It returns operations. A staged commit means it broke its contract; report that rather than laundering it. |
| "The unapproved record next to my edit is obviously right too" | Its digest was never minted, so no plan can carry it. Surface it for the next approval. |
