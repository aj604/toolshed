# insight-red RED findings

2026-07-04. Arm: the **0.5.5** `detecting-doc-bloat` skill text (no insights channel,
two-kind doc taxonomy — living claim docs vs planning artifacts), served from a scratch
copy so the agents never saw the current 0.6.0 text. Two fresh subagents, red-A and
red-B, neutral prompt ("run a full bloat audit of this repo per the skill file"), fixture
`tests/baselines/insight-red/fixture/`, report-only. Both outputs pass the 0.5.5
validator; no fixture edits. Verbatim outputs: `red-A-output.json`, `red-B-output.json`.
Graded per ANSWER-KEY.md's RED paragraph: did I1/I2 survive *anywhere*
(claims/decision_entry), and was K3 mishandled?

## red-A

**K1 survival — all three planted rationales survive, but mis-channeled.** red-A's B1
(`DISTILL ready` on the design doc) carries I1, I3, and I2 as three payload *claims*
targeted at `CLAUDE.md`, e.g. I1:

> "Exhausted jobs are dropped, never parked — a dead-letter queue was rejected because
> the service deploys unattended and an unmonitored DLQ grows without bound; revisit
> only if an operator rotation ever exists." — target `CLAUDE.md`, evidence
> `src/worker.py:18 \`queue.drop(job)        # dropped outright\``

and I2: "The per-attempt timeout is one global `TIMEOUT_S` for every job type — per-type
budgets were rejected because each new job type would become a tuning decision nobody
owns…" (evidence `src/worker.py:4`). All three recur as decision_entry clauses
("Rejected: dead-letter queue…; exponential backoff…; per-job-type timeouts…" plus a
"Still binds: revisit a DLQ only if an operator rotation ever exists"). So nothing was
lost outright — better than the key's predicted worst case — but every survival is
wrongly channeled:

- The evidence anchors verify the *behavior*, not the *rationale*: `queue.drop(job)`
  proves jobs are dropped; it cannot verify "because the service deploys unattended".
  These are rationale claims wearing code anchors, exactly what the suite's
  verifiability bar rejects in a claim doc.
- The target is `CLAUDE.md` — whose lines 3-4 already carry the dropped-not-parked and
  global-timeout behaviors — not a narrative doc. Applying these claims duplicates
  living lines and pads CLAUDE.md with three rationale paragraphs.
- The B1 evidence simultaneously writes the source off: "Problem/Options/Sketch sections
  are superseded scaffolding" — the Options content the claims rescue is, by the
  record's own evidence, scaffolding. The 0.5.5 text gives the agent no category for
  "breadth worth keeping", so the record contradicts itself.

**K2 (recipe plan):** B2 `DISTILL ready` with one attempts-counter claim, no fabricated
rationale. Fine — but note the 0.5.5 contract never asks whether an insight sweep
happened, so a zero here is indistinguishable from a walk never run.

**K3 — fail.** red-A emits two `CONDENSE` records against the narrative walkthrough
(B3 at `queue-walkthrough.md:5`, B4 at `:10`), collapsing each paragraph to a one-liner.
The doc's `> As of 2026-03-05 (src/worker.py:3-20)` anchor (line 3) — the classifier
under the current taxonomy — is never mentioned. (Minor evidence slop: B3 calls
lines 5-8 "four narrative sentences"; the passage is three sentences over four lines.)

## red-B

**K1 survival — same shape as red-A.** B1's payload claims carry I1 ("Exhausted jobs are
dropped, not dead-lettered — a DLQ was rejected because this system deploys unattended
and an unmonitored DLQ hides failures; revisit only if an operator rotation ever
exists."), I3 (no-backoff/tail-spacing), and I2 ("One global `TIMEOUT_S` (30s) covers
every job type — per-type budgets were rejected because each new job type would become a
tuning decision nobody owns…"), all targeted at `CLAUDE.md`, all anchored to code lines
that prove the behavior only, all repeated as decision_entry "Rejected:" clauses. Same
self-contradiction: B1's evidence declares "Problem/Options/Sketch sections are
superseded scaffolding" while the claims channel rescues the Options content.

**K2:** B2 `DISTILL ready`, one boundary-semantics claim, no fabricated rationale.

**K3 — fail.** Same two `CONDENSE` records on the walkthrough (B3 `:5`, B4 `:10`); the
`> As of` anchor goes unremarked.

## The condense-with-unease signature (both agents, B4)

Both agents' JSON `summary` objects are counts only, but the unease about condensing the
walkthrough's failure-path paragraph is legible in the B4 records themselves: each agent
singles the rationale out as the thing the condense must not lose, then smuggles it into
the condensed line because the taxonomy gives it no home.

- red-A B4 evidence: "six narrative sentences whose checkable content fits one line …
  **plus the tail-spacing rationale**"; its proposal appends "— tail re-entry spaces
  retries by roughly the queue's drain time, letting transient failures clear."
- red-B B4 evidence: "six lines of narrative carry the failure path the code shows at
  src/worker.py:15-20 … **plus one rationale (tail re-entry spaces the retry behind the
  queued backlog, letting transient failures clear)**"; its proposal likewise closes
  "— tail re-entry makes the retry wait behind the queued backlog, so the transient
  condition has usually cleared by the next run."

A condense whose evidence has to carve out an exception for "the rationale" is the
taxonomy telling on itself.

## Distilled failure statement

What the 0.5.5 text loses is not (in this run) the rationale's words — both agents
rescued I1/I2/I3 — it is the rationale's *standing*. With no insights channel, breadth
survives only by contract violation: re-labeled as verifiable claims and pushed at
`CLAUDE.md` with code anchors that verify the behavior but not the reason (the next
audit or writing-docs pass would strip them), or compressed to decision_entry clauses.
And with no narrative kind in the taxonomy, the one doc that should *host* that breadth
— the anchored walkthrough — is itself treated as condensable prose: both agents
CONDENSE'd it twice (K3 fail, 2/2 agents), preserving the rationale only as a trailing
clause inside a one-liner. Insights get demoted to at most a decision-log clause or a
claim-doc squatter; the narrative doc gets shrunk toward the claim bar it was never
supposed to meet.
