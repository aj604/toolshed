# Bloat completion evidence — GREEN milestone

Recorded 2026-07-30 for issue #152 after the review-fix TDD slices.

## Verified behavior

- The public `bloat-plan` artifact records its budgets and is preserved intact
  through scheduler dispatch and assembly. The audit independently re-plans
  from the current context index and refuses stale or repartitioned evidence.
- Engine-owned `ChunkOutcome` and `assemble_bloat_input` author one completion
  contract for interactive and scheduled runs. Per-result digests bind the
  received verdict contents; the outer digest binds the plan, every outcome,
  and every verdict.
- Missing and invalid outcomes are typed `completion_state` gaps. They produce
  per-document `incomplete` evidence and can never be reported clean.
- Resume passes the current manifest to semantic chunk validation. A cached
  result outside its assigned slice remains pending; valid cached chunks still
  retain content-addressed resume behavior.
- Adversarial tests cover stale plans, duplicate chunks, repartition plus
  recomputed digests, verdict edits plus a recomputed outer digest, and malformed
  completion evidence. Every case fails closed.

Focused GREEN commands:

```text
python3 tests/engine/bloat_test.py -q
python3 tests/engine/bloat_cli_test.py -q
python3 tests/scripts/plan-chunks_test.py -q
python3 tests/scripts/validate-bloat-output_test.py -q
```
