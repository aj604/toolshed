---
name: detecting-doc-bloat
description: Use when auditing documentation for low-value content — redundant, verbose, duplicated, or past its useful form — proposing pruning/condensing/distillation, and whenever bloat analysis is invoked programmatically (nightly sweep or PR gate) and must emit a structured, parseable proposal. Read-only — it proposes, a human approves, fixing-doc-bloat applies.
---

# Detecting Doc Bloat

## Overview

**Drift asks whether a doc is *accurate*; bloat asks whether it still *earns its
tokens*. Bloat is accurate content past its useful form** — a line that restates
the code beside it, four sentences carrying one fact, two docs holding the same
setup block, a design doc whose decisions have already moved into the code. None
of it is *wrong*; all of it costs a reader (human or agent) attention it does not
repay. This skill declares the *shape* of that judgment so it runs the same way
every time and can be **invoked programmatically to propose pruning** — not a
one-off prose review.

Three non-negotiables make the output usable:

1. **A verdict requires evidence.** Never flag a passage because it "feels
   redundant." Redundant means you found the code or the other doc it duplicates
   and can cite it. Verbose means you can state the one fact the many lines carry.
   Every record names the `file:line`, quote, or grep that proves the finding.
2. **The result is structured, not prose.** Emit the declared record shape below.
   A human summary on top is fine; the structured block is the contract downstream
   tooling parses and a human approves by ID.
3. **Read-only — this skill never edits.** It proposes; a human approves record
   IDs; **`fixing-doc-bloat` applies the approved subset.** Approval of IDs is the
   only bridge from a finding to a file change. Do not edit, delete, or "just fix
   the small one" — surface it as a record and stop.

**REQUIRED SUB-SKILL:** Use **writing-docs** for every replacement or extraction
text you propose — a `CONDENSE` `proposal`, an `EXTRACT-AND-MOVE` `text`, a
`DISTILL` claim must all meet its bar (dense, anchored, no aspirational or
narrative prose). This skill finds and classifies bloat; writing-docs governs how
the proposed replacement reads. **`fixing-doc-bloat`** consumes this skill's
records and applies the approved ones, dispatching `DISTILL ready` work to the
`doc-distiller` agent.

## The engine (run these four steps, in order)

1. **Inventory** the docs in scope. In full-audit, get them by running
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/list-docs.py --with-lines`
   (reads `.github/doc-sync/audit-scope.json` if present, else defaults to
   git-tracked `*.md`); do **not** enumerate docs with shell `find`/`ls` or shell
   out to `wc`. `--with-lines` returns each doc's line count, largest first; use
   it to **plan sweep order** — scan the biggest docs first, where the most tokens
   (and so the most likely leverage) sit. This is a planning aid only, a rough
   proxy for where to look; it does **not** set record order — records are still
   ordered by verdict class (doc-level/distill before line-level cuts) per step 4
   and the Modes section. In diff-scoped, take only the docs the diff touched.
   Classify each doc as one of **three kinds**:
   - **Living claim-style docs** (README, CLAUDE.md, runbooks, `docs/reference/`
     claim docs) — track the current repo, line-governed by writing-docs.
   - **Durable narrative docs** — first line is growing-docs' `> As of <date>
     (<anchors>)` marker: walkthroughs, ADRs, conceptual/architecture overviews,
     workflow docs. They also track the current repo, as narrative; growing-docs
     owns their bar. **The anchor line is the classifier, not the directory** — an
     anchored doc is narrative wherever it sits, and is never a planning artifact.
   - **Planning artifacts** (design docs, specs, plans — conventionally
     `docs/plans/`) — describe an *intended change*. Location is a hint; what the
     doc does is the test.

2. **Judge passages and docs against the writing-docs bar.** Walk every passage
   of every doc in scope — paragraph by paragraph, not a skim for highlights — and
   ask **three questions of each passage, in order**, emitting a record for every
   yes. **Do not stop at a doc's first finding: bloat clusters** — a multi-section
   living doc commonly yields several records. A zero in the summary for a verdict
   class means you asked its question of every passage and got no yes, not that
   you never asked. The three questions:
   - **Does it restate what the code shows on its face?** → `CUT`: a signature, a
     name, a fact self-evident from the adjacent code or example, adding no
     information. Evidence: the code line it restates.
   - **Does it spend many lines on one checkable fact?** → `CONDENSE`: the tell is
     a narrative paragraph — several sentences whose checkable content fits one
     line citing the constant/symbol. Evidence: the passage; `proposal`: that one
     dense line (per writing-docs).
   - **Is it right content in the wrong doc?** → `EXTRACT-AND-MOVE`: the tell is a
     caveat or gotcha ("quirk", "note that", "silently", "worth knowing") addressed
     to operators or agents but sitting in a user-facing doc — an operational
     gotcha buried in a README belongs in CLAUDE.md or the runbook. **Value is not
     placement** — a high-value line can still be misplaced; do not "keep" it where
     it is, and do not delete it. `proposal`:
     `{"target": <right doc>, "text": <the line to land>}`.
   And a *doc* against its neighbors is bloat when it is:
   - **near-duplicate of another doc** → `MERGE-DOC` (fold the unique remainder
     into the survivor, `proposal: {"target": <survivor>}`) or `RETIRE-DOC` (the
     doc carries nothing the other lacks — delete it). Evidence: quote or cite the
     overlapping passage in *both* docs.

   **Durable narrative docs are judged against their own bar, not the claim
   bar.** Narrative prose is their job — never `CUT`/`CONDENSE` a walkthrough or
   overview passage *for being narrative*. What still counts as bloat in one:
   a passage duplicating another doc's same-audience content, a dead command
   block its own anchor shows superseded, or whole-doc `MERGE-DOC`/`RETIRE-DOC`
   with quoted overlap. A stale `> As of` anchor is drift's business, not bloat.

3. **Classify planning artifacts by whether their implementation has landed.**
   This is the verdict unique to this skill; do the check, do not eyeball it. For
   each planning artifact, grep/read the code for the symbols and behavior it
   describes:
   Durable narrative docs are **exempt from this step** — they track the repo,
   not an intended change; there is nothing to land. For each true planning
   artifact:
   - **Implementation landed** (the code the doc designs now exists) →
     `DISTILL`, `status: "ready"`, with a full `payload`. A design/spec/plan whose
     implementation has landed is a **distillation candidate: its value has already
     moved into the code**; what remains in the doc is scaffolding — the problem
     statement, the code sketch the real code now supersedes. The residue worth
     keeping is (a) the *durable decisions* — the "we chose X over Y, and here's
     the constraint that outlives the code" — extracted as `claims` into the
     living docs (each `claim` **verified against the code its `evidence` cites**,
     `target` = the living doc it belongs in), (b) the *durable insight* — breadth
     no living doc carries and code cannot show: rationale for deliberate
     absences, rejected alternatives with their reasons, deferred-work seams, the
     system-shape picture — extracted as `insights` into a durable narrative doc
     (`target`, usually under `docs/reference/`; each `insight` carries an
     `anchor` naming its provenance — the artifact `path @ SHA`, or a `file:line`
     / date), and (c) one `decision_entry` for the decision log. Everything else
     is git history. **The insight walk is mandatory, not a vibe check:** before
     emitting a `ready` record, walk the artifact section by section and ask of
     each — *if this section vanishes, is there a decision, constraint, or
     deliberate absence a future maintainer could wrongly "fix"?* Every yes
     becomes an insight (or a claim, when a living claim doc is the right home).
     The record's `evidence` must account for the walk's outcome: name the
     sections that yielded insights, or close with
     `insight sweep: none — pure implementation recipe`. An empty `insights` you
     can defend is common (most plans are recipe); an empty `insights` because
     you never walked is a lossy distill. An insight that merely restates a
     claim or the decision entry is bloat relocated, not breadth preserved.
     This is a `DISTILL`, not a per-line `CUT` spree and
     **not** a "keep it as a historical record" — a design doc kept verbatim as a
     historical record is exactly the bloat this verdict removes: decisions go to
     the log, breadth to a narrative doc, scaffolding to git history.
   - **Implementation not landed** (the code the doc designs does not exist yet —
     the grep for its symbols returns nothing) → `DISTILL`,
     `status: "pending-implementation"`, **`payload: null`**. There is no landed
     code to verify claims against, so no claims may be extracted. A pending design
     is accurate about the future; it is neither bloat to cut nor ready to distill —
     the record exists to *say so*, not to propose an edit. Never manufacture a
     payload for it, and never propose deleting it.

4. **Emit** the records + summary (the contract below). First, the completeness
   re-pass: **re-walk each living doc three times, one lens per walk** — the `CUT`
   lens (any line restating adjacent code?), the `CONDENSE` lens (any paragraph
   spending several sentences on one fact?), the `EXTRACT-AND-MOVE` lens (any
   caveat/gotcha whose audience lives in another doc?). One combined read reliably
   drops a lens; three single-lens scans are cheap on doc-sized text. Then
   **validate the result mechanically** before handing it off: pipe it through
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
   (reads the JSON on stdin or as a file arg). It enforces the enum / per-verdict
   proposal / location / status / payload / evidence / summary rules and exits
   nonzero on any violation — **don't emit a result it rejects.** It checks
   *shape*, not whether a verdict is *right*; that judgment is still yours.

**Precision guard: the target of a consolidation is not itself bloat.** A dense,
accurate doc that another finding points *into* — the `EXTRACT-AND-MOVE` target,
the `MERGE-DOC` survivor, a `DISTILL` claim's or insight's target — is where value
is being *concentrated*. Do not also flag it as redundant. A short, dense CLAUDE.md is
doing its job, not bloating; adding cross-reference boilerplate to "clarify" two
docs is a bloat audit that *increases* line count — never propose it.

**And redundancy is judged within one audience.** CLAUDE.md/AGENTS.md is a
distinct doc *type* — tribal knowledge inherited by every agent session — not a
second README. Dedup verdicts (`CUT` as restatement, `MERGE-DOC`) require
*same-audience* redundancy: a fact carried in both README (for humans) and
CLAUDE.md (for agents) is deliberate placement across the audience split, not
bloat. writing-docs owns that split and is the yardstick for where a claim
belongs.

## The output contract (this is the "shape")

The bloat report holds one record per finding. Each record uses exactly these
fields (no extras): `id`, `doc`, `location`, `verdict`, `evidence`, `proposal`,
`status`, `payload`. Approval is **by `id`** — the human returns a subset of IDs
and `fixing-doc-bloat` applies exactly those.

| Field | Rule |
|---|---|
| `id` | non-empty string, unique within the report (e.g. `"B1"`) — approval is by ID |
| `doc` | path of the judged doc, non-empty string |
| `location` | passage verdicts (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`): `file:line`, single line, no ranges — the **first line of the passage** (its anchor; the full extent opens `evidence`). Doc verdicts (`RETIRE-DOC`/`MERGE-DOC`/`DISTILL`): must be `null` |
| `verdict` | one of `CUT` / `CONDENSE` / `EXTRACT-AND-MOVE` / `RETIRE-DOC` / `MERGE-DOC` / `DISTILL` — literal enum, no invented values |
| `evidence` | mandatory non-empty string for **every** verdict (the code line, quoted overlap, or grep that proves the finding). Passage verdicts: must **open with the passage's full extent** — `file:start-end` (`file:start` if the passage is one line), where `file:start` equals `location` — then the proof. The span is normative: it is what `fixing-doc-bloat` deletes or replaces |
| `proposal` | `CONDENSE`: non-empty string, the complete replacement line. `EXTRACT-AND-MOVE`: `{"target": <doc>, "text": <text to land>}`, both non-empty. `MERGE-DOC`: `{"target": <survivor doc>}`. All others (`CUT`/`RETIRE-DOC`/`DISTILL`): `null` |
| `status` | `DISTILL` only: `"pending-implementation"` or `"ready"`. All other verdicts: `null` |
| `payload` | non-null **iff** `DISTILL` + `ready`: `{"claims": [{"claim","target","evidence"}, …] (all non-empty), "decision_entry": <non-empty draft log entry>, "insights": [{"insight","target","anchor"}, …] (optional, all non-empty — `target` a durable narrative doc, `anchor` the provenance)}` — at least one claim or one insight. Otherwise (`pending-implementation`, and every non-DISTILL verdict): `null` |

Emit the canonical wrapped object
`{"records": [...], "summary": {"cut": N, "condense": N, "extract_and_move": N, "retire_doc": N, "merge_doc": N, "distill": N}}`;
on success the validator prints a `summary:` line as JSON, recomputed from the
records, that automation can gate on. It accepts a bare array too and recomputes
the authoritative summary for you.

See **output-contract.md** for a worked four-record example (a `CONDENSE`, a
`MERGE-DOC`, a `DISTILL ready` with a two-claim payload, and a
`DISTILL pending-implementation` with a null payload) with every field populated.

## Modes

- **Full audit** (manual / nightly sweep): inventory every doc, judge every
  passage and every planning artifact, emit the full report. Order records by
  leverage — doc-level verdicts and distillations (large token wins) before
  single-line cuts.
- **Diff-scoped** (PR gate / what automation calls): input is a diff or commit
  range; judge only the docs the diff touched. **A landing planning artifact is not
  an objection** — a PR that adds a design doc for unbuilt code is *correct*; emit
  `DISTILL pending-implementation` for it, not a complaint. Completeness is the
  metric: every planning artifact in the diff yields exactly one `DISTILL` record
  (`ready` if its code also landed in the diff, `pending-implementation` if not).

## Presenting to a human (targeted response)

When a human triages in-session (not a gate consuming JSON), lead with a
**manufactured summary**, then attach the JSON below it — never the JSON instead
of a summary. Group records by doc, then by verdict; one line per record:

```
README.md
  [B1] CONDENSE   README.md:22 — 7 lines of eviction narrative → one line citing CACHE_TTL_S (src/cache.py:5)
  [B2] EXTRACT    README.md:31 — cold-start latency gotcha belongs in RUNBOOK.md
docs/plans/2025-11-02-cache-layer-design.md
  [B3] DISTILL(ready) — implementation landed (src/cache.py); 2 claims (TTL=300s, LRU cap=1024) + 1 insight (no-invalidation rationale → docs/reference/caching.md) + log entry
```

Then ask for the approved IDs. The approved subset is what `fixing-doc-bloat`
receives — nothing you present as a summary is authorization on its own.

## Red flags — STOP

- A prose report with no structured records → automation can't gate on it, a human
  can't approve it by ID. Emit the record shape.
- A verdict with an empty or asserted-not-shown `evidence` field ("this feels
  redundant", "the Setup sections are identical" with no quote) → go get the code
  line or the quoted overlap; an assertion is not evidence.
- A `DISTILL ready` payload whose claims weren't verified against the landed code →
  you're laundering the doc's prose into a living doc unchecked. Open the line each
  `evidence` cites first.
- A `payload` on a `pending-implementation` record → forbidden; there is no code to
  verify against. `pending-implementation` carries `payload: null`, always.
- Treating a landed design doc as a "historical record to keep" → that is the bloat
  `DISTILL ready` exists to remove; extract the decisions and insights, retire the
  scaffolding.
- Classifying a doc whose first line is the `> As of` anchor as a planning artifact,
  or proposing `DISTILL` for it → it tracks the current repo as narrative; only its
  own-bar verdicts (step 2) apply, wherever the file sits.
- `CUT`/`CONDENSE` on a narrative doc's passage because it is narrative → narrative
  is that doc's job; flag it only against the narrative doc's own bar.
- A `DISTILL ready` whose `insights` restate its `claims` or `decision_entry` →
  bloat relocated, not breadth preserved; insights carry only what neither code nor
  the log can.
- A `DISTILL ready` whose `evidence` doesn't account for the insight walk (sections
  named, or `insight sweep: none — …`) → "no insights" is a conclusion the walk
  earns, never a default; run the per-section walk and say so.
- Marking an `EXTRACT-AND-MOVE` candidate "keep as-is" (it's valuable) or sending it
  to a code comment / deletion → value ≠ placement; move it to the right doc intact.
- Flagging the *target* of an extraction/merge, or a short dense doc, as bloat → the
  precision guard above; consolidation targets are where value concentrates.
- About to `CUT` or `MERGE-DOC` a CLAUDE.md/AGENTS.md line because README says it
  too → different audience, not redundancy; dedup requires same-audience overlap.
- Proposing to *add* cross-reference or "clarifying" lines → a bloat audit does not
  increase line count.
- Proposing an edit as an instruction ("change X to Y"), or making any edit → this
  skill is read-only; `proposal` is complete replacement text, and application is
  `fixing-doc-bloat`'s job after approval.
- An invented verdict (e.g. `PRUNE`, `DELETE`) → use the six enum values only.
- Stopping a doc's sweep at its first finding, or emitting without the three-lens
  re-pass → bloat clusters, and a single combined read reliably drops one of the
  three passage lenses; run step 4's one-lens-per-walk re-pass on every living doc
  before emitting.
- Emitting only findings that resemble the worked example → output-contract.md
  shows record *shape*, not an inventory of what to look for. Its records are from
  a different repo than yours; run the full sweep (engine step 2) for every verdict
  class, including the ones the example happens not to show.
- Skipping the validator → run it; never hand off a result it rejects.
