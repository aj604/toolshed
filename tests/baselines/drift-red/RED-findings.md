# detecting-doc-drift — RED findings

**Date:** 2026-06-14
**Verdict: RED did not fail.** Across 12 baseline subagents (no skill), 4 task framings,
and 2 model tiers, capable agents already perform evidence-based drift detection well. Per
the writing-skills Iron Law (no skill without a failing test) this blocks writing the skill
as designed. Decision escalated to Avery.

## Fixtures built (kept for reuse)

- `drifted-CLAUDE.md` — the agent1 known-good CLAUDE.md with 6 planted STALE claims, 6 TRUE
  claims, 1 UNVERIFIABLE claim. Repo under test: `tests/fixtures/taskflow/`.
- `ANSWER-KEY.md` — per-claim kind/tier/verdict grading key.
- Diff-scoped fixture: a synthetic diff (worker schema 3→4, exit 4→7; migrate stamps 4)
  against the 6 `tests/baselines/bootstrap-green/` doc files. The schema/exit fact is
  referenced in 4 of those files, including a verbatim `(schema 3)` snippet buried in a
  fenced `make migrate` output block in `agent1/README.md:21` (the "sneaky" reference).

## Scenarios run

| # | Mode | Framing | Model | Agents | Result |
|---|------|---------|-------|--------|--------|
| 1 | Full audit | suspicion-primed ("worried it's out of date, flag anything") | Opus | 3 | **clean pass** — 6/6 stale caught, U1 flagged, evidence cited, 0 false-VERIFIED, 0 false-positives |
| 2 | Full audit | low-suspicion / efficiency ("quick sanity check, don't go overboard, it's been reliable") | Opus | 3 | **clean pass** — 6/6 stale, U1 flagged, full evidence; pressure to rubber-stamp did NOT work |
| 3 | Diff-scoped | "here's a diff — which doc passages are now stale?" | Opus | 3 | **clean pass** — all 4 affected files incl. the README snippet; 2 unaffected READMEs correctly left alone; unrelated exit-3 refs correctly NOT flagged |
| 4a | Full audit | low-suspicion (×2) | Haiku | 2 | **mostly pass** — caught all behavioral/value drift (port, schema, exit, POST status, phantom export); MISSED `make reset`→`make clean` (both runs) and one missed `setup-db.js`; U1 never flagged |
| 4b | Diff-scoped | as #3 | Haiku | 1 | **clean pass** — all 4 files incl. README snippet, 2 READMEs left alone |

## What the baseline got RIGHT (the predicted failures did NOT occur)

The ANSWER-KEY predicted: false-VERIFIED on behavioral drift, evidence-free "looks
consistent" passes, blind trust in file:line anchors, no tiering causing misses,
UNVERIFIABLE silently accepted. For Opus, **none** of these occurred:

- **Evidence, not vibes.** Every Opus agent opened the cited source lines and quoted the
  real values (`server.js:21 → 8080`, `worker.js:17 → schema !== 3`, `:49 → 201`). No
  claim was passed on "seems consistent."
- **Anchors didn't fool them.** The drifted doc kept correct-looking `file:line` anchors on
  wrong values; agents opened the line anyway and caught the mismatch.
- **Behavioral drift caught by reading.** S3 (schema/exit) and S4 (POST 201 vs 200) needed
  code reading, not just grep — agents did it unprompted.
- **Precision held.** No TRUE claim was wrongly flagged; the unrelated exit-3 references
  were explicitly identified as out-of-scope in diff mode.
- **UNVERIFIABLE surfaced.** Opus flagged U1 ("worker is reasonably fast…") as an
  unverifiable claim to cut — even noting the worker body is an empty stub.
- **Extras.** Agents volunteered out-of-scope findings (off-by-one line anchors,
  undocumented `WORKER_INTERVAL_MS`, the `lint.js` comment overstating "parse").

## The one real (small) gap — Haiku only

- Haiku eyeballed the command table and **missed `make reset` (real target: `make clean`)**
  in both full-audit runs — a Tier-1, grep-checkable claim it didn't grep the Makefile for.
- Haiku **never flagged the UNVERIFIABLE line** (U1).
- Haiku's diff-scoped run was nonetheless clean.

This is the only behavior resembling the designed failure mode (incomplete coverage of
plausible-looking, statically-checkable claims), and only on a cheaper model.

## Interpretation

Drift detection is a **verification** task, and current models are naturally strong, even
eager, verifiers — the opposite of the **generation** tasks where skills 1–2 found real
failures (fabrication, completeness-chasing). The design's core value proposition —
**tiered escalation for cost control at scale** — could not be exercised: on a small repo
"read everything" is cheap and optimal, and agents correctly did exactly that. A tiering
discipline would only help (and would only be observable failing) at a scale these fixtures
cannot reach (hundreds of claims across dozens of docs in a large repo), and even then it
is unproven that Opus would fail to tier sensibly on its own.

## Recommendation (for Avery)

Do not write `detecting-doc-drift` as a discipline skill against this evidence. Options:
1. **Fold its load-bearing contract into `doc-sync-automation` (skill 4)** as the automation
   procedure — evidence-required verification, diff-scoped reverse-search completeness,
   VERIFIED/STALE/UNVERIFIABLE vocabulary, blast-radius/idempotency guardrails. That is
   where the actor is automation (possibly a cheaper model) that genuinely won't reinvent
   the method, and where the Haiku gap above actually bites.
2. **Build a large-scale fixture** to try to force the tiering/cost failure, then RED→GREEN
   on cost-control only. Higher effort, uncertain payoff.
3. **Ship a thin procedural skill** aimed explicitly at cheaper automation runners, RED-
   tested on Haiku (the `make reset` / UNVERIFIABLE gap), scoped to "evidence + full
   coverage," not tiering.

## Reframe (Avery's steer, 2026-06-14)

> "the point is to declare the shape of this. it will be invoked programmatically and
> trigger updates."

This relocates the RED axis. The skill is **not** a discipline skill for interactive Claude
and **not** primarily about recall — it is the **declared procedure + output contract** that
automation (`doc-sync-automation`, skill 4) invokes programmatically to *trigger updates*.
Tested against that purpose, the baseline DID fail — universally:

- **No machine-actionable output (all 12/12 agents).** Every agent emitted free-form prose
  for a human ("Not safe to commit", "thumbs up with caveats"), each with a different,
  unparseable structure. Nothing a downstream trigger could consume: no stable per-claim
  record of `{claim, kind, tier, verdict, evidence, location, fix}`. An automation calling
  these agents could not reliably act on the result.
- **No deterministic procedure.** Each agent improvised its own steps/format. "Declare the
  shape" means a fixed extract→verify→classify→**emit structured result** pipeline so two
  runs (or two models) produce the same shape.
- **Completeness/classification gaps on the realistic runner (Haiku).** Skipped a Tier-1
  grep-checkable claim (`make reset`) and never emitted UNVERIFIABLE — exactly the kind of
  silent gap that makes automated triggers miss drift or mis-trigger.

**This is the GREEN target:** a procedural/reference skill that declares (a) the two modes,
(b) the extract→verify(tiered)→classify→emit pipeline with the evidence-required contract,
(c) a structured result shape automation can parse to trigger updates, (d) the
VERIFIED/STALE/UNVERIFIABLE vocabulary. GREEN = re-run the Haiku scenarios WITH the skill
and confirm a parseable, complete, correctly-classified result.
