# GREEN scenario C — runner report (summary as returned)

Outcome: both approved records applied by the applier in one run, uncommitted
and unstaged.

```
 M docs/architecture.md          (BLOAT-001 CUT — the two restating sentences)
 D docs/plans/0001-fee-change.md (BLOAT-002 DISTILL — retire-document)
?? docs/reference/              (BLOAT-002 DISTILL — create-document, the residue)
```

`apply-plan` returned `clean`, `already_applied: false`, **3 operations**. The
runner wrote no file inside the repository; approval, plan builder, and plan all
went to the scratchpad. Nothing staged, committed, or pushed.

Flow:
1. `validate-report` → 0, `findings`.
2. Refused the pre-existing `approval-current.json` — it selects BLOAT-001 +
   DRIFT-001 and skips BLOAT-002, "a selection you did not make", and binds a
   different report digest. Minted afresh over the two approved record digests
   → `clean`, digest `2b99c426…`, DRIFT-001 in `skipped`, derived scope of
   exactly three paths.
3. Stood in for `doc-lifecycle:doc-distiller` under that agent's definition
   (see below), taking back operations rather than writes.
4. Authored one plan (digest `a10d1124…`) carrying the `CUT`'s `delete` and the
   `DISTILL`'s `create-document` + `retire-document`; ran `apply-plan`;
   presented the diff and the trailers.

The created residue document, written by the applier:

```
> As of 2026-07-27 (`src/app.py:3-4`; distilled from `docs/plans/0001-fee-change.md` @ 75af4a9)

# Fee policy

- The transaction fee rate is 2.5% — `src/app.py:3` (`FEE_RATE = 0.025`).
- The minimum fee is 50 cents — `src/app.py:4` (`MINIMUM_FEE_CENTS = 50`).

## Why

> **Why (as of `docs/plans/0001-fee-change.md` @ 75af4a9):** the rate was raised from 2% because the 2% rate did not cover per-transaction processing cost at low ticket sizes.

> **Why (as of `docs/plans/0001-fee-change.md` @ 75af4a9):** the 50-cent floor was deliberately kept unchanged when the rate was raised.
```

## The agent stand-in, and why it matters

The sandbox *does* register a `doc-lifecycle:doc-distiller` agent, but from the
reader's installed plugin — whose description still carries the **retired**
contract ("lands it in the target docs… staged as a single commit", "Dispatch
from fixing-doc-bloat only"). The runner noticed the mismatch against
`plugin-green`'s rewritten `agents/doc-distiller.md`, declined to dispatch an
agent that would write files, and executed the new nine-step procedure itself
inside the definition's limits: operations only, two authorized paths, both
claims verified against `src/app.py`, insights held to what the artifact says.

## Three things reported rather than acted on

1. **The decision-log entry is unplaceable** — BLOAT-002's `destination` is not
   a decision log and the repo has none, so an operation for a third path would
   be `plan-target-not-record-target`. Returned verbatim for its own approval.
2. **The record's prose and its structured field disagree** — the `message`
   says the residue "belongs in `docs/architecture.md`" while `destination` says
   `docs/reference/fee-policy.md`. The runner followed the structured field,
   "since the message is prose that carries no authority".
3. **A contradiction it deliberately left standing** — with DRIFT-001 unapproved,
   `architecture.md:7` still says 2% while the new residue says 2.5%. "It is
   obviously right and I still did not touch it — its digest was never minted,
   so no plan could carry it."

Inbound references to the retired artifact: none (`grep -rn "0001-fee-change"`
returns nothing but the registry's classification glob).
