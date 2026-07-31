# Auditing and fixing bloat with `detecting-doc-bloat` and `fixing-docs`

> As of 2026-07-30 (doc-lifecycle 0.45.0, engine verdict and scheduled-audit contracts; `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md`, `plugins/doc-lifecycle/engine/doclifecycle/bloat.py`, `plugins/doc-lifecycle/skills/fixing-docs/SKILL.md`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat-audit.yml`)

**You should already have:** the plugin installed and [the principles](principles.md)
read — especially §3, because this loop *is* the propose → approve → apply contract.
This is the entry point for a repo whose docs exist but have grown heavy.

Bloat is **accurate content past its useful form** — nothing here is *wrong*, which is
why drift audits don't catch it. A line restating the code beside it, a paragraph
carrying one fact, two docs with the same setup block, a design doc whose decisions
already moved into the code: all of it costs a reader attention it doesn't repay.

## Step 1 — ask for the audit

> audit the docs for bloat

`detecting-doc-bloat` walks every passage of every doc in scope. It is **read-only**: it
will not fix "just the small one" — every finding becomes a record, and it stops. On a
large scope it first plans bounded chunks and audits one chunk per subagent,
shape-checking each result before assembling them. The assembled judgments then go
through the engine (`doclifecycle bloat-audit`), which checks every one of them against
an index of the whole repository and writes the report.

That last step is what makes a bloat verdict trustworthy: "this is redundant" is a claim
about the *corpus*, and no subagent reading eight files can settle it. The engine
supplies every fact — which documents exist, where a passage also occurs, which document
owns it, exactly which files a bulk scope covers — and refuses a judgment that
contradicts them.

## Step 2 — read the proposal

You get a human summary grouped by document, one line per finding, backed by the
structured report — the skill never pastes raw JSON at you. Each record carries an
**id**, one of six verdicts, the passage it covers, and **cited evidence** — the code
line it restates, the quoted overlap, the grep. "Feels redundant" is not admissible.

| Verdict | Means |
|---|---|
| `CUT` | the passage restates what the adjacent code already shows |
| `CONDENSE` | many lines, one checkable fact — the record includes the one-line replacement |
| `EXTRACT-AND-MOVE` | right content, wrong doc (an operator gotcha buried in a README) |
| `MERGE-DOC` / `RETIRE-DOC` | a doc is a near-duplicate of another — fold the remainder in, or delete it |
| `DISTILL` | a design doc whose implementation landed — approving it sends the artifact to the distiller, which extracts the durable residue and retires the scaffolding |

For example, a repo with a small caching library and a stale design doc might triage to
three records like these (trimmed from the skill's own [output contract's worked
example](../../plugins/doc-lifecycle/skills/detecting-doc-bloat/output-contract.md), which
carries the full JSON for these plus a fourth, `B4`, a `RETIRE-DOC` scope record):

- **`B1`** `CONDENSE` — `README.md` — seven lines of eviction narrative carry one fact
  (`CACHE_TTL_S`, `src/cache.py:5`)
- **`B2`** `EXTRACT-AND-MOVE` → `RUNBOOK.md` — a cold-start gotcha buried in the README,
  not the runbook its audience actually reads
- **`B3`** `DISTILL(ready)` — `docs/plans/2025-11-02-cache-layer-design.md` — the
  implementation landed; `src/cache.py:5` and `:14` match the design

A directory of ephemeral artifacts — ten dated plan/spec files for work that merged — is
not a seventh verdict. It is one `RETIRE-DOC` naming an **inclusion rule** (a doc set, a
glob, a kind), which the engine expands from its index into one record per member. You
approve or refuse them member by member, and the list is re-derivable rather than
something the auditor asserted. (The older `POLICY` record, whose file list the model
echoed back from your scope config, is gone — with its `policy_scope` knob.)

## Step 3 — approve the records you want (this is the only mandate there is)

> apply B1 and B3

`fixing-docs` — the same door drift fixes go through — applies **exactly the approved
records**; the ids are how you say it, and each record's digest is what gets minted into
the approval set the applier will not write without. B2 above stays untouched —
even if it's obviously right, even if B1's edit lands one paragraph away. `CONDENSE`
replacement text lands byte-verbatim; nothing gets reworded, blended, or "rounded out."

Two special cases worth knowing before your first approval:

- **`DISTILL` (ready)** is the big one: the record itself carries only the
  classification and the landed-code proof — nothing expensive was authored before you
  approved. On approval `fixing-docs` dispatches the `doc-distiller` agent, which walks
  the artifact, drafts the durable claims and insights (verifying each claim against the
  code it cites), and **returns them as edit-plan operations rather than writing
  anything**. What it may place is bounded by the record: one record authorizes its own
  document and its `destination`, and residue belonging anywhere else comes back
  reported, for its own approval rather than a silent edit. A `DISTILL` record's
  `destination` is **optional** (`bloat.RESIDUE_VERDICTS`) and is checked as a path
  nobody has written yet rather than looked up among the documents that exist — the
  residue's home is usually a new file. A record that names none is a *retire-only*
  distillation: legal, and lossy exactly when the residue was never landed under some
  record. **Don't accept a retire-only diff without deciding where its residue goes** —
  the scaffolding is in git history either way, but the decisions are not.
- **`DISTILL` (pending-implementation)** — a design doc for code that *hasn't* landed —
  is never actionable, even if you approve it. A pending design is accurate about the
  future; the record exists to say so, not to propose an edit. Which of the two a record
  says is not the auditor's call: the status is transcribed from the artifact's own
  `> Status:` marker, and the engine refuses a record that disagrees with the file. When
  the work lands, *you* flip the marker; the next audit reads `ready`.

## What this loop will never do

Edit without an approved ID, delete content a record didn't span, or treat its own
summary as authorization. If that discipline ever feels slow, it's the reason a bloat PR
is reviewable at all.

## Next

The approval loop remains interactive: you read and approve records by ID through
`fixing-docs`. A separate weekly, read-only scheduled bloat audit can sweep the registered
corpus and publish a typed report, including explicit incomplete coverage. No scheduled lane
applies its findings. See the [scheduling guide](scheduling-doc-sync.md) for installation,
cadence, and trust boundaries; when a report arrives, use Steps 2 and 3 above to review and
apply only the IDs you approve.
