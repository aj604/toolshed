# bloat-inventory regreen — headless full-audit produces a report

Milestone: `detecting-doc-bloat` gains a `python3` inventory tool
(`scripts/list-docs.py`) so the headless full-audit sweep stops improvising shell
enumeration the CI allowlist denies. Design:
`docs/plans/2026-07-03-doc-bloat-inventory-tool-design.md`.

## RED (the failure this fixes)

`doc-bloat.yml` run `28686984185` (2026-07-03) failed at `Assert detect produced a
report`: Claude ran to `success` (17 turns, `is_error: false`) with 2 permission
denials and never wrote `bloat-report.json`; the prune/distill lanes were skipped.

Reproduced locally under the CI allowlist
`Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)`: the first tool call after loading
the skill was `Bash: find . -name "*.md" …` — matched by neither `Bash(git *)` nor
`Bash(python3 *)`, so denied. Second latent denial: the skill told the model to run the
validator as a bare `${CLAUDE_PLUGIN_ROOT}/…/validate-bloat-output.py` path, also not
`python3 …`. A raw `*.md` sweep also over-scoped to ~160 tracked files (mostly
`tests/baselines/**`, `tests/fixtures/**`).

## GREEN (this run)

Constrained local rerun, edited skill overlaid onto the registered plugin path, exact
CI allowlist plus an explicit deny of shell escape hatches
(`find`/`ls`/`cat`/`grep`/`wc`/…) to mirror CI's default-deny. Model: `claude-sonnet-5`.

Observed:

- Inventory ran `python3 …/detecting-doc-bloat/scripts/list-docs.py` — no `find`/`ls`.
- The validator ran as `python3 …/validate-bloat-output.py <report>`.
- 51 turns (a real full audit, vs the RED run's truncated 17).
- `Write` produced `bloat-report.json`; it passed the mechanical validator:
  `OK: 11 record(s) valid`, summary `{"cut":0,"condense":0,"extract_and_move":0,
  "retire_doc":0,"merge_doc":0,"distill":11}` (all planning artifacts under
  `docs/plans/`).
- No blocking denials: 6 `wc -l *.md` size-sort conveniences were denied and the model
  recovered without them.

## Caveats / residuals

- The overlay test resolved `${CLAUDE_PLUGIN_ROOT}` to the main checkout, so the model
  inferred that as repo root and wrote the report there. In CI the checkout root is the
  cwd and the plugin lives in a separate install dir, so the report lands at the repo
  root the workflow asserts on. Not a code defect.
- The model still reaches for `wc` to order records by leverage; recoverable and
  non-blocking, but a candidate for a future skill nudge (use `Read`/line counts, or the
  helper could emit line counts).
- True strict-deny `permission_denials_count: 0` on a clean runner is confirmed by
  construction (both driven commands are `python3 …`) and pending the first real
  `workflow_dispatch` after this lands on `main` (the workflow installs the plugin from
  the marketplace's default branch).
