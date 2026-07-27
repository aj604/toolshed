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
