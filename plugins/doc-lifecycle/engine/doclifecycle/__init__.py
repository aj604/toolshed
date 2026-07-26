"""doc-lifecycle engine: stdlib-only library behind every skill and workflow.

Library functions are the implementation; the `python3 -m doclifecycle`
entrypoints are thin wrappers over them, so a command and an import cannot
disagree.
"""

# The version of the artifacts this engine emits (inventory payloads today;
# reports, approval sets, and edit plans later). Distinct from
# `registry.SCHEMA_VERSION`, which versions the registry file a consumer writes.
ARTIFACT_SCHEMA_VERSION = 1
