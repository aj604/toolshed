# RED — evidence brevity bar (`detecting-doc-drift`)

**Date:** 2026-07-03
**Skill under test:** `detecting-doc-drift`'s `evidence` field — whether the current skill
text caps it at one line (pointer + fact) or lets it accrete narrative. The writable axis is
**evidence discipline**, not verdict correctness (both runs below classify correctly).

## The primary RED record: production nightly dogfood PR (2026-07-03, range bd91cb6..3983574)

The nightly doc-sync PR — the real automation this skill's output feeds — emitted this STALE
record's `evidence` under the current skill text (verbatim from the PR body, `CLAUDE.md:9`):

> **evidence:** Commit 8c439c6 (in this range) added .github/workflows/release.yml, a runnable
> GitHub Actions workflow (bash run: steps at lines 20, 25, 43) that lives under .github/ but
> is NOT part of the doc-sync install. ls .github/workflows/ returns both doc-sync.yml and
> release.yml, so the exhaustive 'only other runnable code' enumeration now omits a runnable
> file. PR docs: sync with main (2026-07-02) #5 (0b72777) had fixed this line to add the
> doc-sync install, but release.yml landed afterward and re-staled it.

Five sentences. It carries: restated `ls` output, prior-PR history ("#5 had fixed this
line... re-staled it"), and reasoning narrative — none of which the record needs, since the
verdict already says STALE and the `fix` field already says what the line should become.
Pointer + fact would be one line: `.github/workflows/release.yml (added 8c439c6) is runnable
but absent from the list`. This is the primary record — it is production evidence, not a
synthetic pressure test, and the rule lands on its strength alone.

## The subagent run: pressure-loaded prompt, current skill text

A fresh subagent (no changes to the skill yet) was given a scenario engineered to tempt
narrative: a stale retry-count claim whose underlying commit (`abc1234`) also touched
CHANGELOG.md, plus a decoy fact (an earlier PR #41 had already fixed this same line once
before, so it drifted twice). The subagent read the current SKILL.md and output-contract.md,
then emitted this record verbatim:

```json
{"claim": "the worker retries failed jobs 3 times", "location": "docs/README.md:12", "kind": "value", "tier": 2, "verdict": "STALE", "evidence": "services/worker/retry.js:8 — `const MAX_RETRIES = 5;` (changed in commit abc1234, also updating CHANGELOG.md)", "fix": "the worker retries failed jobs 5 times"}
```

**Verdict, tier, kind, and `fix` are all correct.** The `evidence` field is one line by line
count — but it still smuggles in history the new bar forbids: "(changed in commit abc1234,
also updating CHANGELOG.md)" is exactly the "how the drift arose" narrative that doesn't
belong, even though it didn't take the bait on the PR #41 detail. Line count alone is not
the same as pointer-plus-fact; the parenthetical proves the current text has no rule against
appending commit/history trivia to an otherwise-terse line.

## Interpretation

The two records fail differently but for the same underlying reason: **nothing in the
current skill text says evidence excludes history.** The rules paragraph (SKILL.md ~line 80)
requires evidence to exist and requires it to prove the verdict, but never says what evidence
must *exclude*. The production PR shows the unbounded failure mode (five sentences); the
subagent run shows that even a terse-looking single line still leaks commit/changelog
history when nothing forbids it. Either failure, pasted into a PR body by the nightly
automation this skill drives, bloats the review surface with restated command output and
git-log narrative a reviewer has to read past to find the actual fact.

## Implication for GREEN

Add a one-line evidence bar — "pointer + fact," explicitly excluding history (prior PRs, how
the drift arose) and restated command output — to both SKILL.md's rules paragraph and its
red-flags list, and to output-contract.md's intro paragraph. GREEN re-runs the identical
pressure-loaded prompt against the edited skill text and checks that `evidence` names only
`services/worker/retry.js:8` and `MAX_RETRIES = 5`, with no mention of PR #41, commit
9f21e07, commit abc1234, or CHANGELOG.
