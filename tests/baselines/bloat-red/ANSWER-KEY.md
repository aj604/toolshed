# bloat-red answer key (grading reference — NOT shown to baseline agents)

Fixture: `tests/baselines/bloat-red/fixture/` (a self-contained fake repo, treated as
the repo under test — not `tests/fixtures/`). Six planted items, one per verdict class
in the contract (`docs/plans/2026-07-03-doc-bloat-and-distillation-plan.md`, "The
bloat-report contract"): `CUT`, `CONDENSE`, `EXTRACT-AND-MOVE`, `MERGE-DOC`/`RETIRE-DOC`
(either accepted — see grading note), `DISTILL` ready, `DISTILL` pending-implementation.

A bloat audit is graded on:
- **Recall** — of the 6 planted items, how many surfaced with the right verdict class?
- **Evidence discipline** — is each finding backed by a concrete file:line / quoted
  passage, or asserted ("this section feels redundant") without showing it?
- **Verdict correctness** — right verdict, not just "this is bloat"?
- **Proposal quality** — does `CONDENSE` supply real replacement text? Does
  `EXTRACT-AND-MOVE` name the real target doc and real text to land?
- **DISTILL discrimination** — ready vs. pending-implementation kept distinct, and no
  payload manufactured for the pending one?
- **Format** — structured/parseable output (something resembling the record shape:
  id/doc/location/verdict/evidence/proposal), not free-form prose?
- **No unsolicited edits** — the baseline prompt says "do not edit any files"; did the
  agent report-only?

## Planted items — 6

| ID | Location | Expected verdict | Expected proposal/payload gist |
|----|----------|-------------------|---------------------------------|
| P1 | `fixture/README.md:6-14` (`## Setup` section) paired with `fixture/SETUP.md:1-9` | `MERGE-DOC` (target `SETUP.md`→`README.md` or vice versa) **or** `RETIRE-DOC` on `SETUP.md` — accept either | Content overlaps near-verbatim: both say "Clone the repo, then install the package in editable mode" + the same `pip install -e .` block + the same "No environment variables are required to run the test suite locally" line. `MERGE-DOC` proposal: `{"target": "README.md"}` (or `"SETUP.md"`, whichever survives). No standalone reason for two docs to carry the same setup instructions. |
| P2 | `fixture/README.md:19-20` ("The `send_alert` function takes a channel and a message and delivers the message to that channel.") | `CUT` | Restates what `fixture/src/notify.py:7` (`def send_alert(channel, msg):`) already shows on its face — the signature is self-evident from the code one line away in the same doc's usage example. No new information. |
| P3 | `fixture/README.md:30-38` ("Delivery failures are not always permanent…" through "…raises `AlertFailed` so the caller knows delivery ultimately did not succeed.") | `CONDENSE` | Nine lines / four sentences of narrative to convey one fact: retries happen automatically, capped, then raises. Dense replacement is one line citing the constant, e.g.: "Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed` (`src/notify.py:3`)." |
| P4 | `fixture/README.md:40-43` ("One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S` exceeds the receiving channel's flush interval…") | `EXTRACT-AND-MOVE` (target `fixture/CLAUDE.md`) | This is an operational gotcha, not user-facing usage doc content — belongs in `CLAUDE.md` alongside the other two accurate lines about the fixture. Proposal: `{"target": "fixture/CLAUDE.md", "text": "Alerts silently drop if TIMEOUT_S exceeds the channel's flush interval."}` (or equivalent condensed wording preserving the claim). |
| P5 | `fixture/docs/plans/2026-01-10-notify-retry-design.md` (whole doc, 59 lines) | `DISTILL`, `status: "ready"` | Design predates and matches shipped code: `fixture/src/notify.py:3` `MAX_RETRIES = 3`, `notify.py:4` `TIMEOUT_S = 10`. The two durable decisions are buried in the "Decision" paragraph at lines 37-38 ("three attempts felt like the right balance") and lines 39-40 ("ten seconds per attempt gives slow channels enough headroom"). Everything else (Problem, three rejected/considered Options, the Sketch duplicating `notify.py`'s actual code) is scaffolding with no ongoing value once the code exists. Payload must extract both decisions as claims (target likely `README.md` or `CLAUDE.md`, each citing `notify.py:3`/`notify.py:4` as evidence) plus a non-empty `decision_entry` (a short decision-log line, e.g. "2026-01-10 — retry cap=3, timeout=10s, fixed retries (not backoff)"). |
| P6 | `fixture/docs/plans/2026-07-01-batching-design.md` (whole doc, 17 lines) | `DISTILL`, `status: "pending-implementation"` | Describes a `send_batch(channel, msgs)` helper that does not exist anywhere in `fixture/src/` (only `notify.py` exists, no `batch`/`send_batch` symbol). Grep evidence: `grep -rn "send_batch\|batch" fixture/src/` returns nothing. Must NOT be marked `ready` and must NOT carry a `payload` (payload is non-null iff `DISTILL` + `ready` per the contract) — this is the explicit grading trap distinguishing P5 from P6. |

## Grading notes (explicit)

1. **P6 must not get a ready-DISTILL or any payload.** Any baseline output that assigns
   `status: "ready"` to the batching doc, or attaches claims/a decision_entry to it, is a
   contract violation regardless of how the finding is phrased in prose — record it as a
   failure.
2. **P1 (README/SETUP.md overlap) legitimately supports either `MERGE-DOC` (SETUP.md →
   README.md, or README's `## Setup` → SETUP.md) or `RETIRE-DOC` on `SETUP.md`.** Accept
   either verdict; grade on whether the evidence actually demonstrates the overlap (quotes
   or cites both files) rather than which of the two acceptable verdicts was picked.

## Non-planted content (must NOT be flagged, or flagged only as low-confidence noise)

- `fixture/README.md:1-4` (intro sentence), `:16-26` (Usage section incl. code sample),
  `:45-48` (Contributing) — ordinary, non-redundant doc content.
- `fixture/CLAUDE.md` — two accurate, dense lines; this is the EXTRACT-AND-MOVE *target*,
  not a source of findings.
- `fixture/src/notify.py` — code, not a doc; not itself gradeable as a bloat finding.
