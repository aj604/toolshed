#!/usr/bin/env python3
"""Guards every workflow's `plugin_marketplaces:` value against the format
`anthropics/claude-code-action` accepts.

Root cause this locks in: the action's marketplace-URL validator requires an
`https://` URL to end in `.git` (regex `/^https:\\/\\/[...]+\\.git$/`) and passes
local paths straight through. The old pin `…/toolshed.git#v<version>` carries a
`#<ref>` fragment after `.git`, so the action now rejects it with
"Invalid marketplace URL format" — breaking every model step. The durable pin is
a local checkout of the release tag, referenced by path.

Contract asserted: no shipped `plugin_marketplaces` value is an `https://` URL
that fails to end in `.git`. Local-path pins (including `${{ runner.temp }}/…`
expressions) and plain `.git` URLs pass; a `#ref`-fragmented URL fails.

Run: python3 tests/scripts/marketplace-pin_test.py
"""

import glob
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

WORKFLOW_GLOBS = [
    # Published templates the scheduling-doc-sync skill installs.
    "plugins/doc-lifecycle/skills/scheduling-doc-sync/*.yml",
    # This repo's own dogfooded install.
    ".github/workflows/*.yml",
]

MARKETPLACE_LINE = re.compile(r"plugin_marketplaces:\s*(?P<value>\S.*?)\s*$")


def marketplace_values():
    """Yield (path, lineno, value) for every plugin_marketplaces: assignment."""
    seen = set()
    for pattern in WORKFLOW_GLOBS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    m = MARKETPLACE_LINE.search(line)
                    if not m:
                        continue
                    value = m.group("value").strip().strip("'\"")
                    yield os.path.relpath(path, ROOT), lineno, value


class MarketplacePin(unittest.TestCase):
    def test_workflows_exist(self):
        # Guard against the globs silently matching nothing (renamed dirs, etc.).
        self.assertTrue(
            list(marketplace_values()),
            "no plugin_marketplaces: lines found — did the workflow layout move?",
        )

    def test_no_https_url_rejected_by_action(self):
        offenders = []
        for path, lineno, value in marketplace_values():
            if value.startswith("https://") and not value.endswith(".git"):
                offenders.append(f"{path}:{lineno} -> {value}")
        self.assertEqual(
            offenders,
            [],
            "these plugin_marketplaces values are https URLs not ending in .git, "
            "which anthropics/claude-code-action rejects (pin via a local checkout "
            "of the release tag instead):\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
