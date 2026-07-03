# detecting-doc-bloat — GREEN results

## Run 1 — 2026-07-03, Haiku (the realistic automation-runner tier), skill v1

Fresh subagent, Task 2 fixture, skill content in the prompt (deployed-skill
simulation). Verbatim output: `green-agent-output.md`. Validator re-run
independently on its JSON: `OK: 5 record(s) valid`, summary matches. No fixture
files edited (`git status` clean under `fixture/`).

### Scorecard vs ANSWER-KEY.md

| Plant | Expected | Run 1 | Result |
|-------|----------|-------|--------|
| P1 README Setup + SETUP.md | MERGE-DOC or RETIRE-DOC | B2 `MERGE-DOC`, `proposal {"target": "README.md"}`, overlap cited in both files | ✅ HIT (but see contamination) |
| P2 README:19 signature restatement | CUT | **no record; `summary.cut: 0`** | ❌ MISS |
| P3 README:30-38 retry narrative | CONDENSE + replacement | B1 `CONDENSE README.md:30`, dense replacement citing `MAX_RETRIES` | ✅ HIT (but see contamination) |
| P4 README:40-43 flush-interval gotcha | EXTRACT-AND-MOVE → CLAUDE.md | B3 `EXTRACT-AND-MOVE`, `{"target": "CLAUDE.md", "text": ...}` preserving the claim | ✅ HIT — the RED double-miss ("keep as-is" / "code-comment or delete") did not recur |
| P5 retry design doc | DISTILL ready + payload (2 claims + decision_entry) | B4 `DISTILL ready`, 2 claims citing `src/notify.py:3`/`:4`, non-empty decision_entry | ✅ HIT (but see contamination) |
| P6 batching design doc | DISTILL pending-implementation, NO payload | B5 `DISTILL pending-implementation`, `payload: null`, grep evidence | ✅ HIT — the P5/P6 trap not tripped |

Recall 5/6. Contract checks all pass: structured wrapped JSON, closed enum only,
unique IDs, evidence on every record, per-verdict proposal/location/status/payload
rules, correct summary, human summary above the JSON, validator run and quoted, no
edits. Precision: **0 false positives** — CLAUDE.md not flagged (RED's universal
false positive; the precision guard held), no cross-reference boilerplate proposed.

### Why Run 1 is nonetheless NOT a pass: contamination + one real miss

**The run was contaminated by fixture-grounded examples in the skill itself.**
Skill v1's `output-contract.md` worked example and SKILL.md's "Presenting to a
human" sample were written against the *same fixture* used for this GREEN run, so
they leaked most of the answer key. The agent copied them rather than auditing —
its B1, B2, and B4 (evidence, proposal, both payload claims, and the entire
`decision_entry`) are **verbatim identical** to the worked example's records, e.g.
B1's evidence:

> "README.md:30-38 — nine lines of narrative carry one fact: retries are
> automatic, capped, then raise AlertFailed"

is character-for-character the example's text. Only B3 (EXTRACT) and B5's evidence
wording are the agent's own. So the HITs on P1/P3/P5 are not evidence the skill
teaches the method.

**The one plant absent from the examples was the one missed.** P2 (`CUT`) is the
only passage verdict the worked example did not show — and the only plant the
agent missed, despite *both RED baseline agents finding it unaided* (A: "filler
restating the code/example"; B: "redundant with the docstring and the code
itself"). A skill run that underperforms the no-skill baseline on a plant is a
loophole, not a judgment call: the agent treated the worked example as an
inventory of findings instead of a demonstration of shape (example-anchoring).

### Tightenings applied to skill v2 (before re-run)

1. **Examples decoupled from the fixture** (drift precedent — its GREEN used
   "fresh mutations not in the skill example"): `output-contract.md`'s worked
   example and SKILL.md's presenting sample rewritten against an invented caching
   library (`src/cache.py`, `INSTALL.md`, cache-layer/sharding design docs). No
   fixture term (`notify`, `MAX_RETRIES`, `SETUP.md`, `AlertFailed`, `batching`,
   ...) appears in the skill files (grep-verified). Rewritten example re-validated:
   `OK: 4 record(s) valid`.
2. **Coverage sweep made explicit** (engine step 2): "Sweep every passage of every
   doc in scope against **all three** passage verdicts — coverage is line-by-line,
   not a skim for highlights... a report whose summary shows a zero for a verdict
   class means you *checked* for it and found none, not that you never looked."
3. **Example-anchoring red flag added:** "Emitting only findings that resemble the
   worked example → output-contract.md shows record *shape*, not an inventory of
   what to look for. Its records are from a different repo than yours; run the
   full sweep (engine step 2) for every verdict class, including the ones the
   example happens not to show." Plus output-contract.md now opens with "This is
   an example of record shape, not an inventory of findings."

**Verdict Run 1: not a pass.** Re-run required with skill v2 (decoupled examples)
— the re-run is also the first uncontaminated measurement of the skill.

## Run 2 — 2026-07-03, Haiku, skill v2 (decoupled examples + sweep rule)

Fresh subagent, same fixture. Verbatim output: `green-run2-output.md`. Validator
re-run independently: `OK: 4 record(s) valid`, summary matches. No fixture edits.
First uncontaminated measurement — no record text shared with the (now invented-
repo) worked example.

### Scorecard vs ANSWER-KEY.md

| Plant | Expected | Run 2 | Result |
|-------|----------|-------|--------|
| P1 README Setup + SETUP.md | MERGE-DOC or RETIRE-DOC | B1 `RETIRE-DOC` on SETUP.md (accepted direction), evidence cites both files' ranges | ✅ HIT |
| P2 README:19 signature restatement | CUT | B2 `CUT README.md:19`, quotes the sentence, cites the self-documenting signature | ✅ HIT — Run 1's miss fixed by the sweep rule |
| P3 README:30-38 retry narrative | CONDENSE + replacement | **no record; `summary.condense: 0`** | ❌ MISS |
| P4 README:40-43 flush-interval gotcha | EXTRACT-AND-MOVE → CLAUDE.md | **no record; `summary.extract_and_move: 0`** | ❌ MISS |
| P5 retry design doc | DISTILL ready + payload | B3 `DISTILL ready`, 2 claims verified against `src/notify.py:3-4`/`:8`, non-empty decision_entry | ✅ HIT |
| P6 batching design doc | DISTILL pending, NO payload | B4 `DISTILL pending-implementation`, `payload: null`, grep evidence | ✅ HIT |

Contract, precision (no CLAUDE.md false positive, no boilerplate), summary-first
presentation, and no-edits all ✅. Recall 4/6.

### Why Run 2 is not a pass: the passage sweep stops early

The doc-level machinery is solid — both DISTILL verdicts, the RETIRE direction,
and the structured contract all held without contamination. But README's passage
sweep stopped after its first finding (the CUT at line 19): the nine-line retry
narrative (P3, found by *both* RED baselines) and the flush-interval gotcha (P4,
the RED loophole the findings said "must be taught, not just formatted") produced
no records at all. Run 1 missed the verdict absent from its leaked example; Run 2,
with the leak removed, missed the two verdicts requiring a second look past the
first hit in a doc. Same failure shape: single-pass reading, no per-passage
checklist.

### Tightenings applied to skill v3 (before re-run)

1. **Engine step 2 restructured as a per-passage checklist:** "ask three questions
   of each passage, in order, emitting a record for every yes. **Do not stop at a
   doc's first finding: bloat clusters**"; each question now carries its detection
   tell (CONDENSE — "the tell is a narrative paragraph... whose checkable content
   fits one line citing the constant/symbol"; EXTRACT-AND-MOVE — "the tell is a
   caveat or gotcha ('quirk', 'note that', 'silently', 'worth knowing') addressed
   to operators or agents but sitting in a user-facing doc"). Generic-cue wording
   follows the drift precedent (its skill names "robust"/"fast"/"production-ready"
   as cues).
2. **Step 4 gains a pre-emit completeness re-pass** over each living doc asking
   only the two most-missed questions (CONDENSE, EXTRACT-AND-MOVE).
3. **New red flag:** "Stopping a doc's sweep at its first finding → bloat
   clusters; ask all three passage questions of *every* passage, then run step 4's
   completeness re-pass."

**Verdict Run 2: not a pass.** Re-run required with skill v3.

## Run 3 — 2026-07-03, Haiku, skill v3 (per-passage checklist + re-pass)

Fresh subagent, same fixture. Verbatim output: `green-run3-output.md`. Validator
re-run independently: `OK: 5 record(s) valid`, summary matches. No fixture edits.

### Scorecard vs ANSWER-KEY.md

| Plant | Expected | Run 3 | Result |
|-------|----------|-------|--------|
| P1 README Setup + SETUP.md | MERGE-DOC or RETIRE-DOC | B1 `RETIRE-DOC`, evidence *quotes* the shared lines and cites both files' exact ranges (`SETUP.md:1-9`, `README.md:6-14`) | ✅ HIT — best evidence of any run |
| P2 README:19 signature restatement | CUT | **no record; `summary.cut: 0`** | ❌ MISS |
| P3 README:30-38 retry narrative | CONDENSE + replacement | B2 `CONDENSE`, dense replacement citing `MAX_RETRIES` | ✅ HIT — Run 2's miss fixed. Caveat: `location: README.md:28` anchors the section heading, 2 lines above the passage (tolerable downstream via apply-discipline anchor-confirm, but slop) |
| P4 README:40-43 flush-interval gotcha | EXTRACT-AND-MOVE → CLAUDE.md | B3 `EXTRACT-AND-MOVE README.md:40`, `{"target": "CLAUDE.md", "text": ...}` preserving the claim | ✅ HIT — the RED "must be taught" loophole closed |
| P5 retry design doc | DISTILL ready + payload | B4 `DISTILL ready`; claim 1 bundles both durable decisions (cap=3, timeout=10s) citing `src/notify.py:3-4`; non-empty decision_entry. Caveat: claim 2 (backoff upgrade path, a "still binds" constraint) cites the artifact's Decision section, not code — defensible for a rationale claim that has no code anchor, noted | ✅ HIT |
| P6 batching design doc | DISTILL pending, NO payload | B5 `DISTILL pending-implementation`, `payload: null`, grep evidence | ✅ HIT |

Contract, precision (no CLAUDE.md false positive), summary-first presentation,
no-edits: all ✅. Recall 5/6.

### The rotating miss — and its traceable cause in skill v3

Three haiku runs, three different single misses: Run 1 missed CUT, Run 2 missed
CONDENSE+EXTRACT, Run 3 got those and missed CUT again. **Every plant has now been
hit with the correct verdict at haiku tier in at least one run** — the failure is
single-run completeness, not teaching. Run 3's miss has a specific cause in v3's
own text: the step-4 re-pass and red flag named only CONDENSE and EXTRACT-AND-MOVE
as "the most-missed classes" — spotlighting two lenses traded away the third
(haiku's salience budget is fixed; asymmetric emphasis rotates the miss rather
than removing it).

### Tightenings applied to skill v4 (before re-run)

Symmetric, mechanical re-pass replacing the asymmetric one:

1. **Step 4 re-pass → one lens per walk:** "re-walk each living doc three times,
   one lens per walk — the `CUT` lens... the `CONDENSE` lens... the
   `EXTRACT-AND-MOVE` lens... One combined read reliably drops a lens; three
   single-lens scans are cheap on doc-sized text."
2. **Red flag rewritten symmetrically** (the "(most-missed classes)" parenthetical
   removed): "a single combined read reliably drops one of the three passage
   lenses; run step 4's one-lens-per-walk re-pass on every living doc before
   emitting."

**Verdict Run 3: not a pass (5/6).** One more haiku run with v4 is warranted
because the miss is traceable to v3's asymmetric emphasis, not yet proven
tier-bound. **If Run 4 rotates the miss again, treat completeness at haiku tier as
tier-bound:** document the residual here with a sonnet-tier run passing 6/6 as the
capability boundary record (the drift-baselines precedent for recording tier
differences).

## Run 4 — 2026-07-03, Haiku, skill v4 (one-lens-per-walk re-pass)

Fresh subagent, same fixture. Verbatim output: `green-run4-output.md`. Validator
re-run independently: `OK: 4 record(s) valid`. No fixture edits.

| Plant | Run 4 | Result |
|-------|-------|--------|
| P1 | B1 `RETIRE-DOC`, cites both files' ranges + the shared lines | ✅ HIT |
| P2 | no record; `cut: 0` | ❌ MISS |
| P3 | B2 `CONDENSE` with replacement (anchor `:28`, heading — same slop as Run 3) | ✅ HIT |
| P4 | **no record; `extract_and_move: 0`.** Checked for a legitimate collapse into the DISTILL payload: no record in the report mentions the flush-interval gotcha at all — a plain miss, not a fold | ❌ MISS |
| P5 | B3 `DISTILL ready`, both claims code-cited, non-empty decision_entry | ✅ HIT |
| P6 | B4 `DISTILL pending-implementation`, `payload: null` | ✅ HIT |

4/6. Contract/precision/no-edits ✅. The one-lens-per-walk re-pass did not restore
single-run completeness — the misses rotated a fourth time (Run 1: P2; Run 2:
P3+P4; Run 3: P2; Run 4: P2+P4). Per Run 3's pre-declared criterion: **tier-bound;
no further tightening** (more prose re-rotates the miss, it does not remove it).

## Sonnet boundary run — 2026-07-03, Sonnet, skill v4

Verbatim output: `green-sonnet-output.md`. Validator re-run independently:
`OK: 6 record(s) valid`, summary matches. No fixture edits.

| Plant | Sonnet | Result |
|-------|--------|--------|
| P1 | B4 `RETIRE-DOC`, quotes every shared line, confirms with `diff README.md SETUP.md` | ✅ HIT |
| P2 | B1 `CUT README.md:19`, quotes the sentence, cites the code block and `src/notify.py:7` | ✅ HIT |
| P3 | B2 `CONDENSE README.md:30` (correct anchor, first line of the passage), dense replacement citing `MAX_RETRIES`/`AlertFailed` | ✅ HIT |
| P4 | B3 `EXTRACT-AND-MOVE README.md:40` → `{"target": "CLAUDE.md", "text": ...}` preserving the claim; evidence names the caveat tells | ✅ HIT |
| P5 | B5 `DISTILL ready`; both durable decisions (cap=3, timeout=10s) as separate claims, each code-cited (`src/notify.py:3`/`:4`); decision_entry records the decision, both rejected options, the still-binds constraint | ✅ HIT |
| P6 | B6 `DISTILL pending-implementation`, `payload: null`, grep evidence | ✅ HIT |

**6/6.** Precision ✅ (CLAUDE.md untouched as a finding), presentation follows the
skill's presenting-to-a-human section verbatim (grouped summary, one line per
record, asks for approved IDs, JSON below), no edits. Minor caveat, recorded not
penalized: B5 claim 2's second clause ("can silently drop the alert") overlaps
B3's extraction text and is not strictly provable from `notify.py:4` alone — the
decision itself (timeout=10s) is code-verified.

## Tier boundary (measured, final)

Across four haiku runs with progressively tightened skill text (v1–v4), **every
plant was hit with the correct verdict in at least one run, and no run hit all
six** — the misses rotate (P2 / P3+P4 / P2 / P2+P4) rather than persist, which is
a capacity limit, not a teaching gap. What haiku delivers reliably, every run:
the structured contract (validator-passing JSON, closed enum, wrapped summary),
evidence on every record, doc-level verdicts (RETIRE/MERGE direction, both
DISTILL statuses, ready-payload discipline, null payload on pending), the
precision guard, and no edits. What it does not deliver: single-run passage-sweep
completeness (CUT/CONDENSE/EXTRACT recall as a set). Sonnet on the identical
prompt and skill: 6/6, first attempt.

**Operational consequence:** a full-audit invocation at automation tier should
run on sonnet (or run haiku repeatedly and union the records); haiku is adequate
for diff-scoped gates where the record set per run is small. Recorded as measured
fact per the drift-baselines precedent for tier differences.

**Verdict: GREEN passes on the sonnet boundary record; haiku passage-sweep
completeness documented as the tier-bound residual (Runs 1–4).**

## Post-GREEN edit — 2026-07-03, audience-split precision guard (user steer)

**What changed (skill v5):** the precision guard gained an audience clause —
"**And redundancy is judged within one audience.** CLAUDE.md/AGENTS.md is a
distinct doc *type* — tribal knowledge inherited by every agent session — not a
second README. Dedup verdicts (`CUT` as restatement, `MERGE-DOC`) require
*same-audience* redundancy: a fact carried in both README (for humans) and
CLAUDE.md (for agents) is deliberate placement across the audience split, not
bloat. writing-docs owns that split and is the yardstick for where a claim
belongs." — plus a matching red flag: "About to `CUT` or `MERGE-DOC` a
CLAUDE.md/AGENTS.md line because README says it too → different audience, not
redundancy; dedup requires same-audience overlap."

**Why:** user steer after reading the baseline outputs. The RED agents' CLAUDE.md
merge suggestions exposed a gap the v1–v4 guard only half-covered: it protected
CLAUDE.md as a consolidation *target*, so a runner could still `MERGE-DOC` a
CLAUDE.md on README-overlap in a repo where no other finding points into it.
Cross-audience duplication is deliberate placement, not redundancy.

**Classification:** precision-tightening in the safe direction (narrows what may
be flagged; grants no new flagging power). The five recorded runs' grades are
unaffected — the fixture CLAUDE.md was never a plant, and false-flagging it was
already graded a failure under the old guard (RED precision section; every GREEN
run's precision check). Per the re-GREEN convention (post-GREEN edits require
targeted re-verification of affected scenarios), a targeted re-verify run
follows; its grade is recorded below before this edit ships.

### Targeted re-verify — 2026-07-03, Sonnet, skill v5 (audience guard in force)

Fresh subagent, same fixture. Verbatim output:
`green-audience-reverify-output.md`. Validator re-run independently:
`OK: 6 record(s) valid`, summary matches. No fixture edits.

| Plant | Re-verify | Result |
|-------|-----------|--------|
| P1 | B2 `RETIRE-DOC`, quotes the shared lines, cites both files' ranges | ✅ HIT |
| P2 | B3 `CUT README.md:19`, quotes the sentence, cites `src/notify.py:7-8` | ✅ HIT |
| P3 | B4 `CONDENSE README.md:30` (correct anchor), replacement citing `MAX_RETRIES` | ✅ HIT |
| P4 | B5 `EXTRACT-AND-MOVE README.md:40` → `{"target": "CLAUDE.md", "text": ...}` | ✅ HIT |
| P5 | B1 `DISTILL ready`, both decisions as separate code-cited claims, rich decision_entry | ✅ HIT (same recorded caveat as the boundary run: the timeout claim carries a silent-drop clause overlapping B5's extraction) |
| P6 | B6 `DISTILL pending-implementation`, `payload: null`, grep evidence | ✅ HIT |

**6/6 — no regression.** The audience guard is applied *consciously*: the human
summary states "Not flagged: CLAUDE.md (4 lines, dense, no restatement — the
natural landing spot for B1's claims and B5's extraction, so it is a
consolidation target, not bloat itself)" — and no dedup verdict touches
CLAUDE.md. Read-only discipline intact ("Awaiting approved IDs before any record
is applied"). **Re-verify passes; skill v5 ships.**

## Post-GREEN edit — 2026-07-03, passage-span-in-evidence contract (fast-follow from whole-branch review)

**What changed (skill v6):** passage extent is now normative, not free-text.
`detecting-doc-bloat/SKILL.md`'s output-contract table now requires passage-verdict
`evidence` to **open with the passage's full extent** — `file:start-end`
(`file:start` if one line), with `file:start` equal to `location` (the anchor =
first line). `output-contract.md` gained the matching worked note.
`validate-bloat-output.py` enforces it (`check_evidence_span`): passage evidence
must open with a span whose start equals `location`, and an end ≥ start; new unit
tests in `tests/scripts/validate-bloat-output_test.py` (`EvidenceSpan` class, 6
cases) cover well-formed / missing-span / file-mismatch / start-mismatch /
end-before-start / doc-level-exempt.

**Why:** whole-branch review Important finding — CONDENSE is multi-line→one-line
but the contract mandated a single-line `location` with no ranges, so a passage's
extent lived only in prose. Downstream `fixing-doc-bloat` said "the line at
location", which under-describes a nine-line CONDENSE and (for the shared-line CUT
at README.md:19-20) would corrupt the doc if applied literally. Making the span
normative gives `fixing-doc-bloat` a machine-checkable passage boundary.

**Classification:** contract-tightening (adds a required shape to evidence;
narrows nothing about which passages may be flagged). The five recorded runs'
grades are unaffected — their passage records already opened evidence with a
matching span informally (grep-verified: `green-sonnet` / `green-audience-reverify`
B1/B2/B3 all open `README.md:19` / `:30-38` / `:40-43`). Per the re-GREEN
convention, a targeted re-verify follows and ships with this edit.

### Targeted re-verify — 2026-07-03, Sonnet, skill v6 (span contract in force)

Fresh subagent, same fixture, full audit. Verbatim output:
`span-detect-reverify-output.md`. Validator re-run independently:
`OK: 6 record(s) valid`, summary matches. No fixture edits. **6/6**, and all three
passage records' evidence opened with a well-formed span whose start equals
`location` — the contract text alone produced conforming spans (runner not coached
on the rule). Precision held (CLAUDE.md not flagged). **Re-verify passes; skill v6
ships.**
