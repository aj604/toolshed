# Shadow-mode parity gate — cycle record (issue #76)

The artifacts of one full shadow cycle of the new read-only audit lane over this repository's
real documentation, run alongside the still-live legacy `doc-sync` lane. The gate itself — its
pass criteria, pre-registered before the cycle, and its verdict — is
`docs/plans/2026-07-26-shadow-parity-gate.md`. This directory is that record's evidence.

| File | What it is |
|---|---|
| `registry.json` | the classification the shadow run used; derivation rules are declared in the gate record |
| `shadow-cycle.py` | the harness: worktree digest, per-document slices, and the two-round verdict merge — **removed** by aj604/toolshed#77 along with the legacy lane it compared against; read it at the recorded commit below, or `git show 939458f:tests/baselines/shadow-parity-gate/shadow-cycle.py` |
| `verdicts.json` | what the model workers returned, merged across all three rounds — the run's one irreproducible input |
| `shadow-report.json` | the validated report `drift-audit` produced from it |
| `shadow-meta.json` | the shadow run's cost, rounds, and model |
| `legacy-report.json` | the legacy lane's most recent produced report, from run `28847329392` |
| `legacy-meta.json` | that run's cost, turns, duration, and scope |
| `comparison.json` | `compare-shadow-lanes.py compare` over the two lanes' artifacts |

## The commit the cycle ran against

The report's lineage pins base commit `90ead6d4ec48e5cd2fd7b69551e6a03f6dc358b6`, tree
`e19b2f1400137f8b286f896c88fd7c3ef2df8270`. **That commit is not an ancestor of this branch**:
the branch was rebased onto `main` after the cycle, which rewrote it. The tree it names differs
from the rebased branch in four audited documents — `docs/decisions.md`,
`plugins/doc-lifecycle/engine/README.md`, and the `bootstrapping-docs` and `scheduling-doc-sync`
`SKILL.md`s — all of them changed by #74's merge, not by the cycle.

So `validate-report --repo .` calls this report stale at any commit on this branch, which is
the contract working as designed (`plugin_version` alone marks every prior report stale). The
gate record's adjudications quote the file and the fact they rest on, not just a line number,
for that reason: line numbers moved, the facts did not. Re-deriving the report at a later
commit produces a different report, and should.

Reproducing the derived half, from a checkout at that commit — which is where the two scripts
below still live. Both were removed from the tip by aj604/toolshed#77: `shadow-cycle.py` and
`compare-shadow-lanes.py` compared this lane against the legacy one, and retired with it. The
recipe is preserved as run, not as something to run here.

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

### What is kept, and why not everything

`verdicts.json` and the two `legacy-*` files are irreproducible — one is 55 model sessions of
output, the others are a CI artifact whose lane has been failing since 2026-07-12. Those had to
be kept.

`shadow-report.json` and `comparison.json` are derivable from them, and are kept anyway: they
are what a reader checking the verdict actually reads, and re-deriving them needs a checkout at
a commit this branch no longer contains. `segments.json` is derivable too and is *not* kept —
it is 687 KB of intermediate nobody reads, and `slices` regenerates it with no model. The rule
is "keep what the verdict is checked against", not "keep whatever cannot be recomputed".
