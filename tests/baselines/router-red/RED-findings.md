# router-red RED findings

2026-07-04. Arm setup: two general-purpose subagents (router-red-A, router-red-B), fresh
context, neutral prompt (no mention of the router rule, CLAUDE.md policy, scope, or
churn), auditing `fixture/` against the **0.6.0** `detecting-doc-bloat` skill text
(post-insights, pre-router-rule) served from a scratch copy so the agents could not see
the current text or `writing-docs/agent-context.md`. Outputs: `router-red-A-output.json`,
`router-red-B-output.json`. Both pass the current validator; no fixture files were
edited. Graded against `ANSWER-KEY.md` (R1–R5) per its "Expected RED (0.6.0 text)
failure shape" — RED is graded on documenting that shape, not on matching the GREEN
column.

## Scorecard against the expected RED shape

| Item | Expected RED shape | router-red-A | router-red-B |
|------|--------------------|--------------|--------------|
| R1 `make seed` gotcha (CLAUDE.md:5-6) | untouched | untouched (no record) | untouched (no record) |
| R2 golden-regen section (CLAUDE.md:9-15) | stays — no reverse lens exists | **stays** — no record; CLAUDE.md never audited as a source at all | **stays** — no record; same |
| R3 503 line (CLAUDE.md:7) | likely untouched | untouched | untouched |
| R4 port-lock gotcha (README.md:11-14) | aimed at CLAUDE.md | EXTRACT-AND-MOVE → CLAUDE.md, one dense line | EXTRACT-AND-MOVE → CLAUDE.md, one dense line |
| R5 Windows newline note (README.md:16-18) | aimed at CLAUDE.md (the predicted mis-landing) | **routed to `docs/reference/export.md`** — beat the prediction | **routed to `docs/reference/export.md`** — beat the prediction |

## Per-agent grades

### router-red-A

Two records, both EXTRACT-AND-MOVE out of README.md; zero records on CLAUDE.md.

- **R4 (B1)**: correct target and dense one-line landing. Proposal: "- The dev server
  keeps a `.portlock` file after a crash and silently binds a random port on the next
  start — delete `.portlock` before restarting." Evidence quotes the tells ("'One thing
  worth knowing', 'silently binds a random port'"), verifies novelty ("`grep -rn
  portlock` matches only README.md:14, so no agent/operator doc carries the `.portlock`
  fact today"), and flags the span problem: "the gotcha sentence begins mid-line 11
  after `` Run `exporter run --tenant NAME`. ``, which must stay — only the gotcha
  moves."
- **R5 (B2)**: to `docs/reference/export.md`, correctly noting the existing owner:
  "docs/reference/export.md:4-5 states 'Newline handling is explicit: the writer opens
  files in binary mode (`src/export.py:4`)' but lacks the Windows trailing-newline
  consequence." Anchors check out against the fixture.
- **R1/R3**: no records — matches the expected RED shape.
- **R2**: no record — the predicted structural failure, delivered.

Evidence discipline: good — quotes, `file:line`, spans on both records; all anchors
verified correct.

### router-red-B

Structurally identical: two EXTRACT-AND-MOVE records out of README.md, zero on
CLAUDE.md.

- **R4 (B1)**: to CLAUDE.md, one dense line: "- **Delete `.portlock` before restarting
  the dev server after any crash** — a stale port lock file makes the next start
  silently bind a random port." Also flags the mid-line start: "line 11 also opens with
  the usage sentence 'Run `exporter run --tenant NAME`.', which is not part of the
  extracted passage and must remain".
- **R5 (B2)**: to `docs/reference/export.md`, citing the same existing claim at
  export.md:4-5 and the `src/export.py:4` comment ("opens in binary mode to control
  newlines explicitly" — verbatim match with the fixture).
- **R1/R2/R3**: no records — expected RED shape.

Evidence discipline: good; anchors verified.

## Where RED judgment beat the old text — and what that does *not* prove

The key predicted R5 aimed at CLAUDE.md, because the 0.6.0 EXTRACT tell says an
operational gotcha "belongs in CLAUDE.md or the runbook". Both RED agents routed R5 to
`docs/reference/export.md` anyway — router-red-A because the target already carried the
adjacent claim, router-red-B likewise ("is where this consequence belongs"). Say it
plainly: **the old text permitted the mis-landing; these two agents' taste declined it.**
Nothing in the 0.6.0 text distinguishes R4's broad scope from R5's narrow scope — a
different model, or the same model on a fixture without a conveniently pre-existing
export.md, has the text's explicit blessing to land R5 in CLAUDE.md. The new router rule
forbids it. So R5 in this baseline demonstrates permitted-vs-forbidden, not
observed-failure-vs-fix; the observed failure is R2.

## Distilled failure statement

The 0.6.0 text structurally cannot make CLAUDE.md leaner, and this baseline shows it in
both directions at once:

1. **No reverse lens.** Neither agent audited CLAUDE.md as a source doc — not one record
   targets it, not even the deliberately borderline 503 line. The 6-line golden-regen
   procedure (CLAUDE.md:9-15), the key's "clear-cut case" for extraction out
   (multi-line, one-task, existing natural target at `docs/reference/testing.md`), sat
   unexamined. Under 0.6.0, CLAUDE.md is only ever a landing *target*; content flows in
   and nothing flows out.
2. **Net effect: CLAUDE.md grows.** Both agents' proposals add one line (R4) and remove
   zero — net +1 each. The user's actual requirement (the key's net-effect check:
   "leaner or stay put in every line it keeps") fails for both, and must fail for any
   0.6.0 run that finds a broad-scope gotcha, because the text has no mechanism that
   removes lines from the always-loaded file.
3. **Landing bar unstated.** R4 landed as one dense line and R5 avoided CLAUDE.md, but
   both outcomes ride on agent taste: the 0.6.0 tell ("belongs in CLAUDE.md or the
   runbook") states no scope test, no density requirement, no leaner-or-same constraint.
   What went right here is not reproducible from the text.
