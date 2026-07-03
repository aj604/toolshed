# GREEN — evidence brevity bar (`detecting-doc-drift`)

**Date:** 2026-07-03
**Setup:** fresh general-purpose subagent, the identical pressure-loaded prompt from the RED
run (stale retry-count claim; decoy history: commit `abc1234` also touched CHANGELOG.md, and
an earlier PR #41 / commit `9f21e07` had fixed this same doc line once before), run against
the edited SKILL.md and output-contract.md carrying the one-line pointer+fact evidence bar.

## The emitted record (verbatim)

```json
{
  "claim": "The worker retries failed jobs 3 times",
  "location": "docs/README.md:12",
  "kind": "value",
  "tier": 2,
  "verdict": "STALE",
  "evidence": "services/worker/retry.js:8 — `const MAX_RETRIES = 5;`",
  "fix": "The worker retries failed jobs 5 times"
}
```

The runner explicitly noted it kept PR #41 and the earlier-fix history out of `evidence`
"per the no-narrative rule" — the bar was read and applied, not accidentally satisfied.

## Evaluation against the Step 5 expectation

Expected: `evidence` is a single line naming `services/worker/retry.js:8` and
`MAX_RETRIES = 5`, with no mention of PR #41, commit 9f21e07, or CHANGELOG.

- One line: **yes** — pointer (`services/worker/retry.js:8`) + fact (`const MAX_RETRIES = 5;`),
  nothing else.
- Names `services/worker/retry.js:8`: **yes**.
- Names `MAX_RETRIES = 5`: **yes**.
- No PR #41: **yes**.
- No commit 9f21e07: **yes**.
- No CHANGELOG: **yes** — and the `abc1234` / "also updating CHANGELOG.md" parenthetical the
  RED subagent smuggled in is gone too.
- Verdict/kind/tier/`fix` unchanged from RED and still correct — the bar trimmed evidence
  without degrading classification.

**PASS.** The identical prompt that produced history-laden evidence under the old text
produces pointer+fact evidence under the new text.
