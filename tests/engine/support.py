"""Shared fixtures for the engine suites.

Puts the engine package on `sys.path` (it ships inside the plugin, not as an
installed distribution) and builds throwaway repositories on disk — the suites
test real filesystem behavior, never a mocked one.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ENGINE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "plugins", "doc-lifecycle", "engine"
    )
)
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)


def run_command(*argv, cwd=None):
    """Invoke `python3 -m doclifecycle` as a subprocess — the command seam."""
    env = dict(os.environ, PYTHONPATH=ENGINE)
    return subprocess.run(
        [sys.executable, "-m", "doclifecycle", *argv],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


# A registry covering one document of each kind, with the planning rule in a
# declared set so a bulk enumeration has something to expand. Shared by the
# suites that need a corpus rather than one file, so "the same corpus" means
# the same bytes in each.
CORPUS_REGISTRY = """{
  "schema_version": 1,
  "roots": ["docs"],
  "sets": ["plans"],
  "rules": [
    {"glob": "docs/*.md", "kind": "living"},
    {"glob": "docs/guides/*.md", "kind": "narrative"},
    {"glob": "docs/plans/*.md", "kind": "planning", "set": "plans"}
  ]
}
"""

# One sentence for suites that need the same content in two places.
SHARED_SENTENCE = "Fee changes require a migration note."


class RepoTestCase(unittest.TestCase):
    def repo(self, files):
        """Materialize {repo-relative path: contents} in a temp dir; return it."""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel, contents in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(contents)
        return root
