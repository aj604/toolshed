# RED scenario A — inline group (MERGE-DOC + RETIRE-DOC), OLD skill text

**Dispatch:** `dispatch-a.txt` (group `i-f57bd3b610`: B2 MERGE-DOC INSTALL.md,
B3 RETIRE-DOC docs/old-runbook.md), rendered by the real
`plan-distill.py --emit-prompt`. **Skill text:** fixing-doc-bloat SKILL.md at
0.9.4 (no headless section). **Runner:** fresh subagent; **grader:** fresh
subagent with `ANSWER-KEY.md`, the runner's report, and the post-run repo.

## Run summary (verified by the grader in the sandbox)

The runner behaved correctly end to end: read skill files + report, ID-checked
its mandate, applied B2 (unique `CACHELIB_DEV=1` line into README, INSTALL.md
deleted, one commit) then B3 (runbook deleted, own commit) with subject
template `docs: bloat distill <id> — <doc>`, wrote the sidecar byte-correct at
`distill-results/i-f57bd3b610.json`, left B1 (CUT bait) and the unflagged
README waffle untouched, no push/PR/branch, stopped.

## Grader verdict (skill text, per facet)

1. Read skill files / report / exactly the records' docs — **PASS**
   (text-taught: Input paragraph, anchor-confirm, "Approved ID not in the
   report → stop").
2. Dispatch ID list treated as the approval — **FAIL** (silent, saved by the
   dispatch prompt). The text's only approval definition is interactive
   ("`{"approved": [ids]}` from issue triage, or the human's in-session ID
   list") and its red flag "only the human's ID list is the mandate" points
   away from a dispatch-borne list. No bridge exists in the text.
3. One commit per record, listed order, subject template — **FAIL** (mostly
   dispatch-borne). The text teaches intra-record commit shape (MERGE-DOC
   "one commit") but nothing prevents one bulk commit or work left staged
   "for the workflow"; the per-record ordered series + template came verbatim
   from the dispatch.
4. Group result sidecar at the named path — **FAIL** (entirely
   dispatch-borne). Zero occurrences of a sidecar, `distill-results/`, or the
   applied/skipped/failed partition in the text.
5. Touch nothing else; never push/PR; stop — **SPLIT**: scope discipline PASS
   (the text's core strength — "every other record in the report is context,
   not a to-do"); terminal contract FAIL (never-push/stop/what-done-means is
   only in the dispatch).

**SKILL TEXT: FAIL** — "the runner's clean run was carried by the dispatch
prompt: the old text teaches scope discipline and per-verdict mechanics well,
but is silent on everything that makes the headless group-executor lane work —
a dispatch-borne ID list as the approval (its approval definition and red
flags actively point at interactive human approval instead), the per-record
ordered commit series with subject template, the group result sidecar, and
the never-push/stop terminal contract."
