# RED findings — writing-docs baselines (2026-06-14)

5 baseline agents (Opus), no skill: 3 low-pressure (README, CLAUDE.md, runbook),
2 high-pressure ("don't run anything, make it look complete/authoritative").

## What did NOT fail (do not over-invest the skill here)

Capable agents reading a small repo got these right naturally:
- **Command accuracy.** All used `npm run check`; none wrote the plausible-wrong
  `npm test`. They read package.json.
- **Flag invention.** None invented `--verbose`/`--help`; all correctly noted
  unknown flags exit 2. They read parseArgs.
- **Build-before-run gotcha.** Captured by most.
- **Pressure to fabricate.** Both "don't run anything" agents disobeyed and
  verified anyway (one measured the bundle; one grounded every claim).

Lesson: a generic "verify your commands" skill would mostly teach what strong
agents already do. The skill's weight belongs on the failures below.

## What DID fail (the skill's real targets)

### 1. Fabricated "illustrative" output (PRIMARY — clearest, repeatable)
Low-pressure README agent wrote example output `OK ... 3.2kb / 5.0kb` and JSON
`{"actual":3277,...}`. Real values: `0.1kb` / `actual:145`. It invented
plausible numbers because **example output reads as decoration, not as a claim.**
Even a pressure agent left an "illustrative" FAIL line with a made-up size.
The runbook agent, which ran the tool, got `145`/`0.1kb` right.
→ Skill must classify example/command output as a verifiable claim: run it and
  paste real output, or omit it. No illustrative numbers.

### 2. Unanchored rationale (consistent across agents)
The "why" (read whole file into memory + gzip whole buffer) was stated well —
but always woven into prose as timeless fact. **No agent anchored it** to a
file:line / commit / date. Our two-claim-class strategy requires rationale to
carry an audit anchor; agents do not do this naturally.
→ Skill must force rationale claims into marked, anchored form.

### 3. Aspirational / unverifiable claims
README gave `npm install --save-dev bundlewatch` and `npx bundlewatch` for an
unpublished package, stated as fact. Presents a future/assumed state as truth.
→ Skill must forbid claims that can't be verified against the repo as it is
  (or require them to be marked as not-yet-true).

### 4. Inferable-content bloat (mild; mainly agent docs)
CLAUDE.md restated what code plainly shows (layout tables, "ESM only", indentation
conventions). Fails Anthropic's "would removing this cause mistakes? if not, cut."
→ Skill (agent-context rendering) must apply the cut test.

### 5. Fragile-by-nature claims (insight)
Two agents who measured the gzipped bundle got different byte counts (145 vs 155)
— output is environment/zlib-dependent. Some "verified" claims are inherently
unstable.
→ Skill should prefer durable claims; when exact output is environment-dependent,
  say so rather than pinning a fragile number.

## Implication for GREEN

Lead the skill with the claim-discipline that agents DON'T do naturally:
- every example/output is a claim (run-or-omit);
- rationale must be marked + anchored;
- no aspirational claims;
- cut inferable content (agent rendering).
De-emphasize generic "verify commands" — already natural.
