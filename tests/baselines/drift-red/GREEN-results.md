# detecting-doc-drift — GREEN results

**Date:** 2026-06-14. Re-ran the failing scenarios on **Haiku** (the realistic automation
runner that failed RED) WITH the skill, invoked programmatically.

## Full audit (green-variant-CLAUDE.md, fresh mutations not in the skill example)

| Check | Result |
|-------|--------|
| Structured JSON output (the core RED failure) | ✅ FIXED — clean records, all fields |
| Recall on 6 planted STALE | ✅ 6/6 (`make check`, exit `2`, Node `18`, `/health 204`, `slugify`, `scripts/seed.js`) |
| `make check`→`make lint` grep (Haiku's RED miss) | ✅ FIXED — grepped Makefile, no `check:`, fix emitted |
| Evidence on every record incl. VERIFIED | ✅ |
| Per-claim tier assigned | ✅ |
| UNVERIFIABLE extraction ("robust and production-ready") | ❌ MISS — not extracted; `unverifiable: 0` |
| Precision | ⚠️ 2 false-positives: flagged the exit-3 `file:line` anchors STALE for pointing at the guard line (`server.js:12`) rather than the exact `exit()` line — over-strict |

## Diff-scoped (worker schema 3→4 / exit 4→7, 6 green docs)

| Check | Result |
|-------|--------|
| Structured JSON output | ✅ |
| Completeness — all affected passages | ✅ 4/4 files incl. the verbatim `(schema 3)` snippet in `agent1/README.md:21` |
| Unaffected docs left alone | ✅ both READMEs omitted |
| Evidence on each | ✅ |
| `kind` uses the declared enum | ❌ invented kinds (`schema_version_mismatch`, `command_output_example`) |

## Verdict: GREEN passes on the core contract; 3 loopholes for REFACTOR

The defining RED failure — no machine-actionable output — is fixed in both modes, and the
Haiku command-grep gap is closed. Remaining for REFACTOR:

1. **UNVERIFIABLE not extracted.** Haiku skips vague quality-claims entirely. Strengthen the
   extract step to actively scan for them and emit UNVERIFIABLE.
2. **`kind` enum not enforced.** Declare kind as a closed set; records must use it verbatim
   so automation can switch on it.
3. **Anchor over-flagging.** Distinguish "value at the cited line is wrong" (STALE) from "an
   anchor points at the relevant construct but not the exact line" (VERIFIED). Only flag an
   anchor when it points to a wrong/nonexistent location.

## REFACTOR (Haiku, two iterations)

**Iter 1** (extract step + anchor rule + kind enum added): UNVERIFIABLE ✅ now extracted;
`kind` enum ✅ respected; anchor over-flagging ❌ persisted — Haiku sidestepped the rule by
*decomposing* each gotcha into a separate `path` claim ("the exit is at line 14") and grading
line-number precision (3 false STALEs).

**Iter 2** (strengthened: "the anchor is metadata on a claim, never its own claim; never
emit a STALE whose `fix` only changes a line number"): all three loopholes closed.

| Loophole | Iter 2 result |
|----------|---------------|
| No machine-actionable output | ✅ clean structured JSON, both modes |
| UNVERIFIABLE skipped | ✅ "robust and production-ready" → UNVERIFIABLE |
| Invented `kind` values | ✅ only the six enum values |
| Anchor / line-number over-flagging | ✅ exit-3 gotcha is one VERIFIED record; no line-number-only fixes |
| Recall on real drift | ✅ 6/6 |
| False positives | ✅ 0 |

Residual (cosmetic, not fixed): the cheap model miscounted its own `summary` line (`stale:5`
vs 6 actual records). The parseable records — the contract's source of truth — are all
correct; automation counts records, not the summary. Not worth a further iteration.

**Verdict: GREEN+REFACTOR pass.** Skill bulletproofed against all observed loopholes on the
realistic automation runner (Haiku).
