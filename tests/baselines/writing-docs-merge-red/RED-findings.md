# RED — merge `writing-for-llms` into `writing-docs` (one door)

**Date:** 2026-06-20
**Change under test:** collapse the two doc-authoring skills into a single `writing-docs` entry
point that routes by audience (human standard vs. + density) and by job weight (inline vs.
dispatch generalist / `llm-doc-writer`). Retires `writing-for-llms` as a separate skill.

## Setup

- Fixture: `tests/fixtures/taskflow` (3-component workspace). Truth in repo.
- Input: `SOURCE-claude.md` — an **accurate but bloated** agent-facing CLAUDE.md (~1197 words):
  narrative scaffolding, second-person welcome copy, inferable prose, redundancy, unanchored
  "why". No planted drift — this RED tests density/routing, not fact-finding.
- Task to agents: "this CLAUDE.md has grown bloated; rewrite it to standard." Agent-facing doc.

## Runs

| Run | Model | What it had | Output |
|-----|-------|-------------|--------|
| A | Opus-class | only `writing-docs` (the door that names CLAUDE.md) | `agentA-opus-output.md` |
| B | Sonnet | only `writing-docs` | `agentB-sonnet-output.md` |
| C | Opus-class | the realistic skill **list** (4 descriptions), routing-only | — (decision report) |

## Result: the predicted axis (output not dense) is the WRONG axis — same trap as llm-doc RED

Grading on "did the rewrite get dense" measures **capability**, and capable agents densify
*regardless* of any density skill, because `writing-docs`' spine ("if a line is neither a
verifiable nor a marked-rationale claim, cut it") incidentally removes non-signal tokens:

| Run | Reduction | Did it densify? |
|-----|-----------|-----------------|
| A (Opus) | 1197 → 281 w (~76%) | yes — but called it a *side effect* of the spine, not a density rule |
| B (Sonnet) | ~490 → ~210 w (~57%) | yes — tables, cut welcome/hedging copy |

So reduction-% is discarded as the RED axis (tier-dependent, unfair — mirrors the llm-doc RED
finding that recall was the wrong axis).

## The real RED axis: the two-door ecosystem dead-ends the agent (tier-INDEPENDENT, writable)

### Finding 1 — discovery dead-end: first matching door ends the search

Run C, choosing from descriptions alone (verbatim):
> "`writing-docs`. … the only description naming CLAUDE.md as the primary trigger."
> "Honestly: probably not [open a second], and **that's the trap**. Once `writing-docs` opens
>  and gives a coherent contract, it *feels complete*. … The first skill that satisfies the
>  surface request tends to end the search."
> "The boundary … is **genuinely blurry**. The descriptions don't tell me whether they're
>  alternatives or a pipeline."

Consequence confirmed by A and B (different tiers, same door):
- Both declared `writing-docs` **"sufficient."**
- Both explicitly noted density guidance is **absent** from it ("doesn't itself cover
  token-economy… deferred to `writing-for-llms`") — i.e. they knew the other skill existed and
  still did not load it.
- **Neither dispatched `llm-doc-writer`.** B: "the `llm-doc-writer` agent type … would be
  appropriate for a larger multi-file audit, but not here." The specialist is never reached.

### Finding 2 — the density rule exists but is split across the door boundary and under-applied

Correction after reading the full skill: `writing-docs` **does** carry an inferability rule
(Rule 4, "Cut what the reader can already infer") and a "One bar, two renderings" section
saying agent docs are "maximum signal-per-token." So it is *not* true that no density rule
exists. Two real problems remain:

- **It defers instead of carrying.** Line 75 / `agent-context.md` say agent density "Defers to
  the `writing-for-llms` skill for token economy." That deferral *is* the second door — the
  exact handoff Finding 1 shows the agent won't walk through. The density bar is half-here,
  half-in-the-skill-nobody-opens.
- **Under-applied, and the specialist never enforces it.** Even with Rule 4 present, Run A
  *added three* true-but-inferable facts (`PORT` `8080`, `WORKER_INTERVAL_MS` `5000`, `lint.js`
  dir-walk). The rule is easy to skip on agent docs, and the one capability built to enforce it
  rigorously — the `llm-doc-writer` agent — is never dispatched (Findings 1).

So the merge's job is not "invent a density rule" — it is **pull the deferred density bar fully
inline** (stop pointing at a second door) and **make specialist dispatch the default for heavy
agent-facing jobs**.

## Why the fix is MERGE, not description surgery

Sharper descriptions ("writing-docs = human; writing-for-llms = agent") would fix routing but:
- re-imposes the "pick the right skill" load the user explicitly rejected (one door is the goal);
- leaves agent docs needing BOTH spine + density, forcing `writing-for-llms` to duplicate the
  spine (it already partially does). One door carries both without duplication.

So the merge is the chosen fix; description surgery is the rejected alternative.

## Implications for GREEN — what the merged `writing-docs` must do

1. **Be the single door that ends the search correctly** — its description absorbs the
   `writing-for-llms` triggers (agent docs, token bloat, context rot) so the first match is also
   the complete one. No second skill to discover.
2. **Pull the deferred density bar fully inline** — stop saying "defers to `writing-for-llms`";
   state the agent-doc density rule (cut verifiable-but-inferable; reader reads the repo on
   demand; spend tokens on what isn't reconstructable) in this skill. Addresses Finding 2.
3. **Make dispatch the default for heavy agent-facing jobs** — route to `llm-doc-writer` so the
   specialist (method + own context) is actually reached, instead of "feels sufficient, proceed."
4. **Not over-correct** — a one-line human-doc edit must stay inline; REFACTOR pressure-tests
   that the router doesn't dispatch a subagent for trivial work.
