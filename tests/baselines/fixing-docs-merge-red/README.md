# fixing-docs merge RED baselines — method

Baseline (RED) runs for the #70 fixing-skill merge, run 2026-07-27 against the
**pre-merge skill pair** — `fixing-doc-drift` and `fixing-doc-bloat` at plugin
version 0.27.0, plus their shared spine `references/apply-discipline.md`. Those
three files are what RED grades; the merged `fixing-docs` door replaced all
three.

The architecture change under test: with the applier landed (#69), the two fix
skills collapse into one door whose whole body is the applier flow — mint
approval set → edit plan → applier → present the staged diff — with the
record's finding code as internal routing. `apply-discipline.md` is superseded
by the applier contract (`plugins/doc-lifecycle/engine/README.md`, "Approval
sets" and "The applier"). `doc-distiller` stops writing files and returns
edit-plan operations instead.

## Method

- One sandbox repo built by script (`fixture70/build_report.py`, kept with the
  run): a living `docs/architecture.md` carrying one wrong fee rate against
  `src/app.py` plus a redundant paragraph, a landed planning artifact
  `docs/plans/0001-fee-change.md`, a `.doc-lifecycle/registry.json`, real git
  history. Artifacts (report, approval sets) are built with the **real** engine
  helpers — `report.current_lineage()`, `segment.segment_document()`,
  `finding.build_finding()`, `mint-approval` — never hand-faked digests, and
  verified with the engine's own CLI verdicts before any run.
- One fresh runner subagent per scenario, given only the sandbox repo, the
  plugin path, and the scenario prompt verbatim; required to end with a
  complete ordered ACTION LOG and the sandbox's post-run `git status
  --porcelain` / `git diff`.
- Runners never grade their own work: one fresh grader subagent per scenario,
  given `ANSWER-KEY.md`, the runner's report, and the post-run git state — per
  the fresh-graders rule.
- Grading is of the **skill text**, not the runner's luck: a runner who
  stumbles into the right shape while the text is silent is a FAIL for that
  criterion (see `ANSWER-KEY.md`, "Grading").

Scenarios: `scenario-a.md` (drift record, no approval set), `scenario-b.md`
(stale approval set), `scenario-c.md` (bloat `CUT` + `DISTILL` through one
door). Scenario B is graded as a text audit rather than a runner run — the
pre-merge pair has no approval-set concept at all, so there is no stale-recovery
text to put under pressure; the finding is recorded in `RED-findings.md`.

GREEN reruns of the same scenarios against the merged text:
`../fixing-docs-merge-green/`.
