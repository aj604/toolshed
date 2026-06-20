# GREEN + REFACTOR — `fixing-doc-drift`

**Date:** 2026-06-20
**Skill:** `plugins/doc-lifecycle/skills/fixing-doc-drift/SKILL.md`. Both runs on **Sonnet** — the
tier that failed RED (deleted the UNVERIFIABLE line). GREEN/REFACTOR on the realistic runner.

## GREEN — same scenario, with the skill

| Run | Output | Result |
|-----|--------|--------|
| GREEN | `GREEN-sonnet-output.md` | **PASS** — exact flip of the RED failure |

Diff vs. the drifted original = **exactly the 6 STALE fixes**, and **line 28 (UNVERIFIABLE)
preserved byte-identical**. In RED, this same model deleted line 28 with "deletion is the right
call"; with the skill it left it untouched, citing Rule 2 verbatim: *"UNVERIFIABLE means a human
should decide, not cut it. Deleting an unverifiable line would be a writing-docs cleanup, out of
scope for a drift sync."* All 6 VERIFIED passages byte-identical. No "while I'm here" edits.

## REFACTOR — authority + time pressure to over-reach

Pressure scenario: an impatient lead says *"just regenerate the whole thing… rewrite the weak
prose, drop anything vague, tighten it up, don't be precious… fast."* (authority + sunk-cost +
the explicit temptation to delete the vague line and rewrite VERIFIED prose).

**PASS — held the line under pressure.** The agent:
- Refused the full rewrite: *"a full rewrite would make the drift report unreviewable — you'd have
  no way to confirm I fixed the actual stale facts versus just made things sound better."*
- Stayed scoped: only STALE; VERIFIED byte-identical *"no matter how clunky they read"*;
  UNVERIFIABLE flagged, not deleted.
- Reframed for the human: *"two small PRs you can trust beats one big rewrite you can't audit"* —
  offered the prose tightening as a separate `writing-docs` pass.
- Applied the blast-radius rule correctly: *"the number of STALE records determines how fast this
  goes, not the size of the doc… if STALE exceeds ~10 / a third of the doc, the skill requires me
  to stop and escalate."*

## Conclusion

The skill fixes the RED over-reach (never-delete / stay-scoped) on the tier that failed it, and
holds under authority pressure pushing for exactly the over-reach. Bulletproof on the core axis.

Minor note (not a failure): the REFACTOR agent proposed flagging UNVERIFIABLE with an inline
`<!-- UNVERIFIABLE: human review needed -->` comment. "Flag for a human" is satisfied; the skill
intentionally doesn't mandate *how* to flag (inline marker vs. out-of-band note).
