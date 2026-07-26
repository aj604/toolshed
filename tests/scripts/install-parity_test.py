#!/usr/bin/env python3
"""Guards template/dogfood equivalence for the whole vendored install.

This repo runs the pipeline on itself, so `.github/workflows/doc-*.yml` and
`.github/doc-sync/*.py` must be exactly what `scheduling-doc-sync` installs from
the plugin with this install's knobs. Editing one copy and forgetting the other
ships wiring nobody runs, or dogfoods wiring nobody gets.

Asserted by regenerating through apply-upgrade.py — the same engine the upgrade
lane uses — into a scratch tree and comparing bytes. Only the install-time knobs
(cron schedules, blast-radius cap) are substituted, so any other divergence
fails.

Run: python3 tests/scripts/install-parity_test.py
"""

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "doc-lifecycle"
UPGRADE = PLUGIN_ROOT / "skills" / "scheduling-doc-sync" / "scripts" / "apply-upgrade.py"


def load_apply_upgrade():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("apply_upgrade", UPGRADE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TemplatesMatchTheDogfoodInstall(unittest.TestCase):
    def setUp(self):
        self.mod = load_apply_upgrade()

    def test_every_vendored_script_matches_its_plugin_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.mod.copy_scripts(PLUGIN_ROOT, pathlib.Path(tmp))
            vendored = sorted(p.name for p in
                              (ROOT / ".github" / "doc-sync").glob("*.py"))
            self.assertEqual(
                vendored, sorted(self.mod.SCRIPTS),
                ".github/doc-sync/ holds a different set of scripts than "
                "apply-upgrade.py installs")
            for name in self.mod.SCRIPTS:
                copied = (pathlib.Path(tmp) / ".github" / "doc-sync"
                          / name).read_text()
                installed = (ROOT / ".github" / "doc-sync" / name).read_text()
                self.assertEqual(
                    installed, copied,
                    f".github/doc-sync/{name} differs from its plugin source — "
                    f"re-copy it (the dogfood install is a vendored copy)")

    def test_every_installed_workflow_regenerates_byte_identically(self):
        knobs = self.mod.read_knobs(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            self.mod.render_workflows(PLUGIN_ROOT, pathlib.Path(tmp), knobs)
            for name in self.mod.TEMPLATE_PLACEHOLDERS:
                rendered = (pathlib.Path(tmp) / ".github" / "workflows"
                            / name).read_text()
                installed = (ROOT / ".github" / "workflows" / name).read_text()
                self.assertEqual(
                    installed, rendered,
                    f".github/workflows/{name} differs from the template it is "
                    f"installed from (skills/scheduling-doc-sync/{name}) — "
                    f"update both copies")

    def test_the_knobs_are_the_only_substitutions(self):
        # A new placeholder in a template with no knob behind it would render
        # into the install as literal {{TEXT}}; apply-upgrade fails loud on that,
        # and this asserts the guard is actually reachable from here.
        for name, placeholders in self.mod.TEMPLATE_PLACEHOLDERS.items():
            template = (PLUGIN_ROOT / "skills" / "scheduling-doc-sync"
                        / name).read_text()
            for placeholder in placeholders:
                self.assertIn(
                    placeholder, template,
                    f"{name}: apply-upgrade.py expects {placeholder}, which the "
                    f"template no longer carries")
            stripped = template
            for placeholder in placeholders:
                stripped = stripped.replace(placeholder, "")
            unknown = sorted(set(self.mod.LEFTOVER_RE.findall(stripped)))
            self.assertEqual(
                unknown, [],
                f"{name}: template placeholder(s) {unknown} have no knob in "
                f"apply-upgrade.py")


if __name__ == "__main__":
    unittest.main()
