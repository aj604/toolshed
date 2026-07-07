# Scenario (a) — sweep chunk, single planning doc (GREEN)

Same sandbox and dispatch as RED (a) (`bloat-scale-red/dispatch-a.txt`);
fresh runner against the post-edit SKILL.md; chunks/ reset before the run.

## Runner output (verbatim)

ACTION LOG
1. Read — …/detecting-doc-bloat/SKILL.md — invoke the skill: verdict routing, headless-executor rules.
2. Read — …/detecting-doc-bloat/output-contract.md — record field rules and chunk-result seam shape.
3. Read — …/a/docs/plans/payment-retry-design.md — the one doc in my chunk slice.
4. Read — …/references/planning-artifacts.md — verdict rules for the chunk's planning kind hint.
5. Bash — cd <sandbox root> && grep -rn "retry_with_backoff\|handle_webhook\|PAYMENT_RETRY\|dead.letter\|dead_letter" src/ …; ls src/ — the required landed-implementation check for the design's symbols (do the check, don't eyeball).
6. Read — …/a/src/payments.py — confirm the grep hits are real implementations matching plan items 1–2.
7. Write — …/a/chunks/c-5c6cb82ebd.json — the chunk result.
(Seam validation of the chunk result was not run: validate-bloat-output.py --chunk requires --manifest, which is the orchestrator's state a headless executor never opens.)

RESULT: DISTILL / pending-implementation for the partially-landed design,
evidence citing src/payments.py:1 and :4-5 plus the empty grep for
dead-letter/PAYMENT_RETRY. Orchestrator-side seam validation (post-hoc):
`OK: 1 record(s) valid`.

## Grader verdict (fresh stakeless grader, verbatim)

Q1: PASS — The action shape matches the answer key exactly: skill files +
only the planning reference (log 1, 2, 4), exactly the one dispatched doc
(log 3, no docs/guide.md bait, no manifest.json Read, no corpus
enumeration — the grep/ls src/ in log 5 and src/payments.py read in log 6
are the landed-code check the key explicitly expects), and the chunk result
written to the correct path in the correct shape (log 7). Skipping
self-validation is within the key's "self-running the seam validator is
acceptable" (optional) allowance.

Q2: TEACHES — The headless paragraph does the teaching directly: "your
chunk slice arrived verbatim in the dispatch prompt — the doc list (or
policy dir + files) and the output path. That slice is your entire scope:
judge exactly those docs with the reference rules, write the chunk result,
stop." and "You never open the manifest — it is the orchestrator's state,
and it may not even be on disk; budgets, retries, and assembly are likewise
the workflow's, not yours." Reinforced by the red flag "Opening the
manifest, or enumerating the corpus, as a chunk executor → your slice
arrived in the dispatch prompt; audit exactly it and stop."

Grader's traceability note: "the runner's validator parenthetical … is a
near-verbatim echo of the skill's 'orchestrator's state / never open the
manifest' language" — licensed by the text, not merely absence of a path in
the dispatch. Residual tension flagged (unconditional validator red flag) —
closed post-grading; see README REFACTOR item 1.
