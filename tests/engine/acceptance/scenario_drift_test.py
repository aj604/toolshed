#!/usr/bin/env python3
"""Scenario drift (issue #65): the drift audit over the acceptance fixture.

Seams, per the engine's convention (`plugins/doc-lifecycle/engine/README.md`):
`plan_drift_audit()` and `audit_drift()` as library calls, and `python3 -m
doclifecycle drift-audit` as a subprocess — over the REAL temporary git
repository scenario one builds, with its two commits, its hostile filenames,
its symlinks, and its prompt-injection content in both a document and a source
file.

What it holds that the unit suite cannot: the fixture's diff really is a source
change between two commits, its narrative anchor really names the file that
changed, its waiver file is the shape a scheduled install carries, and the
documents the audit walks include filenames chosen to break naive tooling.

Run: python3 tests/engine/acceptance/scenario_drift_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from support import ENGINE  # noqa: E402  (also puts the engine on sys.path)

from doclifecycle.drift import (  # noqa: E402
    MODE_FULL,
    MODE_INCREMENTAL,
    audit_drift,
    plan_drift_audit,
)
from doclifecycle.finding import FACTUAL, NORMATIVE, RATIONALE  # noqa: E402
from doclifecycle.render import render_report  # noqa: E402
from doclifecycle.report import validate_report  # noqa: E402
from doclifecycle.results import (  # noqa: E402
    STATE_FINDINGS,
    STATE_PARTIAL,
    Invalid,
)
from doclifecycle.segment import segment_document  # noqa: E402

# Every living document in the fixture: the ordinary one, the fee policy the
# bloat scenario added, and the three filenames chosen to break naive tooling.
LIVING_DOCS = (
    fixture.HOSTILE_LEADING_DASH_DOC,
    fixture.LIVING_DOC,
    fixture.POLICY_DOC,
    fixture.HOSTILE_SHELL_METACHAR_DOC,
    fixture.HOSTILE_HOMOGLYPH_DOC,
)

# What the second fixture commit changed the fee rate to.
OBSERVED_RATE = "FLAT_FEE_RATE = 0.025"


def run_cli(*argv, cwd=None):
    env = dict(os.environ, PYTHONPATH=ENGINE)
    return subprocess.run(
        [sys.executable, "-m", "doclifecycle", *argv],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def marker(repo):
    with open(os.path.join(repo, fixture.MARKER_PATH), encoding="utf-8") as fh:
        return fh.read().strip()


class DriftScenarioTestCase(fixture.AcceptanceFixtureTestCase):
    def verdicts(self, repo, plan, stale=(fixture.LIVING_FACTUAL,)):
        """A lane's answer for every living document the plan declared.

        The fixture's own prose supplies three of the four assertion classes:
        its normative sentence and its rationale sentence carry no evidence
        obligation and so are classified and left unjudged, and everything else
        is factual and VERIFIED against the fixture's evidence source — except
        the texts named in `stale`, so a scenario states only what it is about.
        """
        unjudged = {
            fixture.LIVING_NORMATIVE: NORMATIVE,
            fixture.LIVING_RATIONALE: RATIONALE,
        }
        documents = []
        for planned in plan.documents:
            if planned.obligation != "assertions":
                continue
            segmentation = segment_document(repo, planned.path)
            entries = []
            for unit in segmentation.units:
                if not unit.assertion_capable:
                    continue
                if unit.text in unjudged:
                    entries.append({"unit": unit.digest,
                                    "assertion_class": unjudged[unit.text]})
                elif unit.text in stale:
                    entries.append({
                        "unit": unit.digest, "assertion_class": FACTUAL,
                        "verdict": "STALE", "kind": "value", "tier": 3,
                        "evidence": {"source": fixture.EVIDENCE_SOURCE,
                                     "line": 7, "observed": OBSERVED_RATE},
                        "fix": unit.text.replace("2% rate", "2.5% rate"),
                    })
                else:
                    entries.append({
                        "unit": unit.digest, "assertion_class": FACTUAL,
                        "verdict": "VERIFIED", "kind": "behavior", "tier": 2,
                        "evidence": {"source": fixture.EVIDENCE_SOURCE,
                                     "line": 7, "observed": OBSERVED_RATE},
                    })
            documents.append({"path": planned.path, "status": "ok",
                              "verdicts": entries})
        return {"documents": documents}

    def full_report(self, repo, **kwargs):
        plan = plan_drift_audit(repo, mode=MODE_FULL)
        kwargs.setdefault("verdicts", self.verdicts(repo, plan))
        return audit_drift(repo, mode=MODE_FULL, **kwargs)

    def diff_report(self, repo, **kwargs):
        plan = plan_drift_audit(repo, mode=MODE_INCREMENTAL, since=marker(repo))
        kwargs.setdefault("verdicts", self.verdicts(repo, plan))
        return audit_drift(repo, mode=MODE_INCREMENTAL, since=marker(repo),
                           **kwargs)


class TruthfulScopeClaims(DriftScenarioTestCase):
    """First acceptance criterion: two modes, two honest claims."""

    def test_a_full_corpus_run_declares_every_living_and_narrative_document(self):
        repo = self.build_fixture()

        report = self.full_report(repo)

        self.assertEqual(
            set(report.scope.documents),
            set(LIVING_DOCS) | {fixture.NARRATIVE_DOC},
        )

    def test_a_diff_scoped_run_declares_only_what_the_change_reached(self):
        """The second fixture commit changed the payment module. Exactly two
        documents name it, and neither the hostile living documents nor the
        planning document are declared."""
        repo = self.build_fixture()

        report = self.diff_report(repo)

        self.assertEqual(report.scope.documents,
                         (fixture.LIVING_DOC, fixture.NARRATIVE_DOC))

    def test_the_two_runs_do_not_claim_the_same_coverage(self):
        repo = self.build_fixture()

        full = self.full_report(repo)
        diff = self.diff_report(repo)

        self.assertNotEqual(full.scope.basis, diff.scope.basis)
        self.assertIn(marker(repo), diff.scope.basis)
        self.assertLess(len(diff.scope.documents), len(full.scope.documents))

    def test_every_declared_document_completed(self):
        repo = self.build_fixture()

        report = self.full_report(repo)

        self.assertEqual(
            [i.scope for i in report.incomplete
             if i.scope in report.scope.documents],
            [],
        )

    def test_an_unclassified_document_stops_it_claiming_full_coverage(self):
        """The fixture holds one document under the declared root that no rule
        claims. Its obligation is unknown, so it could not be examined — and a
        full-corpus run that stayed silent about it would be claiming a
        coverage it does not have."""
        repo = self.build_fixture()

        report = self.full_report(repo)

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual([i.scope for i in report.incomplete],
                         [fixture.STRAY_DOC])

    def test_the_excluded_planning_document_is_named_with_its_reason(self):
        repo = self.build_fixture()

        plan = plan_drift_audit(repo, mode=MODE_FULL)

        self.assertIn(fixture.PLANNING_DOC, [d.path for d in plan.excluded])

    def test_both_reports_are_the_validator_s_own_verdict(self):
        """Built through `report.validate_report`, so an audit cannot emit
        something the contract would refuse — and each report re-validates from
        its own payload to the same verdict."""
        repo = self.build_fixture()

        for report in (self.full_report(repo), self.diff_report(repo)):
            with self.subTest(report.lineage.audit_mode):
                revalidated = validate_report(report.to_dict(), repo_root=repo,
                                              audit_config_digest=report.lineage
                                              .audit_config_digest)
                self.assertEqual(revalidated.status, report.status)
                self.assertEqual(revalidated.digest, report.digest)
                self.assertEqual(revalidated.scope.documents,
                                 report.scope.documents)


class AFailedChunkIsNeverClean(DriftScenarioTestCase):
    """Second acceptance criterion."""

    def failed_chunk_report(self, repo):
        plan = plan_drift_audit(repo, mode=MODE_FULL)
        payload = self.verdicts(repo, plan)
        payload["documents"] = [
            entry for entry in payload["documents"]
            if entry["path"] != fixture.LIVING_DOC
        ] + [{
            "path": fixture.LIVING_DOC, "status": "failed", "chunk": "chunk-2",
            "reason": "the chunk worker failed twice",
        }]
        return audit_drift(repo, mode=MODE_FULL, verdicts=payload)

    def test_a_failed_chunk_makes_the_result_partial(self):
        repo = self.build_fixture()

        report = self.failed_chunk_report(repo)

        self.assertEqual(report.status, STATE_PARTIAL)

    def test_the_gap_names_the_document_and_the_chunk_that_lost_it(self):
        repo = self.build_fixture()

        report = self.failed_chunk_report(repo)

        gap = next(i for i in report.incomplete
                   if i.scope == fixture.LIVING_DOC)
        self.assertIn("chunk-2", gap.reason)

    def test_the_document_stays_in_the_declared_scope_it_failed_inside(self):
        """Dropping it from the scope would turn a gap into a silence."""
        repo = self.build_fixture()

        report = self.failed_chunk_report(repo)

        self.assertIn(fixture.LIVING_DOC, report.scope.documents)

    def test_no_rendering_of_that_report_reads_as_clean(self):
        repo = self.build_fixture()

        rendered = render_report(self.failed_chunk_report(repo))

        self.assertNotIn("clean", rendered)
        self.assertIn("NOT fully examined", rendered)
        self.assertIn("## Not examined", rendered)
        self.assertIn("chunk-2", rendered)

    def test_the_command_exits_partial_rather_than_success(self):
        repo = self.build_fixture()
        payload = os.path.join(repo, "verdicts.json")
        with open(payload, "w", encoding="utf-8") as fh:
            plan = plan_drift_audit(repo, mode=MODE_FULL)
            entries = self.verdicts(repo, plan)
            entries["documents"] = [
                e for e in entries["documents"] if e["path"] != fixture.LIVING_DOC
            ] + [{"path": fixture.LIVING_DOC, "status": "failed",
                  "chunk": "chunk-2", "reason": "the chunk worker failed twice"}]
            json.dump(entries, fh)

        result = run_cli("drift-audit", "--repo", repo, "--verdicts", payload)

        self.assertEqual(result.returncode, 4)
        self.assertIn("not-examined", result.stderr)


class TheNarrativeDocument(DriftScenarioTestCase):
    """Third acceptance criterion: dated honestly, never line-verified."""

    def anchor_record(self, report, code="ANCHOR-STALE"):
        return next(r for r in report.records if r.extra["code"] == code)

    def test_the_anchor_is_stale_against_the_module_it_names(self):
        """`> As of 2026-07-20 (... src/payment_service.py)`, and the second
        fixture commit changed that module afterwards."""
        repo = self.build_fixture()

        record = self.anchor_record(self.full_report(repo))

        self.assertEqual(record.extra["path"], fixture.NARRATIVE_DOC)
        self.assertEqual(record.extra["as_of"], "2026-07-20")
        self.assertEqual(record.extra["evidence"]["source"],
                         fixture.EVIDENCE_SOURCE)

    def test_the_finding_points_at_the_anchor_line_itself(self):
        repo = self.build_fixture()

        record = self.anchor_record(self.full_report(repo))

        self.assertEqual(record.extra["location"],
                         f"{fixture.NARRATIVE_DOC}:3")
        self.assertEqual(record.extra["assertion"], fixture.NARRATIVE_ANCHOR)

    def test_the_check_fires_in_the_diff_scoped_run_too(self):
        repo = self.build_fixture()

        record = self.anchor_record(self.diff_report(repo))

        self.assertEqual(record.extra["code"], "ANCHOR-STALE")

    def test_its_prose_is_never_forced_through_a_claim_check(self):
        """The guide's opening is connective prose. A narrative document owes
        an honest date, not a verdict per sentence — so no verdict is asked for
        it, and none is accepted."""
        repo = self.build_fixture()
        plan = plan_drift_audit(repo, mode=MODE_FULL)
        segmentation = segment_document(repo, fixture.NARRATIVE_DOC)
        unit = next(u for u in segmentation.units
                    if u.text == fixture.NARRATIVE_NON_ASSERTIVE)
        payload = self.verdicts(repo, plan)
        payload["documents"].append({
            "path": fixture.NARRATIVE_DOC, "status": "ok",
            "verdicts": [{
                "unit": unit.digest, "assertion_class": FACTUAL,
                "verdict": "VERIFIED", "kind": "behavior", "tier": 1,
                "evidence": {"source": fixture.EVIDENCE_SOURCE,
                             "observed": OBSERVED_RATE},
            }],
        })

        result = audit_drift(repo, mode=MODE_FULL, verdicts=payload)

        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems],
                         ["drift-verdict-on-narrative-document"])

    def test_it_is_examined_without_a_model_saying_anything(self):
        repo = self.build_fixture()

        report = audit_drift(repo, mode=MODE_FULL)

        self.assertNotIn(fixture.NARRATIVE_DOC,
                         [i.scope for i in report.incomplete])
        self.assertIn("ANCHOR-STALE", [r.extra["code"] for r in report.records])


class FollowableEvidence(DriftScenarioTestCase):
    """Fourth acceptance criterion."""

    def stale_record(self, report):
        return next(r for r in report.records if r.extra["code"] == "STALE")

    def test_a_stale_finding_names_the_document_line_it_is_about(self):
        repo = self.build_fixture()

        record = self.stale_record(self.full_report(repo))

        self.assertEqual(record.extra["location"], f"{fixture.LIVING_DOC}:3")
        self.assertEqual(record.extra["assertion"], fixture.LIVING_FACTUAL)

    def test_it_names_the_source_line_and_the_fact_observed_there(self):
        repo = self.build_fixture()

        record = self.stale_record(self.full_report(repo))

        self.assertEqual(record.extra["evidence"],
                         {"source": fixture.EVIDENCE_SOURCE, "line": 7,
                          "observed": OBSERVED_RATE})

    def test_the_pointer_reaches_the_fact_it_claims_to(self):
        """Followable in the strong sense: open the cited file at the cited
        line and the observed fact is there."""
        repo = self.build_fixture()
        record = self.stale_record(self.full_report(repo))

        with open(os.path.join(repo, record.extra["evidence"]["source"]),
                  encoding="utf-8") as fh:
            lines = fh.read().splitlines()

        self.assertEqual(lines[record.extra["evidence"]["line"] - 1],
                         record.extra["evidence"]["observed"])

    def test_the_waiver_the_install_carries_surfaces_on_the_finding(self):
        repo = self.build_fixture()

        record = self.stale_record(
            self.full_report(repo, waivers=fixture.WAIVERS_PATH)
        )

        self.assertEqual(record.extra["waived"]["source"], fixture.WAIVERS_PATH)
        self.assertEqual(record.extra["waived"]["claim"],
                         "calculates fees at a flat 2% rate")

    def test_the_waiver_does_not_erase_the_finding_from_the_raw_report(self):
        repo = self.build_fixture()

        waived = self.full_report(repo, waivers=fixture.WAIVERS_PATH)
        raw = self.full_report(repo)

        self.assertEqual([r.extra["code"] for r in waived.records],
                         [r.extra["code"] for r in raw.records])
        self.assertEqual([r.digest for r in waived.records],
                         [r.digest for r in raw.records])

    def test_an_injected_instruction_cannot_be_given_a_verdict(self):
        """The fixture's living document tells its reader to approve everything
        and delete a file. It is an HTML comment: structure, not prose."""
        repo = self.build_fixture()
        plan = plan_drift_audit(repo, mode=MODE_FULL)
        segmentation = segment_document(repo, fixture.LIVING_DOC)
        injected = next(u for u in segmentation.units if u.kind == "html_block")
        payload = self.verdicts(repo, plan)
        for entry in payload["documents"]:
            if entry["path"] == fixture.LIVING_DOC:
                entry["verdicts"].append({
                    "unit": injected.digest, "assertion_class": FACTUAL,
                    "verdict": "VERIFIED", "kind": "behavior", "tier": 1,
                    "evidence": {"source": fixture.EVIDENCE_SOURCE,
                                 "observed": OBSERVED_RATE},
                })

        report = audit_drift(repo, mode=MODE_FULL, verdicts=payload)

        self.assertEqual(report.status, STATE_PARTIAL)
        gap = next(i for i in report.incomplete if i.scope == fixture.LIVING_DOC)
        self.assertIn("classification-not-assertion-capable", gap.reason)
        self.assertTrue(os.path.exists(
            os.path.join(repo, fixture.EXCLUDED_DOC)))


class TheHostileFixtureCases(DriftScenarioTestCase):
    """Fifth acceptance criterion, plus the filenames chosen to break tooling."""

    def tree(self, repo):
        listing = {}
        for base, dirs, names in os.walk(repo):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in names:
                path = os.path.join(base, name)
                listing[os.path.relpath(path, repo)] = (
                    os.lstat(path).st_mtime_ns, os.lstat(path).st_size
                )
        return listing

    def test_a_filename_that_reads_as_an_option_is_audited_like_any_other(self):
        repo = self.build_fixture()

        report = self.full_report(repo)

        self.assertIn(fixture.HOSTILE_LEADING_DASH_DOC, report.scope.documents)

    def test_shell_metacharacters_and_homoglyphs_are_audited_too(self):
        repo = self.build_fixture()

        report = self.full_report(repo)

        for path in (fixture.HOSTILE_SHELL_METACHAR_DOC,
                     fixture.HOSTILE_HOMOGLYPH_DOC):
            with self.subTest(path):
                self.assertIn(path, report.scope.documents)

    def test_a_symlink_is_never_declared_or_opened(self):
        repo = self.build_fixture()

        report = self.full_report(repo)

        for path in fixture.SYMLINK_PATHS:
            with self.subTest(path):
                self.assertNotIn(path, report.scope.documents)

    def test_the_full_corpus_audit_changes_nothing_in_the_repository(self):
        repo = self.build_fixture()
        before = self.tree(repo)

        self.full_report(repo, waivers=fixture.WAIVERS_PATH)

        self.assertEqual(self.tree(repo), before)

    def test_the_diff_scoped_audit_changes_nothing_either(self):
        repo = self.build_fixture()
        before = self.tree(repo)

        self.diff_report(repo, waivers=fixture.WAIVERS_PATH)

        self.assertEqual(self.tree(repo), before)

    def test_an_audit_of_hostile_and_malformed_input_changes_nothing(self):
        """Every refusal path, over the same fixture: an unknown mode, a
        baseline that is not a commit, verdicts that are not a payload, a
        verdict naming a document nobody declared, and a broken waivers file."""
        repo = self.build_fixture()
        before = self.tree(repo)

        audit_drift(repo, mode="deep")
        audit_drift(repo, mode=MODE_INCREMENTAL, since="f" * 40)
        audit_drift(repo, mode=MODE_FULL, verdicts="drop tables")
        audit_drift(repo, mode=MODE_FULL, verdicts={"documents": [
            {"path": fixture.SYMLINK_ABS_DOC, "status": "ok", "verdicts": []},
        ]})
        audit_drift(repo, mode=MODE_FULL, waivers=fixture.PLANNING_DOC)

        self.assertEqual(self.tree(repo), before)

    def test_the_working_tree_is_still_clean_after_an_audit(self):
        repo = self.build_fixture()

        self.full_report(repo, waivers=fixture.WAIVERS_PATH)

        status = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(status.stdout, "")

    def test_the_command_writes_nothing_either(self):
        repo = self.build_fixture()
        before = self.tree(repo)

        result = run_cli("drift-audit", "--repo", repo, "--waivers",
                         fixture.WAIVERS_PATH)

        self.assertEqual(result.returncode, 4)
        self.assertEqual(self.tree(repo), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
