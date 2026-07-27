# Shadow-mode parity gate — cycle record (issue #76)

The artifacts of one full shadow cycle of the new read-only audit lane over this repository's
real documentation, run alongside the still-live legacy `doc-sync` lane. The gate itself — its
pass criteria, pre-registered before the cycle, and its verdict — is
`docs/plans/2026-07-26-shadow-parity-gate.md`. This directory is that record's evidence.

| File | What it is |
|---|---|
| `registry.json` | the classification the shadow run used; derivation rules are declared in the gate record |
| `shadow-cycle.py` | the harness: worktree digest, per-document slices, and the two-round verdict merge |
| `verdicts.json` | what the model workers returned, merged across all three rounds — the run's one irreproducible input |
| `shadow-report.json` | the validated report `drift-audit` produced from it |
| `shadow-meta.json` | the shadow run's cost, rounds, and model |
| `legacy-report.json` | the legacy lane's most recent produced report, from run `28847329392` |
| `legacy-meta.json` | that run's cost, turns, duration, and scope |
| `comparison.json` | `compare-shadow-lanes.py compare` over the two lanes' artifacts |

Base commit: `90ead6d4ec48e5cd2fd7b69551e6a03f6dc358b6`. The report's lineage pins it, so
`validate-report` calls the report stale against any later commit — expected, and why the
adjudications in the gate record cite that commit.

Reproducing the derived half, from a checkout at that commit:

```bash
D=tests/baselines/shadow-parity-gate
python3 $D/shadow-cycle.py slices --repo . --registry $D/registry.json --out /tmp/shadow
python3 plugins/doc-lifecycle/engine/doc-lifecycle.py drift-audit --repo . --mode full \
  --registry $D/registry.json --verdicts $D/verdicts.json \
  --waivers .github/doc-sync/drift-waivers.json
python3 plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/compare-shadow-lanes.py compare \
  --legacy $D/legacy-report.json --legacy-meta $D/legacy-meta.json \
  --shadow $D/shadow-report.json --shadow-meta $D/shadow-meta.json \
  --segments /tmp/shadow/segments.json
```

`segments.json` is not kept here: `slices` re-derives it from the repository, deterministically
and with no model, and it is the largest artifact of the run.
