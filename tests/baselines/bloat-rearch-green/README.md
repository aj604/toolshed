# bloat-rearch GREEN — method and results

GREEN verification for the detecting-doc-bloat rearchitecture, run 2026-07-06
against the **rebuilt** skill (thin router + `references/` + contract v2 +
harness scripts). Same scenarios, prompts, fixture
(`tests/fixtures/plan-swarm/`), and answer key
(`tests/fixtures/plan-swarm-ANSWER-KEY.md`) as
`tests/baselines/bloat-rearch-red/`; fresh runners, fresh stakeless graders
(never the author).

## Results

| Scenario | RED | GREEN |
|---|---|---|
| (a) headless chunk executor | FAIL (v1 first emission; validator-source archaeology; 1 off-allowlist call) | **PASS** — first-attempt validator pass; "I did not need to read any tool source code" |
| (b) policy-scope swarm | FAIL (rules learned from tooling, not text) | **PASS** — one POLICY record, files verbatim, 3-of-10 sampling, rules cited to `planning-artifacts.md` + SKILL.md |
| (c) landed planning artifact | FAIL (full detect-time payload authored, then discarded; residue in evidence) | **PASS** — "classification plus landed-code evidence only; no claims/insights/decision-entry content authored"; nothing drafted-and-discarded |
| (d) invalid chunk at the seam | FAIL (v1 had no seam) | **PASS** — scripted: seam rejects naming violations; assembly refuses the gap by chunk name (outputs in `../bloat-rearch-red/scenario-d.md`; unchanged inputs) |
| (e) interactive large scope | FAIL (started the inline mega-sweep; recovery via archaeology; double-spend) | **PASS** — planner → 4 dispatched executors (orchestrator read none of the corpus) → per-chunk seam validation → assembly; report validates, 5 records match the key |

Grader verdict for (a)/(b)/(c): "3/3 PASS — GREEN holds. No automatic-fail
condition in the answer key fired in any transcript: no `payload` fields, no
per-file superpowers walk, no out-of-slice record, no off-allowlist tool, no
verdict on the narrative guide, no edits, no inline 15-doc sweep."

## REFACTOR notes applied (post-GREEN edits, read-review-only)

Both edits align prose with already-passing graded behavior; neither changes a
graded rule, so affected scenarios were not re-run (per the re-GREEN
convention, noted here instead):

1. SKILL.md's plan template gained a comment documenting `--config` scope
   narrowing (grader note: the (b) runner had to read the planner's docstring
   for the flag — sanctioned CLI usage, now documented at the call site).
2. output-contract.md's DISTILL-evidence rule now reads "…plus at most brief
   classification framing — never the doc's substance" (grader note: the
   passing (c) evidence carried a superseded-scaffolding clause the old
   "nothing more" letter didn't admit).

Grader notes not requiring text changes: GREEN harnesses should require
runners to persist their report JSON (evidence-retention; adopted in this
run's scenario files where artifacts exist); `git ls-files` is an acceptable
allowlisted enumeration path for executors (the manifest, not an inventory
helper, is the executor's work order).
