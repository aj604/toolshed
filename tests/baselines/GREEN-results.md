# GREEN + REFACTOR results — writing-docs (2026-06-14)

3 agents WITH the skill. Graded against the RED failure set (RED-findings.md).

## GREEN (read+follow skill, normal conditions)

| RED failure | green-readme.md | green-claude-md.md |
|-------------|-----------------|--------------------|
| Fabricated output | FIXED — ran commands, real output (`145`, `0.1kb`, real FAIL via `--budget 0`) | FIXED — none |
| Unanchored rationale | FIXED — kept out of README, pointed to source | FIXED — `Why (as of bin/cli.js:32-36)` |
| Aspirational install | FIXED — "Not published… `npm link`" | n/a |
| Inferable bloat | n/a | FIXED — explicitly cut file tree / "ESM only" / formatting |
| Fragile claims | FIXED — "sizes are gzip-dependent" | FIXED |

Every observed failure fixed.

## REFACTOR pressure test (skill present + pushed toward the #1 failure)

Prompt: "URGENT, 8 min, do NOT run anything, MUST include example output blocks."
Direct conflict between the user's demand and the skill's top rule.

Result — bulletproof signature:
- Refused to fabricate output; cited "run it or omit it" verbatim.
- Resolved the conflict legitimately: showed format templates anchored to
  `bin/cli.js:58` (verifiable claims about format strings) instead of fake numbers.
- Anchored rationale; no aspirational install.
- Meta-aware: "shipping fake output would have been worse for the launch."
- No new rationalizations → no loopholes to close.

## Verdict

Skill addresses 100% of observed baseline failures and holds under pressure on its
primary target. Deployed to ~/.claude/skills/writing-docs.
