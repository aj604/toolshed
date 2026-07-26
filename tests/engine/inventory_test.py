#!/usr/bin/env python3
"""Tests for the engine's registry-driven closed-world inventory.

Seam: doclifecycle.inventory.build_inventory(repo_root) — repository in, typed
inventory or typed invalid result out. Nothing below this seam is tested
directly.

Run: python3 tests/engine/inventory_test.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "..",
            "plugins", "doc-lifecycle", "engine",
        )
    ),
)

from doclifecycle.inventory import build_inventory  # noqa: E402


def registry(**overrides):
    reg = {"schema_version": 1, "roots": ["docs"], "rules": []}
    reg.update(overrides)
    return json.dumps(reg)


class InventoryTestCase(unittest.TestCase):
    def repo(self, files):
        """Materialize {relpath: contents} in a temp dir; return its path."""
        root = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        for rel, contents in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(contents)
        return root


class Classification(InventoryTestCase):
    def test_registered_document_carries_kind_and_no_set(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
        })

        result = build_inventory(repo)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [(d.path, d.kind, d.doc_set) for d in result.documents],
            [("docs/architecture.md", "living", None)],
        )


class Precedence(InventoryTestCase):
    def test_last_matching_rule_wins(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                sets=["adr"],
                rules=[
                    {"glob": "docs/**/*.md", "kind": "living"},
                    {"glob": "docs/adr/*.md", "kind": "narrative", "set": "adr"},
                ],
            ),
            "docs/adr/0001-use-json.md": "# ADR 1\n",
            "docs/architecture.md": "# Architecture\n",
        })

        result = build_inventory(repo)

        self.assertEqual(
            [(d.path, d.kind, d.doc_set) for d in result.documents],
            [
                ("docs/adr/0001-use-json.md", "narrative", "adr"),
                ("docs/architecture.md", "living", None),
            ],
        )

    def test_a_broad_rule_placed_last_overrides_a_specific_one(self):
        # The mirror of the case above: precedence is rule order, not glob
        # specificity, so the same two rules reversed classify differently.
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                sets=["adr"],
                rules=[
                    {"glob": "docs/adr/*.md", "kind": "narrative", "set": "adr"},
                    {"glob": "docs/**/*.md", "kind": "living"},
                ],
            ),
            "docs/adr/0001-use-json.md": "# ADR 1\n",
        })

        result = build_inventory(repo)

        self.assertEqual(
            [(d.kind, d.doc_set) for d in result.documents], [("living", None)]
        )

    def test_document_records_the_rule_that_classified_it(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[
                    {"glob": "docs/**/*.md", "kind": "living"},
                    {"glob": "docs/plans/*.md", "kind": "planning"},
                ],
            ),
            "docs/plans/rearchitecture.md": "# Plan\n",
        })

        result = build_inventory(repo)

        self.assertEqual(result.documents[0].rule, "docs/plans/*.md")


class ClosedWorld(InventoryTestCase):
    def test_unregistered_document_under_a_root_is_a_finding(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/guides/*.md", "kind": "narrative"}],
            ),
            "docs/guides/onboarding.md": "# Onboarding\n",
            "docs/stray.md": "# Stray\n",
        })

        result = build_inventory(repo)

        self.assertEqual(result.status, "ok")
        self.assertEqual([d.path for d in result.documents], ["docs/guides/onboarding.md"])
        self.assertEqual(
            [(f.code, f.path) for f in result.findings],
            [("unregistered-document", "docs/stray.md")],
        )

    def test_document_outside_every_root_is_neither_inventoried_nor_a_finding(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
            "src/notes.md": "# Notes\n",
        })

        result = build_inventory(repo)

        self.assertEqual([d.path for d in result.documents], ["docs/architecture.md"])
        self.assertEqual(result.findings, ())


class InvalidRegistry(InventoryTestCase):
    def test_unparseable_registry_invalidates_the_whole_run(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/architecture.md": "# Architecture\n",
        })

        result = build_inventory(repo)

        self.assertEqual(result.status, "invalid")
        self.assertEqual([p.code for p in result.problems], ["registry-unparseable"])
        # Not a partial inventory: an invalid run has no documents to report.
        self.assertFalse(hasattr(result, "documents"))

    def test_missing_registry_invalidates_the_whole_run(self):
        repo = self.repo({"docs/architecture.md": "# Architecture\n"})

        result = build_inventory(repo)

        self.assertEqual(result.status, "invalid")
        self.assertEqual([p.code for p in result.problems], ["registry-missing"])
        self.assertIn(".doc-lifecycle/registry.json", result.problems[0].message)


REJECTED_REGISTRIES = [
    ("not an object", "[]", "registry-invalid-shape"),
    (
        "future schema version",
        {"schema_version": 2, "roots": ["docs"], "rules": []},
        "registry-schema-version",
    ),
    (
        "missing schema version",
        {"roots": ["docs"], "rules": []},
        "registry-missing-field",
    ),
    ("missing roots", {"schema_version": 1, "rules": []}, "registry-missing-field"),
    ("missing rules", {"schema_version": 1, "roots": ["docs"]}, "registry-missing-field"),
    (
        "unknown top-level field",
        {"schema_version": 1, "roots": ["docs"], "rules": [], "policy": "strict"},
        "registry-unknown-field",
    ),
    (
        "no roots declared",
        {"schema_version": 1, "roots": [], "rules": []},
        "registry-invalid-shape",
    ),
    (
        "rule is not an object",
        {"schema_version": 1, "roots": ["docs"], "rules": ["docs/**/*.md"]},
        "registry-invalid-rule",
    ),
    (
        "rule missing glob",
        {"schema_version": 1, "roots": ["docs"], "rules": [{"kind": "living"}]},
        "registry-invalid-rule",
    ),
    (
        "rule missing kind",
        {"schema_version": 1, "roots": ["docs"], "rules": [{"glob": "docs/*.md"}]},
        "registry-invalid-rule",
    ),
    (
        "rule has unknown field",
        {
            "schema_version": 1,
            "roots": ["docs"],
            "rules": [{"glob": "docs/*.md", "kind": "living", "owner": "avery"}],
        },
        "registry-invalid-rule",
    ),
    (
        "unknown kind",
        {
            "schema_version": 1,
            "roots": ["docs"],
            "rules": [{"glob": "docs/*.md", "kind": "reference"}],
        },
        "registry-unknown-kind",
    ),
    (
        "undeclared set",
        {
            "schema_version": 1,
            "roots": ["docs"],
            "rules": [{"glob": "docs/*.md", "kind": "narrative", "set": "adr"}],
        },
        "registry-unknown-set",
    ),
    (
        "absolute glob",
        {
            "schema_version": 1,
            "roots": ["docs"],
            "rules": [{"glob": "/etc/*.md", "kind": "living"}],
        },
        "registry-unsafe-glob",
    ),
    (
        "traversing glob",
        {
            "schema_version": 1,
            "roots": ["docs"],
            "rules": [{"glob": "docs/../../*.md", "kind": "living"}],
        },
        "registry-unsafe-glob",
    ),
    (
        "backslash glob",
        {
            "schema_version": 1,
            "roots": ["docs"],
            "rules": [{"glob": "docs\\*.md", "kind": "living"}],
        },
        "registry-unsafe-glob",
    ),
    (
        "absolute root",
        {"schema_version": 1, "roots": ["/etc"], "rules": []},
        "registry-unsafe-root",
    ),
    (
        "traversing root",
        {"schema_version": 1, "roots": ["../secrets"], "rules": []},
        "registry-unsafe-root",
    ),
    (
        "whole-repo root",
        {"schema_version": 1, "roots": ["."], "rules": []},
        "registry-unsafe-root",
    ),
    (
        "unsafe exclude",
        {"schema_version": 1, "roots": ["docs"], "exclude": ["../*"], "rules": []},
        "registry-unsafe-exclude",
    ),
    (
        "set is not a string",
        {"schema_version": 1, "roots": ["docs"], "sets": [1], "rules": []},
        "registry-invalid-shape",
    ),
]


class RegistryValidation(InventoryTestCase):
    def test_every_rejected_registry_yields_its_typed_problem(self):
        for name, body, code in REJECTED_REGISTRIES:
            with self.subTest(name):
                text = body if isinstance(body, str) else json.dumps(body)
                repo = self.repo({
                    ".doc-lifecycle/registry.json": text,
                    "docs/architecture.md": "# Architecture\n",
                })

                result = build_inventory(repo)

                self.assertEqual(result.status, "invalid")
                self.assertIn(code, [p.code for p in result.problems])
                self.assertFalse(hasattr(result, "documents"))

    def test_every_problem_is_reported_not_just_the_first(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": json.dumps({
                "schema_version": 1,
                "roots": ["docs"],
                "rules": [
                    {"glob": "docs/*.md", "kind": "reference"},
                    {"glob": "/absolute.md", "kind": "living"},
                ],
            }),
            "docs/architecture.md": "# Architecture\n",
        })

        result = build_inventory(repo)

        self.assertEqual(
            sorted(p.code for p in result.problems),
            ["registry-unknown-kind", "registry-unsafe-glob"],
        )

    def test_schema_version_problem_says_how_to_recover(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": json.dumps(
                {"schema_version": 99, "roots": ["docs"], "rules": []}
            ),
        })

        result = build_inventory(repo)

        message = result.problems[0].message
        self.assertIn("99", message)
        self.assertIn("1", message)
        self.assertIn("migrat", message.lower())


class DeclaredRoots(InventoryTestCase):
    def test_declared_root_that_does_not_exist_invalidates_the_run(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                roots=["docs", "handbook"],
                rules=[{"glob": "**/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
        })

        result = build_inventory(repo)

        self.assertEqual(result.status, "invalid")
        self.assertEqual([p.code for p in result.problems], ["registry-missing-root"])
        self.assertIn("handbook", result.problems[0].message)

    def test_a_root_can_be_a_single_file(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                roots=["CLAUDE.md", "docs"],
                rules=[{"glob": "**/*.md", "kind": "living"}],
            ),
            "CLAUDE.md": "# Repo guide\n",
            "docs/architecture.md": "# Architecture\n",
        })

        result = build_inventory(repo)

        self.assertEqual(
            [d.path for d in result.documents], ["CLAUDE.md", "docs/architecture.md"]
        )

    def test_excluded_subtree_is_neither_inventoried_nor_a_finding(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                exclude=["docs/vendor/**"],
                rules=[{"glob": "docs/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
            "docs/vendor/upstream.md": "# Upstream\n",
        })

        result = build_inventory(repo)

        self.assertEqual([d.path for d in result.documents], ["docs/architecture.md"])
        self.assertEqual(result.findings, ())


class Symlinks(InventoryTestCase):
    """Inventory refuses symlinks outright; #67's path authorization owns the
    general rule. A symlink is reported, never followed and never inventoried."""

    def test_symlinked_document_is_a_finding_not_a_document(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
            "secrets/credentials.md": "token: hunter2\n",
        })
        os.symlink(
            os.path.join(repo, "secrets", "credentials.md"),
            os.path.join(repo, "docs", "innocent.md"),
        )

        result = build_inventory(repo)

        self.assertEqual([d.path for d in result.documents], ["docs/architecture.md"])
        self.assertEqual(
            [(f.code, f.path) for f in result.findings],
            [("symlinked-path", "docs/innocent.md")],
        )

    def test_symlinked_directory_is_reported_and_not_followed(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
            "elsewhere/leaked.md": "# Leaked\n",
        })
        os.symlink(os.path.join(repo, "elsewhere"), os.path.join(repo, "docs", "alias"))

        result = build_inventory(repo)

        self.assertEqual([d.path for d in result.documents], ["docs/architecture.md"])
        self.assertEqual(
            [(f.code, f.path) for f in result.findings],
            [("symlinked-path", "docs/alias")],
        )


class Digests(InventoryTestCase):
    # `printf '# Architecture\n' | shasum -a 256` — an independent literal, not
    # a value recomputed the way the engine computes it.
    ARCHITECTURE_DIGEST = (
        "2e7cb38229f7877e569cc05dd9c8fb71b30954ad2c9978328d69f5d377f81505"
    )

    def inventory(self, doc_contents="# Architecture\n", **reg):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "living"}], **reg
            ),
            "docs/architecture.md": doc_contents,
        })
        return build_inventory(repo)

    def test_document_digest_is_the_sha256_of_its_bytes(self):
        result = self.inventory()

        self.assertEqual(result.documents[0].digest, self.ARCHITECTURE_DIGEST)

    def test_inventory_digest_is_stable_across_runs(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "living"}],
            ),
            "docs/architecture.md": "# Architecture\n",
        })

        self.assertEqual(
            build_inventory(repo).digest, build_inventory(repo).digest
        )

    def test_inventory_digest_changes_when_a_document_changes(self):
        self.assertNotEqual(
            self.inventory().digest, self.inventory("# Architecture v2\n").digest
        )

    def test_inventory_digest_changes_when_classification_changes(self):
        living = self.inventory()
        planning = build_inventory(self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/**/*.md", "kind": "planning"}],
            ),
            "docs/architecture.md": "# Architecture\n",
        }))

        self.assertNotEqual(living.digest, planning.digest)

    def test_registry_digest_ignores_formatting_but_not_meaning(self):
        rules = [{"glob": "docs/**/*.md", "kind": "living"}]
        compact = build_inventory(self.repo({
            ".doc-lifecycle/registry.json": json.dumps(
                {"schema_version": 1, "roots": ["docs"], "rules": rules},
                separators=(",", ":"),
            ),
            "docs/architecture.md": "# Architecture\n",
        }))
        reordered = build_inventory(self.repo({
            ".doc-lifecycle/registry.json": json.dumps(
                {"rules": rules, "roots": ["docs"], "schema_version": 1}, indent=4
            ),
            "docs/architecture.md": "# Architecture\n",
        }))
        narrowed = build_inventory(self.repo({
            ".doc-lifecycle/registry.json": registry(
                rules=[{"glob": "docs/*.md", "kind": "living"}]
            ),
            "docs/architecture.md": "# Architecture\n",
        }))

        self.assertEqual(compact.registry_digest, reordered.registry_digest)
        self.assertNotEqual(compact.registry_digest, narrowed.registry_digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
