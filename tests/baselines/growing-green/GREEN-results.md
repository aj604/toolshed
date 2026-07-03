# GREEN results — growing-docs (2026-07-03)

Same 3 scenarios × 2 as growing-red (same fixture seeding), agents given the edited
worktree skill files (installed plugin cache still served the pre-edit versions, so
agents were pointed at the SKILL.md files and told to scan all descriptions and follow
what applies). RED record: ../growing-red/RED-findings.md.

**Verdict: 6/6 pass. No REFACTOR edits warranted** (rationale at bottom).

## Scenario A ("second teammate this week hit exit 3") — 2/2 pass

- Both agents **named the signal** before writing (a1's Done entry: "second newcomer in
  one week (Priya Mon, Marcus Wed) hit 'api refuses to start' exit 3 and lost ~1h each")
  — the signal class RED agents never articulated.
- **Gap-vs-drift routing worked both directions.** Both ran the drift pipeline on the
  false README/CLAUDE.md lines (validated reports, STALE-only fixes); a1 additionally
  identified the absent symptom→remedy fact as a *gap* and grew a two-line exit-3 note
  via growing-docs — the exact artifact class RED-a2 had suppressed citing the doc
  contract ("prose restating what the tooling now says"). The counter-weight rule works.
- Both **created `docs/doc-scope.md`** (did not exist) with Done + signed deferrals.
- Artifacts stayed minimal — no catalogues.

## Scenario B (bootstrap exit) — 2/2 pass

- Both produced `docs/doc-scope.md` as a **file**, every deferred item with a
  `promote when:` signal (RED: 2/2 chat-only, no signals).
- Asked what happens next, both articulated the designed ownership: signal fires →
  growing-docs promotes → item moves to Done. (RED: "drift tooling handles the future"
  — which only maintains existing docs.)
- b1 seeded Done with the bootstrap itself; both ended AGENTS.md with a pointer line to
  the record (allowed; contents stayed out of always-loaded files).

## Scenario C (onboarding walkthrough) — 2/2 pass

- Both treated **growing-docs as the governing skill** (RED: dead-end + improvisation).
  No gutting instinct in either transcript; writing-docs' carve-out now routes instead
  of stranding.
- Both walkthroughs open with the REQUIRED anchor as the first line under the title:
  `> As of 2026-07-03 (<anchors>)` (RED: 0/2 had any doc-level staleness anchor).
- Embedded claims actually run: c1's doc survived an independent fresh-eyes audit
  (every anchor, exit code, and quoted output verified empirically; "zero false claims").
- Both updated the scope record; both routed the false README line to the drift pair
  (growing-docs' routing table) rather than silently bundling it.

## Observations recorded, no action taken

1. **Create-if-absent:** the skill says "on exit: update it" without "create it if
   absent" — flagged as a possible loophole pre-GREEN. 4/4 agents who found no record
   created one unprompted. No failing test → no edit (Iron Law).
2. **Attention narrowing (scenario A):** RED agents also added a fail-fast Makefile
   guard; GREEN agents fixed docs only. Likely harness priming (GREEN prompts pointed
   agents at the doc skills directory), not skill text — growing-docs neither forbids
   nor discourages code fixes. Watch in real use; an edit here has no failing test.
3. **Routing edge:** an incomplete CLAUDE.md table row was classified as gap-and-defer
   by c1 but drift-and-fix by c2. Both principled, both recorded; the edge (is
   false-by-incompleteness "false"?) is judgment the skill deliberately leaves open.

## REFACTOR rationale

No new rationalizations surfaced in any transcript; all four RED rationalizations hit
their counters (the rationalization table was cited by a1/c2 when declining to
catalogue). Convergence across paired runs was high (same record format, same anchor
shape, same routing). Per writing-skills, refactor closes loopholes found in testing —
none were found, so no post-test edits were made.

## Post-review fixes (independent continuity review, 3 fresh readers)

Behavioral tests passed, but the read-only continuity reviewers found four wording
defects, fixed after GREEN (reader-comprehension failures, not behavior failures):

1. `bootstrapping-docs/repo-shape.md` Rule 7 still carried the old "deferred note"
   ending verbatim, contradicting the new flow (design-scope miss) → rewritten to the
   scope-record ending.
2. growing-docs "on exit: update it" never said create-if-absent (2 reviewers flagged;
   observation 1 above upgraded from watch to fix), and "move promoted items" didn't
   cover the fresh-signal case — the skill's main path → "create it if absent" + "log
   what you wrote in Done".
3. bootstrapping-docs inlined the scope-record item syntax — a second copy of a
   single-owner format → parenthetical cut; pointer is the only source.
4. writing-docs Rule 5 twin read as the *same reader* burned twice; growing-docs counts
   across people/sessions → "a fact derived the hard way twice — by anyone, across
   sessions".

## Re-verify on shipped text (2026-07-03, post-fix) — 2/2 pass

The four fixes above changed skill text after the 6-agent GREEN, so two targeted agents
re-ran the affected flows against the final wording:

- **b3 (bootstrap):** with the inline format fragment removed, the agent followed the
  by-reference pointer and took the record format from growing-docs' own section
  (cited it by line range) — full structure correct (title, format comment, signed
  Deferred, Done). The single-owner joint holds without the local copy.
- **a3 (growth, no existing record):** created `docs/doc-scope.md` and quoted the new
  wording as the reason ("update it — create it if absent" + the red flag). Gap/drift
  split, named signal, and smallest artifacts all held.

repo-shape.md Rule 7's rewrite has no scenario coverage (no multi-unit fixture); it now
states the same contract the GREEN-tested SKILL.md ending does, verified by read-review
only.
