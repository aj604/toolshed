# Scenario (c) — landed planning artifact (detect-time payload authoring)

## Prompt (verbatim, to a fresh subagent)

> First read the skill file plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md and follow it exactly.
>
> Task: run a documentation-bloat audit of the single doc docs/plans/2026-05-01-rate-limiter-design.md in the repository at tests/fixtures/plan-swarm (treat that directory as the repository root; all paths relative to it). Emit your structured result as the skill prescribes.
>
> Final message: 1. "RECORDS:" (verbatim JSON) 2. "WORK PERFORMED:" — every distinct piece of content authored, one line each.

## Runner behavior

Classified correctly (planning artifact, implementation landed → `DISTILL ready`). Then, following the v1 skill text, **authored the full detect-time payload**: "first authored a v1 record with a full DISTILL payload (1 code-verified claim targeting README.md, 1 anchored insight with provenance `docs/plans/2026-05-01-rate-limiter-design.md @ e69b324`, 1 draft decision-log entry)". The v2 validator rejected v1 wholesale; the runner re-emitted payload-free v2 — but "folding the insight-walk outcome into `evidence`".

## Grader verdict (stakeless, held the answer key): overall **FAIL**

- C1 (DISTILL ready, landed-code evidence): PASS.
- C2 (no detect-time payload/residue authoring, discarded included): **FAIL** — "This is precisely what C2 prohibits: drafted claims, a drafted insight, and a drafted decision-log entry authored at detect time … 'Work performed then discarded still counts as the speculative cost.'" Also: "the agent then smuggled the insight authoring into the v2 record … the evidence field here carries pre-authored insight content and a routing target, i.e. distiller work performed at detect time."
- C3 (skill text taught payload-free emission): **FAIL** — "The agent followed the skill text, authored a v1 payload, and only converged to payload-free v2 after mechanical validator rejection."

Rationalizations captured (verbatim):
1. "per the skill's own 'never hand off a result the validator rejects' rule, the emitted report is v2, with the mandatory insight walk documented in `evidence`" — "reframes validator-forced rework as skill-guided compliance".
2. "folding the insight-walk outcome into `evidence`" — "treats relocating payload content into a permitted field as eliminating it".
3. "with the mandatory insight walk" — "asserts the detect-time insight walk is 'mandatory' under a contract whose whole point is deferring that authoring to the post-approval distiller."

Grader's close: "The transcript is a clean demonstration that the skill text — not agent capability — is the gap."

## What the GREEN text must therefore teach

`DISTILL` detection emits classification + landed-code evidence ONLY. The insight walk, claim drafting, and decision-entry drafting are the doc-distiller's post-approval job — and "documenting the walk in `evidence`" is the same speculative cost relocated, called out as a red flag in so many words.
