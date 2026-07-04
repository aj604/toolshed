# insight-red answer key (grading reference — NOT shown to baseline agents)

Fixture: `tests/baselines/insight-red/fixture/` (self-contained fake repo). Tests
whether the detector's **insight walk** (detecting-doc-bloat step 3, added in
doc-lifecycle 0.6.0) actually changes behavior: RED arm runs the 0.5.5 skill text
(no insights channel, two-kind doc taxonomy), GREEN arm runs the current text.
Three planted items.

## Planted items

| ID | Doc | Expected (GREEN) | Trap it tests |
|----|-----|------------------|---------------|
| K1 | `docs/plans/2026-02-14-worker-queue-design.md` | `DISTILL ready`. Claims: MAX_ATTEMPTS=5 and/or TIMEOUT_S=30, verified against `src/worker.py:3-4`. **Insights (≥1 required, both = full marks):** I1 — the deliberate DLQ absence (Options §A: unattended deploys, unmonitored DLQ worse than dropping, revisit-if-operator-rotation); I2 — global-not-per-type timeout (Options §C: per-type budgets are an unowned tuning decision). I3 (accept as bonus) — no-backoff-because-tail-reentry-spaces-attempts (Options §B). Each insight anchored, targeted at a narrative/reference doc, NOT restating the claims. Evidence accounts for the walk (names the Options sections). | Recall: does the walk surface breadth a maintainer could wrongly "fix" (add the missing DLQ, add per-type timeouts)? |
| K2 | `docs/plans/2026-03-01-attempts-field-plan.md` | `DISTILL ready`. Claims optional/minimal (the code carries it all). **Insights: exactly 0**, and evidence states the outcome (e.g. `insight sweep: none — pure implementation recipe`). | Precision: an agent that manufactures insights from a recipe doc is relocating bloat. Fabricated insights here = precision failure even if K1 scored. |
| K3 | `docs/reference/queue-walkthrough.md` | **No DISTILL record, not classified a planning artifact** — first line is the `> As of` anchor, so it is a durable narrative doc. No `CUT`/`CONDENSE` for being narrative. (A `MERGE-DOC`/`RETIRE-DOC` would also be wrong — nothing duplicates it at doc level.) | Taxonomy: the anchor is the classifier. Also the narrative own-bar rule. |

## Grading

Per agent, record:
1. **K1 recall** — insights surfaced (0, 1, 2, 3), correctly anchored/targeted, walk
   accounted in evidence?
2. **K2 precision** — zero insights AND stated, or fabricated/unaccounted?
3. **K3 classification** — left alone (pass), DISTILL'd or claim-bar CUT (fail)?
4. **Contract shape** — would `validate-bloat-output.py` accept the payload
   (insights items `{insight,target,anchor}` all non-empty)?

RED arm (0.5.5 text) has no insights channel; grade instead: did I1/I2 survive
*anywhere* (claims or decision_entry), and was K3 mis-classified as a planning
artifact / DISTILL target? Expected RED failure mode: I1/I2 reduced to at most a
clause in the decision entry or lost outright; K3 at risk of DISTILL because the
0.5.5 taxonomy has no narrative kind.

## Notes

- Baseline prompt is neutral: "run a full bloat audit of this repo per the skill
  file" — it must NOT mention insights, breadth, narrative docs, or the walk.
- Agents are report-only; any fixture edit is a failure.
- K1's Options §B (backoff) is deliberately weaker than §A/§C — a near-claim
  (tail-reentry spacing is visible in code comments). Surfacing it as an insight is
  acceptable, not required; graders should not penalize either way.
