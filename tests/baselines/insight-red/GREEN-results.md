# insight-red GREEN results

2026-07-04. Arm: the **current** (0.6.0) `detecting-doc-bloat` skill text — mandatory
insight walk, three-kind taxonomy (living claim docs / planning artifacts / durable
narrative docs). Two fresh subagents, green-A and green-B, same neutral prompt and
fixture as the RED arm, report-only. Both outputs pass the current
`validate-bloat-output.py`; no fixture edits. Verbatim outputs: `green-A-output.json`,
`green-B-output.json`. Graded per ANSWER-KEY.md.

## green-A

**K1 — 3/3 insights (I1, I3, I2), walk accounted.** B1 (`DISTILL ready` on the design
doc) carries three payload insights, each targeted at the narrative doc
`docs/reference/queue-walkthrough.md` with a section-level dated anchor, e.g. I1:

> "The missing dead-letter queue is deliberate: exhausted jobs are dropped, not parked,
> because this system deploys unattended and an unmonitored DLQ grows without bound and
> hides failures better than dropping does. Revisit only if an operator rotation ever
> exists for this service." — anchor
> `docs/plans/2026-02-14-worker-queue-design.md §Options A @ 2026-02-14`

I3 (bonus per the key) and I2 ("The single global `TIMEOUT_S` is deliberate, not an
oversight: per-job-type budgets were rejected because they turn each new job type into
a tuning decision nobody owns…") follow with §Options B / §Options C anchors. The
evidence accounts for the walk by name: "insight sweep: Options §A (DLQ rejected —
unattended deploys, unmonitored DLQ hides failures), §B (…), §C (…) → 3 insights". None
of the three is a claim restatement — `claims` is empty and the rationale is the payload
— though each insight's opening clause re-carries a behavior CLAUDE.md:3-4 already
states (noted under residuals). One skeptical mark: **the empty `claims` list is
unaccounted** — the key expected the MAX_ATTEMPTS/TIMEOUT_S bounds as claims; skipping
them is defensible (README.md:9-10 and CLAUDE.md:3-4 already carry both, anchored), but
green-A's evidence never says so, so the zero is an assertion, not a shown result.

**K2 — pass.** B2 (`DISTILL ready` on the recipe plan): `insights: []` *and* stated —
evidence closes "insight sweep: none — pure implementation recipe (Task 1 field-add,
Task 2 code now landed, Task 3 verification steps; no rationale, constraint, or rejected
alternative)". One claim (the attempts-counter mechanism) extracted to README.md. No
fabrication.

**K3 — pass.** No record of any kind against `docs/reference/queue-walkthrough.md`; the
narrative doc is left alone (contrast both RED agents' double CONDENSE).

## green-B

**K1 — 3/3 insights, walk accounted in the most explicit form of the four runs.** B1's
evidence: "Insight walk, section by section: Options §A (dead-letter queue rejected —
unattended deploys, unmonitored DLQ grows without bound), §B (…), §C (…) each carry
rationale for a deliberate absence a future maintainer could wrongly 'fix' → 3
insights" — and, alone among the four agents, it also accounts for the empty claims
list: "Decision section's checkable bounds (5 attempts, 30s) are already carried by
README.md:9-10 and CLAUDE.md:3-4, so no new claims to extract". The three insights match
green-A's in substance (I1 quoted: "The absence of a dead-letter queue is deliberate:
exhausted jobs are dropped, not parked, because this system deploys unattended — an
unmonitored DLQ grows without bound and hides failures better than dropping does.
Revisit only if an operator rotation ever exists for this service."), all targeted at
`docs/reference/queue-walkthrough.md`. Skeptical mark on the anchors: all three are the
whole-doc form `docs/plans/2026-02-14-worker-queue-design.md @ 911b9ef` — the hash is
real (the toolshed commit that introduced the fixture), so provenance survives the
doc's retirement via git, but it resolves only in the *host* repo's history, not the
fixture-as-repo's own, and it gives a future reader no section pointer. Well-formed per
the contract (non-empty), weaker-formed than green-A's `§Options A @ 2026-02-14`.

**K2 — pass.** B2 evidence: "insight sweep: none — pure implementation recipe. One claim
extracted: the `attempts`-counter mechanism, which no living doc currently names
(README.md:9-10 and CLAUDE.md:3-4 carry the bounds, not the field)" — zero insights,
stated, and the one claim's placement argued. (Shape nuance: green-B's B2 payload omits
the `insights` key entirely where green-A wrote an explicit `[]`; the validator accepts
both, and the explicit-zero lives in the evidence text.)

**K3 — pass.** No record against the walkthrough.

## Scorecard

| Key | Expected | green-A | green-B |
|-----|----------|---------|---------|
| K1 recall | ≥1 of I1/I2 (both = full), anchored, narrative target, walk in evidence | pass — 3/3 (I1+I2, I3 bonus), §-level dated anchors, walk named in evidence | pass — 3/3, walk accounted section by section, doc-level commit-hash anchors |
| K2 precision | exactly 0 insights AND stated | pass — `[]` + "insight sweep: none — pure implementation recipe (…)" | pass — stated, with claim-placement argument |
| K3 classification | walkthrough left alone | pass — no record | pass — no record |
| Contract shape | validator accepts | pass (given) | pass (given) |

The RED arm's failure signature did not recur: no rationale-as-claims aimed at
CLAUDE.md, no CONDENSE against the anchored narrative doc, and the rationale rides the
channel built for it.

## Residual weaknesses worth tracking

1. **Neither agent extracted the key's expected K1 claims** (MAX_ATTEMPTS=5 /
   TIMEOUT_S=30). The zero is arguably *more* correct than the key — both bounds are
   already anchored in README.md:9-10 and CLAUDE.md:3-4, and re-extracting them would
   relocate bloat — but the key and the runs disagree, and only green-B showed its
   reasoning. green-A's empty `claims` is a bare assertion: the skill text mandates
   accounting for an insight-sweep zero but not a claims zero, an asymmetry a future
   tightening could close ("every empty payload channel gets one evidence clause").
2. **Anchor form is unpinned.** green-A anchored at section+date, green-B at
   whole-doc+commit-hash; both pass the non-empty contract, but the hash form loses the
   section and is meaningless inside the fixture's own world. If anchors are meant to be
   followable after the source doc is retired, the contract should say what they must
   contain.
3. **Insights lead with restatement.** Both agents' I1/I2 open by re-asserting a
   behavior CLAUDE.md:3-4 already carries ("exhausted jobs are dropped, not parked";
   "single global `TIMEOUT_S`") before delivering the rationale. Tolerated here because
   the rationale is the bulk and the payload, and the framing clause makes the insight
   self-standing in the narrative doc — but it grazes the red flag about insights
   restating claims; a stricter run would open with the rationale.
4. **Both agents wrote every insight to the same target** (`queue-walkthrough.md`). It
   is the only narrative doc in the fixture, so nothing else was available; the fixture
   cannot distinguish "chose the right narrative doc" from "chose the only one". A
   future fixture with two narrative docs would test targeting for real.
