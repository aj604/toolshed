# GREEN scenario (d) — invalid chunk result at the seam (scripted, no model)

Same inputs as `../bloat-rearch-red/scenario-d.md`, re-run against the shipped
scripts; outputs identical to those recorded there:

- `--chunk` on the invalid result → exit 1, six violations named, including
  the enum rejection of `PRUNE` against the seven-verdict set.
- `--assemble` over a gap → exit 1, one "partial assembly refused" line **per
  missing chunk, by name**; `--allow-partial` (never passed in CI) skips
  missing chunks with a stderr note but still fails on invalid ones
  (`tests/scripts/validate-bloat-output_test.py::Assembly` pins all of this).
- The workflow's discard → one fresh retry → fail-naming-the-chunk wiring is
  pinned by `tests/scripts/render-report_test.py::WorkflowWiring` (seam step,
  retry step, `--max-turns 15`, `fail-fast: false`, no `--allow-partial`).

Verdict: **PASS** — a bad run now fails at the record, not at minute 42, and
every valid chunk survives as a checkpoint artifact.
