# Building skills test-first — the RED → GREEN → REFACTOR discipline this suite uses

> As of 2026-08-05 (doc-lifecycle 0.46.9; `tests/baselines/`, `plugins/doc-lifecycle/skills/`)

**You should already have:** read [the principles](principles.md) and CLAUDE.md's
Conventions section, which names the top-level convention this guide details — skills
here are built test-first via `superpowers:writing-skills` (RED → GREEN → REFACTOR),
with every milestone's baseline retained under `tests/baselines/`. This guide is for
adding or reworking a skill in this plugin, not for using the shipped ones.

## Write to the failure you observed, not the one you predicted

Every skill in this suite started from a RED baseline — real agents, without the skill,
against a real fixture — and the skill text closed exactly what that run got wrong,
never a guessed failure mode. `writing-docs` was written to fabricated "illustrative"
example output, timeless unanchored rationale, aspirational install steps, and
inferable-content bloat; `bootstrapping-docs` was written to completeness-chasing (full
API refs, helper-signature catalogs, directory trees) with no scope or stop signal —
observed even though every gotcha in the RED run was correctly found. The lesson behind
both: a capable model already gets the *facts* right on a small repo without help; what
it lacks naturally is the *discipline* a skill supplies, and that discipline only shows
up in a real RED run, never in a design conversation about what agents "probably" do
wrong.

## Size the fixture to the failure you're hunting

A fixture that's too small can hide the exact failure a skill exists to catch:
`tests/fixtures/sample-repo` (small) was enough to surface `writing-docs`'s failures but
too small to make `bootstrapping-docs`'s completeness-chasing show — there's nothing to
over-catalog in a two-file repo. `tests/fixtures/taskflow`, a multi-component fixture,
was built to give that failure somewhere to happen; `detecting-doc-drift`'s own RED
baseline later reused both.

## GREEN/REFACTOR: re-run RED, then push directly at the rule

The pattern that held for both skills above (`tests/baselines/GREEN-results.md`,
`tests/baselines/bootstrap-green/GREEN-results.md`): re-run the exact RED scenario with
the skill present and confirm the observed failure is fixed, then run one REFACTOR
pressure test that pushes the agent directly at the skill's core rule — an urgent
framing plus a demand that directly conflicts with it. The acceptance bar is a
**bulletproof signature**, not merely "the pressure test passed": the agent refuses the
conflicting demand, cites the skill's rule (by name or near-verbatim), and names the
specific temptation it declined, rather than silently complying or silently ignoring the
prompt. A GREEN that can't produce that signature under direct pressure isn't done, no
matter what the unpressured run showed.

**What a GREEN does not prove: that the skill triggers.** Every GREEN run in this suite
handed agents the SKILL.md file directly, so description-based routing — the model
picking the skill on its own from the description alone — has never been exercised.
A GREEN shows the text teaches the rule once the agent is reading it; it says nothing
about whether the agent would have found it. Treat triggering as a separate check
against the installed plugin, not something a GREEN covers
(`tests/baselines/growing-green/GREEN-results.md` records the same caveat).

## A RED that doesn't fail is itself a finding

Two skills in this suite were reshaped by what a RED run *didn't* find — read that as a
design decision, not an unfinished skill:

- **`detecting-doc-drift`** was originally scoped to teach agents to *find* drift
  better. RED refuted that premise: twelve baseline agents, across both audit modes and
  two model tiers, already detected planted drift well — capable agents are naturally
  strong *verifiers*, unlike the generation failures `writing-docs`/`bootstrapping-docs`
  targeted. The real, universal gap was that every agent answered in free-form prose, not
  a result an automation could parse and act on. So the skill is deliberately a
  **procedural/contract skill**: it declares a deterministic
  extract → verify(tiered) → classify → emit-structured-records shape, not a
  "how to spot drift better" lesson — a different kind of skill than the rest, on
  purpose.
- **The LLM-doc-writing work** (`llm-doc-writer` / what later merged into `writing-docs`)
  was first graded on catching planted factual errors, and that axis turned out
  tier-dependent and unfair to a fixed model — a stronger model wins on recall alone,
  which teaches nothing about the skill text. The axis that was actually tier-independent
  and written by the skill: fabrication and laundering of unverified specifics. The same
  Sonnet model, same prompt: without the rule it laundered a false `npm test` command and
  fabricated an API; with the rule, it did neither. That's the RED/GREEN pair that
  shipped, not a recall benchmark.

## Full-audit automation has a measured model-tier floor

`detecting-doc-bloat`'s full-audit completeness has a measured tier boundary, not a
documented one: across four Haiku runs against the bloat fixture (with progressively
tightened skill text), no single run caught all six planted findings — each run missed
one or two, and which finding it missed rotated (P2; P3+P4; P2; P2+P4) rather than
repeating, so it reads as a capacity limit rather than a teaching gap a better skill
draft would close. Every planted finding was still caught by at least one of the four
runs. A Sonnet run against the identical fixture and skill text hit 6/6 on the first
attempt. Full detail: `tests/baselines/bloat-red/GREEN-results.md` ("Tier boundary
(measured, final)"). `doc-bloat-audit.yml` pins no model today, so a full-audit
automation invocation that lands on Haiku is choosing this gap, not a neutral default —
run it on Sonnet, or run Haiku repeatedly and union the resulting records.

## Next

Retain every RED/GREEN/REFACTOR record under `tests/baselines/`, one directory per
milestone — several of the findings above are provable only there. Once a new skill's
GREEN holds, wire it in per [the principles](principles.md) and CLAUDE.md's own skill
conventions.
