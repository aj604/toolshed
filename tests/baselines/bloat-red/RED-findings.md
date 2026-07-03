# bloat-red RED findings

Baseline: two general-purpose subagents (A = sonnet, B = haiku), fresh context, no skill,
no answer key, prompt verbatim from the task brief ("You are auditing documentation for
bloat… Do not edit any files."). Outputs: `agentA-output.md`, `agentB-output.md`. Graded
against `ANSWER-KEY.md` (P1–P6) and the bloat-report contract
(`docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md`, "The bloat-report contract").

## Recall scorecard

| Item | Expected | Agent A (sonnet) | Agent B (haiku) |
|------|----------|------------------|-----------------|
| P1 README:6-14 + SETUP.md | MERGE-DOC or RETIRE-DOC | HIT — "Prune `SETUP.md` entirely" (RETIRE-DOC class), overlap quoted in full | HIT (inverse direction) — delete README's Setup, keep SETUP.md as source of truth (MERGE-DOC-target-SETUP class; acceptable per key note 2) |
| P2 README:19 | CUT | HIT — flagged lines 18–20, "filler restating the code/example" | HIT — "redundant with the docstring and the code itself" |
| P3 README:30-38 | CONDENSE | HIT — with concrete replacement text citing MAX_RETRIES/TIMEOUT_S | HIT — with replacement line "(3 attempts, 10s timeout per attempt)" |
| P4 README:40-43 | EXTRACT-AND-MOVE → CLAUDE.md | **MISS — verdict inverted**: "Keep this one; it's the highest-value sentence in the whole README" / summary row "Keep as-is" | **MISS — verdict wrong and destructive**: "Move the `TIMEOUT_S` / flush-interval edge case to an inline comment in `src/notify.py` if it's a real gotcha, or delete it if it's speculative." |
| P5 retry design doc | DISTILL ready + payload (2 claims + decision_entry) | **MISS** — "This doc is otherwise fine as a historical record and shouldn't be pruned wholesale — flagging only the one sentence" (cut line 37's "after going back and forth"). No implemented-vs-doc comparison, no claim extraction, no decision entry | **MISS** — flags only the Sketch section, on a wrong theory: "pseudocode that doesn't match implementation… The sketch is not code; it's aspirational documentation" (the sketch in fact mirrors the shipped constants/flow). No ready status, no payload |
| P6 batching doc | DISTILL pending-implementation, NO payload | **MISS (no record)** — "No pruning needed here on bloat grounds… Not actionable today since the status is currently accurate." Correctly avoided ready/payload, but produced no finding at all | **PARTIAL/WRONG** — flagged it, but as "Speculative, unactionable content" with "Delete if the decision has been made elsewhere… this doc is now stale" — proposes possibly deleting an accurate pending design. No pending-implementation concept. Did not assign ready/payload (trap not tripped) |

Recall: A 3/6, B 3/6 (P1–P3 solid for both; P4–P6 — the verdicts unique to this skill —
missed by both).

## Precision failures (non-planted content flagged)

Both flagged `CLAUDE.md`, which the answer key marks as the EXTRACT target, not a source:

- A (#4): "`CLAUDE.md` is redundant with `README.md`'s opening line… a candidate for
  merging into README.md's intro rather than maintained as a second, separately-drifting
  file". This would *delete the target doc* P4's extraction needs.
- B (#6): "CLAUDE.md is a minimal agent-facing summary, but it doesn't signal why it
  exists or how it differs from README" → recommends adding cross-reference boilerplate
  to both files (adds lines to fix "bloat").

B also inverted doc priority on P3: "doesn't add insight beyond what's already in the
design doc" — grading the living README against the planning artifact instead of the code.

## Failure classes (per brief) — appeared / did not appear

### 1. Free-form prose, no records / ids / enums — APPEARED (both)

Neither output is machine-parseable or approvable by ID. A is narrative sections plus a
prose summary table with verdicts like "**Delete**", "**Condense to ~1–2 sentences with
concrete numbers**", "**Consider merging into README.md** or leave minimal", "**No change
now; revisit when `send_batch` ships**" — free-text actions, hedged, no closed enum, no
record ids. B is closer to structured (numbered findings with **Location / Issue /
Recommendation**) but still no ids for approval, no verdict enum (its categories are
ad-hoc: "Duplication", "Verbose/restating code", "Speculative/unactionable", "Pseudocode
drift", "Unclear separation"), and recommendations offer unresolvable alternatives
("Either: Move… Delete… If keeping, update…"). Nothing either agent produced could pass
`validate-bloat-output.py` or drive an approve-by-ID fix step.

### 2. Missing / asserted-not-shown evidence — APPEARED (B); largely did NOT appear (A)

- B's anchors are sloppy or wrong: "Setup section, lines 6–12" (actual 6–14), "CLAUDE.md
  (5 lines)" (actual 4), "README.md (49 lines)" (actual 48), and asserted claims with no
  quote: "The Setup section in README is identical to SETUP.md verbatim" (true, but shown
  nowhere), plus the false assertion that the sketch "doesn't match implementation".
- A's evidence discipline was *good*: it quoted the duplicated setup block in full, quoted
  each padded sentence of P3, and cited real line numbers throughout. Record explicitly:
  for a strong model the skill does not need to fix evidence recall — it needs to declare
  the evidence *field* so the discipline is contractual, not model-dependent.

### 3. No ready-vs-pending distinction on planning artifacts — APPEARED (both, the core gap)

Neither agent has the concept that a design doc whose implementation has landed should be
*distilled* (durable decisions extracted, scaffolding retired):

- A on the implemented design: "This doc is otherwise fine as a historical record and
  shouldn't be pruned wholesale" — treats it as an ADR to keep verbatim forever; never
  checks it against `src/notify.py`.
- A on the pending design: "No bloat… Not actionable today" — correct outcome, but by
  luck of "no bloat found", not by a pending-implementation determination.
- B recommends deleting the implemented design's Sketch for the wrong reason and floats
  deleting the pending design outright ("Delete if the decision has been made elsewhere").
  Neither ever states "implementation exists for X, not for Y" as the deciding test.

No claims extraction, no decision-log entry, no payload from either — the entire DISTILL
half of the contract is absent from baseline behavior.

### 4. No proposal text — did NOT appear for CONDENSE; APPEARED for EXTRACT-AND-MOVE

Both agents volunteered concrete replacement text for P3 (A: "Failed sends are retried up
to `MAX_RETRIES` (3) times with a `TIMEOUT_S` (10s) timeout per attempt…"; B: "Retries on
transient failures (3 attempts, 10s timeout per attempt)."). So CONDENSE proposals come
free — the skill only needs to give them a field. But the structured EXTRACT proposal
(`{"target", "text"}`) appeared nowhere: A kept P4 in place; B sent it to a code comment
or deletion. The move-with-target concept must be taught, not just formatted.

### 5. Unsolicited edits — did NOT appear (both)

Both agents were report-only, as instructed by the prompt. The skill's no-edit rule is
belt-and-suspenders, not a fix for observed behavior.

## Failures observed beyond the brief's predicted classes

- **Confidently inverted verdicts**: A didn't merely miss P4 — it graded the extract
  candidate "the highest-value sentence in the whole README" and instructed "Keep as-is".
  A skill that only adds structure would format this wrong answer nicely; the skill text
  must define EXTRACT-AND-MOVE as "valuable content, wrong doc" (value ≠ placement).
- **Destructive recommendations without an approval gate**: B proposes deleting a true
  operational gotcha ("delete it if it's speculative") and possibly deleting an accurate
  pending design doc. This is the concrete case for report-only + approve-by-ID.
- **Fix-by-adding-boilerplate**: B's remedy for CLAUDE.md/README "unclear separation" is
  to add cross-reference lines to both docs — a bloat audit that increases line count.
- **No summary/counts**: neither output ends in anything a gate could consume (the
  contract's `summary` object with per-verdict counts).

## What Task 3's skill text must therefore teach (loopholes to close)

1. The closed 6-verdict enum + record shape + validator invocation (fixes class 1 — the
   universal failure).
2. The DISTILL decision procedure: for every `docs/plans/` artifact, check whether the
   implementation exists in code; `ready` + mandatory payload (claims + decision_entry)
   when it does, `pending-implementation` + null payload when it does not (fixes class 3,
   both directions of the P5/P6 trap).
3. EXTRACT-AND-MOVE as a verdict for accurate-but-misplaced content, with mandatory
   `{"target", "text"}` (fixes the P4 double miss — "keep" and "code-comment/delete" are
   both wrong for the same passage).
4. Evidence as a mandatory per-record field with real file:line anchors (fixes B's class-2
   failures; declares shape for A).
5. Report-only + approval-by-ID framing (mitigates B's destructive suggestions; class 5
   stays declared even though not observed).
6. Precision guardrail: the extraction *target* doc and dense, accurate lines are not
   findings (both agents' CLAUDE.md false positive).
