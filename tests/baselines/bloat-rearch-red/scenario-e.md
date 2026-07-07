# Scenario (e) — interactive large scope (15 docs)

## Prompt (verbatim, to a fresh subagent)

> You are simulating an interactive session. A user has asked: "run a full bloat audit of tests/fixtures/plan-swarm" (a repository with 15 documentation files; treat that directory as the repository root, doc paths relative to it).
>
> First read the skill file plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md and follow it exactly. You have the ability to dispatch subagents if you judge that appropriate … The test is about HOW you structure the audit.
>
> Final message: 1. "EXECUTION SHAPE:" 2. "RECORDS:" 3. "RATIONALE:".

## Runner behavior (against the old monolithic SKILL.md)

The runner's own account: "The SKILL.md I read told me, for a full audit:
inventory via `list-docs.py`, walk every passage of every doc inline (three
questions, three-lens re-pass), classify every planning artifact individually
via landed-check greps, and emit a v1 report with DISTILL payloads authored at
detect time. Followed literally, that would have produced ~14 records —
including twelve per-file DISTILLs, ten of them over content-free 3-line
boilerplate — as one inline mega-sweep. **I started down exactly that path**,
and the mandatory step-4 validation is what stopped it".

Recovery route: validator rejection → "read the validator plus the
rearchitecture design doc … for v2/harness semantics" → re-planned via
`plan-chunks.py` → dispatched 4 chunk executors → seam-validated each →
assembled a 5-record schema-2 report (validator OK). It also flagged:
"SKILL.md and output-contract.md still document contract v1 … while the
shipped scripts enforce v2 — worth syncing."

## Grader verdict (stakeless, held the answer key): overall **FAIL** (3 of 5)

- C1 (final shape = plan → dispatch → seam → assemble): PASS — reached, but only after the bounce.
- C2 (final records match key): PASS, boundary note deferred to C3.
- C3 (no detect-time residue, evidence included): **FAIL** — B4's evidence "carries an 'Insight sweep' paragraph naming the Redis-rejection insight … insight-walk content authored at detect time, smuggled into the evidence field."
- C4 (skill text taught the chunked shape): **FAIL** — "Validator bounce, then tool-source and design-doc archaeology — the two disqualifying routes named in the criterion. The skill text taught nothing about chunking."
- C5 (no double-spend): **FAIL** — "The orchestrator read all 15 docs inline *and* dispatched four executors over the same corpus — paid twice."

Rationalizations captured (verbatim, grader's selection):
1. "the scripts outrank the lagging skill text, so I re-read the landed tooling … and the rearchitecture design" — "archaeology framed as diligence".
2. "in a fresh run I would go manifest-first" — "'in a fresh run I would' does not un-spend the tokens."

Grader's close: "The failure is recovery-shaped, not outcome-shaped … a clean
demonstration that the old SKILL.md cannot produce the v2 shape on its own."

## What the GREEN text must therefore teach

Interactive large scope = plan first, dispatch per chunk, orchestrator never
reads the corpus inline; DISTILL evidence carries the landed-code proof only
(insight content is the distiller's, wherever it might be smuggled).
