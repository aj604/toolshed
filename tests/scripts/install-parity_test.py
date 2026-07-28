#!/usr/bin/env python3
"""Guards template/dogfood equivalence for the whole vendored install.

This repo runs the pipeline on itself, so `.github/workflows/doc-*.yml`,
`.github/doc-sync/*.py`, and the vendored `.github/doc-sync/engine/` tree must be
exactly what `scheduling-doc-sync` installs from the plugin with this install's
knobs. Editing one copy and forgetting the other ships wiring nobody runs, or
dogfoods wiring nobody gets.

Asserted by regenerating through apply-upgrade.py — the same engine the upgrade
lane uses — into a scratch tree and comparing bytes. Only the install-time knobs
(the lanes' cron schedules) are substituted, so any other divergence fails. The
engine is a whole-directory comparison rather than a rendering: it is vendored
wholesale, never rendered and never edited in place.

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

# The new engine is vendored wholesale rather than edited in place: the lanes that
# run it (doc-audit.yml, doc-apply.yml) call `.github/doc-sync/engine/`, and what
# they run must be the engine this repo sources and tests. Equivalence is a
# directory-tree comparison, per issue #57's distribution decision.
ENGINE_SRC = PLUGIN_ROOT / "engine"
ENGINE_DEST = ROOT / ".github" / "doc-sync" / "engine"


def load_apply_upgrade():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("apply_upgrade", UPGRADE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TemplatesMatchTheDogfoodInstall(unittest.TestCase):
    def setUp(self):
        self.mod = load_apply_upgrade()
        # This repository has adopted the registry contract, so its install
        # carries the new engine's lanes on top of the base wiring.
        self.new_lane = self.mod.adopted_registry(ROOT)
        self.assertTrue(
            self.new_lane,
            "this repository is the dogfood install of the new engine — "
            ".doc-lifecycle/registry.json must be landed")
        self.scripts = self.mod.scripts_for(ROOT)
        self.templates = self.mod.templates_for(ROOT)

    def test_every_vendored_script_matches_its_plugin_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.mod.copy_scripts(PLUGIN_ROOT, pathlib.Path(tmp),
                                  new_lane=self.new_lane)
            vendored = sorted(p.name for p in
                              (ROOT / ".github" / "doc-sync").glob("*.py"))
            self.assertEqual(
                vendored, sorted(self.scripts),
                ".github/doc-sync/ holds a different set of scripts than "
                "apply-upgrade.py installs")
            for name in self.scripts:
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
            self.mod.render_workflows(PLUGIN_ROOT, pathlib.Path(tmp), knobs,
                                      new_lane=self.new_lane)
            for name in self.templates:
                rendered = (pathlib.Path(tmp) / ".github" / "workflows"
                            / name).read_text()
                installed = (ROOT / ".github" / "workflows" / name).read_text()
                self.assertEqual(
                    installed, rendered,
                    f".github/workflows/{name} differs from the template it is "
                    f"installed from (skills/scheduling-doc-sync/{name}) — "
                    f"update both copies")

    def test_the_vendored_engine_tree_is_byte_identical(self):
        def tree(root):
            return {
                str(p.relative_to(root)): p.read_bytes()
                for p in sorted(root.rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts
            }

        self.assertTrue(
            ENGINE_DEST.is_dir(),
            ".github/doc-sync/engine/ is missing — the new engine's lanes run "
            "the vendored copy, not the plugin checkout")
        source, vendored = tree(ENGINE_SRC), tree(ENGINE_DEST)
        self.assertEqual(
            sorted(vendored), sorted(source),
            ".github/doc-sync/engine/ holds a different set of files than "
            "plugins/doc-lifecycle/engine/ — re-vendor it wholesale "
            "(apply-upgrade.py's copy_engine), never edit it in place")
        for name in sorted(source):
            self.assertEqual(
                vendored[name], source[name],
                f".github/doc-sync/engine/{name} differs from "
                f"plugins/doc-lifecycle/engine/{name} — the vendored engine is "
                f"a copy, and the plugin tree is the single source")

    def test_the_knobs_are_the_only_substitutions(self):
        # A new placeholder in a template with no knob behind it would render
        # into the install as literal {{TEXT}}; apply-upgrade fails loud on that,
        # and this asserts the guard is actually reachable from here.
        for name, placeholders in self.templates.items():
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
