# Preserved drift-report artifacts

Two real `doc-audit` run artifacts from this repository, retrieved from GitHub
Actions storage before it expired them. They are the positive and negative cases
for the report-seeding revalidation gate that Phase B (#171) specifies, and the
evidence behind the cost baseline that phase is designed against
(`docs/plans/2026-08-02-assertion-ledger-bootstrap-phase-b.md`).

Both ran against `base_commit 5ef1471df810df79726285d94104df3dde678faa`, with
the same registry, scope, and evidence-tools configuration, 24 hours apart.

| | `2026-08-01-complete/` | `2026-08-02-partial/` |
|---|---|---|
| run | [30683683887](https://github.com/aj604/toolshed/actions/runs/30683683887) | [30732219548](https://github.com/aj604/toolshed/actions/runs/30732219548) |
| `status` | `findings` | `partial` |
| documents examined | 31 / 31 | 6 / 31 |
| documents incomplete | 0 | 25 |
| records | 132 | 2 |
| cost | $69.71 | $68.97 |
| turns | 165 | 184 |
| duration | 62 min | 36 min |
| report `digest` field | `adb168df05ed9db94312368c8a95fbf7be2fcd35fd12a07117b86d388daa5385` | `ccfb67808a742bb593cf17ea3b676619b37e0ec979fe3efeeb069c8e6266ed2f` |
| file sha256 | `36435ab74542c27633ea3864680126ec4ca1e3fd48d0b9d99de5c0ea0701ec07` | `7508ae5eea65e2fb8441afccddbb9307cc396f474dcb998cb9d64d101af413a1` |

## Why each is kept

**`2026-08-01-complete/` is the valid-seed case.** It is the first complete
full-corpus audit on record for this repository: every registered document
examined, nothing incomplete. It carries **per-unit** data for every unit rather
than only for findings —

```json
{"unit": "<digest>", "assertion_class": "factual", "obligation": "evidence",
 "location": "CLAUDE.md:3", "kind": "structure", "tier": 1,
 "evidence": {"observed": "..."}}
```

— which is what makes seeding worth doing at all: it supplies `class` and
`obligation` for every unit plus the evidence a model actually consulted. Class
distribution across its 1,988 classified living units: factual 1,265 (63.6%),
normative 441 (22.2%), rationale 174 (8.8%), non-assertive 108 (5.4%). Because
Phase A forbids normative and rationale units from carrying probe strategies,
36.4% of units are class-forced to a strategy with no model judgment required.

**`2026-08-02-partial/` is the must-seed-nothing case.** It returned
`"no verdict set was returned for this document"` for all 25 living documents and
examined only the six narrative documents, whose `anchor` obligation needs no
model. A seeding implementation that accepts it is broken: a partial report must
seed nothing, per #169.

The pair is also the clearest evidence for #169's premise. Same repository, same
commit, same configuration: $69.71 for 132 findings across 31 documents, then
$68.97 for 2 findings across 6. Cost is fixed; output is not.

## Handling

These are immutable evidence. Do not regenerate, reformat, or re-serialize them
— the file hashes above are what makes them usable as fixtures, and a rewritten
file is no longer the artifact the runs produced. `tests/fixtures/` is declared a
non-gate root by `.github/scripts/release-manifest.py`, so nothing here gates a
release.
