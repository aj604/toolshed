#!/usr/bin/env python3
"""Guards template/dogfood equivalence for the whole vendored install.

This repo runs the pipeline on itself, so `.github/workflows/doc-*.yml`,
`.doc-lifecycle/wiring/*.py`, and the vendored `.doc-lifecycle/wiring/engine/`
tree must be exactly what `scheduling-doc-sync` installs from the plugin with
this install's knobs. Editing one copy and forgetting the other ships wiring
nobody runs, or dogfoods wiring nobody gets.

Asserted by regenerating through apply-upgrade.py — the same engine the upgrade
lane uses — into a scratch tree and comparing bytes. Only the install-time knobs
(the lanes' cron schedules) are substituted, so any other divergence fails. The
engine is a whole-directory comparison rather than a rendering: it is vendored
wholesale, never rendered and never edited in place.

This suite also owns the one static claim about the move that produced this
layout (aj604/toolshed#133): nothing the plugin ships still reaches for the
pre-#133 install directory. Whole-tree equivalence between plugin and install is
already its subject, so a path that survived the move is its business too.

Run: python3 tests/scripts/install-parity_test.py
"""

import importlib.util
import os
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "doc-lifecycle"
UPGRADE = PLUGIN_ROOT / "skills" / "scheduling-doc-sync" / "scripts" / "apply-upgrade.py"

# The new engine is vendored wholesale rather than edited in place: the lanes that
# run it (doc-audit.yml, doc-apply.yml) call `.doc-lifecycle/wiring/engine/`, and
# what they run must be the engine this repo sources and tests. Equivalence is a
# directory-tree comparison, per issue #57's distribution decision.
ENGINE_SRC = PLUGIN_ROOT / "engine"
ENGINE_DEST = ROOT / ".doc-lifecycle" / "wiring" / "engine"

LEGACY_ROOT = ".github/doc-sync"
# `os.path.join(".github", "doc-sync", …)` and `repo / ".github" / "doc-sync"`:
# the same path, spelled so that neither `.github/doc-sync` nor
# `.doc-lifecycle` appears anywhere in the line. Anchored on the separator that
# makes it a path component, so the lane's own name — `git config user.name
# "doc-sync"` — is not mistaken for one.
SPLIT_LEGACY_COMPONENT = re.compile(
    r"""(?:[,/]\s*["']doc-sync["']|["']doc-sync["']\s*[,/])""")

# The two modules that name the pre-#133 directory on purpose, and why. Every
# other mention in a shipped template or script is a reference the relocation
# missed, and would send a lane at a path that no longer exists.
LEGACY_REFERENCE_ALLOWED = {
    # The migration door's legacy contract. It recognizes a consumer arriving
    # from a genuinely pre-registry install, which really does live there;
    # repointing it would break recognition of the installs it exists for.
    "engine/doclifecycle/migrate.py",
    # The path classifier keeps the old prefix beside the new one so an install
    # that has not yet relocated — and any leftover the relocation left behind —
    # is still classified as wiring rather than handed back as source.
    "engine/doclifecycle/paths.py",
    # The relocation itself: the code that carries an install out of the old
    # directory, the authority that permits exactly that, and the summary a
    # maintainer reads when it happens all have to name where it is leaving.
    "skills/scheduling-doc-sync/scripts/apply-upgrade.py",
    "skills/scheduling-doc-sync/scripts/stage-upgrade.py",
    "skills/scheduling-doc-sync/scripts/render-report.py",
}


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
            wiring = ROOT / ".doc-lifecycle" / "wiring"
            vendored = sorted(p.name for p in wiring.glob("*.py"))
            self.assertEqual(
                vendored, sorted(self.scripts),
                ".doc-lifecycle/wiring/ holds a different set of scripts than "
                "apply-upgrade.py installs")
            for name in self.scripts:
                copied = (pathlib.Path(tmp) / ".doc-lifecycle" / "wiring"
                          / name).read_text()
                installed = (wiring / name).read_text()
                self.assertEqual(
                    installed, copied,
                    f".doc-lifecycle/wiring/{name} differs from its plugin source — "
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
            ".doc-lifecycle/wiring/engine/ is missing — the new engine's lanes run "
            "the vendored copy, not the plugin checkout")
        source, vendored = tree(ENGINE_SRC), tree(ENGINE_DEST)
        self.assertEqual(
            sorted(vendored), sorted(source),
            ".doc-lifecycle/wiring/engine/ holds a different set of files than "
            "plugins/doc-lifecycle/engine/ — re-vendor it wholesale "
            "(apply-upgrade.py's copy_engine), never edit it in place")
        for name in sorted(source):
            self.assertEqual(
                vendored[name], source[name],
                f".doc-lifecycle/wiring/engine/{name} differs from "
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


class TheOldInstallDirectoryIsGone(unittest.TestCase):
    """aj604/toolshed#133: nothing still reaches for `.github/doc-sync/`.

    A missed reference is a lane calling a path that no longer exists — a
    failure a consumer discovers on their first run after upgrading, at 01:00,
    with no one watching. Cheaper to fail here.
    """

    def test_no_shipped_template_or_script_names_the_old_directory(self):
        offenders = []
        for path in sorted(PLUGIN_ROOT.rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".yml"):
                continue
            rel = str(path.relative_to(PLUGIN_ROOT))
            if rel in LEGACY_REFERENCE_ALLOWED:
                continue
            for number, line in enumerate(
                    path.read_text().splitlines(), 1):
                # The joined spelling, and the split one. A path assembled
                # component by component — `os.path.join(".github",
                # "doc-sync", …)` — reads as neither the old path nor the new
                # one to a search for either, which is exactly how one survived
                # the move with its own docstring already updated.
                if LEGACY_ROOT in line or SPLIT_LEGACY_COMPONENT.search(line):
                    offenders.append(f"{rel}:{number}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            f"these still name {LEGACY_ROOT}/, which a current install does not "
            f"have — repoint them at .doc-lifecycle/ (or, if the reference is "
            f"deliberately about a pre-#133 install, say so in "
            f"LEGACY_REFERENCE_ALLOWED)")

    def test_the_dogfooded_install_holds_no_trace_of_it(self):
        self.assertFalse((ROOT / ".github" / "doc-sync").exists(),
                         "this repo's own install has not been relocated")
        self.assertFalse((ROOT / ".github" / "doc-sync-marker").exists(),
                         "the loose marker survived the relocation")

    def test_the_three_tiers_are_where_the_contract_says(self):
        root = ROOT / ".doc-lifecycle"
        for name in ("registry.json", "audit-scope.json", "drift-waivers.json",
                     "evidence-tools.json", "installed-version"):
            self.assertTrue((root / name).is_file(),
                            f".doc-lifecycle/{name} is missing")
        self.assertTrue((root / "wiring" / "engine").is_dir())
        self.assertTrue((root / "state" / "sync-marker").is_file())
        # `.github/` keeps the workflow YAML and nothing else of the plugin's.
        self.assertEqual(
            sorted(p.name for p in (ROOT / ".github").iterdir()),
            ["scripts", "workflows"],
            ".github/ holds doc-lifecycle content other than the workflows")


if __name__ == "__main__":
    unittest.main()
