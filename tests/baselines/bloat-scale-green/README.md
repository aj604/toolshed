# bloat-scale GREEN baselines — method and verdicts

GREEN runs for the bloat scale-hardening skill-text edit, run 2026-07-07
against the **post-edit SKILL.md** (headless slice-from-the-prompt contract).
Same sandboxes, same real `--emit-prompt` dispatches, same answer key as
`tests/baselines/bloat-scale-red/` (ANSWER-KEY.md there); fresh runners and
fresh stakeless graders, none reused from RED.

## Verdicts

| Scenario | Run (Q1) | Skill text (Q2) | Notes |
|---|---|---|---|
| (a) sweep chunk, planning doc | PASS | **TEACHES** | no manifest read, no enumeration, exact slice + landed-code greps; runner's validator abstention quoted the skill's own "orchestrator's state" reasoning — text-traced, not luck |
| (b) policy chunk | narrow FAIL | **TEACHES** | one `find \| head -50` issued *in the same first message* as the skill reads — launched before the just-read text could bind; grader: "runner impatience, not skill-text misdirection". No manifest read; runner's closing note quotes the new red flag correctly |

Q2 — the criterion the RED baselines failed on — is GREEN in both scenarios.
Grader (a) on the teaching sentences: the headless paragraph ("your chunk
slice arrived verbatim in the dispatch prompt… You never open the manifest —
it is the orchestrator's state, and it may not even be on disk") and the new
red flag ("Opening the manifest, or enumerating the corpus, as a chunk
executor → your slice arrived in the dispatch prompt; audit exactly it and
stop").

## REFACTOR (applied after grading, from the graders' loophole notes)

1. Grader (a): the unconditional "Skipping the validator at any seam → run
   it" red flag could read as license for an executor to open the manifest
   "just to validate". Applied: the red flag now names orchestrator seams and
   carries the carve-out "(As a headless executor, seam validation is the
   workflow's own step — never a license to open the manifest.)" Both GREEN
   runners had already resolved the tension exactly this way — the clause
   pins the resolution they chose.
2. Grader (b): the enumeration in run (b) fired before the text could bind —
   a skill-text counter cannot reach a call made in the same message. The
   structural fix went where it binds at t=0: `POLICY_PROMPT` in
   `plan-chunks.py` now carries the same scope fence the sweep prompt always
   had ("This list is your entire scope; do not enumerate the tree…"),
   pinned by a unit test (`plan-chunks_test.py`,
   `test_policy_prompt_lists_files_verbatim_and_names_policy`). The sweep
   prompt's identical fence held in both RED (a) and GREEN (a).

No third full run: the red-flag clause codifies behavior both GREEN runners
already exhibited, and the prompt fence is deterministic script output under
unit test — per the targeted re-verify convention for post-GREEN edits.
