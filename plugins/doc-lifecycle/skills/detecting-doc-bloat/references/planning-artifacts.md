# Planning artifacts

Reference for `detecting-doc-bloat` chunk executors whose chunk carries
`planning` hints. Verdict shapes: `output-contract.md`.

## Planning artifacts: classify by whether the implementation landed

A planning artifact (design doc, spec, plan — conventionally `docs/plans/`)
describes an *intended change*. Location is a hint; **the registry is the
test, not the doc's shape or a `> Status:` marker on it.** `python3 -m
doclifecycle segment --repo . --path <path>` — which this skill already
requires you to run for every unit digest — prints that document's `kind` at
the top level of its output: this is the registry's own classification, the
same one the engine checks a `DISTILL` verdict's path against
(`bloat-distill-not-planning`). A doc registered `living` or `narrative` that
happens to carry a `> Status:` marker and sit under a `specs/`-shaped path is
**not** a planning artifact for this audit — the marker there is a finding to
surface (the registry and the doc's own habits disagree), never a licence to
emit `DISTILL` against it. A doc whose first line is the `> As of` anchor is
narrative, never a planning artifact, regardless of what `segment` reports —
per `verdict-lenses.md`, the anchor line is the classifier for that case.

**The file is the authority; you are a reporter.** A true planning artifact
carries its own lifecycle state as a `> Status: <pending-implementation|ready>`
block-quote marker (absent or malformed reads as `pending-implementation`,
never `ready`). Your verdict's `status` **copies that marker verbatim** — the
engine checks the two match and refuses any verdict whose `status` disagrees
with the file (`bloat-status-not-file-bound`). You never decide `status` from
what the grep finds; the grep decides whether the marker is *current*, nothing
else. `DISTILL` against a document the registry classifies as anything but
`planning` is refused outright (`bloat-distill-not-planning`).

For each true planning artifact, **do the check, do not eyeball it**:
grep/read the code for the symbols and behavior it describes, then emit
exactly one `DISTILL` verdict:

- **The marker says `ready`** → `status: "ready"`. `evidence` = the landed
  code (`file:line` per design symbol) that confirms the marker is current.
  A design whose implementation has landed and whose marker already says so
  is a distillation candidate: its value has already moved into the code;
  what remains is scaffolding plus whatever durable decisions and insights the
  **doc-distiller** will extract **after a human approves this record's
  digest**. Your verdict carries the classification, the proof, and — when you
  can say where that residue belongs — a `destination`: the path of the
  document the distiller would author it into, which must be one **nobody has
  written yet** (the engine checks that, and refuses an occupied path). It
  carries nothing else: no `proposal`, no residue text anywhere. Omit
  `destination` only when there is genuinely nothing to place; that is a
  *retire-only* distillation, and it loses whatever residue no other record
  lands. **Detection never
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
  naming the absent symbols. **Name no `destination`.** Nothing has landed, so
  there is no residue to place yet — a destination here would widen the
  approval set's mutation scope to a document nobody is authoring, on a
  record that carries no evidence anything is ready to move into it.
- **The marker says `pending-implementation`, but the grep finds the design's
  symbols already landed** → `status: "pending-implementation"` — you copy
  the file, you never override it, however current your own evidence makes it
  look. `evidence` names the landed symbols (`file:line` per design symbol)
  *and states that the marker is stale*: the implementation has landed but the
  file has not been updated to say so. That note is what gives the human the
  signal to flip the marker — a git-approved edit, never yours to make — after
  which the *next* audit's grep confirms currency and emits `ready`. **Name no
  `destination` here either** — the record's `status` stays
  `pending-implementation` because you copy the file, not your own evidence,
  and a `pending-implementation` record is unactionable by convention only:
  nothing in its shape stops a destination from being minted into an approval.
  The next `ready` audit, against the flipped marker, is where a destination
  belongs.

In diff-scoped runs, **a landing planning artifact is not an objection** — a
PR that adds a design doc for unbuilt code is *correct*; emit
`DISTILL pending-implementation` for it, not a complaint. Every planning
artifact in scope yields exactly one `DISTILL` verdict.

## A swarm of ephemeral artifacts: one scope, never N walks

When a whole class of planning artifacts is ephemeral process scaffolding for
work already merged, the judgment is **one bulk `RETIRE-DOC` over a `scope`**,
not one `DISTILL` per file. Declare the inclusion rule the class actually has
— `{"set": "<doc set>"}`, `{"glob": ...}`, or `{"kind": "planning"}` — and the
engine expands it from the index into one finding per member, each with its
own digest for the human to approve or refuse.

- `evidence` = what makes them one class: the shared shape, and the landed
  state they scaffolded.
- `sample` = the members you actually read (2–3 is enough; opening all N
  defeats the point). It is review order, and authorizes nothing.
- Never list the members. `files` is a refused field: membership comes from
  the enumeration, so a list supplied here could authorize a retirement nobody
  enumerated.

A `scope` verdict carries no `path`, `units`, `destination`, `proposal`, or
`status` — its subject is the rule, not a document.

## Red flags — STOP

- Authoring claims, insights, or a decision entry at detect time — in
  `evidence`, in `proposal`, in an invented field, or anywhere else → that is
  the distiller's post-approval job; emit classification + proof only.
- "I'll put the insight walk in `evidence`, since the contract has nowhere
  else for it" → residue in a permitted field is still detect-time authoring.
  STOP.
- Emitting one `DISTILL` per member of an ephemeral swarm → one `RETIRE-DOC`
  over the scope; the engine expands it into the per-member findings.
- Naming a bulk retirement's members — a `files` key, or a `scope` narrowed to
  the paths you happened to open → declare the inclusion rule; the sample is
  what you read, never the mandate.
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
- Naming a `destination` on a `pending-implementation` verdict → nothing has
  landed to place anywhere; a destination there widens the eventual approval's
  mutation scope to a document nobody is authoring. Only a `ready` verdict may
  name one.
