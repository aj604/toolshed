# Scenario (d) — invalid chunk result at the seam (scripted, no model)

## RED claim

The v1 architecture validates only a whole report at end-of-run
(`validate-bloat-output.py [FILE]`, per its v1 usage docstring) — a malformed
record surfaces at minute 42, after all spend. There is no seam, no retry, no
checkpoint: the production failure mode (career-compass run 28833711517).

## Inputs

`bad-chunk.json`:

```json
{"chunk": "c-c4b8ea0955", "records": [{"id": "B1", "doc": "README.md", "verdict": "PRUNE"}]}
```

Manifest: `plan-chunks.py` over `tests/fixtures/plan-swarm` (4 chunks:
p-9ca251fbbd policy + c-c4b8ea0955 / c-9dd8b0fa2f / c-9cae926ef2 sweep).

## v2 seam behavior (the fix, verified)

`validate-bloat-output.py --chunk bad-chunk.json --manifest manifest.json` → exit 1:

```
record[0] (B1): missing required field 'location'
record[0] (B1): missing required field 'evidence'
record[0] (B1): missing required field 'proposal'
record[0] (B1): missing required field 'status'
record[0] (B1): missing required field 'files'
record[0] (B1): verdict 'PRUNE' not in ['CONDENSE', 'CUT', 'DISTILL', 'EXTRACT-AND-MOVE', 'MERGE-DOC', 'POLICY', 'RETIRE-DOC']

FAILED: 6 contract violation(s)
```

`--assemble empty-chunks/ --manifest manifest.json --out report.json` → exit 1,
one line **per missing chunk by name**, e.g.:

```
chunk p-9ca251fbbd: no result file at .../p-9ca251fbbd.json — partial assembly refused
```

The workflow's one-fresh-retry-then-fail-naming-the-chunk wiring is pinned by
`tests/scripts/render-report_test.py::WorkflowWiring` (seam step, retry step,
no `--allow-partial` in CI).

## Verdict

FAIL for the v1 architecture (no seam exists to reject at); the v2 seam and
no-partial assembly behave as designed. GREEN re-runs the same inputs
unchanged.
