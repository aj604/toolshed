# Shadow-mode parity gate, second cycle — run record

The artifacts of the 2026-07-27 shadow cycle of the read-only audit lane over this repository's
real documentation (aj604/toolshed#117). The gate itself — its criteria, re-registered before the
cycle in commit `983837b`, and its **FAIL** verdict — is
`docs/plans/2026-07-27-shadow-parity-gate-rerun.md`. This directory is that record's evidence.

The first cycle's artifacts stay at `tests/baselines/shadow-parity-gate/` and are not superseded:
that directory holds the only legacy-lane report and meta this comparison has, and this cycle
reads them from there rather than copying them.

| File | What it is |
|---|---|
| `verdicts.json` | what the model workers returned, merged across all three rounds — the run's one irreproducible input |
| `shadow-report.json` | the validated report `drift-audit` produced from it |
| `shadow-meta.json` | the run's per-session cost, turn, and duration distributions, and the assertions-judged denominator criterion G5 is measured on |
| `comparison.json` | `compare-shadow-lanes.py compare` over the two lanes' artifacts |
| `digest-before.json`, `digest-after.json` | criterion G1b's two measurements |
| `freshness-check.json` | criterion G3's `validate-report --repo .`, run at the audited commit |
| `fanout.py` | the worker orchestrator — how the 58 headless sessions were dispatched and what prompt they were given |

The registry is not kept here: this cycle audited against the landed `.doc-lifecycle/registry.json`
(#75), which is what `doc-audit.yml` reads, so there is no stand-in to record.

## The commit the cycle ran against

`983837b53ba88358b270a9ba6cd4192669772161`, tree `e5d6aedfb457ee3e0c9770a40e060dbff00c4cb2` — the
pre-registration commit, whose only content is the re-registered criteria and the instrument that
measures them.

`validate-report --repo .` returns `findings` at that commit and `stale` at any later one, which is
the contract working as designed: the verdict edits `docs/plans/`, the registry inventories it, and
the inventory digest is part of the report's lineage.

## Reproducing the derived half, from a checkout at that commit

```bash
D=tests/baselines/shadow-parity-gate-rerun
python3 tests/baselines/shadow-parity-gate/shadow-cycle.py digest --repo .
python3 plugins/doc-lifecycle/engine/doc-lifecycle.py drift-audit --repo . --mode full \
  --verdicts $D/verdicts.json --waivers .github/doc-sync/drift-waivers.json \
  --evidence-command gh
python3 plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/compare-shadow-lanes.py compare \
  --legacy tests/baselines/shadow-parity-gate/legacy-report.json \
  --legacy-meta tests/baselines/shadow-parity-gate/legacy-meta.json \
  --shadow $D/shadow-report.json --shadow-meta $D/shadow-meta.json \
  --segments /tmp/shadow/segments.json
```

`segments.json` comes from `shadow-cycle.py slices --repo . --registry .doc-lifecycle/registry.json
--out /tmp/shadow`, which takes no model. `--evidence-command gh` is what
`probe-evidence-tool.py declared --flags` renders from `.github/doc-sync/evidence-tools.json`, the
same way `doc-audit.yml` derives it.

## How the three rounds were folded

`shadow-cycle.py merge` takes one `--slices` directory and one `--repair` directory, and this cycle
ran two repair rounds. The second repair re-ran a task the first had left failing, so the two were
overlaid into a single directory — same filename, later round written second — before the merge.
That is the same rule the harness applies per unit (a later answer wins), applied once per task
file rather than per unit, and it is exact here because every task writes exactly one answer file.

Round 1 refused 4 of 25 documents; repair 1 cleared 3 and repair 2 cleared the last.

## What is kept, and why not everything

`verdicts.json` is 58 model sessions of output and cannot be recomputed. `shadow-report.json`,
`comparison.json`, and the three small evidence files are derivable from it, and are kept anyway:
they are what a reader checking the verdict actually reads, and re-deriving them needs a checkout at
a commit whose lineage this branch will no longer match. `segments.json` is derivable with no model
and is *not* kept — it is intermediate nobody reads. The rule is "keep what the verdict is checked
against", not "keep whatever cannot be recomputed".

`fanout.py` is kept for a different reason: it carries the worker prompt verbatim, and the verdict's
G3 section is a claim about what that prompt did and did not say.
