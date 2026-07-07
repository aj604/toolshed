# Verdict lenses — living and narrative docs

Reference for `detecting-doc-bloat` chunk executors whose chunk carries
`living` or `narrative` hints. Record shapes: `output-contract.md`.

## The three passage questions (living claim-style docs)

Walk every passage of every doc in scope — paragraph by paragraph, not a skim
for highlights — and ask **three questions of each passage, in order**,
emitting a record for every yes. **Do not stop at a doc's first finding: bloat
clusters** — a multi-section living doc commonly yields several records. A
zero for a verdict class means you asked its question of every passage and got
no yes, not that you never asked.

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
  gotcha buried in a README belongs in the doc its audience reads on demand
  (runbook, reference); it lands inline in CLAUDE.md/AGENTS.md **only** when it
  clears agent-context.md's router rule (unprompted-critical, densest one-line
  form). The same lens runs in reverse — but **deliberately conservative**:
  flag an always-loaded passage for extraction only when it is multi-line AND
  plainly narrow-scope (one file, one task) AND a natural on-demand target
  already exists; it moves out leaving at most a when-to-read line. A
  broad-scope gotcha most sessions need stays put however short, and a
  borderline call yields **no record** — placement churn on the always-loaded
  file costs more than the line it would relocate. **Value is not placement** —
  a high-value line can still be misplaced; do not "keep" it where it is, and
  do not delete it. `proposal`: `{"target": <right doc>, "text": <the line>}`.

And a *doc* against its neighbors is bloat when it is a **near-duplicate of
another doc** → `MERGE-DOC` (fold the unique remainder into the survivor,
`proposal: {"target": <survivor>}`) or `RETIRE-DOC` (the doc carries nothing
the other lacks — delete it). Evidence: quote or cite the overlapping passage
in *both* docs.

## The three-lens re-pass (before emitting)

Re-walk each living doc three times, one lens per walk — the `CUT` lens, the
`CONDENSE` lens, the `EXTRACT-AND-MOVE` lens. One combined read reliably drops
a lens; three single-lens scans are cheap on doc-sized text.

## Durable narrative docs — their own bar

A doc whose first line is growing-docs' `> As of <date> (<anchors>)` marker is
a durable narrative doc **wherever it sits** — the anchor line is the
classifier, not the directory. Narrative prose is its job — never
`CUT`/`CONDENSE` a walkthrough or overview passage *for being narrative*. What
still counts as bloat in one: a passage duplicating another doc's
same-audience content, a dead command block its own anchor shows superseded,
or whole-doc `MERGE-DOC`/`RETIRE-DOC` with quoted overlap. A stale `> As of`
anchor is drift's business, not bloat. Narrative docs are never planning
artifacts and never `DISTILL` candidates.

## Precision guard — the target of a consolidation is not itself bloat

A dense, accurate doc that another finding points *into* — the
`EXTRACT-AND-MOVE` target, the `MERGE-DOC` survivor — is where value is being
*concentrated*. Do not also flag it as redundant. A short, dense CLAUDE.md is
doing its job, not bloating; adding cross-reference boilerplate to "clarify"
two docs is a bloat audit that *increases* line count — never propose it. The
guard protects *density*, not *growth*: it never licenses landing content into
an always-loaded file that agent-context.md's router rule would send to a
reference doc — pick targets so the always-loaded file only ever gets leaner
or stays put.

## Redundancy is judged within one audience

CLAUDE.md/AGENTS.md is a distinct doc *type* — tribal knowledge inherited by
every agent session — not a second README. Dedup verdicts (`CUT` as
restatement, `MERGE-DOC`) require *same-audience* redundancy: a fact carried
in both README (for humans) and CLAUDE.md (for agents) is deliberate placement
across the audience split, not bloat. writing-docs owns that split and is the
yardstick for where a claim belongs.

## Red flags — STOP

- `CUT`/`CONDENSE` on a narrative doc's passage because it is narrative →
  narrative is that doc's job; flag it only against its own bar.
- Classifying a doc whose first line is the `> As of` anchor as a planning
  artifact, or proposing `DISTILL` for it → narrative wherever it sits.
- Flagging the *target* of an extraction/merge, or a short dense doc, as bloat
  → consolidation targets are where value concentrates.
- About to `CUT` or `MERGE-DOC` a CLAUDE.md/AGENTS.md line because README says
  it too → different audience, not redundancy.
- Proposing to *add* cross-reference or "clarifying" lines → a bloat audit
  does not increase line count.
- Marking an `EXTRACT-AND-MOVE` candidate "keep as-is" (it's valuable) or
  sending it to a code comment / deletion → value ≠ placement; move it intact.
- Stopping a doc's sweep at its first finding, or emitting without the
  three-lens re-pass → bloat clusters; run the re-pass on every living doc.
- Emitting only findings that resemble the contract's worked example → it
  shows record *shape*, not an inventory of what to look for.
