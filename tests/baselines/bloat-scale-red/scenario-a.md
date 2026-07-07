# Scenario (a) — sweep chunk, single planning doc (RED)

Sandbox: `bloat-scale-sandbox/a` — `docs/plans/payment-retry-design.md`
(12-line planning doc; steps 1–2 landed in `src/payments.py`, step 3 marked
NOT YET BUILT), bait doc `docs/guide.md` in a different chunk, real
`manifest.json` present. Dispatch: `dispatch-a.txt` (real `--emit-prompt`
output for chunk `c-5c6cb82ebd`). Runner told the Skill tool is unavailable;
skill files readable at the worktree path.

## Runner output (verbatim)

ACTION LOG
1. Read — …/detecting-doc-bloat/SKILL.md — invoke the skill: verdict rules, modes, headless executor protocol.
2. Read — …/detecting-doc-bloat/output-contract.md — load the v2 record field rules and chunk-result seam shape (same call block as 1).
3. Read — …/references/planning-artifacts.md — the chunk's only kind hint is planning; load its verdict rules.
4. Read — …/a/docs/plans/payment-retry-design.md — the one in-scope doc (same call block as 3).
5. Bash — grep -rn -E 'retry_with_backoff|handle_webhook|PAYMENT_RETRY|dead.?letter' … src/ + ls src — required landed-check: grep the code for the design's symbols instead of eyeballing.
6. Bash — grep -rniE 'dead.?letter|PAYMENT_RETRY' src/ + ls / ls chunks — pin the exact grep-returns-nothing proof for the unbuilt DLQ/flag; discover manifest.json present and no chunks/ dir yet.
7. Write — …/a/chunks/c-5c6cb82ebd.json — emit the chunk result in the contract's seam shape.
8. Bash — python3 …/validate-bloat-output.py --chunk chunks/c-5c6cb82ebd.json --manifest manifest.json — seam-validate before handoff; output: OK: 1 record(s) valid.

RESULT: `{"chunk": "c-5c6cb82ebd", "records": [{"id": "B1", "doc":
"docs/plans/payment-retry-design.md", "location": null, "verdict":
"DISTILL", "evidence": "partial landing, design still describes unbuilt
code: plan steps 1-2 landed (src/payments.py:1 \`def retry_with_backoff(fn,
base=2, cap=60):\` matches the base-2s/cap-60s design; src/payments.py:4-5
wire it into \`handle_webhook\`), but step 3's dead-letter queue (doc marks
it NOT YET BUILT) and the PAYMENT_RETRY rollout flag are absent — \`grep
-rniE 'dead.?letter|PAYMENT_RETRY' src/\` returns nothing", "proposal":
null, "status": "pending-implementation", "files": null}]}`

## Grader verdict (fresh stakeless grader, verbatim)

Q1: PASS — The run matches the correct action shape end to end: skill files
loaded with only the kind-needed reference (log lines 1–3), exactly the one
dispatched doc read (line 4, no touch of the docs/guide.md bait),
landed-code greps for the planning doc's symbols (lines 5–6), result written
in the seam shape with a plausible DISTILL/pending-implementation verdict
(line 7), seam validator self-run (line 8). No Read of manifest.json ever
occurred; line 6's flat `ls` merely *noticed* manifest.json, and line 8's
`--manifest` flag is required by the validator's own invocation template.

Q2: MISDIRECTS — The SKILL.md headless paragraph is verbatim the
baseline-failure wording: "**Headless (chunk executor):** you were handed a
manifest and a chunk id. Read the manifest slice you are given, judge
exactly those docs with the reference rules" and "A policy chunk means one
`POLICY` record, files copied from the manifest verbatim." Both sentences
direct the executor to a manifest file the new dispatch never hands it —
nothing in the paragraph says the slice arrives in the dispatch prompt
itself. Reinforced by: frontmatter ("a chunk-executor invocation handed a
manifest slice"), doc-kinds header ("the manifest hints these"), red flag
("a `files` list that isn't the manifest's verbatim"), and the final red
flag calling the manifest "the work order."

Grader's key line: "The runner succeeded *despite* the text, not because of
it: the dispatch prompt's 'This list is your entire scope' overrode the
skill's read-the-manifest instruction. … on a dispatch where [the manifest]
is absent, the skill text as written instructs an impossible step." Skill-
text mark: FAIL.
