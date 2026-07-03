# Span detect re-verify — passage-span-in-evidence contract (2026-07-03)

Fresh Sonnet subagent, bloat-red fixture, detecting-doc-bloat SKILL.md +
output-contract.md as edited for the span contract (passage-verdict evidence
must open with `file:start-end` anchored at `location`; validator-enforced).
Full-audit invocation. Read-only (no fixture edits).

## Result: 6/6, all spans well-formed

| Plant | Record | Location | Evidence opens | Anchor match |
|-------|--------|----------|----------------|--------------|
| P2 CUT | B1 | README.md:19 | `README.md:19` (one-line span) | ✅ =location |
| P3 CONDENSE | B2 | README.md:30 | `README.md:30-38` | ✅ start=location |
| P4 EXTRACT | B3 | README.md:40 | `README.md:40-43` | ✅ start=location |
| P1 MERGE-DOC | B4 | null | (doc-level, no span) | n/a |
| P5 DISTILL ready | B5 | null | (doc-level) | n/a |
| P6 DISTILL pending | B6 | null | (doc-level) | n/a |

Validator (re-run independently on the emitted JSON):

```
OK: 6 record(s) valid
summary: {"cut": 1, "condense": 1, "extract_and_move": 1, "retire_doc": 0, "merge_doc": 1, "distill": 2}
```

Every passage record's evidence opened with the passage's full extent whose
start equals `location`; the validator's new span check passed on all three
without the runner being coached on the rule — the contract text alone produced
conforming spans. Precision held (CLAUDE.md audited, not flagged; it is the B3/B5
target). Recall 6/6 at Sonnet tier, matching the pre-span boundary run.

**Re-verify passes for detecting-doc-bloat under the span contract.**
