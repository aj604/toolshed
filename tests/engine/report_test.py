#!/usr/bin/env python3
"""Tests for the report contract: lineage, the five result states, rendering.

Seam: the library functions `validate_report`, `load_report`, `current_lineage`,
and `render_report`. The CLI half of the same contract lives in
`report_cli_test.py`, which asserts the command hands back exactly these
results.

Run: python3 tests/engine/report_test.py
"""

import json
import os
import re
import subprocess
import sys
import unittest
import uuid
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402

from doclifecycle import (  # noqa: E402
    ARTIFACT_SCHEMA_VERSION,
    PLUGIN_VERSION,
    RULESET_VERSION,
)
from doclifecycle import repository  # noqa: E402
from doclifecycle.digest import sha256_canonical  # noqa: E402
from doclifecycle.finding import finding_digest  # noqa: E402
from doclifecycle.render import render_report  # noqa: E402
from doclifecycle.report import (  # noqa: E402
    AUDIT_MODES,
    EXCLUSION_PLANNING_KIND,
    EXCLUSION_UNAFFECTED_BY_RANGE,
    MAX_NESTING,
    REQUIRED_LINEAGE_FIELDS,
    SCOPE_DECLARED_ONLY,
    SCOPE_DOCUMENT_UNKNOWN,
    SCOPE_EXCLUSION_KIND_MISMATCH,
    SCOPE_INVENTORY_UNACCOUNTED,
    SCOPE_WHOLE_INVENTORY,
    Report,
    current_lineage,
    load_report,
    parse_lineage,
    validate_report,
)
from doclifecycle.results import (  # noqa: E402
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_INVALID,
    STATE_PARTIAL,
    STATE_STALE,
    Invalid,
)
from doclifecycle.segment import segment_document  # noqa: E402

REGISTRY = json.dumps({
    "schema_version": 1,
    "roots": ["docs"],
    "rules": [{"glob": "docs/**/*.md", "kind": "living"}],
})

REPO_FILES = {
    ".doc-lifecycle/registry.json": REGISTRY,
    "docs/architecture.md": "# Architecture\n",
    "src/app.py": "print('hi')\n",
}

CONFIG_DIGEST = "c" * 64

RECORD = {
    "id": "DRIFT-001",
    "digest": "a" * 64,
    "code": "STALE",
    "path": "docs/architecture.md",
}


def lineage_payload(**overrides):
    """A structurally valid lineage; overrides swap one field at a time."""
    payload = {
        "repository": "origin:github.com/aj604/toolshed",
        "base_commit": "0" * 40,
        "audit_mode": "full",
        "inventory_digest": "1" * 64,
        "audit_config_digest": CONFIG_DIGEST,
        "registry_digest": "2" * 64,
        "ruleset_version": RULESET_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "evidence_boundary": {"sources": ["src/**"],
                              "excluded": ["src/vendor/**"], "commands": []},
    }
    payload.update(overrides)
    return payload


def report_payload(status=STATE_FINDINGS, lineage=None, records=None,
                   incomplete=None, **overrides):
    payload = {
        "status": status,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": lineage_payload() if lineage is None else lineage,
        "records": [dict(RECORD)] if records is None else records,
        "incomplete": [] if incomplete is None else incomplete,
    }
    payload.update(overrides)
    return payload


def codes(result):
    return sorted(p.code for p in result.problems)


class GitRepoTestCase(RepoTestCase):
    """Staleness is a comparison against a real repository, never a mock."""

    def git_repo(self, files=None):
        files = dict(REPO_FILES if files is None else files)
        # A distinct blob per fixture, outside the declared roots: two repos
        # built from identical trees in the same second would otherwise commit
        # to the same sha, and could not be told apart by identity.
        files[".fixture-id"] = uuid.uuid4().hex
        root = self.repo(files)
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
        )
        for argv in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["commit", "-q", "-m", "fixture"],
        ):
            subprocess.run(
                ["git", "-C", root, *argv], check=True, env=env,
                capture_output=True, text=True,
            )
        return root

    def fresh_lineage(self, repo, **overrides):
        """Lineage that matches `repo` exactly — the producing run's own."""
        state, problems = current_lineage(repo, audit_config_digest=CONFIG_DIGEST)
        self.assertEqual(problems, ())
        payload = lineage_payload(**state)
        payload.update(overrides)
        return payload


class ValidReports(unittest.TestCase):
    def test_findings_report_validates_as_findings(self):
        result = validate_report(report_payload())

        self.assertIsInstance(result, Report)
        self.assertEqual(result.status, STATE_FINDINGS)
        self.assertEqual([r.id for r in result.records], ["DRIFT-001"])

    def test_clean_report_validates_as_clean(self):
        result = validate_report(report_payload(status=STATE_CLEAN, records=[]))

        self.assertEqual(result.status, STATE_CLEAN)

    def test_partial_report_names_what_it_did_not_examine(self):
        result = validate_report(report_payload(
            status=STATE_PARTIAL,
            incomplete=[{"scope": "docs/huge.md", "reason": "chunk budget"}],
        ))

        self.assertEqual(result.status, STATE_PARTIAL)
        self.assertEqual(result.incomplete[0].scope, "docs/huge.md")

    def test_record_fields_beyond_the_contract_survive_validation(self):
        # Record internals belong to the segmenter (#63); the contract carries
        # them through untouched rather than silently dropping them.
        result = validate_report(report_payload())

        self.assertEqual(result.records[0].to_dict()["code"], "STALE")

    def test_payload_round_trips_through_the_validator(self):
        payload = validate_report(report_payload()).to_dict()

        self.assertEqual(validate_report(payload).to_dict(), payload)

    def test_digest_is_over_meaning_not_formatting(self):
        reordered = json.loads(json.dumps(report_payload(), sort_keys=True))

        self.assertEqual(
            validate_report(report_payload()).digest,
            validate_report(reordered).digest,
        )

    def test_digest_changes_when_a_record_changes(self):
        other = dict(RECORD, digest="b" * 64)

        self.assertNotEqual(
            validate_report(report_payload()).digest,
            validate_report(report_payload(records=[other])).digest,
        )

    def test_digest_changes_when_lineage_changes(self):
        self.assertNotEqual(
            validate_report(report_payload()).digest,
            validate_report(report_payload(
                lineage=lineage_payload(base_commit="f" * 40)
            )).digest,
        )

    def test_a_declared_digest_that_does_not_match_the_content_is_invalid(self):
        result = validate_report(report_payload(digest="9" * 64))

        self.assertEqual(codes(result), ["report-digest-mismatch"])

    def test_a_declared_digest_that_matches_is_accepted(self):
        payload = report_payload()
        payload["digest"] = validate_report(payload).digest

        self.assertIsInstance(validate_report(payload), Report)


class SchemaVersion(unittest.TestCase):
    def test_a_future_schema_version_is_rejected_never_guessed(self):
        result = validate_report(
            report_payload(schema_version=ARTIFACT_SCHEMA_VERSION + 1)
        )

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["report-schema-version"])
        self.assertIn("migrate", result.problems[0].message.lower())

    def test_an_older_schema_version_is_rejected_too(self):
        result = validate_report(report_payload(schema_version=0))

        self.assertEqual(codes(result), ["report-schema-version"])

    def test_a_missing_schema_version_is_rejected(self):
        payload = report_payload()
        del payload["schema_version"]

        self.assertEqual(codes(validate_report(payload)), ["report-missing-field"])

    def test_a_version_that_merely_compares_equal_to_one_is_rejected(self):
        # In Python `True == 1` and `1.0 == 1`; in a schema neither is the
        # integer version, and comparing rather than type-guarding accepts both.
        for version in ("1", True, 1.0, [1], {"version": 1}, None):
            with self.subTest(version=version):
                result = validate_report(report_payload(schema_version=version))

                self.assertEqual(codes(result), ["report-schema-version"])


class LineageFields(unittest.TestCase):
    def test_every_required_lineage_field_is_enumerated(self):
        self.assertEqual(set(REQUIRED_LINEAGE_FIELDS), {
            "repository",
            "base_commit",
            "audit_mode",
            "inventory_digest",
            "audit_config_digest",
            "registry_digest",
            "ruleset_version",
            "plugin_version",
            "evidence_boundary",
        })

    def test_dropping_any_lineage_field_fails_with_a_typed_error(self):
        for field in REQUIRED_LINEAGE_FIELDS:
            with self.subTest(field=field):
                lineage = lineage_payload()
                del lineage[field]

                result = validate_report(report_payload(lineage=lineage))

                self.assertIsInstance(result, Invalid)
                self.assertEqual(codes(result), ["report-missing-lineage-field"])
                self.assertIn(field, result.problems[0].message)

    def test_a_missing_lineage_object_is_a_missing_field(self):
        payload = report_payload()
        del payload["lineage"]

        self.assertEqual(codes(validate_report(payload)), ["report-missing-field"])

    def test_lineage_must_be_an_object(self):
        result = validate_report(report_payload(lineage=["repository"]))

        self.assertEqual(codes(result), ["report-invalid-lineage"])

    def test_an_unknown_lineage_field_is_rejected(self):
        lineage = lineage_payload(head_commit="0" * 40)

        result = validate_report(report_payload(lineage=lineage))

        self.assertEqual(codes(result), ["report-unknown-lineage-field"])

    def test_malformed_lineage_values_are_rejected_field_by_field(self):
        cases = [
            ("repository", "", "report-invalid-lineage"),
            ("repository", 7, "report-invalid-lineage"),
            ("base_commit", "not-a-sha", "report-invalid-lineage"),
            ("base_commit", "ABCDEF" + "0" * 34, "report-invalid-lineage"),
            ("audit_mode", "sample", "report-unknown-audit-mode"),
            ("inventory_digest", "1" * 63, "report-invalid-lineage"),
            ("audit_config_digest", None, "report-invalid-lineage"),
            ("registry_digest", "zz" + "2" * 62, "report-invalid-lineage"),
            ("ruleset_version", "1", "report-invalid-lineage"),
            ("ruleset_version", 0, "report-invalid-lineage"),
            ("plugin_version", "", "report-invalid-lineage"),
            ("evidence_boundary", ["src/**"], "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": []},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": ["src/**"], "extra": 1},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": ["src\n**"]},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"excluded": ["v"]},
             "report-invalid-evidence-boundary"),
            # A declared tool is a bare executable name: a boundary that cannot
            # be read as "which programs could a verdict rest on" declares
            # nothing a reader can check.
            ("evidence_boundary", {"sources": ["src/**"], "commands": "gh"},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": ["src/**"],
                                   "commands": ["gh pr list"]},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": ["src/**"],
                                   "commands": ["/usr/bin/gh"]},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": ["src/**"], "commands": [""]},
             "report-invalid-evidence-boundary"),
            ("evidence_boundary", {"sources": ["src/**"], "commands": [7]},
             "report-invalid-evidence-boundary"),
            # `$` in a Python pattern matches before a trailing newline, so an
            # anchored `match` would let one through into a lineage field.
            ("evidence_boundary", {"sources": ["src/**"], "commands": ["gh\n"]},
             "report-invalid-evidence-boundary"),
        ]
        for field, value, code in cases:
            with self.subTest(field=field, value=value):
                lineage = lineage_payload(**{field: value})

                result = validate_report(report_payload(lineage=lineage))

                self.assertIsInstance(result, Invalid)
                self.assertIn(code, codes(result))

    def test_every_audit_mode_in_the_closed_set_is_accepted(self):
        for mode in AUDIT_MODES:
            with self.subTest(mode=mode):
                lineage = lineage_payload(audit_mode=mode)

                result = validate_report(report_payload(lineage=lineage))

                self.assertIsInstance(result, Report)

    def test_problems_are_reported_exhaustively_not_first_one_only(self):
        lineage = lineage_payload(base_commit="nope", plugin_version="")

        result = validate_report(report_payload(lineage=lineage))

        self.assertEqual(len(result.problems), 2)

    def test_a_lineage_problem_says_where_it_was_found(self):
        lineage = lineage_payload(base_commit="nope")

        result = validate_report(report_payload(lineage=lineage))

        self.assertEqual(result.problems[0].location, "lineage.base_commit")


class ResultStates(unittest.TestCase):
    def test_only_clean_means_the_declared_scope_completed_with_nothing_found(self):
        result = validate_report(report_payload(status=STATE_CLEAN, records=[]))

        self.assertEqual(result.status, STATE_CLEAN)
        self.assertEqual(result.records, ())
        self.assertEqual(result.incomplete, ())

    def test_a_clean_report_carrying_records_is_inconsistent(self):
        result = validate_report(report_payload(status=STATE_CLEAN))

        self.assertEqual(codes(result), ["report-state-inconsistent"])

    def test_a_findings_report_with_no_records_is_inconsistent(self):
        result = validate_report(report_payload(status=STATE_FINDINGS, records=[]))

        self.assertEqual(codes(result), ["report-state-inconsistent"])

    def test_a_partial_report_that_names_nothing_incomplete_is_inconsistent(self):
        result = validate_report(report_payload(status=STATE_PARTIAL))

        self.assertEqual(codes(result), ["report-state-inconsistent"])

    def test_an_incomplete_scope_alone_forces_the_partial_state(self):
        result = validate_report(report_payload(
            status=STATE_FINDINGS,
            incomplete=[{"scope": "docs/huge.md", "reason": "chunk budget"}],
        ))

        self.assertEqual(codes(result), ["report-state-inconsistent"])

    def test_invalid_is_never_a_state_a_report_can_carry(self):
        # An invalid run has no content to report, so a report claiming to be
        # invalid is a contradiction rather than a verdict.
        result = validate_report(report_payload(status=STATE_INVALID))

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["report-invalid-status"])

    def test_an_unknown_status_is_rejected(self):
        result = validate_report(report_payload(status="ok"))

        self.assertEqual(codes(result), ["report-invalid-status"])

    def test_a_missing_status_is_rejected(self):
        payload = report_payload()
        del payload["status"]

        self.assertEqual(codes(validate_report(payload)), ["report-missing-field"])

    def test_incomplete_entries_must_name_a_scope_and_a_reason(self):
        for entry in ({"scope": "docs/a.md"}, {"reason": "budget"},
                      {"scope": "", "reason": "b"}, "docs/a.md",
                      {"scope": "a", "reason": "b", "extra": 1}):
            with self.subTest(entry=entry):
                result = validate_report(report_payload(
                    status=STATE_PARTIAL, incomplete=[entry]
                ))

                self.assertIn("report-invalid-incomplete", codes(result))


class Records(unittest.TestCase):
    def test_a_record_must_carry_an_id_and_a_digest(self):
        for record in ({"digest": "a" * 64}, {"id": "R1"}, {"id": "", "digest": "a" * 64},
                       {"id": "R1", "digest": "short"}, "R1"):
            with self.subTest(record=record):
                result = validate_report(report_payload(records=[record]))

                self.assertEqual(codes(result), ["report-invalid-record"])

    def test_records_must_be_a_list(self):
        result = validate_report(report_payload(records={"id": "R1"}))

        self.assertEqual(codes(result), ["report-invalid-shape"])

    def test_two_records_sharing_a_digest_is_invalid(self):
        # Approval binds to record digests: duplicates would make a selection
        # ambiguous about which record it authorized.
        result = validate_report(report_payload(
            records=[dict(RECORD), dict(RECORD, id="DRIFT-002")]
        ))

        self.assertEqual(codes(result), ["report-duplicate-record"])

    def test_two_records_sharing_an_id_is_invalid(self):
        result = validate_report(report_payload(
            records=[dict(RECORD), dict(RECORD, digest="b" * 64)]
        ))

        self.assertEqual(codes(result), ["report-duplicate-record"])

    def test_a_number_json_cannot_represent_is_rejected(self):
        # json.loads accepts NaN and json.dumps re-emits it, so a record
        # carrying one would make the engine's own output unparseable — and the
        # digest is taken over that same encoding.
        for value in (float("nan"), float("inf"), float("-inf"),
                      {"nested": [float("nan")]}, [{"deep": float("inf")}]):
            with self.subTest(value=value):
                result = validate_report(
                    report_payload(records=[dict(RECORD, measure=value)])
                )

                self.assertEqual(codes(result), ["report-nonfinite-number"])

    def test_a_record_at_the_nesting_limit_is_accepted(self):
        nest = {"leaf": 1}
        for _ in range(MAX_NESTING - 3):        # record, field, …, leaf
            nest = {"deeper": nest}

        result = validate_report(
            report_payload(records=[dict(RECORD, tree=nest)])
        )

        self.assertIsInstance(result, Report)

    def test_a_record_nested_past_the_limit_is_a_verdict_not_a_crash(self):
        for build in (lambda inner: {"deeper": inner}, lambda inner: [inner]):
            with self.subTest(shape=build(None).__class__.__name__):
                nest = 1
                for _ in range(MAX_NESTING + 50):
                    nest = build(nest)

                result = validate_report(
                    report_payload(records=[dict(RECORD, tree=nest)])
                )

                self.assertEqual(codes(result), ["report-nesting-too-deep"])

    def test_a_depth_bomb_never_reaches_the_digest(self):
        # The digest encodes with json.dumps, which recurses: a record that
        # validated but could not be hashed would crash after the verdict.
        nest = 1
        for _ in range(5000):
            nest = [nest]

        result = validate_report(
            report_payload(records=[dict(RECORD, tree=nest)])
        )

        self.assertIsInstance(result, Invalid)

    def test_a_valid_report_survives_a_strict_json_encoder(self):
        payload = validate_report(report_payload(
            records=[dict(RECORD, ratio=0.5, count=3)]
        )).to_dict()

        json.dumps(payload, allow_nan=False)   # must not raise


class Shape(unittest.TestCase):
    def test_a_non_object_payload_is_invalid(self):
        for payload in ([], "report", 3, None):
            with self.subTest(payload=payload):
                result = validate_report(payload)

                self.assertEqual(codes(result), ["report-invalid-shape"])

    def test_an_unknown_top_level_field_is_rejected(self):
        result = validate_report(report_payload(summary="all good"))

        self.assertEqual(codes(result), ["report-unknown-field"])

    def test_a_report_never_carries_problems_of_its_own(self):
        # A problem is a reason a run is invalid; a validated report has none.
        result = validate_report(report_payload(problems=[]))

        self.assertEqual(codes(result), ["report-unknown-field"])


class Staleness(GitRepoTestCase):
    def test_lineage_matching_the_repository_is_not_stale(self):
        repo = self.git_repo()

        result = validate_report(
            report_payload(lineage=self.fresh_lineage(repo)),
            repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertEqual(result.status, STATE_FINDINGS)
        self.assertEqual(result.stale_reasons, ())

    def test_each_lineage_field_that_can_drift_makes_the_report_stale(self):
        repo = self.git_repo()
        cases = [
            ("repository", "origin:github.com/someone/else",
             "lineage-repository-mismatch"),
            ("base_commit", "f" * 40, "lineage-base-commit-mismatch"),
            ("inventory_digest", "1" * 64, "lineage-inventory-mismatch"),
            ("registry_digest", "2" * 64, "lineage-registry-mismatch"),
            ("audit_config_digest", "d" * 64, "lineage-audit-config-mismatch"),
            ("ruleset_version", RULESET_VERSION + 1, "lineage-ruleset-mismatch"),
            ("plugin_version", "0.0.1", "lineage-plugin-mismatch"),
        ]
        for field, value, code in cases:
            with self.subTest(field=field):
                lineage = self.fresh_lineage(repo, **{field: value})

                result = validate_report(
                    report_payload(lineage=lineage),
                    repo_root=repo,
                    audit_config_digest=CONFIG_DIGEST,
                )

                self.assertEqual(result.status, STATE_STALE)
                self.assertEqual([r.code for r in result.stale_reasons], [code])

    def test_a_stale_reason_says_what_was_expected_and_what_is_current(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo, plugin_version="0.0.1")

        result = validate_report(
            report_payload(lineage=lineage), repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        reason = result.stale_reasons[0]
        self.assertEqual(reason.reported, "0.0.1")
        self.assertEqual(reason.current, PLUGIN_VERSION)
        self.assertIn("re-run", reason.message)

    def test_every_drifted_field_is_reported_not_just_the_first(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(
            repo, base_commit="f" * 40, plugin_version="0.0.1"
        )

        result = validate_report(
            report_payload(lineage=lineage), repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertEqual(
            sorted(r.code for r in result.stale_reasons),
            ["lineage-base-commit-mismatch", "lineage-plugin-mismatch"],
        )

    def test_stale_is_distinct_from_invalid_and_keeps_the_report_content(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo, base_commit="f" * 40)

        result = validate_report(
            report_payload(lineage=lineage), repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertIsInstance(result, Report)
        self.assertNotIsInstance(result, Invalid)
        self.assertEqual([r.id for r in result.records], ["DRIFT-001"])

    def test_a_clean_report_whose_lineage_drifted_is_stale_not_clean(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo, base_commit="f" * 40)

        result = validate_report(
            report_payload(status=STATE_CLEAN, records=[], lineage=lineage),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        )

        self.assertEqual(result.status, STATE_STALE)

    def test_editing_a_document_makes_a_matching_report_stale(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo)
        with open(os.path.join(repo, "docs/architecture.md"), "a") as fh:
            fh.write("new claim\n")

        result = validate_report(
            report_payload(lineage=lineage), repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(
            [r.code for r in result.stale_reasons], ["lineage-inventory-mismatch"]
        )

    def test_a_stale_verdict_reads_back_in_unchanged(self):
        # A pipeline persists what `validate-report` printed and re-checks it
        # later; the artifact it wrote must not read as invalid.
        repo = self.git_repo()
        verdict = validate_report(
            report_payload(lineage=self.fresh_lineage(repo, plugin_version="0.0.1")),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        ).to_dict()

        self.assertEqual(validate_report(verdict).to_dict(), verdict)

    def test_a_carried_stale_verdict_stands_when_nothing_can_disprove_it(self):
        repo = self.git_repo()
        verdict = validate_report(
            report_payload(lineage=self.fresh_lineage(repo, plugin_version="0.0.1")),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        ).to_dict()

        result = validate_report(verdict)

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(
            [r.code for r in result.stale_reasons], ["lineage-plugin-mismatch"]
        )

    def test_a_carried_stale_verdict_is_cleared_by_a_repository_it_matches(self):
        repo = self.git_repo()
        stamped = report_payload(
            lineage=self.fresh_lineage(repo),
            status=STATE_STALE,
            stale_reasons=[{
                "code": "lineage-plugin-mismatch", "message": "drifted once",
                "reported": "0.0.1", "current": PLUGIN_VERSION,
            }],
        )

        result = validate_report(
            stamped, repo_root=repo, audit_config_digest=CONFIG_DIGEST
        )

        self.assertEqual(result.status, STATE_FINDINGS)
        self.assertEqual(result.stale_reasons, ())

    def test_a_weaker_check_cannot_clear_a_carried_stale_verdict(self):
        # The reason came from comparing the audit-configuration digest. A run
        # that does not supply one never compares that field, so it is in no
        # position to clear the verdict — otherwise a less thorough check would
        # launder a stale report clean.
        repo = self.git_repo()
        stamped = validate_report(
            report_payload(
                lineage=self.fresh_lineage(repo, audit_config_digest="d" * 64)
            ),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        ).to_dict()
        self.assertEqual(stamped["status"], STATE_STALE)

        result = validate_report(stamped, repo_root=repo)

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(
            [r.code for r in result.stale_reasons],
            ["lineage-audit-config-mismatch"],
        )

    def test_the_same_check_that_set_a_verdict_can_clear_it(self):
        repo = self.git_repo()
        stamped = validate_report(
            report_payload(
                lineage=self.fresh_lineage(repo, audit_config_digest="d" * 64)
            ),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        ).to_dict()

        result = validate_report(
            stamped, repo_root=repo, audit_config_digest="d" * 64
        )

        self.assertEqual(result.status, STATE_FINDINGS)
        self.assertEqual(result.stale_reasons, ())

    def test_a_carried_reason_naming_an_uncomparable_field_stands(self):
        # A reason this engine cannot re-check is not a reason it can dismiss.
        repo = self.git_repo()
        stamped = report_payload(
            lineage=self.fresh_lineage(repo),
            status=STATE_STALE,
            stale_reasons=[{
                "code": "lineage-evidence-boundary-mismatch",
                "message": "the boundary moved", "reported": "src/**",
                "current": "src/api/**",
            }],
        )

        result = validate_report(
            stamped, repo_root=repo, audit_config_digest=CONFIG_DIGEST
        )

        self.assertEqual(result.status, STATE_STALE)

    def test_a_carried_reason_is_not_duplicated_by_the_current_check(self):
        repo = self.git_repo()
        stamped = validate_report(
            report_payload(lineage=self.fresh_lineage(repo, plugin_version="0.0.1")),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        ).to_dict()

        result = validate_report(
            stamped, repo_root=repo, audit_config_digest=CONFIG_DIGEST
        )

        self.assertEqual(
            [r.code for r in result.stale_reasons], ["lineage-plugin-mismatch"]
        )

    def test_a_stale_report_that_names_no_drift_is_inconsistent(self):
        result = validate_report(report_payload(status=STATE_STALE))

        self.assertEqual(codes(result), ["report-state-inconsistent"])

    def test_stale_reasons_on_a_report_that_is_not_stale_are_inconsistent(self):
        result = validate_report(report_payload(stale_reasons=[{
            "code": "lineage-plugin-mismatch", "message": "drifted",
            "reported": "0.0.1", "current": PLUGIN_VERSION,
        }]))

        self.assertEqual(codes(result), ["report-state-inconsistent"])

    def test_malformed_stale_reasons_are_rejected(self):
        for reason in ({"code": "c"}, "drift", {
            "code": "c", "message": "m", "reported": "", "current": "x",
        }, {"code": "c", "message": "m", "reported": "a", "current": "b", "x": 1}):
            with self.subTest(reason=reason):
                result = validate_report(
                    report_payload(status=STATE_STALE, stale_reasons=[reason])
                )

                self.assertEqual(codes(result), ["report-invalid-stale-reason"])

    def test_a_carried_stale_verdict_does_not_change_the_report_digest(self):
        # Approval binds to the digest, so a verdict recorded on top of a report
        # must not re-key it.
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo, plugin_version="0.0.1")

        self.assertEqual(
            validate_report(report_payload(lineage=lineage)).digest,
            validate_report(
                report_payload(lineage=lineage), repo_root=repo,
                audit_config_digest=CONFIG_DIGEST,
            ).digest,
        )

    def test_without_a_repository_the_verdict_is_never_stale(self):
        # Structural validation alone cannot know the repository state, and must
        # not guess a freshness it did not check.
        result = validate_report(report_payload(lineage=lineage_payload()))

        self.assertEqual(result.status, STATE_FINDINGS)

    def test_the_audit_config_digest_is_only_compared_when_one_is_supplied(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo, audit_config_digest="d" * 64)

        result = validate_report(report_payload(lineage=lineage), repo_root=repo)

        self.assertEqual(result.status, STATE_FINDINGS)

    def test_invalid_beats_stale(self):
        repo = self.git_repo()
        lineage = self.fresh_lineage(repo, base_commit="f" * 40)
        del lineage["plugin_version"]

        result = validate_report(
            report_payload(lineage=lineage), repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["report-missing-lineage-field"])

    def test_an_unreadable_repository_state_fails_closed(self):
        # Not a git repository: freshness cannot be established, so the run is
        # invalid rather than silently certified fresh.
        repo = self.repo(dict(REPO_FILES))

        result = validate_report(report_payload(), repo_root=repo)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["repository-state-unavailable"])

    def test_an_invalid_registry_makes_the_repository_state_unavailable(self):
        repo = self.git_repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/architecture.md": "# Architecture\n",
        })

        result = validate_report(report_payload(), repo_root=repo)

        self.assertIsInstance(result, Invalid)
        self.assertIn("repository-state-unavailable", codes(result))


class WholeDocumentRecordAuthority(GitRepoTestCase):
    def complete_record(self, repo, path, lineage):
        parsed, problems = parse_lineage(lineage)
        self.assertEqual(problems, ())
        segmentation = segment_document(repo, path)
        self.assertNotIsInstance(segmentation, Invalid, segmentation)
        units = [unit.digest for unit in segmentation.units]
        return {
            "id": "BLOAT-R1",
            "digest": finding_digest(parsed, "RETIRE-DOC", path, units),
            "code": "RETIRE-DOC",
            "path": path,
            "units": units,
        }

    def test_current_lineage_report_cannot_carry_a_partial_retirement(self):
        path = "docs/architecture.md"
        repo = self.git_repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            path: "# Architecture\n\nFirst claim. Second claim.\n",
        })
        lineage_payload = self.fresh_lineage(repo)
        lineage, problems = parse_lineage(lineage_payload)
        self.assertEqual(problems, ())
        segmentation = segment_document(repo, path)
        self.assertNotIsInstance(segmentation, Invalid, segmentation)
        self.assertGreater(len(segmentation.units), 1)
        units = [segmentation.units[0].digest]
        record = {
            "id": "BLOAT-FORGED",
            "digest": finding_digest(lineage, "RETIRE-DOC", path, units),
            "code": "RETIRE-DOC",
            "path": path,
            "units": units,
        }

        result = validate_report(
            report_payload(lineage=lineage_payload, records=[record]),
            repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(
            codes(result), ["report-whole-document-units-incomplete"]
        )

    def test_duplicate_whole_document_unit_is_invalid_without_a_repository(self):
        unit = "b" * 64
        record = {
            "id": "BLOAT-FORGED",
            "digest": "a" * 64,
            "code": "RETIRE-DOC",
            "path": "docs/architecture.md",
            "units": [unit, unit],
        }

        result = validate_report(report_payload(records=[record]))

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(
            codes(result), ["report-whole-document-unit-duplicate"]
        )

    def test_complete_old_record_stays_stale_when_the_document_gains_a_unit(self):
        path = "docs/architecture.md"
        repo = self.git_repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            path: "# Architecture\n\nFirst claim.\n",
        })
        lineage = self.fresh_lineage(repo)
        record = self.complete_record(repo, path, lineage)
        with open(os.path.join(repo, path), "a", encoding="utf-8") as fh:
            fh.write("\nSecond claim.\n")

        result = validate_report(
            report_payload(lineage=lineage, records=[record]),
            repo_root=repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertIsInstance(result, Report, result)
        self.assertEqual(result.status, STATE_STALE)
        self.assertIn(
            "lineage-inventory-mismatch",
            [reason.code for reason in result.stale_reasons],
        )


class CurrentLineage(GitRepoTestCase):
    def test_it_reports_the_repository_state_a_report_must_match(self):
        repo = self.git_repo()

        state, problems = current_lineage(repo, audit_config_digest=CONFIG_DIGEST)

        self.assertEqual(problems, ())
        self.assertEqual(set(state), {
            "repository", "base_commit", "inventory_digest", "registry_digest",
            "audit_config_digest", "ruleset_version", "plugin_version",
        })
        self.assertEqual(state["plugin_version"], PLUGIN_VERSION)
        self.assertEqual(state["ruleset_version"], RULESET_VERSION)
        self.assertEqual(state["audit_config_digest"], CONFIG_DIGEST)

    def test_the_base_commit_is_the_repository_head(self):
        repo = self.git_repo()
        head = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        state, _ = current_lineage(repo)

        self.assertEqual(state["base_commit"], head)

    def test_a_remoteless_repository_is_identified_by_its_root_commit(self):
        repo = self.git_repo()

        state, _ = current_lineage(repo)

        self.assertTrue(state["repository"].startswith("root-commit:"))

    def test_two_repositories_never_share_an_identity(self):
        self.assertNotEqual(
            current_lineage(self.git_repo())[0]["repository"],
            current_lineage(self.git_repo())[0]["repository"],
        )

    def test_a_declared_origin_remote_names_the_repository(self):
        repo = self.git_repo()
        subprocess.run(
            ["git", "-C", repo, "remote", "add", "origin",
             "https://github.com/aj604/toolshed.git"],
            check=True, capture_output=True,
        )

        state, _ = current_lineage(repo)

        self.assertEqual(state["repository"], "origin:github.com/aj604/toolshed")

    def test_the_environment_cannot_redirect_the_check_to_another_repository(self):
        # A composite action or an earlier workflow step that exports GIT_DIR
        # would otherwise make the freshness check answer about someone else's
        # tree, past the toplevel guard, and in the direction of certifying.
        subject, other = self.git_repo(), self.git_repo()
        honest, _ = current_lineage(subject)

        for name in repository.REDIRECTING_VARS:
            with self.subTest(variable=name):
                with mock.patch.dict(
                    os.environ, {name: os.path.join(other, ".git")}
                ):
                    redirected, problems = current_lineage(subject)

                self.assertEqual(problems, ())
                self.assertEqual(redirected["repository"], honest["repository"])
                self.assertEqual(redirected["base_commit"], honest["base_commit"])

    def test_a_non_git_directory_yields_a_typed_problem_not_a_guess(self):
        state, problems = current_lineage(self.repo(dict(REPO_FILES)))

        self.assertEqual(state, {})
        self.assertEqual([p.code for p in problems], ["repository-state-unavailable"])

    def test_the_engine_plugin_version_tracks_the_published_manifest(self):
        # Lineage pins the plugin version, so a bump that misses the engine
        # would silently mark every fresh report stale.
        manifest = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..",
            "plugins", "doc-lifecycle", ".claude-plugin", "plugin.json",
        )
        with open(manifest, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["version"], PLUGIN_VERSION)


class RemoteNormalization(unittest.TestCase):
    """Identity is a security primitive: two repositories must never normalize
    to one string, and one repository must always normalize to one string."""

    def test_spellings_of_one_repository_agree(self):
        cases = [
            ("https://github.com/aj604/toolshed.git", "github.com/aj604/toolshed"),
            ("https://github.com/aj604/toolshed/", "github.com/aj604/toolshed"),
            ("http://github.com/aj604/toolshed", "github.com/aj604/toolshed"),
            ("https://user:pw@github.com/aj604/toolshed",
             "github.com/aj604/toolshed"),
            ("git@github.com:aj604/toolshed.git", "github.com/aj604/toolshed"),
            ("ssh://git@github.com/aj604/toolshed", "github.com/aj604/toolshed"),
            ("git://github.com/aj604/toolshed", "github.com/aj604/toolshed"),
            ("https://GitHub.COM/aj604/toolshed", "github.com/aj604/toolshed"),
            # A port routes to the repository; it is not the repository.
            ("ssh://git@github.com:22/aj604/toolshed", "github.com/aj604/toolshed"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(repository.normalize_remote(url), expected)

    def test_distinct_repositories_stay_distinct(self):
        groups = [
            # A stripped port must not merge into the path.
            ("ssh://git@github.com:22/a/b", "ssh://git@github.com/22/a/b"),
            # Paths are case-sensitive on plenty of forges; hosts are not.
            ("https://git.example.com/Team/Repo",
             "https://git.example.com/team/repo"),
            ("https://github.com/aj604/toolshed",
             "https://github.com/aj604/toolshed2"),
        ]
        for left, right in groups:
            with self.subTest(left=left, right=right):
                self.assertNotEqual(
                    repository.normalize_remote(left),
                    repository.normalize_remote(right),
                )

    def test_a_remote_cannot_be_spelled_to_look_like_the_root_commit_fallback(self):
        # The two identity forms carry distinct prefixes; crossing them would
        # let a remote impersonate a remoteless repository.
        identity = f"origin:{repository.normalize_remote('https://root-commit:0/x')}"

        self.assertFalse(identity.startswith("root-commit:"))


class LoadReport(GitRepoTestCase):
    def test_it_reads_validates_and_agrees_with_validate_report(self):
        payload = report_payload()
        repo = self.repo({"report.json": json.dumps(payload)})

        self.assertEqual(
            load_report(os.path.join(repo, "report.json")).to_dict(),
            validate_report(payload).to_dict(),
        )

    def test_an_unparseable_report_file_is_invalid(self):
        repo = self.repo({"report.json": "{ not json"})

        result = load_report(os.path.join(repo, "report.json"))

        self.assertEqual(codes(result), ["report-unparseable"])

    def test_a_report_file_that_is_not_utf8_is_invalid_not_a_traceback(self):
        # A UnicodeDecodeError is a ValueError, not an OSError; without its own
        # arm the caller gets a Python traceback instead of a verdict.
        root = self.repo({"placeholder": ""})
        path = os.path.join(root, "report.json")
        with open(path, "wb") as fh:
            fh.write(b'\xff\xfe{"status": "clean"}')

        result = load_report(path)

        self.assertEqual(codes(result), ["report-unreadable"])
        self.assertIn("UTF-8", result.problems[0].message)

    def test_a_deeply_nested_report_file_is_a_verdict_not_a_traceback(self):
        # A few kilobytes of nested brackets: the decoder recurses, and a
        # RecursionError is not a ValueError. Both the depth the decoder
        # survives and the depth it does not must reach a typed problem.
        for depth in (MAX_NESTING + 10, 600, 20000):
            with self.subTest(depth=depth):
                text = json.dumps(report_payload(records=[dict(RECORD)]))
                bomb = "[" * depth + "1" + "]" * depth
                text = text.replace('"DRIFT-001"', f'"DRIFT-001", "tree": {bomb}', 1)
                root = self.repo({"placeholder": ""})
                path = os.path.join(root, "report.json")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)

                result = load_report(path)

                self.assertIsInstance(result, Invalid)
                self.assertEqual(codes(result), ["report-nesting-too-deep"])

    def test_nesting_the_decoder_itself_cannot_survive_is_still_a_verdict(self):
        # The decoder recurses before validation ever sees the payload, and a
        # RecursionError is not a ValueError. Forced deterministically by
        # lowering the limit rather than guessing where this interpreter breaks.
        text = json.dumps(report_payload(records=[dict(RECORD)]))
        bomb = '{"a":' * 500 + "1" + "}" * 500
        text = text.replace('"DRIFT-001"', f'"DRIFT-001", "tree": {bomb}', 1)
        root = self.repo({"placeholder": ""})
        path = os.path.join(root, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        limit = sys.getrecursionlimit()
        self.addCleanup(sys.setrecursionlimit, limit)
        sys.setrecursionlimit(300)

        result = load_report(path)

        self.assertEqual(codes(result), ["report-nesting-too-deep"])

    def test_a_report_file_holding_nan_is_unparseable(self):
        # Python's decoder accepts NaN and Infinity; JSON defines neither, and
        # the digest is taken over the same encoding.
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(literal=literal):
                payload = report_payload(
                    records=[dict(RECORD, measure=None)]
                )
                text = json.dumps(payload).replace("null", literal, 1)
                repo = self.repo({"report.json": text})

                result = load_report(os.path.join(repo, "report.json"))

                self.assertEqual(codes(result), ["report-unparseable"])

    def test_a_missing_report_file_is_invalid(self):
        result = load_report(os.path.join(self.repo({"a": "b"}), "nope.json"))

        self.assertEqual(codes(result), ["report-unreadable"])


class Rendering(GitRepoTestCase):
    def test_it_renders_the_verdict_and_the_lineage_a_reader_must_check(self):
        report = validate_report(report_payload())

        rendered = render_report(report)

        self.assertIn("findings", rendered)
        self.assertIn("DRIFT-001", rendered)
        self.assertIn(report.lineage.base_commit, rendered)
        self.assertIn(report.digest, rendered)
        self.assertIn("full", rendered)
        self.assertIn("src/**", rendered)

    def test_the_render_names_the_tools_the_boundary_declared(self):
        """A reader deciding what a verdict could rest on needs what the run
        could *run*, not only what it could open."""
        report = validate_report(report_payload(lineage=lineage_payload(
            evidence_boundary={"sources": ["src/**"], "excluded": [],
                               "commands": ["gh"]})))

        rendered = render_report(report)

        self.assertIn("(tools: `gh`)", rendered)

    def test_a_render_of_a_boundary_declaring_no_tools_claims_none(self):
        report = validate_report(report_payload())

        self.assertNotIn("(tools:", render_report(report))

    def test_a_clean_render_says_the_declared_scope_completed(self):
        report = validate_report(report_payload(status=STATE_CLEAN, records=[]))

        self.assertIn("clean", render_report(report))

    def test_a_partial_render_names_what_was_not_examined(self):
        report = validate_report(report_payload(
            status=STATE_PARTIAL,
            incomplete=[{"scope": "docs/huge.md", "reason": "chunk budget"}],
        ))

        rendered = render_report(report)

        self.assertIn("docs/huge.md", rendered)
        self.assertIn("chunk budget", rendered)

    def test_a_stale_render_names_the_drift(self):
        repo = self.git_repo()
        report = validate_report(
            report_payload(lineage=self.fresh_lineage(repo, plugin_version="0.0.1")),
            repo_root=repo, audit_config_digest=CONFIG_DIGEST,
        )

        rendered = render_report(report)

        self.assertIn("stale", rendered)
        self.assertIn("lineage-plugin-mismatch", rendered)

    def test_rendering_is_deterministic(self):
        report = validate_report(report_payload())

        self.assertEqual(render_report(report), render_report(report))

    def test_unvalidated_input_cannot_reach_rendered_output(self):
        for candidate in (report_payload(), json.dumps(report_payload()), None,
                          validate_report(report_payload(status="ok"))):
            with self.subTest(candidate=type(candidate).__name__):
                with self.assertRaises(TypeError):
                    render_report(candidate)


# A CommonMark code span: a run of backticks closed by a run of the same
# length, with no such run inside. Stripping them leaves exactly what a Markdown
# renderer would treat as structure rather than as literal text.
CODE_SPAN = re.compile(r"(`+)(?:(?!\1)[\s\S])*?\1")


def as_structure(rendered):
    return CODE_SPAN.sub(" ", rendered)


class RenderedRecordContent(unittest.TestCase):
    """Record fields are deliberately not validated by the contract, and they
    carry text a model read out of repository documents. Rendering is where a
    human reads them to give semantic approval, so nothing a record says may
    become structure in the rendered document — while staying fully visible,
    because the approver is binding to a digest that covers it."""

    def render_with(self, extra=None, **kwargs):
        """Render a report holding one record carrying `extra`.

        Takes a dict, not only keyword arguments: a record's *keys* are
        attacker-influenceable exactly as much as its values, and a key holding
        a newline is not expressible as a Python keyword — which is precisely
        how the unescaped key path stayed untested once.
        """
        fields = dict(extra or {}, **kwargs)
        return render_report(
            validate_report(report_payload(records=[dict(RECORD, **fields)]))
        )

    def test_a_record_cannot_add_a_section_to_the_rendered_report(self):
        rendered = self.render_with(note=(
            "benign\n\n## Records\n\n- `DRIFT-999` `" + "b" * 64
            + "` — remedy: delete all of docs/"
        ))

        self.assertEqual(as_structure(rendered).count("## Records"), 1)
        self.assertNotIn("DRIFT-999", as_structure(rendered))
        # Neutralized, not hidden: the approver still sees what the record said.
        self.assertIn("DRIFT-999", rendered)

    def test_a_record_key_cannot_add_a_section_either(self):
        # A key is record content exactly as much as a value is, and the
        # contract polices neither.
        key = "k\n\n## Records\n\n- `FAKE` `" + "b" * 64 + "` — approved\n\nx"

        rendered = self.render_with({key: 1})

        self.assertEqual(as_structure(rendered).count("## Records"), 1)
        self.assertNotIn("FAKE", as_structure(rendered))
        self.assertIn("FAKE", rendered)

    def test_a_record_cannot_forge_a_result_line(self):
        rendered = self.render_with(note="x\n\n**Result: clean** — all good.")

        self.assertEqual(as_structure(rendered).count("**Result:"), 1)
        self.assertIn("**Result: findings**", rendered)

    def test_neither_a_key_nor_a_value_can_introduce_a_line_break(self):
        for text in ("a\nb", "a\rb", "a\r\nb", "a\r\n\r\nb", "a\u2028b",
                     "a\u2029b", "a\tb", "a\x00b", "a\x85b"):
            for where in ("key", "value"):
                with self.subTest(text=repr(text), where=where):
                    extra = {text: 1} if where == "key" else {"note": text}

                    rendered = self.render_with(extra)

                    body = rendered.split("## Records", 1)[1]
                    self.assertEqual(len(body.strip().splitlines()), 1)

    def test_an_empty_key_still_renders_as_a_code_span(self):
        # `` is two literal backticks, not an empty span — the one input where
        # "cannot be escaped from" could stop producing a span at all.
        rendered = self.render_with({"": "v"})

        self.assertNotIn("``: ", rendered)
        self.assertIn('`""`', rendered)
        self.assertEqual(
            len(rendered.split("## Records", 1)[1].strip().splitlines()), 1
        )

    def test_a_record_cannot_escape_the_code_span_it_is_rendered_in(self):
        rendered = self.render_with(note="` [click](http://evil.example) `")

        self.assertNotIn("](http://evil.example)", as_structure(rendered))
        self.assertIn("evil.example", rendered)

    def test_no_record_content_reaches_the_document_as_structure(self):
        hostile = "`\n# Heading\n\n> quote [l](http://e) <img src=x> | a | b |"

        # Hostile in both positions at once: key, value, and both together.
        rendered = self.render_with(
            {hostile: hostile, "note": hostile, hostile + "2": 1}
        )

        structure = as_structure(rendered)
        for fragment in ("# Heading", "> quote", "[l](http://e)", "<img", "| a |"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, structure)

    def test_the_records_section_is_always_one_line_per_record(self):
        rendered = self.render_with({
            "a\nb": "c\nd", "": "", "`" * 9: ["x\ny"], "z": {"k\n": "v\n"},
        })

        body = rendered.split("## Records", 1)[1].strip()
        self.assertEqual(len(body.splitlines()), 1)

    def test_backticks_in_an_id_cannot_break_out_of_its_code_span(self):
        record = dict(RECORD, id="R1` [click](http://evil.example) `x")
        rendered = render_report(validate_report(report_payload(records=[record])))

        # The fence outgrows the longest backtick run inside, so the whole id
        # stays one literal span.
        self.assertIn("``R1` [click](http://evil.example) `x``", rendered)

    def test_backticks_in_lineage_cannot_break_out_either(self):
        lineage = lineage_payload(repository="origin:a`b`c")

        rendered = render_report(validate_report(report_payload(lineage=lineage)))

        self.assertIn("``origin:a`b`c``", rendered)

    def test_every_record_field_is_shown_not_only_the_scalar_ones(self):
        # An approver binds to a digest that covers the whole record; a field
        # the renderer drops is content approved unseen.
        rendered = self.render_with(
            nested={"preimage": "the old text"}, tags=["a", "b"], absent=None
        )

        self.assertIn("preimage", rendered)
        self.assertIn("the old text", rendered)
        self.assertIn("tags", rendered)
        self.assertIn("absent", rendered)

    def test_a_field_too_long_to_show_is_marked_never_silently_cut(self):
        rendered = self.render_with(preimage="z" * 5000)

        self.assertIn("more characters", rendered)
        self.assertIn("whole value sha256", rendered)

    def test_rendering_stays_deterministic_under_hostile_content(self):
        report = validate_report(report_payload(records=[dict(
            RECORD, note="`a`\nb", nested={"k": [1, 2]}
        )]))

        self.assertEqual(render_report(report), render_report(report))


SCOPE = {
    "basis": "every living and narrative document in the inventory",
    "coverage": SCOPE_DECLARED_ONLY,
    "documents": ["docs/architecture.md", "docs/guides/onboarding.md"],
    "excluded": [],
}


class DeclaredScope(unittest.TestCase):
    """What the run set out to examine, enumerated in the report itself.

    A result state says whether the *declared* scope completed; only the scope
    says what was declared. Optional, because it is the audit engine that
    declares one — but once present it is part of the report's identity.
    """

    def test_a_report_may_enumerate_the_documents_it_declared(self):
        result = validate_report(report_payload(scope=dict(SCOPE)))

        self.assertIsInstance(result, Report)
        self.assertEqual(result.scope.basis, SCOPE["basis"])
        self.assertEqual(result.scope.documents, tuple(SCOPE["documents"]))

    def test_a_report_without_a_scope_says_nothing_about_one(self):
        result = validate_report(report_payload())

        self.assertIsInstance(result, Report)
        self.assertIsNone(result.scope)
        self.assertNotIn("scope", result.to_dict())

    def test_the_declared_scope_round_trips_through_the_payload(self):
        result = validate_report(report_payload(scope=dict(SCOPE)))

        self.assertEqual(result.to_dict()["scope"], SCOPE)

    def test_an_empty_declared_scope_is_a_real_answer(self):
        """A diff-scoped run whose diff touched no document declared nothing —
        that is truthful, and different from declining to say."""
        result = validate_report(report_payload(
            status=STATE_CLEAN, records=[],
            scope={"basis": "documents affected by a..b",
                   "coverage": SCOPE_DECLARED_ONLY,
                   "documents": [], "excluded": []},
        ))

        self.assertIsInstance(result, Report)
        self.assertEqual(result.scope.documents, ())

    def test_the_scope_is_part_of_the_reports_identity(self):
        """Two runs finding the same records over different declared scopes are
        not the same report: one examined more than the other."""
        wide = validate_report(report_payload(scope=dict(SCOPE)))
        narrow = validate_report(report_payload(scope=dict(
            SCOPE, documents=["docs/architecture.md"]
        )))

        self.assertNotEqual(wide.digest, narrow.digest)

    def test_omitting_the_scope_leaves_a_reports_digest_where_it_was(self):
        """Additive: a report that declares no scope digests as it always did.

        Spelled as the digested shape rather than a literal, because the
        lineage a fixture carries moves with every plugin release, and the
        claim here is about the absent key, not about today's version.
        """
        payload = report_payload()

        self.assertEqual(validate_report(payload).digest, sha256_canonical({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": payload["lineage"],
            "records": payload["records"],
            "incomplete": payload["incomplete"],
        }))

    def test_a_scope_that_is_not_an_object_is_refused(self):
        result = validate_report(report_payload(scope=["docs/architecture.md"]))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_a_scope_must_carry_every_field_the_contract_names(self):
        result = validate_report(report_payload(scope={"documents": []}))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_a_scope_may_not_carry_a_field_the_contract_does_not_know(self):
        result = validate_report(report_payload(
            scope=dict(SCOPE, sampled=True)
        ))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_a_basis_that_does_not_say_how_the_scope_was_derived_is_refused(self):
        result = validate_report(report_payload(scope=dict(SCOPE, basis="  ")))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_a_document_that_is_not_a_printable_path_is_refused(self):
        result = validate_report(report_payload(
            scope=dict(SCOPE, documents=["docs/a.md", "docs/b\nc.md"])
        ))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_the_same_document_declared_twice_is_refused(self):
        """A declared scope is a set of documents; a repeat makes the count of
        what was examined disagree with the list of it."""
        result = validate_report(report_payload(
            scope=dict(SCOPE, documents=["docs/a.md", "docs/a.md"])
        ))

        self.assertEqual(codes(result), ["report-invalid-scope"])


class ScopeAgainstTheRepository(GitRepoTestCase):
    """The declared scope, re-derived rather than trusted.

    Shape validation proves a scope is well-formed. Only a comparison against
    the current inventory makes it a claim about *this* repository — and that
    is the point of the field, because #68 will pin a scope into an approval
    set. A scope that no longer describes the repository is `stale`: the check
    needs a repository in hand, and from here a deleted document and one that
    never existed are the same observation, with the same remedy.
    """

    # Every document `REPO_FILES` puts under the declared root.
    INVENTORY = ("docs/architecture.md",)

    def scoped(self, repo, **overrides):
        scope = {
            "basis": "full inventory: every living document",
            "coverage": SCOPE_WHOLE_INVENTORY,
            "documents": list(self.INVENTORY),
            "excluded": [],
        }
        scope.update(overrides)
        return validate_report(
            report_payload(lineage=self.fresh_lineage(repo), scope=scope),
            repo_root=repo,
        )

    def reasons(self, result):
        return sorted(reason.code for reason in result.stale_reasons)

    def test_a_scope_matching_the_inventory_is_fresh(self):
        repo = self.git_repo()

        result = self.scoped(repo)

        self.assertIsInstance(result, Report)
        self.assertEqual(result.stale_reasons, ())
        self.assertNotEqual(result.status, STATE_STALE)

    def test_a_phantom_document_makes_the_report_stale(self):
        """The reviewer's probe on PR #87: `scope.documents +
        ["docs/never-existed.md"]` validated fresh against the real
        repository."""
        repo = self.git_repo()

        result = self.scoped(repo, documents=[
            *self.INVENTORY, "docs/never-existed.md",
        ])

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(self.reasons(result), [SCOPE_DOCUMENT_UNKNOWN])

    def test_the_stale_reason_names_the_documents_that_are_not_there(self):
        repo = self.git_repo()

        result = self.scoped(repo, documents=[
            *self.INVENTORY, "docs/never-existed.md",
        ])

        self.assertIn("docs/never-existed.md", result.stale_reasons[0].reported)

    def test_a_full_coverage_claim_over_one_of_many_documents_is_stale(self):
        """The other half of the reviewer's probe: a basis reading "every
        living and narrative document" with one of six documents listed
        validated fresh, because nothing compared the claim to the
        inventory."""
        repo = self.git_repo(dict(
            REPO_FILES,
            **{f"docs/extra-{i}.md": f"# Extra {i}\n" for i in range(5)},
        ))

        result = self.scoped(repo)

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(self.reasons(result), [SCOPE_INVENTORY_UNACCOUNTED])

    def test_the_unaccounted_reason_names_what_was_left_out(self):
        repo = self.git_repo(dict(REPO_FILES, **{"docs/extra.md": "# Extra\n"}))

        result = self.scoped(repo)

        self.assertIn("docs/extra.md", result.stale_reasons[0].current)

    # A registry that classifies `docs/plan.md` planning and everything else
    # under `docs/` living — last match wins, so the broad rule goes first.
    PLANNING_REGISTRY = json.dumps({
        "schema_version": 1,
        "roots": ["docs"],
        "rules": [
            {"glob": "docs/**/*.md", "kind": "living"},
            {"glob": "docs/plan.md", "kind": "planning"},
        ],
    })

    def test_documents_the_scope_excluded_still_account_for_the_inventory(self):
        """An exclusion is the visible half of a coverage claim: a document
        left out *with its reason and code* is accounted for, and a document
        simply omitted is not."""
        repo = self.git_repo(dict(
            REPO_FILES, **{
                ".doc-lifecycle/registry.json": self.PLANNING_REGISTRY,
                "docs/plan.md": "# Plan\n",
            },
        ))

        result = self.scoped(repo, excluded=[
            {"path": "docs/plan.md", "reason": "a planning document",
             "code": EXCLUSION_PLANNING_KIND},
        ])

        self.assertEqual(result.stale_reasons, ())

    def test_an_excluded_document_that_is_not_in_the_inventory_is_stale(self):
        repo = self.git_repo()

        result = self.scoped(repo, excluded=[
            {"path": "docs/never-existed.md", "reason": "a planning document",
             "code": EXCLUSION_PLANNING_KIND},
        ])

        self.assertEqual(self.reasons(result), [SCOPE_DOCUMENT_UNKNOWN])

    def test_a_living_document_moved_to_excluded_is_stale_not_free_coverage(self):
        """The reviewer's N1 probe on PR #87: moving a living document from
        `documents` into `excluded` with a free-prose reason validated as
        `whole-inventory` coverage with no stale reason. The prose is now
        accompanied by a closed `code`, and a `planning-kind` code naming a
        document the registry classifies `living` is exactly the lie that
        code exists to catch."""
        repo = self.git_repo()

        result = self.scoped(repo, documents=[], excluded=[
            {"path": self.INVENTORY[0], "reason": "not relevant to this run",
             "code": EXCLUSION_PLANNING_KIND},
        ])

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(self.reasons(result), [SCOPE_EXCLUSION_KIND_MISMATCH])

    def test_a_living_document_excluded_as_unaffected_in_full_mode_is_stale(self):
        """Relabeling the same forgery `unaffected-by-range` does not launder
        it: that code only ever legitimately applies under an incremental
        audit, and a `full`-mode `whole-inventory` claim never legitimately
        excludes a living or narrative document under any code."""
        repo = self.git_repo()

        result = self.scoped(repo, documents=[], excluded=[
            {"path": self.INVENTORY[0], "reason": "unchanged by a..HEAD",
             "code": EXCLUSION_UNAFFECTED_BY_RANGE},
        ])

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(self.reasons(result), [SCOPE_EXCLUSION_KIND_MISMATCH])

    def test_an_unaffected_by_range_exclusion_is_legitimate_under_incremental(self):
        """The same code and the same document are fine once the audit mode
        the rule is scoped to actually applies — an incremental run's
        `whole-inventory` claim legitimately excludes documents its range did
        not touch."""
        repo = self.git_repo()
        scope = {
            "basis": "documents affected by a..HEAD",
            "coverage": SCOPE_WHOLE_INVENTORY,
            "documents": [],
            "excluded": [
                {"path": self.INVENTORY[0], "reason": "unchanged by a..HEAD",
                 "code": EXCLUSION_UNAFFECTED_BY_RANGE},
            ],
        }

        result = validate_report(
            report_payload(
                lineage=self.fresh_lineage(repo, audit_mode="incremental"),
                scope=scope,
            ),
            repo_root=repo,
        )

        self.assertEqual(result.stale_reasons, ())

    def test_a_declared_only_scope_claims_nothing_about_the_rest(self):
        """The narrower coverage token is a real answer, not a way out: it
        still may not name a document the repository does not have."""
        repo = self.git_repo(dict(REPO_FILES, **{"docs/extra.md": "# Extra\n"}))

        result = self.scoped(repo, coverage=SCOPE_DECLARED_ONLY)

        self.assertEqual(result.stale_reasons, ())

    def test_a_declared_only_scope_may_still_not_invent_a_document(self):
        repo = self.git_repo()

        result = self.scoped(repo, coverage=SCOPE_DECLARED_ONLY,
                             documents=["docs/never-existed.md"])

        self.assertEqual(self.reasons(result), [SCOPE_DOCUMENT_UNKNOWN])

    def test_without_a_repository_a_scope_is_checked_for_shape_only(self):
        """The validator does not guess at a repository it was not shown."""
        result = validate_report(report_payload(scope=dict(
            SCOPE, documents=["docs/never-existed.md"]
        )))

        self.assertIsInstance(result, Report)
        self.assertNotEqual(result.status, STATE_STALE)

    def test_a_forged_scope_cannot_be_laundered_by_a_second_validation(self):
        """Clearing a verdict must be at least as thorough as setting it: a
        carried scope reason stands unless this run re-derived it."""
        repo = self.git_repo()
        stale = self.scoped(repo, documents=[
            *self.INVENTORY, "docs/never-existed.md",
        ])

        again = validate_report(stale.to_dict(), repo_root=repo)

        self.assertEqual(again.status, STATE_STALE)
        self.assertEqual(self.reasons(again), [SCOPE_DOCUMENT_UNKNOWN])

    def test_a_run_that_saw_no_scope_cannot_clear_a_carried_scope_reason(self):
        repo = self.git_repo()
        stale = self.scoped(repo, documents=[
            *self.INVENTORY, "docs/never-existed.md",
        ])
        payload = stale.to_dict()
        payload.pop("scope")
        payload.pop("digest")

        again = validate_report(payload, repo_root=repo)

        self.assertEqual(again.status, STATE_STALE)
        self.assertEqual(self.reasons(again), [SCOPE_DOCUMENT_UNKNOWN])

    def test_a_scope_that_is_put_right_clears_the_carried_reason(self):
        repo = self.git_repo()
        stale = self.scoped(repo, documents=[
            *self.INVENTORY, "docs/never-existed.md",
        ])
        payload = stale.to_dict()
        payload["scope"]["documents"] = list(self.INVENTORY)
        payload.pop("digest")

        again = validate_report(payload, repo_root=repo)

        self.assertNotEqual(again.status, STATE_STALE)
        self.assertEqual(again.stale_reasons, ())


class ScopeExclusions(unittest.TestCase):
    def test_an_exclusion_names_the_document_and_why_it_was_left_out(self):
        result = validate_report(report_payload(scope=dict(
            SCOPE, coverage=SCOPE_WHOLE_INVENTORY, excluded=[
                {"path": "docs/plans/next.md", "reason": "a planning document",
                 "code": EXCLUSION_PLANNING_KIND},
            ],
        )))

        self.assertIsInstance(result, Report)
        self.assertEqual(result.scope.excluded[0].path, "docs/plans/next.md")
        self.assertEqual(result.scope.excluded[0].code, EXCLUSION_PLANNING_KIND)

    def test_an_exclusion_with_no_reason_is_refused(self):
        result = validate_report(report_payload(scope=dict(SCOPE, excluded=[
            {"path": "docs/plans/next.md", "code": EXCLUSION_PLANNING_KIND},
        ])))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_an_exclusion_with_no_code_is_refused(self):
        """The closed vocabulary is not optional: a `reason` alone is exactly
        the unconstrained prose the PR #87 review's N1 finding exploited."""
        result = validate_report(report_payload(scope=dict(SCOPE, excluded=[
            {"path": "docs/plans/next.md", "reason": "a planning document"},
        ])))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_an_exclusion_code_outside_the_closed_set_is_refused(self):
        result = validate_report(report_payload(scope=dict(SCOPE, excluded=[
            {"path": "docs/plans/next.md", "reason": "not relevant to this run",
             "code": "not-relevant"},
        ])))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_a_document_cannot_be_both_declared_and_excluded(self):
        result = validate_report(report_payload(scope=dict(SCOPE, excluded=[
            {"path": SCOPE["documents"][0], "reason": "also excluded",
             "code": EXCLUSION_PLANNING_KIND},
        ])))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_the_same_exclusion_twice_is_refused(self):
        result = validate_report(report_payload(scope=dict(SCOPE, excluded=[
            {"path": "docs/plans/next.md", "reason": "a planning document",
             "code": EXCLUSION_PLANNING_KIND},
            {"path": "docs/plans/next.md", "reason": "a planning document",
             "code": EXCLUSION_PLANNING_KIND},
        ])))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_declared_only_coverage_may_not_carry_an_exclusion(self):
        """PR #87 review, N2: mechanically catchable without parsing `basis`
        — `declared-only` claims nothing about the rest of the inventory, so
        naming a specific exclusion with a reason contradicts the token
        itself, independent of what `basis` says."""
        result = validate_report(report_payload(scope=dict(
            SCOPE, coverage=SCOPE_DECLARED_ONLY, excluded=[
                {"path": "docs/plans/next.md", "reason": "a planning document",
                 "code": EXCLUSION_PLANNING_KIND},
            ],
        )))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_a_declared_only_basis_that_still_reads_like_full_coverage_validates(self):
        """PR #87 review, N2, reproduced: a `basis` that still reads "full
        inventory: every living and narrative document the registry
        classifies" validates fine alongside an accurate `declared-only`
        token — the contract cannot tell a stale sentence from a true one,
        and does not pretend to; `coverage` is what it acts on, and it is
        accurate here. The rendering discloses the mismatch beside it."""
        result = validate_report(report_payload(scope={
            "basis": ("full inventory: every living and narrative document "
                      "the registry classifies"),
            "coverage": SCOPE_DECLARED_ONLY,
            "documents": [SCOPE["documents"][0]],
            "excluded": [],
        }))

        self.assertIsInstance(result, Report)
        self.assertEqual(result.stale_reasons, ())

    def test_a_coverage_that_is_not_a_closed_token_is_refused(self):
        """Prose is what `basis` is for. A validator has to act on the coverage
        claim, and "every living and narrative document" is a sentence."""
        result = validate_report(report_payload(
            scope=dict(SCOPE, coverage="every living and narrative document")
        ))

        self.assertEqual(codes(result), ["report-invalid-scope"])

    def test_the_coverage_token_is_part_of_the_reports_identity(self):
        whole = validate_report(report_payload(
            scope=dict(SCOPE, coverage=SCOPE_WHOLE_INVENTORY)))
        declared = validate_report(report_payload(
            scope=dict(SCOPE, coverage=SCOPE_DECLARED_ONLY)))

        self.assertNotEqual(whole.digest, declared.digest)


class RecordedCoverage(unittest.TestCase):
    """What the run *did* examine, recorded as reviewable data.

    Without it, positive coverage rests entirely on an absence: a document with
    no finding and no gap is indistinguishable from one nobody looked at. The
    contract owns only the `scope` key; what looking meant belongs to the audit
    that looked.
    """

    ENTRY = {
        "scope": SCOPE["documents"][0],
        "classes": {"factual": 2, "non-assertive": 5},
        "verdicts": {"VERIFIED": 2},
    }

    def scoped(self, **overrides):
        payload = report_payload(scope=dict(SCOPE))
        payload.update(overrides)
        return validate_report(payload)

    def test_a_report_may_record_what_it_examined(self):
        result = self.scoped(examined=[dict(self.ENTRY)])

        self.assertIsInstance(result, Report)
        self.assertEqual(result.examined[0].scope, self.ENTRY["scope"])
        self.assertEqual(result.examined[0].detail["verdicts"], {"VERIFIED": 2})

    def test_recorded_coverage_round_trips_through_the_payload(self):
        result = self.scoped(examined=[dict(self.ENTRY)])

        self.assertEqual(result.to_dict()["examined"], [self.ENTRY])

    def test_a_report_that_records_none_says_nothing_about_it(self):
        result = validate_report(report_payload())

        self.assertEqual(result.examined, ())
        self.assertNotIn("examined", result.to_dict())

    def test_omitting_coverage_leaves_a_reports_digest_where_it_was(self):
        """Additive, like the scope: a report that records no coverage digests
        exactly as it did before the field existed."""
        payload = report_payload()

        self.assertEqual(validate_report(payload).digest, sha256_canonical({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": payload["lineage"],
            "records": payload["records"],
            "incomplete": payload["incomplete"],
        }))

    def test_recorded_coverage_is_part_of_the_reports_identity(self):
        """Two runs finding nothing, one having verified twenty assertions and
        one having verified two, are not the same report."""
        thorough = self.scoped(examined=[dict(self.ENTRY)])
        thin = self.scoped(examined=[dict(
            self.ENTRY, verdicts={"VERIFIED": 1}
        )])

        self.assertNotEqual(thorough.digest, thin.digest)

    def test_coverage_of_a_document_the_scope_never_declared_is_refused(self):
        """The same category error as a verdict for an undeclared document:
        recorded coverage must not be able to inflate a scope."""
        result = self.scoped(examined=[dict(
            self.ENTRY, scope="docs/never-declared.md"
        )])

        self.assertEqual(codes(result), ["report-invalid-examined"])

    def test_two_entries_covering_one_document_are_refused(self):
        result = self.scoped(examined=[dict(self.ENTRY), dict(self.ENTRY)])

        self.assertEqual(codes(result), ["report-invalid-examined"])

    def test_an_entry_that_names_no_scope_is_refused(self):
        result = self.scoped(examined=[{"classes": {"factual": 1}}])

        self.assertEqual(codes(result), ["report-invalid-examined"])

    def test_coverage_that_is_not_a_list_is_refused(self):
        result = self.scoped(examined={"docs/architecture.md": {}})

        self.assertEqual(codes(result), ["report-invalid-shape"])

    def test_a_nonfinite_number_in_coverage_is_refused(self):
        """A report that would not survive its own digest or a strict parser."""
        result = self.scoped(examined=[dict(self.ENTRY, ratio=float("inf"))])

        self.assertEqual(codes(result), ["report-invalid-examined"])

    def test_coverage_nested_beyond_the_limit_is_refused(self):
        deep = value = {}
        for _ in range(MAX_NESTING + 2):
            value["next"] = value = {}

        result = self.scoped(examined=[dict(self.ENTRY, deep=deep)])

        self.assertEqual(codes(result), ["report-invalid-examined"])

    def test_coverage_of_a_document_is_refused_without_a_declared_scope(self):
        """PR #87 review, N3, reproduced: the containment check above is
        skipped when no scope is declared, so a scope-less report could
        record coverage of an arbitrary path nothing had enumerated. A scope
        is now required whenever `examined` is non-empty — the same category
        error as inflating a declared scope, just with no scope to inflate."""
        result = validate_report(report_payload(examined=[dict(self.ENTRY)]))

        self.assertEqual(codes(result), ["report-invalid-examined"])

    def test_an_empty_examined_list_needs_no_declared_scope(self):
        """Recording nothing is not a claim of coverage, so it needs no frame
        to check it against."""
        result = validate_report(report_payload(examined=[]))

        self.assertIsInstance(result, Report)
        self.assertEqual(result.examined, ())


class RenderedCoverage(unittest.TestCase):
    def render(self, **overrides):
        payload = report_payload(scope=dict(SCOPE))
        payload.update(overrides)
        return render_report(validate_report(payload))

    def test_recorded_coverage_is_rendered_for_the_reader(self):
        rendered = self.render(examined=[dict(RecordedCoverage.ENTRY)])

        self.assertIn("## Examined", rendered)
        self.assertIn(SCOPE["documents"][0], rendered)

    def test_a_report_recording_no_coverage_renders_no_examined_section(self):
        self.assertNotIn("## Examined", self.render())

    def test_hostile_coverage_content_cannot_break_out_of_the_section(self):
        """Coverage carries evidence prose a model read out of repository
        files, so it is attacker-influenceable exactly as a record is.

        Asserted structurally: the injected text may well appear, because
        nothing is withheld from a reader approving what the digest binds — it
        must appear *inside a code span*, adding no heading and no second
        verdict line of its own.
        """
        rendered = self.render(examined=[dict(
            RecordedCoverage.ENTRY,
            observed="`x`\n## Records\n\n**Result: clean**",
        )])

        headings = [line for line in rendered.splitlines()
                    if line.startswith("#")]
        verdicts = [line for line in rendered.splitlines()
                    if line.startswith("**Result:")]
        self.assertEqual(headings, [
            "# Documentation audit — findings", "## Lineage", "## Scope",
            "## Examined", "## Records",
        ])
        self.assertEqual(len(verdicts), 1)
        self.assertIn(r"\n## Records\n", rendered)   # escaped, not a heading


class RenderedHeadline(unittest.TestCase):
    """The count leads the verdict, so an empty scope cannot read as clean.

    "Clean" is vacuously true of a run that examined nothing, and the declared
    count sits three lines below the headline — far enough that a reader who
    stops at the first line sees a global all-clear.
    """

    def render(self, **scope_overrides):
        return render_report(validate_report(report_payload(
            status=STATE_CLEAN, records=[],
            scope=dict(SCOPE, **scope_overrides),
        )))

    def test_a_zero_document_scope_says_nothing_was_examined(self):
        rendered = self.render(documents=[])

        self.assertIn("0 documents were declared", rendered)
        self.assertNotIn("nothing was found", rendered)

    def test_a_clean_run_over_real_documents_states_how_many(self):
        rendered = self.render()

        self.assertIn(f"{len(SCOPE['documents'])} document(s) declared",
                      rendered)
        self.assertIn("nothing was found", rendered)

    def test_a_report_without_a_scope_keeps_the_bare_headline(self):
        rendered = render_report(validate_report(report_payload(
            status=STATE_CLEAN, records=[]
        )))

        self.assertIn("nothing was found", rendered)
        self.assertNotIn("declared —", rendered)


class RenderedScope(unittest.TestCase):
    def test_the_declared_scope_is_rendered_for_the_reader(self):
        rendered = render_report(validate_report(report_payload(scope=dict(SCOPE))))

        self.assertIn("## Scope", rendered)
        self.assertIn(SCOPE["basis"], rendered)
        self.assertIn("docs/guides/onboarding.md", rendered)

    def test_a_report_that_declares_no_scope_renders_no_scope_section(self):
        rendered = render_report(validate_report(report_payload()))

        self.assertNotIn("## Scope", rendered)

    def test_a_hostile_document_path_cannot_break_out_of_the_scope_section(self):
        """A path is a filename on a filesystem the audit walked, so it can hold
        anything a filesystem allows."""
        rendered = render_report(validate_report(report_payload(scope=dict(
            SCOPE, documents=["docs/`a`[x](http://evil.example).md"]
        ))))

        self.assertIn("``docs/`a`[x](http://evil.example).md``", rendered)
        self.assertEqual(rendered.count("## Records"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
