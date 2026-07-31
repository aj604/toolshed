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
import hashlib
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

UNIT = "a" * 64          # a unit is the sha256 digest `segment` prints
UNIT2 = "b" * 64


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def engine_plan(chunks, index_digest="a" * 64,
                max_documents=8, max_units=400):
    content = {
        "schema_version": 1,
        "index_digest": index_digest,
        "max_documents": max_documents,
        "max_units": max_units,
        "chunks": chunks,
    }
    return {"status": "ok", **content, "digest": digest(content)}


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
    plan = engine_plan([{
        "id": "c-aaa", "documents": ["README.md"], "unit_count": 1,
    }])
    result = {
        "id": "c-aaa", "completion_state": "complete",
        "verdict_ids": [entry.get("id", f"B{position}")
                        for position, entry in enumerate(verdicts, 1)],
        "result_digest": digest({"chunk": "c-aaa", "verdicts": verdicts}),
        "reason": "",
    }
    obj = {
        "schema_version": 1,
        "verdicts": verdicts,
        "completion": {
            "plan": plan,
            "chunks": [result],
            "digest": digest({
                "plan_digest": plan["digest"],
                "chunks": [result], "verdicts": verdicts,
            }),
        },
    }
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
        payload = envelope([cut()])
        del payload["schema_version"]
        r = run(payload)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bare_array_refused_legibly(self):
        r = run([cut()])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("verdicts", r.stderr)
        self.assertIn("envelope", r.stderr)

    def test_completion_cannot_be_omitted_from_an_empty_verdict_envelope(self):
        r = run({"schema_version": 1, "verdicts": []})

        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("completion", r.stderr)

    def test_unsupported_schema_version_refused(self):
        r = run(envelope([cut()], schema_version=2))
        self.assertEqual(r.returncode, 1)
        self.assertIn("schema_version", r.stderr)

    def test_schema_version_that_is_not_an_integer_refused(self):
        # `True == 1` and `1.0 == 1` in Python, but not in a schema. A bare
        # `!=` accepted both, so an envelope the engine refuses validated
        # clean here — the two ends of the same contract disagreeing. Found by
        # review on the split stack.
        for version in (True, 1.0, "1"):
            with self.subTest(schema_version=version):
                r = run(envelope([cut()], schema_version=version))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
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
            # A destination other than cut()'s own README.md: a move to the
            # judged document is bloat-destination-is-source at the engine.
            cut(id="B4", verdict="MERGE-DOC", destination="docs/overview.md"),
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
        self.assert_fails([cut(units=UNIT)], "unit")   # a string, not a list

    def test_a_unit_must_be_a_sha256_digest(self):
        # The likeliest worker error, and purely shape-visible: the engine
        # refuses anything but 64 lowercase hex (finding-invalid-unit).
        for bad in ("README.md:12-15", "the intro paragraph", UNIT[:16],
                    UNIT.upper(), UNIT + "0"):
            r = run(envelope([cut(units=[bad])]))
            self.assertEqual(r.returncode, 1, f"{bad!r}: {r.stdout}{r.stderr}")
            self.assertIn("digest", r.stderr)

    def test_a_unit_carrying_trailing_or_leading_whitespace_is_refused(self):
        # Transcription corruption, and the exact thing the digest seam exists
        # to catch: `"<64 hex>\n"` is not the digest `segment` printed, and the
        # *unstripped* value is what flows on to bloat-audit — which refuses it
        # with `bloat-unknown-unit`. A `$`-anchored `.match()` against a
        # `.strip()`ped copy passed both a trailing LF and a leading space.
        for bad in (UNIT + "\n", " " + UNIT, UNIT + " ", UNIT + "\t"):
            r = run(envelope([cut(units=[bad])]))
            self.assertEqual(r.returncode, 1, f"{bad!r}: {r.stdout}{r.stderr}")
            self.assertIn("digest", r.stderr)

    def test_one_bad_unit_among_good_ones_is_named(self):
        r = run(envelope([cut(units=[UNIT, "README.md:12"])]))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("README.md:12", r.stderr)

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

    def test_empty_sample_is_valid(self):
        # The engine records this finding fine (`sample: []`, verified against
        # `bloat-audit`), and reading no members is a legitimate bulk judgment
        # made from the enumeration alone — the scope is what authorizes, and
        # the sample never was. Refusing it here failed the *whole* assembly,
        # since --allow-partial forgives a missing chunk and never an invalid
        # one, so one false red discarded an entire fan-out.
        r = run(envelope([scope_retire(sample=[])]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_sample_members_must_still_be_non_blank_strings(self):
        for bad in ([""], ["   "], ["docs/a.md", None], [42],
                    ["docs/a.md", ""]):
            r = run(envelope([scope_retire(sample=bad)]))
            self.assertEqual(r.returncode, 1, f"{bad!r}: {r.stdout}{r.stderr}")
            self.assertIn("sample", r.stderr)

    def test_sample_refused_on_a_single_document_verdict(self):
        self.assert_fails([cut(sample=["README.md"])], "sample")

    def test_empty_sample_still_refused_on_a_single_document_verdict(self):
        self.assert_fails([cut(sample=[])], "sample")


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


class DestinationSpelling(unittest.TestCase):
    """The destination checks a shape check can make on its own.

    Each was verified against `python3 -m doclifecycle bloat-audit` first: the
    engine refuses all of them today, so catching them here only moves the
    refusal a seam earlier. The one deliberate omission is recorded below.
    """

    def assert_fails(self, verdicts, fragment):
        r = run(envelope(verdicts))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_a_move_to_the_judged_document_itself_is_refused(self):
        # bloat-destination-is-source.
        for code in ("EXTRACT-AND-MOVE", "MERGE-DOC"):
            over = {"verdict": code, "destination": "README.md"}
            if code == "EXTRACT-AND-MOVE":
                over["proposal"] = "the line to land"
            r = run(envelope([cut(**over)]))
            self.assertEqual(r.returncode, 1, f"{code}: {r.stdout}{r.stderr}")
            self.assertIn("the document being judged", r.stderr)

    def test_residue_destination_equal_to_the_artifact_is_refused(self):
        # bloat-destination-is-source, in the distillation's own words.
        self.assert_fails(
            [distill(destination="docs/plans/old-design.md")],
            "the planning artifact being distilled")

    def test_destination_traversing_out_of_the_repository_is_refused(self):
        # bloat-destination-unauthorized for a residue path,
        # bloat-destination-not-a-document for a move: an index path comes from
        # a tree walk, so no document is ever spelled with a '..' component.
        self.assert_fails([cut(verdict="MERGE-DOC",
                               destination="docs/../../escape.md")], "'..'")
        self.assert_fails([distill(destination="docs/../../escape.md")], "'..'")

    def test_residue_destination_with_whitespace_is_refused(self):
        # A residue destination goes through the engine's `authorize_path`,
        # which refuses whitespace outright (bloat-destination-unauthorized).
        for bad in ("docs/my residue.md", "docs/residue .md"):
            r = run(envelope([distill(destination=bad)]))
            self.assertEqual(r.returncode, 1, f"{bad!r}: {r.stdout}{r.stderr}")
            self.assertIn("whitespace", r.stderr)

    def test_a_move_destination_may_carry_whitespace(self):
        # Deliberately NOT refused. A move destination is only ever checked
        # against the index, and a whitespace-bearing path *can* be an indexed
        # document — verified: with `docs/my guide.md` on disk and classified,
        # bloat-audit accepts MERGE-DOC into it and records the destination.
        # Refusing it here would be a fresh false red of exactly the kind the
        # empty-sample check was.
        r = run(envelope([cut(verdict="MERGE-DOC",
                              destination="docs/my guide.md")]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_legitimate_destination_still_validates(self):
        r = run(envelope([
            cut(id="B1", verdict="MERGE-DOC", destination="docs/readme.md"),
            cut(id="B2", verdict="EXTRACT-AND-MOVE",
                destination="docs/runbook.md", proposal="the line to land"),
            distill(id="B3", destination="docs/reference/cache.md"),
        ]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class SeamFixture(unittest.TestCase):
    """Shared tempdir with a two-chunk manifest."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chunks_dir = os.path.join(self.tmp.name, "chunks")
        os.makedirs(self.chunks_dir)
        self.manifest = {
            "schema": 1,
            "index_digest": "a" * 64,
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
        self.manifest["engine_plan"] = engine_plan([
            {"id": "c-aaa", "documents": ["README.md", "RUNBOOK.md"],
             "unit_count": 6},
            {"id": "c-bbb", "documents": ["docs/plans/old-design.md"],
             "unit_count": 3},
        ])
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

    def engine_manifest(self):
        """`python3 -m doclifecycle bloat-plan`'s shape: bare path lists."""
        path = os.path.join(self.tmp.name, "bloat-plan.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                **engine_plan([
                    {"id": "c-aaa",
                     "documents": ["README.md", "RUNBOOK.md"],
                     "unit_count": 6},
                ], index_digest="c" * 64),
            }, f)
        return path

    def test_engine_plan_manifest_slice_is_read(self):
        # bloat-plan writes `documents: [path]` where plan-chunks.py writes
        # `docs: [{path}]`; reading only one empties the slice and refuses
        # every verdict in the chunk.
        r = self.check(self.first_result(), "--manifest", self.engine_manifest())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_engine_plan_manifest_still_binds_the_slice(self):
        r = self.check(self.first_result([cut(path="OTHER.md")]),
                       "--manifest", self.engine_manifest())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("outside this chunk's slice", r.stderr)

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
        self.assertEqual(set(payload), {"schema_version", "verdicts", "completion"})
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual([v["id"] for v in payload["verdicts"]], ["B1", "B2"])
        self.assertEqual(
            payload["completion"]["plan"], self.manifest["engine_plan"],
        )
        final = run_argv(out)
        self.assertEqual(final.returncode, 0, final.stderr)

    def test_tampered_engine_plan_digest_is_refused(self):
        self.write_both()
        self.manifest["engine_plan"]["digest"] = "f" * 64
        with open(self.manifest_path, "w", encoding="utf-8") as fh:
            json.dump(self.manifest, fh)

        result, _out = self.assemble()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("digest does not match", result.stderr)

    def test_scheduler_membership_must_match_the_engine_plan(self):
        self.write_both()
        self.manifest["chunks"][0]["docs"][0]["path"] = "OTHER.md"
        with open(self.manifest_path, "w", encoding="utf-8") as fh:
            json.dump(self.manifest, fh)

        result, _out = self.assemble()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("exactly match engine_plan", result.stderr)

    def test_malformed_scheduler_manifest_fails_shut_without_a_traceback(self):
        # `chunk_doc_paths` filtered its `docs` dialect only for `isinstance
        # dict`, never for the `path` being a string, so a chunk carrying
        # `docs: [{}]` yielded `[None]` and the notice's `', '.join(...)`
        # raised an uncaught TypeError — a traceback out of the assembler
        # instead of a diagnosis, on the one path whose whole job is surviving
        # an incomplete fan-out. Found by review on the split stack.
        manifest = os.path.join(self.tmp.name, "malformed-manifest.json")
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump({"index_digest": "a" * 64,
                       "chunks": [{"id": "c-aaa", "docs": [{}]}]}, fh)
        out = os.path.join(self.tmp.name, "bloat-verdicts.json")

        r = run_argv("--assemble", self.chunks_dir, "--manifest", manifest,
                     "--out", out, "--allow-partial")

        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("engine_plan", r.stderr)

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
        self.assertEqual(set(self.read(out)),
                         {"schema_version", "verdicts", "completion"})

    def test_complete_assembly_writes_an_empty_unswept_list(self):
        self.write_both()
        unswept = os.path.join(self.tmp.name, "unswept.json")
        r, _ = self.assemble("--allow-partial", "--unswept-out", unswept)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(unswept, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_invalid_chunk_is_a_gap_with_allow_partial(self):
        self.write_chunk("c-aaa.json", self.first_result([cut(verdict="POLICY")]))
        self.write_chunk("c-bbb.json", self.second_result())
        refused, _ = self.assemble()
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        partial, out = self.assemble("--allow-partial")
        self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
        chunk = self.read(out)["completion"]["chunks"][0]
        self.assertEqual(chunk["completion_state"], "invalid")
        self.assertEqual(chunk["id"], "c-aaa")

    def test_unreadable_chunk_is_a_gap_with_allow_partial(self):
        path = os.path.join(self.chunks_dir, "c-aaa.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.write_chunk("c-bbb.json", self.second_result())

        result, out = self.assemble("--allow-partial")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        chunk = self.read(out)["completion"]["chunks"][0]
        self.assertEqual(chunk["completion_state"], "invalid")
        self.assertIn("unreadable", chunk["reason"])

    def test_empty_manifest_assembles_an_empty_envelope(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump({"schema": 1, "index_digest": "a" * 64,
                       "chunks": [], "pending": [],
                       "engine_plan": engine_plan([])}, f)
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
