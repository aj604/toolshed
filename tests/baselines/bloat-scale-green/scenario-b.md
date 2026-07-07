# Scenario (b) — policy chunk (GREEN)

Same sandbox and dispatch as RED (b) (`bloat-scale-red/dispatch-b.txt`);
fresh runner against the post-edit SKILL.md; chunks/ reset before the run.

## Runner output (verbatim)

Opening note: "Per the skill's headless-executor mode, the seam validation
(--chunk --manifest) is the orchestrating workflow's job — the manifest is
its state, and a chunk executor never opens it — so I stop here."

ACTION LOG
1. Read — …/detecting-doc-bloat/SKILL.md — invoke the skill; load router rules, headless-executor mode, red flags.
2. Read — …/detecting-doc-bloat/output-contract.md — load the v2 record field rules and the chunk-result seam shape (same message as call 1).
3. Bash — find <job root> -type f | head -50 — inventory the sandbox job directory (same message as calls 1–2).
4. Read — …/references/planning-artifacts.md — load the policy-chunk rules.
5–7. Read — p1.md, p2.md, p3.md (N=3: sample = whole set; no per-file records).
8. Bash — mkdir -p <job root>/chunks.
9. Write — <job root>/chunks/p-04e855a882.json — exactly one POLICY record, files copied verbatim from the dispatch.
(Not opened: manifest.json, dispatch-prompt.txt, audit-scope.json, README.md — "the dispatch prompt was my slice; the skill forbids a chunk executor from opening the manifest or enumerating the corpus.")

RESULT: one POLICY record, doc docs/superpowers, files = the three
dispatched paths in order, sampled file:line evidence. Orchestrator-side
seam validation (post-hoc): `OK: 1 record(s) valid`.

## Grader verdict (fresh stakeless grader, verbatim)

Q1: FAIL — one real violation: action-log line 3 (find | head -50) is
corpus/tree enumeration, the exact baseline failure the answer key names and
the exact behavior the skill's red flag forbids. The dispatch had already
handed the files list and output path verbatim, so the inventory was
unnecessary by construction. Everything else matched — a narrow fail, not a
wholesale one.

Q2: TEACHES — the headless paragraph carries the slice-from-the-prompt
contract explicitly (quotes as in scenario-a). "The runner's
manifest/validator abstention traces cleanly to that text."

Grader's key causal finding: "the runner issued calls 1–3 in one message,
i.e., the enumeration was launched before the just-read skill text (with its
explicit anti-enumeration red flag) could have been absorbed. The violation
is runner impatience, not skill-text misdirection." Compare RED (b), where
the enumeration existed to locate the manifest the old text demanded.
Structural fix applied post-grading where it binds at t=0 — the dispatch
prompt itself; see README REFACTOR item 2.
