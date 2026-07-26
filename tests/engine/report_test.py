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
from doclifecycle.render import render_report  # noqa: E402
from doclifecycle.report import (  # noqa: E402
    AUDIT_MODES,
    REQUIRED_LINEAGE_FIELDS,
    Report,
    current_lineage,
    load_report,
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
        "evidence_boundary": {"sources": ["src/**"], "excluded": ["src/vendor/**"]},
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

    def render_with(self, **extra):
        return render_report(
            validate_report(report_payload(records=[dict(RECORD, **extra)]))
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

    def test_a_record_cannot_forge_a_result_line(self):
        rendered = self.render_with(note="x\n\n**Result: clean** — all good.")

        self.assertEqual(as_structure(rendered).count("**Result:"), 1)
        self.assertIn("**Result: findings**", rendered)

    def test_a_record_cannot_introduce_a_line_break_at_all(self):
        for text in ("a\nb", "a\rb", "a\r\nb", "a b"):
            with self.subTest(text=repr(text)):
                rendered = self.render_with(note=text)

                body = rendered.split("## Records", 1)[1]
                self.assertEqual(len(body.strip().splitlines()), 1)

    def test_a_record_cannot_escape_the_code_span_it_is_rendered_in(self):
        rendered = self.render_with(note="` [click](http://evil.example) `")

        self.assertNotIn("](http://evil.example)", as_structure(rendered))
        self.assertIn("evil.example", rendered)

    def test_no_record_content_reaches_the_document_as_structure(self):
        hostile = "`\n# Heading\n\n> quote [l](http://e) <img src=x> | a | b |"

        rendered = self.render_with(note=hostile, path=hostile, hint=hostile)

        structure = as_structure(rendered)
        for fragment in ("# Heading", "> quote", "[l](http://e)", "<img", "| a |"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, structure)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
