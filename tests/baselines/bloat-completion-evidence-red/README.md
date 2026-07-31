# Bloat completion evidence — RED milestone

Recorded 2026-07-30 for issue #152 before the completion-evidence fixes.
These are deterministic integration tests, so the TDD milestone is the
observed failing public behavior rather than a model transcript.

## Observed failures

- `test_missing_planned_chunk_is_partial_inside_the_report`: an empty verdict
  list could produce a clean report even though one of at least two planned
  chunks had no result.
- Two-axis review adversarial reproduction: a caller could repartition chunks
  and recompute the plan/completion digests, or edit verdict contents and
  recompute the outer digest, while retaining clean coverage. The digest bound
  caller-authored ids, not the authentic engine plan or received result bytes.
- `test_a_cached_verdict_outside_its_chunk_stays_pending`: resume invoked the
  chunk validator without its manifest, so a shape-valid cached result naming
  a document outside the chunk incorrectly suppressed redispatch.

These failures established the required boundary: completion must preserve a
public engine plan that the audit can independently re-derive, and every
received chunk result must remain bound to its verdict contents and slice.
