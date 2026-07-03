# Growing Docs — demand-driven expansion past the bootstrap minimum

**Date:** 2026-07-02
**Status:** Approved design, not yet implemented
**Problem owner:** doc-lifecycle plugin

## Problem

The suite's lifecycle is bootstrap → write → detect drift → fix drift → schedule sync.
`bootstrapping-docs` deliberately creates the smallest high-leverage doc set and stops,
leaving a deferred note ("Not yet documented: …"). Nothing in the suite ever returns to
that note. Deferral is permanent in practice: the suite is aggressive about *not* creating
documentation and offers no legitimate path for a doc set to grow once something has
genuinely earned documentation. Docs that would produce significantly better experiences
(runbooks after incidents, deeper onboarding, narrative overviews) are systematically
never created.

## Decision summary (from brainstorming, 2026-07-02)

- **Focus:** the bootstrap-stops-too-hard failure (not a recalibration of the cut-test,
  and the narrative-docs hole is addressed only as far as growth demands it).
- **Growth trigger model:** demand signals (not milestones, not scheduled review).
- **Architecture:** new sibling skill `growing-docs`; `bootstrapping-docs` keeps
  create-the-minimum but its exit hands off to the growth path. Growth is a distinct
  lifecycle phase with a distinct trigger context ("repo has no docs" vs. "repo has docs
  and we keep re-explaining something") — one description carrying both would fire for
  neither.
- **Scope record:** a small dedicated file `docs/doc-scope.md`, read on demand, never
  auto-loaded. Format owned by `growing-docs` (single-owner rule); `bootstrapping-docs`
  writes the initial one by reference.
- **Growth menu:** may include narrative docs (tutorial, architecture overview, ADR) when
  the signal demands one, with light guardrails — not a fifth skill.

## New skill: `plugins/doc-lifecycle/skills/growing-docs/SKILL.md`

### Trigger (description sketch)

Use when a repo's baseline docs exist but a demand signal says they're no longer enough —
the same question answered twice, a fact re-derived across sessions, an incident with no
runbook, onboarding pain, "should we document X?", or a `docs/doc-scope.md` item whose
promotion signal has fired. The demand-driven counterpart to bootstrapping-docs: that
skill creates the minimum; this one grows it when reality asks.

### Core method

1. **Second-rediscovery rule.** The first time a fact is asked for or re-derived, answer
   it. The second time, it has earned a doc — write it where the reader would have looked
   first. This is the positive twin of writing-docs Rule 5: "inferable cheaply" is an
   empirical claim, and a second hard derivation falsifies it.
2. **Signal → artifact menu** (smallest artifact that absorbs the signal):
   - Fact re-explained / re-derived → CLAUDE.md gotcha, README section, or reference entry
     — whichever the reader would consult first.
   - Incident with no runbook → runbook (writing-docs runbooks.md).
   - Onboarding pain → deepen README setup, or a tutorial (narrative, guardrails below).
   - Recurring "why is it like this?" → marked+anchored rationale section, or an ADR
     (narrative, guardrails below).
   - Unit became load-bearing / repo grew multi-unit → `docs/reference/` per
     bootstrapping-docs repo-shape.md.
3. **Grow minimally.** Growth is demand-shaped, not completeness-chasing. One signal → one
   smallest artifact. The bootstrapping-docs STOP list (route catalogs, signature lists,
   directory trees) still binds; a demand signal is not a license to catalogue.
4. **Scope record ownership.** `growing-docs` owns the `docs/doc-scope.md` format. On
   entry: read it (if present) alongside the live signal. On exit: promote fired items
   (move to done/remove), add any new deliberate deferrals *with the signal that would
   promote them*.
5. **Quality routing.** Repo-tracking docs → **writing-docs**, the one door, exactly as
   bootstrapping-docs routes today. Narrative docs → inline guardrails (below); do not
   point writing-docs at them.

### Narrative guardrails (carried inline by growing-docs)

Narrative structure is allowed — sequenced, redundant on purpose, not line-by-line claims.
But:

- Every command, path, symbol, and output *inside* the narrative must still be true of the
  repo now; no fabricated example output.
- The doc opens with an anchor — "as of <date / commit>" — so staleness is visible and
  drift tooling has a hook.
- Still the smallest doc that absorbs the signal.

### Scope record format (`docs/doc-scope.md`)

```markdown
# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- <artifact>: <what> — promote when: <signal>

## Done
- <date> <artifact> ← <signal that fired>
```

Read on demand; never referenced from an always-loaded agent file as content (a pointer
line is fine).

## Changes to existing skills

### bootstrapping-docs (ending only)

- Process step 3: "Write a deferred note" → "Write `docs/doc-scope.md` (format owned by
  growing-docs), listing what you did NOT document, each with the demand signal that would
  promote it."
- "End the bootstrap with a deferred note" section: reframe deferral as *deferred until a
  signal*; end with a handoff pointer to growing-docs. Keep the existing warning against a
  standing not-yet-documented section in CLAUDE.md/AGENTS.md.
- Red flag "Finishing the bootstrap with no deferred note" → "…with no scope record".
- Description: add that it ends by installing the scope record and handing growth to
  growing-docs.

### writing-docs (two small edits)

- Rule 5 gains its positive twin (one–two lines): if a reader has now derived a fact the
  hard way twice, it is no longer "cheaply inferable" — that's a growing-docs signal;
  cross-link.
- Scope paragraph: the out-of-scope carve (tutorials, narrative overviews, ADRs) gains
  "to create one when demand justifies it, see growing-docs" so the carve-out is no longer
  a dead end.

## Testing & release

- Repo convention: skills are built test-first (superpowers:writing-skills). RED baseline:
  agent without growing-docs, given a scenario like "we keep re-explaining the migrate
  step to every new session" — expected failure modes: answers again without documenting,
  or dumps a completeness catalogue into CLAUDE.md. GREEN: same scenario with the skill.
  Records under `tests/baselines/growing-red/` and `tests/baselines/growing-green/`.
- Also exercise: bootstrapping-docs' new exit (writes `docs/doc-scope.md`), and a
  narrative-demand scenario (onboarding pain → tutorial with guardrails).
- `claude plugin validate` before merge (YAML colon-space in a description silently drops
  skill metadata).
- Skills are auto-discovered — no plugin.json change. Update repo CLAUDE.md baselines list
  with the new dirs.
- Post-implementation: independent continuity review — one fresh subagent per flow
  (bootstrap→handoff, signal→growth, writing-docs cross-links) to check each still flows.

## Out of scope (this iteration)

- Recalibrating writing-docs' cut-test / Rules 4–5 themselves.
- A general narrative-docs quality skill (tutorials/ADRs get guardrails via growing-docs
  only when demand-created).
- Wiring growth proposals into the nightly doc-sync pipeline (possible follow-up: the
  nightly run could flag fired promotion signals).
