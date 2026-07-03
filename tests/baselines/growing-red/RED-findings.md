# RED findings — growing-docs baselines (2026-07-03)

6 baseline agents, 3 scenarios × 2, on taskflow fixture copies. Scenarios A/C used a
seeded baseline doc set (CLAUDE.md + README missing the migrate gotcha — the README
Setup block affirmatively said `make setup` → `make dev`). Scenario B used the bare
fixture. Agents had today's suite (writing-docs, bootstrapping-docs, drift skills)
and were told to use any skills that apply; growing-docs did not exist.

Design under test: docs/plans/2026-07-02-growing-docs-design.md.

## Scenario A — demand signal ("second teammate this week hit exit 3")

### What did NOT fail (do not over-invest the skill here)

- **Both agents documented the missing fact, minimally and well** — added the migrate
  row/step to CLAUDE.md and README, nothing more. Neither "just answered" nor dumped a
  catalogue. The design's predicted failure mode did not materialize.
- Both also fixed the root cause in code (fail-fast Makefile guard) and correctly kept
  it out of the doc-sync diff per fixing-doc-drift's contract.

### What DID fail (the skill's real targets)

1. **Doc growth happened only because the gap happened to falsify an existing claim.**
   Both agents routed everything through detecting-doc-drift → fixing-doc-drift; both
   classified the README setup sequence as STALE and fixed exactly that. A *pure gap* —
   a recurring question whose answer contradicts no existing doc line — has no path:
   drift detection audits claims that exist. The good outcome was contingent on
   adjacency, not produced by a growth framework.
2. **The demand signal was never named as a signal.** Neither agent's reasoning
   treated "second person this week" as a class of event with a rule attached
   (rediscovery count → document). They diagnosed an incident; the recurrence framing
   played no role in what they decided to write.
3. **No scope record anywhere.** Nothing was consulted or updated to record what is
   documented, what is deliberately not, or what would change that.
4. **Suppression is live.** a2, verbatim: "a troubleshooting section would be prose
   restating what the tooling now says, contrary to the repo's every-line-verifiable
   doc contract" — defensible here, but shows the contract acting as a blanket reason
   against additions, with no counter-weight rule for when demand justifies one.

## Scenario B — current bootstrapping-docs exit (2/2 clean fail)

1. **The deferred note evaporates.** Both agents produced a good `## Not yet
   documented` list — and both left it **chat-only**. b1, verbatim: "It lives only in
   this chat report — it is not in any file. That's deliberate: the skill defines it
   as a one-time bootstrap record… and this repo has no planning/handoff doc to host
   it." The scope decision does not survive the session.
2. **No future owner.** Asked what happens to the list, b2 answered that ongoing
   accuracy is handled by the drift half of the lifecycle — which only maintains docs
   that exist. Growth has no owner; deferred items have no promotion condition, so
   deferral is permanent by construction.

## Scenario C — narrative demand ("onboarding walkthrough") (2/2 dead-end, resolved by improvisation)

1. **The carve-out is a dead end, hit verbatim.** Both agents loaded writing-docs and
   quoted its scope note ("The claim bar would wrongly gut them; don't point this
   skill at them"). c2: "There is no skill in the suite that *owns* walkthroughs."
2. **First instinct was to gut the narrative.** c1, verbatim: "My first instinct after
   loading writing-docs was 'every line must be a mechanically checkable claim — so
   strip the narrative, make it a table of files and behaviors.'" It recovered by
   judgment, not guidance.
3. **Improvised, divergent guardrails.** Both kept the honesty rules voluntarily (ran
   every command, real output, file:line anchors). But **neither** added a doc-level
   staleness anchor ("as of <date/commit>"); c2 invented a manual "if this doc and the
   code disagree, the code wins" footer; c1 added nothing. c2 also flagged that drift
   tooling disclaims the doc it just wrote. Outcome quality rode entirely on
   per-agent improvisation — exactly what a skill exists to remove.
4. **No scope record** (as in A).

## Implication for GREEN

growing-docs is a SIGNAL/SCOPE skill, not a write-better-docs one:

- Name the signal classes (second rediscovery, incident w/o runbook, onboarding pain,
  recurring "why") and attach the rule: second occurrence = the fact has earned a doc,
  written where the reader would have looked first.
- Own the **pure-gap** path drift detection cannot cover (nothing false to flag).
- Own `docs/doc-scope.md`: check on entry, update on exit — this is the artifact the
  whole suite currently lacks (B's evaporating note, A/C's missing record).
- Carry the narrative guardrails inline (truth of embedded claims + **required**
  "as of <date/commit>" doc-level anchor) so C-type jobs stop depending on
  improvisation; keep the smallest-artifact rule so A-type jobs stay minimal.
- bootstrapping-docs edit: deferred note → `docs/doc-scope.md` with a promotion signal
  per item + handoff pointer (fixes B).
- writing-docs edit: carve-out points to growing-docs (fixes C's dead end); Rule 5
  gains the second-rediscovery twin (names A's missing signal class).
- Do NOT lecture about documenting the fact itself or fix-vs-doc balance — baselines
  did that well already.
