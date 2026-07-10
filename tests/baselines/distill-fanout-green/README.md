# distill-fanout GREEN baselines — method

GREEN reruns (2026-07-09) of the two RED scenarios in
`../distill-fanout-red/` (see its README for the full method: sandbox,
real `plan-distill.py --emit-prompt` dispatches, fresh runner + fresh grader
per scenario). The only variable changed from RED: the runner reads the
**new** fixing-doc-bloat SKILL.md — the 0.10.0 text with the
"Headless (group executor)" section
(`plugins/doc-lifecycle/skills/fixing-doc-bloat/SKILL.md`).

Result: both scenarios **PASS for the skill text** — every facet the RED
graders scored as "silent, saved by the dispatch prompt" (dispatch-borne ID
list as the approval, one commit per record in listed order, the group result
sidecar at the dispatch-named path, never-push/PR/merge, then stop) is now
traceable to explicit skill-text sentences, with the graders quoting them per
facet. Records: `scenario-a.md` (inline group), `scenario-b.md` (distill
group — the sandbox permitted real doc-distiller dispatch, exercising the
dispatch-and-commit path).
