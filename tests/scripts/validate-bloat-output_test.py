#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's validate-bloat-output.py.

The script checks the *engine's* bloat verdict shape (`doclifecycle.bloat`) —
six verdicts, `path`/`units` unit digests, enumerable `scope` for bulk
retirement, and the fields a model may never supply — by shape only;
`bloat-audit` stays the authority on everything shape cannot see. Tests run it
as a subprocess: real stdin/file input, real exit codes, real stderr. Covers
the three duties: the final verdicts envelope, the chunk seam
(--chunk/--manifest), and assembly (--assemble/--out/--allow-partial).
Run: python3 tests/scripts/validate-bloat-output_test.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "detecting-doc-bloat",
    "scripts", "validate-bloat-output.py",
)

UNIT = "u-" + "a" * 8
UNIT2 = "u-" + "b" * 8


def cut(**over):
    """A well-formed CUT verdict in the engine shape; override per test."""
    base = {
        "id": "B1",
        "verdict": "CUT",
        "path": "README.md",
        "units": [UNIT],
        "evidence": "restates src/notify.py:3 verbatim",
    }
    base.update(over)
    return base


def distill(**over):
    base = {
        "id": "B9",
        "verdict": "DISTILL",
        "path": "docs/plans/old-design.md",
        "units": [UNIT2],
        "evidence": "implementation landed: src/notify.py:12 matches the design",
        "status": "ready",
    }
    base.update(over)
    return base


def scope_retire(**over):
    base = {
        "id": "B7",
        "verdict": "RETIRE-DOC",
        "scope": {"set": "ephemeral"},
        "evidence": "every member is a dated process artifact for merged work",
        "sample": ["docs/superpowers/plans/a.md"],
    }
    base.update(over)
    return base


def envelope(verdicts, **over):
    obj = {"schema_version": 1, "verdicts": verdicts}
    obj.update(over)
    return obj


def run(payload, *argv, as_file=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if as_file or argv:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return subprocess.run(
                [sys.executable, SCRIPT, path, *argv],
                capture_output=True, text=True)
        finally:
            os.unlink(path)
    return subprocess.run(
        [sys.executable, SCRIPT], input=text, capture_output=True, text=True)


def run_argv(*argv):
    return subprocess.run(
        [sys.executable, SCRIPT, *argv], capture_output=True, text=True)


class Envelope(unittest.TestCase):
    """The final artifact is bloat-audit's envelope, not a bare list."""

    def test_envelope_valid(self):
        r = run(envelope([cut()]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 1 verdict(s) valid", r.stdout)

    def test_envelope_without_schema_version_valid(self):
        r = run({"verdicts": [cut()]})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bare_array_refused_legibly(self):
        r = run([cut()])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("verdicts", r.stderr)
        self.assertIn("envelope", r.stderr)

    def test_unsupported_schema_version_refused(self):
        r = run(envelope([cut()], schema_version=2))
        self.assertEqual(r.returncode, 1)
        self.assertIn("schema_version", r.stderr)

    def test_extra_envelope_key_refused(self):
        r = run(envelope([cut()], summary={"cut": 1}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("summary", r.stderr)

    def test_legacy_record_fields_refused_legibly(self):
        legacy = cut()
        legacy["doc"] = "README.md"
        legacy["location"] = "README.md:12"
        r = run(envelope([legacy]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("doc", r.stderr)
        self.assertIn("path", r.stderr)

    def test_summary_counts_printed(self):
        r = run(envelope([cut(), distill()]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"cut": 1', r.stdout)
        self.assertIn('"distill": 1', r.stdout)

    def test_file_input(self):
        r = run(envelope([cut()]), as_file=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bad_json_exits_2(self):
        r = run("not json {")
        self.assertEqual(r.returncode, 2)


class VerdictShape(unittest.TestCase):
    def assert_fails(self, verdicts, fragment):
        r = run(envelope(verdicts))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_six_verdicts_accepted(self):
        verdicts = [
            cut(id="B1"),
            cut(id="B2", verdict="CONDENSE", proposal="one dense line"),
            cut(id="B3", verdict="EXTRACT-AND-MOVE",
                destination="docs/runbook.md", proposal="the line to land"),
            cut(id="B4", verdict="MERGE-DOC", destination="README.md"),
            cut(id="B5", verdict="RETIRE-DOC"),
            distill(id="B6"),
        ]
        r = run(envelope(verdicts))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_verdict(self):
        self.assert_fails([cut(verdict="POLICY")], "POLICY")

    def test_duplicate_ids(self):
        self.assert_fails([cut(), cut(units=[UNIT2])],
                          "used by more than one verdict")

    def test_missing_id(self):
        bad = cut()
        del bad["id"]
        self.assert_fails([bad], "id")

    def test_empty_evidence(self):
        self.assert_fails([cut(evidence="  ")], "evidence")

    def test_missing_evidence(self):
        bad = cut()
        del bad["evidence"]
        self.assert_fails([bad], "evidence")

    def test_path_required(self):
        bad = cut()
        del bad["path"]
        self.assert_fails([bad], "path")

    def test_units_required_and_nonempty(self):
        self.assert_fails([cut(units=[])], "unit")
        self.assert_fails([cut(units="u-aaaaaaaa")], "unit")

    def test_condense_requires_proposal(self):
        self.assert_fails([cut(verdict="CONDENSE")], "must carry the replacement")

    def test_cut_forbids_proposal(self):
        self.assert_fails([cut(proposal="new text")], "proposal")

    def test_merge_doc_forbids_proposal(self):
        self.assert_fails(
            [cut(verdict="MERGE-DOC", destination="README2.md",
                 proposal="text")], "proposal")

    def test_destination_forbidden_where_nothing_moves(self):
        self.assert_fails([cut(destination="docs/runbook.md")], "destination")

    def test_destination_optional_for_move_verdicts(self):
        # The index derives a destination for duplicated content, so a worker
        # legitimately omits one; bloat-audit is the authority on which.
        r = run(envelope([cut(verdict="MERGE-DOC")]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_destination_string_refused(self):
        self.assert_fails([cut(verdict="MERGE-DOC", destination="  ")],
                          "destination")

    def test_unknown_field_refused(self):
        self.assert_fails([cut(extra="x")], "extra")


class ForbiddenFields(unittest.TestCase):
    """`files` and friends are what an enumeration replaces."""

    def assert_forbidden(self, field, value):
        r = run(envelope([cut(**{field: value})]))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(field, r.stderr)
        self.assertIn("enumerat", r.stderr)

    def test_files_refused(self):
        self.assert_forbidden("files", ["docs/superpowers/plans/a.md"])

    def test_members_refused(self):
        self.assert_forbidden("members", ["a.md"])

    def test_occurrences_refused(self):
        self.assert_forbidden("occurrences", [{"path": "a.md"}])

    def test_contention_refused(self):
        self.assert_forbidden("contention", {"destination": "a.md"})


class ScopeRetirement(unittest.TestCase):
    """Bulk retirement is an enumerable scope — POLICY's replacement."""

    def assert_fails(self, verdicts, fragment):
        r = run(envelope(verdicts))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_scope_retire_doc_valid(self):
        r = run(envelope([scope_retire()]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_selector_accepted(self):
        for rule in ({"set": "ephemeral"}, {"glob": "docs/superpowers/**"},
                     {"kind": "planning"}):
            r = run(envelope([scope_retire(scope=rule)]))
            self.assertEqual(r.returncode, 0, f"{rule}: {r.stderr}")

    def test_unknown_selector_refused(self):
        self.assert_fails([scope_retire(scope={"dir": "docs/superpowers"})],
                          "scope")

    def test_two_selectors_refused(self):
        self.assert_fails(
            [scope_retire(scope={"set": "ephemeral", "kind": "planning"})],
            "scope")

    def test_scope_only_on_retire_doc(self):
        self.assert_fails([scope_retire(verdict="CUT")], "bulk")

    def test_scope_forbids_path_and_units(self):
        self.assert_fails([scope_retire(path="docs/superpowers")], "path")
        self.assert_fails([scope_retire(units=[UNIT])], "units")

    def test_scope_forbids_destination_proposal_status(self):
        self.assert_fails([scope_retire(destination="README.md")], "destination")
        self.assert_fails([scope_retire(proposal="text")], "proposal")
        self.assert_fails([scope_retire(status="ready")], "status")

    def test_scope_verdict_still_refuses_files(self):
        r = run(envelope([scope_retire(files=["docs/superpowers/plans/a.md"])]))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("files", r.stderr)
        self.assertIn("enumerat", r.stderr)

    def test_sample_must_be_a_path_list(self):
        self.assert_fails([scope_retire(sample="docs/superpowers/plans/a.md")],
                          "sample")

    def test_sample_refused_on_a_single_document_verdict(self):
        self.assert_fails([cut(sample=["README.md"])], "sample")


class DistillStatus(unittest.TestCase):
    def assert_fails(self, verdicts, fragment):
        r = run(envelope(verdicts))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_both_statuses_valid(self):
        for status in ("ready", "pending-implementation"):
            r = run(envelope([distill(status=status)]))
            self.assertEqual(r.returncode, 0, f"{status}: {r.stderr}")

    def test_distill_requires_status(self):
        bad = distill()
        del bad["status"]
        self.assert_fails([bad], "status")

    def test_unknown_status_refused(self):
        self.assert_fails([distill(status="done")], "status")

    def test_status_forbidden_off_distill(self):
        self.assert_fails([cut(status="ready")], "status")


class SeamFixture(unittest.TestCase):
    """Shared tempdir with a two-chunk manifest."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chunks_dir = os.path.join(self.tmp.name, "chunks")
        os.makedirs(self.chunks_dir)
        self.manifest = {
            "schema": 1,
            "chunks": [
                {"id": "c-aaa", "turns": 20,
                 "docs": [{"path": "README.md", "lines": 20, "hint": "living"},
                          {"path": "RUNBOOK.md", "lines": 5, "hint": "living"}]},
                {"id": "c-bbb", "turns": 20,
                 "docs": [{"path": "docs/plans/old-design.md", "lines": 40,
                           "hint": "planning"}]},
            ],
            "pending": ["c-aaa", "c-bbb"],
        }
        self.manifest_path = os.path.join(self.tmp.name, "manifest.json")
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f)

    def write_chunk(self, name, obj):
        path = os.path.join(self.chunks_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        return path

    def first_result(self, verdicts=None):
        return {"chunk": "c-aaa",
                "verdicts": [cut()] if verdicts is None else verdicts}

    def second_result(self):
        return {"chunk": "c-bbb", "verdicts": [distill()]}


class ChunkSeam(SeamFixture):
    def check(self, obj, *argv):
        path = self.write_chunk("candidate.json", obj)
        return run_argv("--chunk", path, *argv)

    def check_m(self, obj):
        return self.check(obj, "--manifest", self.manifest_path)

    def test_valid_chunk_result(self):
        r = self.check_m(self.first_result())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_verdicts_chunk_is_valid(self):
        r = self.check_m(self.first_result([]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_chunk_shape_must_be_exact(self):
        r = self.check_m({"chunk": "c-aaa", "verdicts": [], "extra": 1})
        self.assertEqual(r.returncode, 1)
        self.assertIn("chunk result must be exactly", r.stderr)

    def test_legacy_records_key_refused(self):
        r = self.check_m({"chunk": "c-aaa", "records": []})
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdicts", r.stderr)

    def test_path_outside_chunk_doclist_refused(self):
        r = self.check_m(self.first_result([cut(path="OTHER.md")]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("outside this chunk's slice", r.stderr)

    def test_scope_verdict_is_not_slice_bound(self):
        # A bulk scope is a corpus-wide judgment; the engine binds only a
        # single-document verdict's path to the slice.
        r = self.check_m(self.first_result([scope_retire()]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_chunk_id_fails(self):
        r = self.check_m({"chunk": "c-zzz", "verdicts": []})
        self.assertEqual(r.returncode, 1)
        self.assertIn("not in the manifest", r.stderr)

    def test_without_manifest_verdict_rules_still_apply(self):
        good = self.check(self.first_result())
        self.assertEqual(good.returncode, 0, good.stderr)
        bad = self.check(self.first_result([cut(verdict="POLICY")]))
        self.assertEqual(bad.returncode, 1)


class Assembly(SeamFixture):
    def assemble(self, *extra):
        out = os.path.join(self.tmp.name, "bloat-verdicts.json")
        r = run_argv("--assemble", self.chunks_dir,
                     "--manifest", self.manifest_path, "--out", out, *extra)
        return r, out

    def write_both(self):
        self.write_chunk("c-aaa.json", self.first_result())
        self.write_chunk("c-bbb.json", self.second_result())

    def read(self, out):
        with open(out, encoding="utf-8") as f:
            return json.load(f)

    def test_assembles_into_the_envelope_and_renumbers_ids(self):
        self.write_both()
        r, out = self.assemble()
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = self.read(out)
        self.assertEqual(set(payload), {"schema_version", "verdicts"})
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual([v["id"] for v in payload["verdicts"]], ["B1", "B2"])
        final = run_argv(out)
        self.assertEqual(final.returncode, 0, final.stderr)

    def test_missing_chunk_refused_by_name(self):
        self.write_chunk("c-aaa.json", self.first_result())
        r, _ = self.assemble()
        self.assertEqual(r.returncode, 1)
        self.assertIn("c-bbb", r.stderr)
        self.assertIn("partial assembly refused", r.stderr)

    def test_allow_partial_skips_missing_loudly(self):
        self.write_chunk("c-aaa.json", self.first_result())
        r, out = self.assemble("--allow-partial")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("c-bbb", r.stderr)
        self.assertIn("docs/plans/old-design.md", r.stderr)
        self.assertEqual(len(self.read(out)["verdicts"]), 1)

    def test_allow_partial_records_unswept_chunks_with_docs(self):
        self.write_chunk("c-aaa.json", self.first_result())
        unswept = os.path.join(self.tmp.name, "unswept.json")
        r, out = self.assemble("--allow-partial", "--unswept-out", unswept)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(unswept, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [
                {"chunk": "c-bbb", "docs": ["docs/plans/old-design.md"]}])
        # The envelope stays exactly what bloat-audit accepts.
        self.assertEqual(set(self.read(out)), {"schema_version", "verdicts"})

    def test_complete_assembly_writes_an_empty_unswept_list(self):
        self.write_both()
        unswept = os.path.join(self.tmp.name, "unswept.json")
        r, _ = self.assemble("--allow-partial", "--unswept-out", unswept)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(unswept, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_invalid_chunk_fails_even_with_allow_partial(self):
        self.write_chunk("c-aaa.json", self.first_result([cut(verdict="POLICY")]))
        self.write_chunk("c-bbb.json", self.second_result())
        for extra in ((), ("--allow-partial",)):
            r, _ = self.assemble(*extra)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("c-aaa", r.stderr)

    def test_empty_manifest_assembles_an_empty_envelope(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump({"schema": 1, "chunks": [], "pending": []}, f)
        r, out = self.assemble()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(out)["verdicts"], [])

    def test_usage_errors_exit_2(self):
        cases = (
            ("--assemble", self.chunks_dir),                      # no manifest/out
            ("--assemble", self.chunks_dir, "--manifest", self.manifest_path),
            ("--chunk", "x.json", "--assemble", self.chunks_dir,
             "--manifest", self.manifest_path, "--out", "o.json"),
            ("--allow-partial",),
            ("--unswept-out", "u.json"),
        )
        for argv in cases:
            r = run_argv(*argv)
            self.assertEqual(r.returncode, 2, f"{argv}: {r.stdout}{r.stderr}")


if __name__ == "__main__":
    unittest.main()
