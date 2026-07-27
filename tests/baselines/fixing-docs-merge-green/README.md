# fixing-docs merge GREEN baselines — method

GREEN reruns of `../fixing-docs-merge-red/`'s three scenarios against the
**merged text** — `plugins/doc-lifecycle/skills/fixing-docs/SKILL.md` and the
rewritten `plugins/doc-lifecycle/agents/doc-distiller.md` at plugin version
0.28.0, with `fixing-doc-drift`, `fixing-doc-bloat`, and
`references/apply-discipline.md` removed. Run 2026-07-27.

Same method as RED (see `../fixing-docs-merge-red/README.md`): the same sandbox
built by `fixture70/build_report.py`, the same scenario prompts verbatim, one
fresh runner subagent per scenario against a pristine copy of the repo
(`repo-green-a`, `-b`, `-c`), and one fresh grader per scenario given
`../fixing-docs-merge-red/ANSWER-KEY.md` — never the runner grading itself.

Two deliberate differences from the RED environment, both recorded here so the
runs are comparable:

- The GREEN report carries a `destination` on the `DISTILL` record
  (`docs/reference/fee-policy.md`). Without one the applier authorizes no
  `create-document` at all (`approval.Record.targets()`), so scenario C could
  not have exercised the residue-authoring half of the distiller's contract.
  The report digest was recomputed over the changed records, not hand-edited.
- The runner sandbox cannot dispatch a subagent, so scenario C's runner stands
  in for `doc-distiller` under that agent's own definition and says where.

Results and per-scenario grades: `GREEN-results.md`.
