# router-red answer key (grading reference — NOT shown to baseline agents)

Fixture: `tests/baselines/router-red/fixture/` (self-contained fake repo). Tests the
**router rule** (writing-docs `agent-context.md`, consumed by `detecting-doc-bloat`,
added in doc-lifecycle 0.6.1): always-loaded files are routers — inline placement is a
scope test; landings must not fatten CLAUDE.md; the reverse lens is deliberately
conservative (no churn). RED arm runs the 0.6.0 skill text (post-insights,
pre-router-rule) so any difference is attributable to the router rule alone.

## Planted items — 5

| ID | Location | Expected (GREEN) | Trap it tests |
|----|----------|------------------|---------------|
| R1 | `fixture/CLAUDE.md` `make seed` gotcha (2 lines) | **Left in place** — no extraction out. Broad scope: every test run trips it. | Overcorrection control: the router rule must not strip broad-scope gotchas. |
| R2 | `fixture/CLAUDE.md` "Regenerating the golden files" section (6 lines) | `EXTRACT-AND-MOVE` **out** to `docs/reference/testing.md` (the existing natural target), leaving at most a when-to-read line. Multi-line + plainly one-task (export golden regeneration) + existing target = the conservative reverse lens's clear-cut case. | Reverse lens fires on the clear case. |
| R3 | `fixture/CLAUDE.md` API-client 503 line (1 line) | **No record** (or at most nothing placement-related; a `CUT` for restating `src/client.py:3`'s comment is a defensible judgment — grade it neutral, not a churn failure). What it must NOT get: an extraction/move record. Borderline scope + single line = the no-churn guard. | Hypermanagement control: borderline yields no placement record. |
| R4 | `fixture/README.md` port-lock gotcha ("worth knowing… every local workflow hits this") | `EXTRACT-AND-MOVE` **into** `fixture/CLAUDE.md`, densest one-line form. Broad scope: bites every session after any crash — clears the router rule. | Broad-scope gotchas still reach CLAUDE.md (the rule is a gate, not a wall). |
| R5 | `fixture/README.md` Windows trailing-newline note ("Note that…") | `EXTRACT-AND-MOVE` to `docs/reference/export.md` (existing target) — **NOT** CLAUDE.md. Narrow scope: one file, cross-platform diffing only. | Narrow-scope gotchas route to reference, not the always-loaded file. |

## Expected RED (0.6.0 text) failure shape

The 0.6.0 EXTRACT tell says an operational gotcha "belongs in CLAUDE.md or the
runbook": expect R4 **and R5** both aimed at CLAUDE.md (R5 = the mis-landing the
router rule exists to stop); no reverse lens exists, so R2 stays (or worse, gets
CONDENSE'd inside CLAUDE.md); R1/R3 likely untouched. RED is graded on documenting
that shape, not on matching the GREEN column.

## Grading

Per agent: R1 kept? R2 moved out to the existing target (target correct, pointer
allowed)? R3 free of placement records? R4 into CLAUDE.md as one dense line (quote
the proposal text — a multi-line landing is partial credit)? R5 to export.md not
CLAUDE.md? Plus: shape-valid report, report-only (no fixture edits), evidence
discipline (quotes/`file:line`, spans on passage verdicts).

Net-effect check (the user's actual requirement): under GREEN proposals, CLAUDE.md
must get **leaner or stay put in every line it keeps** — one line in (R4), six out
(R2). An agent whose proposals grow CLAUDE.md overall has failed the rule's point
regardless of per-item scores.

## Notes

- Baseline prompt is neutral — it must NOT mention the router rule, CLAUDE.md
  policy, scope, or churn.
- R3's `CUT`-for-code-restatement ambiguity is deliberate; grade placement only.
- GREEN agents may follow the skill's own reference to
  `writing-docs/agent-context.md`; RED agents must not be pointed at it.
