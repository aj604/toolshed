# GREEN results — scheduled bloat cadence (#144)

The scheduling skill now installs a separate weekly, read-only bloat audit. It preflights the
registry and engine's public plan before model cost, gives one fresh Task each planner-owned chunk
and turn budget, retries one failed seam once, and binds every missing or invalid chunk into #152
completion evidence before the public audit creates a typed report.

## What flipped RED → GREEN

- `bloat-audit-workflow_test.py`: the initial three contract probes pass for the public-plan
  preflight, bounded parallel fan-out, SHA pins, closed tool grant, runner-temp artifacts, and
  report-derived partial summary.
- `render-audit-summary_test.py`: the bloat report surface renders typed incomplete documents and
  chunk ids without consulting the diagnostic unswept sidecar.
- `apply-upgrade_test.py`: regeneration installs the fifth workflow, preserves a standing bloat
  cron, seeds `0 4 * * 1` only when absent, refuses an unreadable standing cron, and declares both
  policy and bloat workflow paths without opting a consumer into policy.
- `install-parity_test.py`: all five dogfood workflows, six vendored scripts, and the complete
  engine tree regenerate byte-identically from the shipped plugin.

## Standards-review hardening

The trusted post-model workflow step now runs after fan-out/retry and before any completion
assembly. It verifies `HEAD == GITHUB_SHA`, unstaged tracked state, staged state, and every
untracked path including ignored files. It never resets, restores, checks out, or cleans. Both
assembly and `bloat-audit` require that step's successful outcome, so a mutation cannot be hidden
inside an apparently read-only report. `PYTHONDONTWRITEBYTECODE=1` keeps the workflow's own Python
invocations from creating ignored cache files in the checkout; plans, worker results, envelopes,
reports, sidecars, and cost data remain allowed under `runner.temp`.

The execution seam passes a clean repository and rejects tracked, staged, ordinary untracked,
ignored-untracked, and moved-HEAD fixtures. The focused review GREEN is 6/6 workflow tests, 20/20
renderer tests, and 7/7 install-parity tests. The renderer selector is now the domain-specific
`--audit-surface drift|bloat`; the ambiguous legacy `--kind` flag is rejected.

Full review evidence: all 22 discovered script suites, all 1,265 engine tests, the 54-suite
release-manifest guard, plugin validation, YAML/JSON parsing, compilation, source/vendor and
template/dogfood parity, version guard, and diff checks passed. This directory is retained
methodology under `tests/baselines/`; the release manifest deliberately keeps baselines outside
executable suite discovery.
