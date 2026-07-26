"""doc-lifecycle engine: stdlib-only library behind every skill and workflow.

Library functions are the implementation; the `python3 -m doclifecycle`
entrypoints are thin wrappers over them, so a command and an import cannot
disagree.
"""

# The version of the artifacts this engine emits (inventory payloads and
# reports today; approval sets and edit plans later). Distinct from
# `registry.SCHEMA_VERSION`, which versions the registry file a consumer writes.
ARTIFACT_SCHEMA_VERSION = 1

# The version of the audit policy this engine implements — what the detectors
# ask of a document, independent of the artifact shape they emit. A report pins
# it in lineage, so a rules change makes prior reports stale instead of
# silently reusable. Bump it when a policy change would alter a verdict.
RULESET_VERSION = 1

# The published plugin version this engine ships inside. Pinned in lineage, so
# it must track `plugins/doc-lifecycle/.claude-plugin/plugin.json` — the engine
# is also vendored into consumers without that manifest, so it cannot read it.
# `tests/engine/report_test.py` fails loudly when the two drift.
PLUGIN_VERSION = "0.14.0"
