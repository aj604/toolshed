#!/usr/bin/env python3
"""Guards the applier's capability boundary at the source level.

The applier (`plugins/doc-lifecycle/engine/doclifecycle/applier.py`) is the
engine's one write path, and model-generated content reaches it only as data
inside the edit-plan and report payloads. The behavioral half of that claim is
held by `tests/engine/applier_test.py` (hostile text lands verbatim, nothing
runs); this suite holds the static half, which no seam-level test can: the
module itself grants no shell, git, or exec capability — its one git use is
the read-only status behind `repository.worktree_changes`, imported, never
spawned here.

A wiring suite, like workflow-permissions_test.py: it reads source, not
behavior, which is why it lives here and not in tests/engine (engine suites
test only the two public seams).

Run: python3 tests/scripts/engine-capability_test.py
"""

import os
import unittest

APPLIER = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "plugins", "doc-lifecycle", "engine", "doclifecycle", "applier.py",
)


class ApplierGrantsNoCapability(unittest.TestCase):
    def setUp(self):
        with open(APPLIER, encoding="utf-8") as fh:
            self.source = fh.read()

    def test_no_subprocess_or_shell(self):
        for needle in ("subprocess", "os.system", "os.popen", "os.exec",
                       "os.spawn", "pty.", "shlex"):
            self.assertNotIn(needle, self.source, needle)

    def test_no_dynamic_execution(self):
        for needle in ("eval(", "exec(", "__import__", "importlib"):
            self.assertNotIn(needle, self.source, needle)

    def test_no_network(self):
        for needle in ("socket", "urllib", "http.client"):
            self.assertNotIn(needle, self.source, needle)

    def test_git_reads_come_from_the_repository_module(self):
        # The git touchpoints are imported read-only reads and nothing else:
        # the status listing behind the confinement check, and the committed
        # bytes the idempotency check derives its answer from.
        self.assertIn(
            "from .repository import head_bytes, worktree_changes",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
