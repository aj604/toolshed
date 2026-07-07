# Auditing and fixing bloat with `detecting-doc-bloat` and `fixing-doc-bloat`

> As of 2026-07-06 (doc-lifecycle contract v2; `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md`, `fixing-doc-bloat/SKILL.md`)

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
large scope it first plans bounded chunks (a deterministic script) and audits one chunk
per subagent, validating each result mechanically before assembling the report.

## Step 2 — read the proposal

You get a human summary grouped by doc, one line per finding, backed by a structured
JSON report. The summary is rendered by a script (`render-report.py bloat-triage` —
the skill never pastes raw JSON at you) and looks like:

```
README.md
  [B1] CONDENSE       README.md:22 — README.md:22-28 — seven lines of eviction narrative carry one fact (CACHE_TTL_S, src/cache.py:5)
  [B2] EXTRACT-AND-MOVE README.md:31 — README.md:31-32 — cold-start latency gotcha belongs in RUNBOOK.md
docs/plans/2025-11-02-cache-layer-design.md
  [B3] DISTILL(ready)  — implementation landed: src/cache.py:5 CACHE_TTL_S, :14 get_or_fill match the design
docs/superpowers
  [B4] POLICY          (10 files) — 10 dated plan/spec artifacts for merged work; one class, not 10 findings
```

Every record carries an **ID**, one of seven verdicts, and **cited evidence** — the code
line it restates, the quoted overlap, the grep. "Feels redundant" is not admissible.

| Verdict | Means |
|---|---|
| `CUT` | the passage restates what the adjacent code already shows |
| `CONDENSE` | many lines, one checkable fact — the record includes the one-line replacement |
| `EXTRACT-AND-MOVE` | right content, wrong doc (an operator gotcha buried in a README) |
| `MERGE-DOC` / `RETIRE-DOC` | a doc is a near-duplicate of another — fold the remainder in, or delete it |
| `DISTILL` | a design doc whose implementation landed — approving it sends the artifact to the distiller, which extracts the durable residue and retires the scaffolding |
| `POLICY` | a directory you declared as one class of ephemeral artifact (scope config) — one bulk record naming every covered file; approving it applies the stated policy (typically retirement) to exactly those files |

## Step 3 — approve by ID (this is the only mandate there is)

> apply B1 and B3

`fixing-doc-bloat` applies **exactly the approved records**. B2 above stays untouched —
even if it's obviously right, even if B1's edit lands one paragraph away. `CONDENSE`
replacement text lands byte-verbatim; nothing gets reworded, blended, or "rounded out."

Two special cases worth knowing before your first approval:

- **`DISTILL` (ready)** is the big one: the record itself carries only the
  classification and the landed-code proof — nothing expensive was authored before you
  approved. On approval the fixer dispatches the `doc-distiller` agent, which walks the
  artifact, drafts the durable claims and insights (verifying each claim against the
  code it cites), lands them in their target docs, appends one entry to
  `docs/decisions.md`, and retires the artifact — staged as a single commit whose draft
  PR shows you exactly what was extracted. Decisions survive; scaffolding goes to git
  history, where it still lives if you ever need it.
- **`DISTILL` (pending-implementation)** — a design doc for code that *hasn't* landed —
  is never actionable, even if you approve it. A pending design is accurate about the
  future; the record exists to say so, not to propose an edit.

## What this loop will never do

Edit without an approved ID, delete content a record didn't span, or treat its own
summary as authorization. If that discipline ever feels slow, it's the reason a bloat PR
is reviewable at all.

## Next

This repo runs the same sweep on itself weekly. When approving records feels routine,
[put it on a schedule](scheduling-doc-sync.md).
