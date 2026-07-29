# Planning artifacts and policy scopes

Reference for `detecting-doc-bloat` chunk executors whose chunk carries
`planning` hints or is a policy chunk. Record shapes: `output-contract.md`.

## Planning artifacts: classify by whether the implementation landed

A planning artifact (design doc, spec, plan — conventionally `docs/plans/`)
describes an *intended change*. Location is a hint; what the doc does is the
test — and a doc whose first line is the `> As of` anchor is narrative, never
a planning artifact.

**The file is the authority; you are a reporter.** A true planning artifact
carries its own lifecycle state as a `> Status: <pending-implementation|ready>`
block-quote marker (absent or malformed reads as `pending-implementation`,
never `ready`). Your record's `status` **copies that marker verbatim** — the
engine checks the two match and refuses any record whose `status` disagrees
with the file. You never decide `status` from what the grep finds; the grep
decides whether the marker is *current*, nothing else.

For each true planning artifact, **do the check, do not eyeball it**:
grep/read the code for the symbols and behavior it describes, then emit
exactly one `DISTILL` record:

- **The marker says `ready`** → `status: "ready"`. `evidence` = the landed
  code (`file:line` per design symbol) that confirms the marker is current.
  A design whose implementation has landed and whose marker already says so
  is a distillation candidate: its value has already moved into the code;
  what remains is scaffolding plus whatever durable decisions and insights the
  **doc-distiller** will extract **after a human approves this record's ID**.
  Your record carries the classification and the proof, nothing else:
  `proposal`, `files`, and any payload-like content = none. **Detection never
  authors the residue.** The insight walk, claim drafting, and decision-entry
  drafting are the distiller's post-approval protocol — running them now is
  speculative work no one approved, and writing their output into `evidence`
  is the same cost relocated, not eliminated. This is also **not** "keep it as
  a historical record" — a design doc kept verbatim as history is exactly the
  bloat this verdict removes; git history is the archive.
- **The marker says `pending-implementation` (or is absent), and the grep for
  its symbols returns nothing** → `status: "pending-implementation"`. A
  pending design is accurate about the future; it is neither bloat to cut nor
  ready to distill — the record exists to *say so*, not to propose an edit.
  Never propose deleting it. `evidence` = the grep that returned nothing,
  naming the absent symbols.
- **The marker says `pending-implementation`, but the grep finds the design's
  symbols already landed** → `status: "pending-implementation"` — you copy
  the file, you never override it, however current your own evidence makes it
  look. `evidence` names the landed symbols (`file:line` per design symbol)
  *and states that the marker is stale*: the implementation has landed but the
  file has not been updated to say so. That note is what gives the human the
  signal to flip the marker — a git-approved edit, never yours to make — after
  which the *next* audit's grep confirms currency and emits `ready`.

In diff-scoped runs, **a landing planning artifact is not an objection** — a
PR that adds a design doc for unbuilt code is *correct*; emit
`DISTILL pending-implementation` for it, not a complaint. Every planning
artifact in scope yields exactly one `DISTILL` record.

## Policy chunks: one record, never a walk

A policy chunk arrives pre-declared: the repo's `audit-scope.json` names the
directory under `policy_scope`, and the manifest hands you its complete file
list. The maintainers have already decided these files are **one class** of
ephemeral process artifact — your job is one bulk judgment, not N audits.

Emit **exactly one `POLICY` record** for the chunk:

- `doc` = the covered directory (the chunk's `dir`, verbatim).
- `files` = the chunk's file list, **verbatim** — selected by filter, never
  re-derived or summarized by you (provenance: a bulk record that cannot name
  its files is unfalsifiable).
- `proposal` = the policy text, e.g. "Ephemeral process artifacts; retire
  after the work merges."
- `evidence` = what makes the directory one class: sample the boilerplate,
  cite the landed state the artifacts scaffolded. Sampling 2–3 files is
  enough; opening all N defeats the point.

Do **not** open every file, emit per-file records, run passage lenses inside
the scope, or author DISTILL records for its members. The whole verdict exists
because N ephemeral artifacts should cost one policy decision, not N
heavyweight walks.

## Red flags — STOP

- Authoring claims, insights, or a decision entry at detect time — in a
  payload-like structure, in `evidence`, or anywhere else → that is the
  distiller's post-approval job; emit classification + proof only.
- "I'll document the insight walk in `evidence` since payloads are gone" →
  payload content in a permitted field is still detect-time authoring. STOP.
- A per-file record for any path inside a policy chunk → one `POLICY` record
  covers the chunk; the seam validator rejects anything else.
- A `POLICY` record whose `files` differ from the manifest chunk's list →
  provenance broken; copy the list verbatim.
- Treating a landed design doc as a "historical record to keep" → that is the
  bloat `DISTILL ready` exists to remove.
- A `ready` status the file's marker does not carry → the engine refuses it;
  do not transcribe your grep into `status` — copy the marker, always.
- A `pending-implementation` classification without the grep that checked for
  landed symbols → do the check, do not eyeball it, even when the marker
  already says `pending-implementation`.
- Landed symbols found against a `pending-implementation` marker, with no note
  that the marker is stale → the human has no signal to flip it, and the next
  audit repeats the same finding.
- Proposing to delete or edit a pending design → it is accurate about the
  future; the record says so and stops.
