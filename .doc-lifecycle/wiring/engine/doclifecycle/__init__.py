"""doc-lifecycle engine: stdlib-only library behind every skill and workflow.

Library functions are the implementation; the `python3 -m doclifecycle`
entrypoints are thin wrappers over them, so a command and an import cannot
disagree.
"""

# The version of the artifacts this engine emits (inventory payloads and
# reports today; approval sets and edit plans later). Distinct from
# `registry.SCHEMA_VERSION`, which versions the registry file a consumer writes.
ARTIFACT_SCHEMA_VERSION = 1

# The version of the audit policy this engine implements — what the audit
# engine asks of a document, independent of the artifact shape it emits. A
# report pins it in lineage, so a rules change makes prior reports stale
# instead of silently reusable. Bump it when a change would alter a verdict.
# 2: a `> As of` reference that resolves to no path is reported unresolvable
# rather than as a file that has left the repository (#97).
# 3: a DISTILL verdict may name the residue document it authors, so a response
# that was refused as `bloat-destination-forbidden` is now recorded (#109).
# 4: a drift verdict may name its unit by the segmenter's per-document ordinal
# instead of the 64-character digest — an integer `drift-verdict-unknown-ordinal`
# rejects outside a document's range, where before any non-digest-string `unit`
# was uniformly `classification-unknown-unit` (#116).
# 5: a drift verdict may cite a declared local tool instead of a repository
# path, so a claim only that tool can settle is VERIFIED or STALE where the
# evidence boundary had left UNVERIFIABLE as the only legal answer (#115).
# 6: a STALE verdict over a soft-wrapped assertion unit may carry LF-separated
# replacement text, so applying the worker-authored fix preserves physical-line
# shape instead of collapsing the passage to one long line (#126).
# 7: planning lifecycle state is file-bound and verdicts report it rather than
# asserting it; a DISTILL verdict against a non-planning document is refused;
# anchor reference candidates are resolved through the canonical path policy;
# and post-write confinement compares the diff to the plan's own written paths
# (#57 review remediation).
# 8: every living assertion carries a review obligation; normative and
# rationale classifications can no longer waive judgment, and every judgment
# records the closed obligation it discharged (#154).
# 9: bloat completion preserves an authentic, re-derivable chunk plan and
# binds each received result to its verdict contents; incomplete fan-out can
# no longer manufacture a clean report (#152).
# 10: RETIRE-DOC, DISTILL, and MERGE-DOC bind the source document's complete
# current deterministic unit set; incomplete or duplicate unit selections are
# refused before a finding can become report or approval authority (#153).
RULESET_VERSION = 10

# The published plugin version this engine ships inside. It must track
# `plugins/doc-lifecycle/.claude-plugin/plugin.json` — the engine is also
# vendored into consumers without that manifest, so it cannot read it.
# `tests/engine/report_test.py` fails loudly when the two drift.
PLUGIN_VERSION = "0.46.12"

# The artifact-facing engine compatibility marker stored in lineage's existing
# `plugin_version` field. Bump it only when a plugin release makes prior
# artifacts unsafe to reuse for a reason not already expressed by the schema or
# ruleset versions. A wording-only release therefore keeps compatible artifacts
# fresh while a genuinely incompatible marker still fails closed.
PLUGIN_COMPATIBILITY_VERSION = "0.44.3"
