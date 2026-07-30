# Output contract — verdict fields + worked example

Reference for `detecting-doc-bloat`. This file is the contract's one home: the
field table, a worked example, and the chunk-result seam shape. The artifact
you emit is the **verdicts envelope** `python3 -m doclifecycle bloat-audit`
reads; the engine turns it into the report. Shape-check every artifact with
`scripts/validate-bloat-output.py` before any handoff — and remember what that
check cannot see: `bloat-audit` is the authority on every fact about the
corpus (see *What the engine decides* below). The field rules below are this
file's own restatement in one place for the model authoring verdicts; the
engine's own refusal codes for every way a verdict can be rejected —
including the `PROPOSAL_VERDICTS` / `DESTINATION_VERDICTS` / `RESIDUE_VERDICTS`
/ `SCOPE_VERDICTS` sets these field rules are drawn from — are owned by
`plugins/doc-lifecycle/engine/README.md` ("Bloat audit", the verdict table and
the "Refusals" table beneath it); this file cites that, not the other way
round.

## Verdict fields

A verdict carries only these ten keys, all optional except as ruled below:
`id`, `verdict`, `path`, `units`, `evidence`, `destination`, `proposal`,
`status`, `scope`, `sample`.

| Field | Rule |
|---|---|
| `id` | non-empty string, unique across the envelope (e.g. `"B1"`). A label the report may renumber — approval binds a record's **digest** |
| `verdict` | one of `CUT` / `CONDENSE` / `EXTRACT-AND-MOVE` / `MERGE-DOC` / `RETIRE-DOC` / `DISTILL` — literal enum, no invented values |
| `path` | the document judged; required unless the verdict carries `scope` |
| `units` | non-empty array of **unit digests** — the `digest` values `python3 -m doclifecycle segment --repo . --path <path>` prints for that document, copied verbatim. This is what the verdict is *about*, and what the applier's span is bounded by. Required unless the verdict carries `scope`. **`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`** (a passage verdict): name only the passage's own units. **`DISTILL`/`MERGE-DOC`/`RETIRE-DOC`** (a whole-document verdict, subject is the document, not a passage): name **every** unit `segment` prints for it, assertion-capable or not — never one representative and never only the assertion-capable subset. **This is a contract you must honor, not one the tooling checks for you**: neither `validate-bloat-output.py` nor the engine's `record_verdicts()` verifies that a whole-document verdict names every unit — both only check that each named unit occurs in the document (`bloat-unknown-unit`), never that none was left out. The applier bounds any positioned operation the remedy uses (`MERGE-DOC`'s move, `DISTILL`'s span edits) to the **hull** of the record's named units — first line through last — so a whole-document verdict naming fewer than every unit silently narrows what the eventual apply can touch, with nothing downstream to catch the gap |
| `evidence` | mandatory non-empty string for **every** verdict — why this content does not earn its tokens. `DISTILL`: the landed-code proof (or the grep-returns-nothing proof) plus at most brief classification framing — never the doc's substance |
| `destination` | where content goes. `EXTRACT-AND-MOVE` / `MERGE-DOC`: the target document — **optional**, because for content that occurs elsewhere the engine derives the destination from the index and refuses a disagreeing one. `DISTILL`: optional, and a path **nobody has written yet** (the residue's home); absent means a retire-only distillation. Any other verdict: absent |
| `proposal` | `CONDENSE` / `EXTRACT-AND-MOVE`: non-empty string, the complete replacement or the text to land (writing-docs bar; placed byte-verbatim). Any other verdict: absent |
| `status` | `DISTILL` only: `"pending-implementation"` or `"ready"`, **copied from the planning document's own `> Status:` marker** — the engine checks the two match (`bloat-status-not-file-bound`) |
| `scope` | a bulk judgment's subject: exactly one of `{"set": <doc set>}`, `{"glob": <pattern>}`, `{"kind": <living\|narrative\|planning>}`. `RETIRE-DOC` only |
| `sample` | `scope` verdicts only: the in-scope paths you actually read. Review prioritization, recorded as such — it never stands in for the enumeration |

**Fields a verdict may never carry:** `files`, `members`, `occurrences`,
`contention`. A bulk finding's members are enumerated from the index, never
asserted by the model — asserted membership is exactly what an enumeration
replaces, and a file list supplied here could authorize a mutation nobody
enumerated.

## What the engine decides, and you do not

Supply judgment — is this worth keeping, and what should replace it. Every
fact comes from the whole-repository context index, and disagreeing with it is
refused, not preferred:

- **Membership of a scope.** `{"set": "ephemeral"}` expands to one finding per
  member (`B4.0`, `B4.1`, …), each with its own digest to approve.
- **A move's destination** for content that occurs elsewhere: the index's
  owner. Naming a different one is `bloat-destination-contradicts-index`.
- **Whether a unit is in the document** you claimed it against, and whether
  the path is a document at all.
- **A `DISTILL` status**, against the file's own marker.
- **Whether a chunk verdict stayed in its slice** — for single-document
  verdicts only; a `scope` judgment is corpus-wide by construction.

## Worked example

Four verdicts covering the shapes that trip agents up. **This is an example of
verdict shape, not an inventory of findings** — these come from an invented
repo (a small caching library plus an ephemeral-artifact swarm); your audit
sweeps for all six verdicts.

```json
{
  "schema_version": 1,
  "verdicts": [
    {
      "id": "B1",
      "verdict": "CONDENSE",
      "path": "README.md",
      "units": ["3a046defbf36f4949d1f2e36240836a3b263d164a96b7a04955b15fc70cedf0d"],
      "evidence": "one checkable fact spread over a narrative line; src/cache.py:5-6 names both constants",
      "proposal": "Entries expire after `CACHE_TTL_S` (300s); past `MAX_ENTRIES` (1024) the least-recently-used entry is evicted."
    },
    {
      "id": "B2",
      "verdict": "EXTRACT-AND-MOVE",
      "path": "README.md",
      "units": ["bf98a9f5ed71d4703bc8e31805b7a7f5d5ddd823d9cebae582bcfe0a30d9feae"],
      "evidence": "an operator gotcha ('workers silently exit') in a user-facing README; RUNBOOK.md is the doc its audience reads on demand",
      "destination": "RUNBOOK.md",
      "proposal": "Swarm workers exit silently when `.cache-state.json` is absent — run `make migrate` before `make dev` (`src/worker.py:9`)."
    },
    {
      "id": "B3",
      "verdict": "DISTILL",
      "path": "docs/plans/2025-11-02-cache-layer-design.md",
      "units": [
        "87abd4c8ec4a2bfeca8ef02bbaebb9c46e0738e58fb8e4b5082979402000fdc8",
        "f1c9e6b0a2d84e5f9a7c3b1d6e0f4a8b2c5d9e7f1a3b6c8d0e2f4a6b8c0d2e4f"
      ],
      "evidence": "implementation landed: src/cache.py:5 `CACHE_TTL_S = 300`, :14 `get_or_fill` match the design; the file's own marker reads ready",
      "status": "ready"
    },
    {
      "id": "B4",
      "verdict": "RETIRE-DOC",
      "scope": { "set": "ephemeral" },
      "evidence": "every member is a dated plan/spec artifact for work already merged (git log confirms) — one class of ephemeral process artifact, not N findings",
      "sample": ["docs/superpowers/plans/2026-06-01-batching-plan.md"]
    }
  ]
}
```

`B1` and `B2` are the passage shapes: both name the unit digests they cover,
and `B2` carries both a `destination` (where the text lands) and a `proposal`
(the text). `B2`'s destination is a **different document than the one judged**,
and may sit outside a chunk's slice — only `path` is slice-bound.

`B3` carries **no residue of any kind** — its `evidence` is the landed-code
proof, full stop. The claims, insights, and decision entry are the
`doc-distiller`'s post-approval job; the rationale lives once in
`references/planning-artifacts.md`. Its `status` is transcribed from the file,
never decided by the grep. Its `units` name **every** unit the document has —
two here because the invented doc is that short — because `DISTILL`'s subject
is the whole document and the applier bounds any span edit the distiller's
remedy uses to the hull of exactly these digests.

`B4` is bulk retirement — the replacement for the retired `POLICY` verdict. It
names an **inclusion rule**, not files: the engine expands `{"set":
"ephemeral"}` into one `RETIRE-DOC` finding per member, so a reviewer can
re-derive the list and approve (or refuse) member by member. `sample` records
which members were actually read, and authorizes nothing.

## Chunk results (the seam artifact)

A chunk executor never emits the envelope. It emits exactly:

```json
{"chunk": "<dispatched chunk id>", "verdicts": [ /* verdicts as above */ ]}
```

Rules the seam validator enforces (`--chunk <file> --manifest <manifest>`):

- A single-document verdict's `path` must be a document the chunk lists. This
  binds `path` only — a `destination` may point anywhere, in or out of slice.
- A `scope` verdict is **not** slice-bound: its subject is the corpus, and the
  index enumerates its members.
- Empty `verdicts` is valid — a clean chunk says so.

Assembly (`--assemble <dir> --manifest <manifest> --out bloat-verdicts.json`)
seam-validates every chunk, renumbers ids `B1..Bn`, and writes the envelope.
The envelope's `completion` object binds the current index digest, a digest of
the planned chunk identities and document membership, and each chunk's result
state plus the verdict ids it contributed. Missing or invalid chunks fail the
assembly by name unless `--allow-partial`; then each stays inside `completion`
as a typed gap and the next content-addressed plan resumes exactly that work.
`--unswept-out` may still render the same gaps for a run surface, but it is
never the report's source of truth and omitting it cannot turn partial clean.
