#!/usr/bin/env python3
"""The assertion-ledger contract and library ``plan_sync`` seam.

Run: python3 tests/engine/sync_test.py
"""

import json
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sync_support import FILES, SyncRepoTestCase  # noqa: E402

from doclifecycle import ARTIFACT_SCHEMA_VERSION  # noqa: E402
from doclifecycle.inventory import build_inventory  # noqa: E402
from doclifecycle.results import Invalid  # noqa: E402
from doclifecycle.segment import segment_document  # noqa: E402
from doclifecycle.sync import (  # noqa: E402
    DEFAULT_LEDGER_PATH,
    MODE_BOOTSTRAP,
    MODE_RECONCILE,
    load_assertion_ledger,
    plan_sync,
)

AS_OF = "2026-08-06"


def codes(result):
    return [problem.code for problem in result.problems]


def canonical_digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class UnchangedSync(SyncRepoTestCase):
    def test_clean_result_has_an_empty_digest_bound_work_order(self):
        repo = self.sync_repo()

        result = plan_sync(repo, AS_OF)

        self.assertEqual(result.status, "clean")
        payload = result.to_dict()
        self.assertEqual(payload["mode"], "sync")
        self.assertEqual(payload["as_of"], AS_OF)
        self.assertEqual(payload["work_order"]["units"], [])
        self.assertEqual(payload["work_order"]["mode"], "sync")
        self.assertEqual(payload["work_order"]["total_chunk_count"], 1)
        self.assertTrue(payload["work_order"]["session_id"].startswith("s-"))
        self.assertTrue(payload["work_order"]["chunk_id"].startswith("c-"))
        bindings = payload["work_order"]["bindings"]
        with open(os.path.join(repo, DEFAULT_LEDGER_PATH), "rb") as fh:
            expected_ledger = hashlib.sha256(fh.read()).hexdigest()
        inventory = build_inventory(repo)
        segmentation = segment_document(repo, "docs/architecture.md")
        expected_unit_set = canonical_digest({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "documents": [{
                "doc": "docs/architecture.md",
                "units": [unit.digest for unit in segmentation.units
                          if unit.assertion_capable],
            }],
        })
        self.assertEqual(bindings, {
            "ledger_digest": expected_ledger,
            "inventory_digest": inventory.digest,
            "unit_set_digest": expected_unit_set,
            "budget_digest": canonical_digest(payload["work_order"]["budget"]),
        })
        self.assertEqual(len(payload["deterministic_results"]["unchanged"]), 1)

    def test_each_bound_input_rekeys_its_corresponding_digest(self):
        baseline_repo = self.sync_repo()
        baseline = plan_sync(baseline_repo, AS_OF).to_dict()["work_order"][
            "bindings"
        ]

        ledger_repo = self.sync_repo()
        records = self.ledger_records(ledger_repo)
        tombstone = dict(records[1])
        tombstone["unit"] = "d" * 64
        tombstone["status"] = "tombstone"
        tombstone["removed"] = {"commit": "e" * 40, "date": AS_OF}
        records.append(tombstone)
        self.write_ledger(ledger_repo, records)
        ledger_changed = plan_sync(ledger_repo, AS_OF).to_dict()["work_order"][
            "bindings"
        ]
        self.assertNotEqual(ledger_changed["ledger_digest"],
                            baseline["ledger_digest"])
        self.assertEqual(ledger_changed["inventory_digest"],
                         baseline["inventory_digest"])
        self.assertEqual(ledger_changed["unit_set_digest"],
                         baseline["unit_set_digest"])

        inventory_repo = self.sync_repo()
        self.write(inventory_repo, "docs/guides/history.md",
                   "> As of 2026-08-06 (changed context)\n")
        inventory_changed = plan_sync(
            inventory_repo, AS_OF
        ).to_dict()["work_order"]["bindings"]
        self.assertNotEqual(inventory_changed["inventory_digest"],
                            baseline["inventory_digest"])
        self.assertEqual(inventory_changed["ledger_digest"],
                         baseline["ledger_digest"])
        self.assertEqual(inventory_changed["unit_set_digest"],
                         baseline["unit_set_digest"])

        unit_files = dict(FILES)
        unit_files["docs/architecture.md"] = (
            "# Architecture\n\nThe service has a new identity.\n"
        )
        unit_repo = self.repo(unit_files)
        self.write_ledger(unit_repo)
        unit_changed = plan_sync(unit_repo, AS_OF).to_dict()["work_order"][
            "bindings"
        ]
        self.assertNotEqual(unit_changed["unit_set_digest"],
                            baseline["unit_set_digest"])

        budget_repo = self.sync_repo(json.dumps({
            "sync": {"max_turns": 12},
        }))
        budget_changed = plan_sync(budget_repo, AS_OF).to_dict()["work_order"][
            "bindings"
        ]
        self.assertNotEqual(budget_changed["budget_digest"],
                            baseline["budget_digest"])
        self.assertEqual(budget_changed["ledger_digest"],
                         baseline["ledger_digest"])
        self.assertEqual(budget_changed["inventory_digest"],
                         baseline["inventory_digest"])
        self.assertEqual(budget_changed["unit_set_digest"],
                         baseline["unit_set_digest"])

    def test_repeated_calls_are_byte_identical_and_never_write_the_ledger(self):
        repo = self.sync_repo()
        ledger = os.path.join(repo, DEFAULT_LEDGER_PATH)
        with open(ledger, "rb") as fh:
            before = fh.read()

        first = json.dumps(plan_sync(repo, AS_OF).to_dict(), indent=2)
        second = json.dumps(plan_sync(repo, AS_OF).to_dict(), indent=2)

        self.assertEqual(first, second)
        with open(ledger, "rb") as fh:
            self.assertEqual(fh.read(), before)

    def test_existing_anchor_check_and_planning_exclusion_are_visible(self):
        repo = self.sync_repo()

        payload = plan_sync(repo, AS_OF).to_dict()["deterministic_results"]

        self.assertEqual(payload["narrative_checks"], [{
            "path": "docs/guides/history.md",
            "coverage": {
                "obligation": "anchor", "anchor": "dated",
                "as_of": AS_OF, "references": [],
            },
            "findings": [],
        }])
        self.assertEqual(
            [(entry["path"], entry["code"]) for entry in payload["excluded"]],
            [("docs/plans/next.md", "planning-kind")],
        )

    def test_narrative_anchor_finding_is_a_deterministic_finding(self):
        repo = self.sync_repo()
        self.write(repo, "docs/guides/history.md", "# Undated history\n")

        result = plan_sync(repo, AS_OF)

        self.assertEqual(result.status, "findings")
        findings = result.to_dict()["deterministic_results"][
            "narrative_checks"
        ][0]["findings"]
        self.assertEqual([finding["code"] for finding in findings],
                         ["ANCHOR-MISSING"])
        self.assertEqual(result.work_order.units, ())

    def test_explicit_session_and_chunk_bindings_are_carried(self):
        repo = self.sync_repo()

        work = plan_sync(
            repo, AS_OF, session_id="bootstrap-7", chunk_id="chunk-a",
            total_chunk_count=3,
        ).to_dict()["work_order"]

        self.assertEqual(
            (work["session_id"], work["chunk_id"], work["total_chunk_count"]),
            ("bootstrap-7", "chunk-a", 3),
        )


class BudgetContract(SyncRepoTestCase):
    def test_absent_config_uses_conservative_defaults_and_binds_them(self):
        work = plan_sync(self.sync_repo(), AS_OF).to_dict()["work_order"]

        self.assertEqual(work["budget"], {
            "max_work_order_units": 40,
            "max_model_calls": 1,
            "max_turns": 40,
            "sync_model": "sonnet",
        })
        self.assertEqual(work["bindings"]["budget_digest"],
                         canonical_digest(work["budget"]))

    def test_sync_section_overrides_each_default_and_is_carried(self):
        config = json.dumps({
            "future-section": {"kept-for": "its owner"},
            "sync": {
                "max_work_order_units": 7,
                "max_model_calls": 2,
                "max_turns": 19,
                "sync_model": "opus",
            },
        })

        work = plan_sync(self.sync_repo(config), AS_OF).to_dict()["work_order"]

        self.assertEqual(work["budget"], {
            "max_work_order_units": 7,
            "max_model_calls": 2,
            "max_turns": 19,
            "sync_model": "opus",
        })

    def test_a_partial_sync_section_uses_field_defaults(self):
        work = plan_sync(
            self.sync_repo(json.dumps({"sync": {"max_turns": 12}})), AS_OF
        ).to_dict()["work_order"]

        self.assertEqual(work["budget"]["max_turns"], 12)
        self.assertEqual(work["budget"]["sync_model"], "sonnet")

    def test_malformed_or_misspelled_config_fails_closed_without_work_order(self):
        cases = (
            ("{", "sync-config-unparseable"),
            (json.dumps({"sync": {"max_model_call": 1}}),
             "sync-config-invalid"),
            (json.dumps({"sync": {"max_turns": 0}}),
             "sync-config-invalid-budget"),
            (json.dumps({"sync": {"sync_model": "not a model alias"}}),
             "sync-config-invalid-model"),
        )
        for config, code in cases:
            with self.subTest(code=code):
                result = plan_sync(self.sync_repo(config), AS_OF)
                self.assertIsInstance(result, Invalid)
                self.assertIn(code, codes(result))
                self.assertNotIn("work_order", result.to_dict())


class LedgerRefusals(SyncRepoTestCase):
    def changed(self, mutate):
        repo = self.repo(FILES)
        records = self.ledger_records(repo)
        mutate(records)
        self.write_ledger(repo, records)
        return plan_sync(repo, AS_OF)

    def test_missing_ledger_never_becomes_bootstrap(self):
        result = plan_sync(self.repo(FILES), AS_OF)

        self.assertEqual(codes(result), ["ledger-missing"])
        self.assertNotIn("work_order", result.to_dict())

    def test_unparseable_line_fails_closed(self):
        repo = self.sync_repo()
        with open(os.path.join(repo, DEFAULT_LEDGER_PATH), "a", encoding="utf-8") as fh:
            fh.write("{not json}\n")

        result = plan_sync(repo, AS_OF)

        self.assertEqual(codes(result), ["ledger-unparseable-line"])

    def test_unknown_schema_fails_closed(self):
        result = self.changed(lambda records: records[0].update(schema=2))
        self.assertIn("ledger-unknown-schema", codes(result))

    def test_foreign_registry_fails_closed(self):
        result = self.changed(
            lambda records: records[0].update(registry_digest="f" * 64)
        )
        self.assertIn("ledger-registry-mismatch", codes(result))

    def test_incompatible_ruleset_fails_closed(self):
        result = self.changed(lambda records: records[0].update(ruleset=999))
        self.assertIn("ledger-ruleset-incompatible", codes(result))

    def test_duplicate_document_plus_unit_identity_fails_closed(self):
        def duplicate(records):
            records.append(dict(records[1]))

        result = self.changed(duplicate)
        self.assertIn("ledger-duplicate-identity", codes(result))

    def probe(self, records):
        entry = records[1]
        entry["strategy"] = "probe"
        entry["probe"] = {
            "kind": "path_exists",
            "args": {"path": "src/app.py", "kind": "file"},
            "expect": {},
        }
        entry["deps"] = [{"path": "src/app.py", "digest": "c" * 64}]

    def test_forbidden_probe_kind_fails_closed(self):
        def bad(records):
            self.probe(records)
            records[1]["probe"]["kind"] = "shell"

        result = self.changed(bad)
        self.assertIn("ledger-forbidden-probe-kind", codes(result))

    def test_forbidden_probe_field_shape_fails_closed(self):
        def bad(records):
            self.probe(records)
            records[1]["probe"].pop("expect")

        result = self.changed(bad)
        self.assertIn("ledger-invalid-probe-shape", codes(result))

    def test_forbidden_nested_probe_fields_fail_closed_for_every_kind(self):
        probes = (
            {
                "kind": "path_exists",
                "args": {"command": "rm -rf /"},
                "expect": {"anything": True},
            },
            {
                "kind": "content_match",
                "args": {"path": "src/app.py", "pattern": "App",
                         "command": "run"},
                "expect": {"presence": "present"},
            },
            {
                "kind": "json_value",
                "args": {"path": "package.json", "pointer": "/name"},
                "expect": {"value": "app"},
            },
            {
                "kind": "symbol_defined",
                "args": {"path": "src/app.py", "language": "javascript",
                         "name": "App.run"},
                "expect": {},
            },
            {
                "kind": "tool_probe",
                "args": {"tool": "gh", "flag": "--execute", "pattern": "gh"},
                "expect": {},
            },
        )
        for probe in probes:
            with self.subTest(kind=probe["kind"]):
                def bad(records):
                    self.probe(records)
                    records[1]["probe"] = probe

                result = self.changed(bad)
                self.assertTrue(set(codes(result)) & {
                    "ledger-invalid-probe-shape", "ledger-invalid-probe-field",
                })
                self.assertNotIn("work_order", result.to_dict())

    def test_command_shaped_dependency_path_fails_closed(self):
        def bad(records):
            self.probe(records)
            records[1]["deps"][0]["path"] = "src/app.py;rm"

        result = self.changed(bad)
        self.assertIn("ledger-invalid-probe-field", codes(result))
        self.assertNotIn("work_order", result.to_dict())

    def test_every_probe_kind_has_a_closed_nested_schema(self):
        probes = (
            {"kind": "path_exists",
             "args": {"path": "src/app.py", "kind": "file"}, "expect": {}},
            {"kind": "content_match",
             "args": {"path": "src/app.py", "pattern": "class App"},
             "expect": {"presence": "present", "count": 1}},
            {"kind": "json_value",
             "args": {"path": "package.json", "pointer": "/name"},
             "expect": {"equals": "app"}},
            {"kind": "symbol_defined",
             "args": {"path": "src/app.py", "language": "python",
                      "name": "App.run"}, "expect": {}},
            {"kind": "tool_probe",
             "args": {"tool": "gh", "flag": "--version", "pattern": "gh"},
             "expect": {}},
        )
        for probe in probes:
            with self.subTest(kind=probe["kind"]):
                repo = self.repo(FILES)
                records = self.ledger_records(repo)
                self.probe(records)
                records[1]["probe"] = probe
                self.write_ledger(repo, records)
                ledger = load_assertion_ledger(
                    repo, build_inventory(repo).registry_digest
                )
                self.assertNotIsInstance(ledger, Invalid)

    def test_parseable_wrong_json_types_are_typed_not_exceptions(self):
        cases = {
            "class-list": lambda records: records[1].update({"class": []}),
            "doc-object": lambda records: records[1].update({"doc": {}}),
            "unit-list": lambda records: records[1].update({"unit": []}),
            "lineage-list": lambda records: records[1].update({"lineage": []}),
            "status-object": lambda records: records[1].update({"status": {}}),
            "covered-nested": lambda records: records[0].update({"covered": [[]]}),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                result = self.changed(mutate)
                self.assertIsInstance(result, Invalid)
                self.assertTrue(codes(result))
                self.assertNotIn("work_order", result.to_dict())

    def test_valid_tombstone_retains_active_fields_and_removal_lineage(self):
        repo = self.sync_repo()
        records = self.ledger_records(repo)
        old = dict(records[1])
        old["unit"] = "d" * 64
        old["status"] = "tombstone"
        old["removed"] = {"commit": "e" * 40, "date": AS_OF}
        records.append(old)
        self.write_ledger(repo, records)

        ledger = load_assertion_ledger(
            repo, build_inventory(repo).registry_digest
        )

        self.assertNotIsInstance(ledger, Invalid)
        self.assertEqual(ledger.entries[-1].status, "tombstone")
        self.assertEqual(plan_sync(repo, AS_OF).status, "clean")

    def test_changed_current_unit_set_fails_closed_until_comparison_slice(self):
        repo = self.sync_repo()
        self.write(repo, "docs/architecture.md",
                   "# Architecture\n\nThe service changed.\n")

        result = plan_sync(repo, AS_OF)

        self.assertEqual(codes(result), ["sync-ledger-unit-set-changed"])
        self.assertNotIn("work_order", result.to_dict())


class ModeAndClockContract(SyncRepoTestCase):
    def test_bootstrap_and_reconcile_are_typed_unimplemented_refusals(self):
        repo = self.sync_repo()
        for mode in (MODE_BOOTSTRAP, MODE_RECONCILE):
            with self.subTest(mode=mode):
                result = plan_sync(repo, AS_OF, mode=mode)
                self.assertEqual(codes(result), [f"sync-{mode}-not-implemented"])
                self.assertNotIn("work_order", result.to_dict())

    def test_unknown_mode_and_missing_or_invalid_as_of_are_typed(self):
        repo = self.sync_repo()
        self.assertEqual(codes(plan_sync(repo, AS_OF, mode="full")),
                         ["sync-unknown-mode"])
        for as_of in (None, "", "2026-02-30"):
            with self.subTest(as_of=as_of):
                self.assertEqual(codes(plan_sync(repo, as_of)),
                                 ["sync-invalid-as-of"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
