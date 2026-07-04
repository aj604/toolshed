# Design rationale — deliberate absences and constraints

> As of 2026-07-04 (items anchored per entry; retired-artifact text retrievable via `git show <sha>:<path>`)

Durable rationale for the doc-lifecycle suite, recovered from retired planning
artifacts and extracted from distillations. Each entry is a decision, constraint, or
deliberate absence a future maintainer might otherwise wrongly "fix", with a
provenance anchor to the text that decided it.

## Suite contract

- **Rationale claims are relevance-checked, never truth-checked.** The drift engine
  checks a marked+anchored rationale claim's anchor — does the decision still apply,
  is the code it references still there — never the claim's truth. Automation never
  silently rewrites rationale.
  (docs/plans/2026-06-09-documentation-skills-suite-design.md @ 09f4300, Decision 2)

## Sync and bloat automation

- **The bloat lanes have no blast-radius cap, deliberately.** The drift nightly caps
  blast radius (past the cap, the fix PR degrades to a labeled issue); the bloat
  lanes are detect-only-then-review — a large proposal is reviewed as a diff, never
  silently applied — so a cap adds nothing. One can be added if PRs prove unwieldy.
  (docs/plans/2026-07-03-doc-bloat-nightly-design.md @ 09f4300, Non-goals / deferred)

## Doc taxonomy and distillation

- **The durable-narrative classifier is the marker, not the directory.** Directory-based
  classification of durable narrative docs was rejected: it breaks on file moves, and the
  prescribed home (`docs/reference/`) is shared with claim-style docs — so the first-line
  `> As of <date> (<anchors>)` marker is the classifier, wherever the file sits.
  (docs/plans/2026-07-04-durable-narrative-docs-design.md @ d695e25)
- **No separate top-level narrative home.** A separate top-level narrative home (e.g.
  `docs/adr/`) was rejected because it re-scatters the agent doc set repo-shape.md Rule 1
  contains — narrative docs live inside the same `docs/reference/` subtree, domain-grouped
  beside the unit's `overview.md` or `architecture.md`.
  (docs/plans/2026-07-04-durable-narrative-docs-design.md @ d695e25)
- **The bloat sweep covers `docs/plans/`; breadth is protected by insights, not excludes.**
  The weekly bloat sweep covers the whole doc set including `docs/plans/` on purpose —
  bloat lives in docs no recent commit touched, and `DISTILL` fires only on planning
  artifacts, so an `audit-scope.json` exclude on `docs/plans/` silently empties the distill
  lane. Protecting durable breadth via excludes was likewise rejected (excludes protect
  directories, not content) — hence the `insights` channel inside the DISTILL payload
  itself, with a mandatory per-section insight walk whose outcome the record's evidence
  must state.
  (docs/plans/2026-07-03-doc-bloat-nightly-design.md @ 09f4300, Decisions item 2;
  docs/plans/2026-07-04-durable-narrative-docs-design.md @ d695e25, Decision 4)
- **Why a third doc kind exists.** The third doc kind exists because a doc describing the
  current system is landed by definition — under the two-kind taxonomy an architecture
  overview is `DISTILL ready` the day it is written. The 2026-07-04 sweep (PRs #25/#26)
  demonstrated the failure: the suite's de facto architecture doc was distilled to an
  11-line entry, losses clustered in rationale-for-deliberate-absences, and inbound
  references were left dangling.
  (docs/plans/2026-07-04-durable-narrative-docs-design.md @ d695e25)
- **Why the always-loaded file is a router.** The router rule exists because the sweep
  machinery's default landing pad (CLAUDE.md/AGENTS.md) plus the precision guard formed a
  ratchet that systematically grew the most expensive file; the guard is therefore scoped
  to density, not growth, and the reverse EXTRACT lens is deliberately conservative
  (multi-line AND plainly narrow-scope AND existing natural target, else no record)
  because placement churn on an always-loaded file costs more than a borderline line.
  (docs/plans/2026-07-04-durable-narrative-docs-design.md @ d695e25)

## Demand-driven growth

- **growing-docs is a sibling skill, not an extension of bootstrapping-docs.** Growth is a
  distinct lifecycle phase with a distinct trigger context ("repo has no docs" vs. "repo has
  docs and we keep re-explaining something") — one skill description carrying both would
  fire for neither.
  (docs/plans/2026-07-02-growing-docs-design.md @ b9e6f97)
- **Narrative docs got light guardrails, not a fifth quality skill.** The guardrails are
  carried inline by growing-docs, and the narrative-docs hole was addressed only as far as
  growth demands it; recalibrating writing-docs' cut-test (Rules 4–5) was explicitly out of
  scope — do not read the growth path as a license to loosen the claim bar.
  (docs/plans/2026-07-02-growing-docs-design.md @ b9e6f97)
- **Deferred seam, deliberately not wired.** The nightly doc-sync run could flag
  `docs/doc-scope.md` items whose promote-when signal has fired — growth proposals stay out
  of the automation pipeline until that follow-up is picked up.
  (docs/plans/2026-07-02-growing-docs-design.md @ b9e6f97)
