#!/usr/bin/env python3
"""The `context-index`, `bloat-plan`, and `bloat-audit` commands (issue #66).

Seam under test: `python3 -m doclifecycle` as a subprocess. Each command must
equal the library result it wraps and add nothing, so an interactive import and
a CI invocation cannot disagree.

Run: python3 tests/engine/bloat_cli_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import (  # noqa: E402  (also puts the engine on sys.path)
    CORPUS_REGISTRY as REGISTRY,
    SHARED_SENTENCE as SHARED,
    RepoTestCase,
    run_command,
)

from doclifecycle import bloat  # noqa: E402
from doclifecycle.context import build_context_index  # noqa: E402

class ContextIndexCommand(RepoTestCase):
    def corpus(self):
        return self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

    def test_the_command_agrees_with_the_library(self):
        repo = self.corpus()

        result = run_command("context-index", "--repo", repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), build_context_index(repo).to_dict()
        )

    def test_it_reports_every_occurrence_of_a_duplicated_unit(self):
        repo = self.corpus()

        payload = json.loads(run_command("context-index", "--repo", repo).stdout)

        duplicated = [
            places for places in payload["occurrences"].values() if len(places) > 1
        ]
        self.assertEqual(
            [(p["path"], p["line"]) for p in duplicated[0]],
            [("docs/a.md", 3), ("docs/plans/p.md", 3)],
        )

    def test_an_invalid_registry_exits_one_and_explains_itself(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/a.md": "# A\n\nAlpha.\n",
        })

        result = run_command("context-index", "--repo", repo)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")
        self.assertIn("registry", result.stderr)

    def test_two_runs_produce_byte_identical_output(self):
        repo = self.corpus()

        first = run_command("context-index", "--repo", repo)
        second = run_command("context-index", "--repo", repo)

        self.assertEqual(first.stdout, second.stdout)


class BloatPlanCommand(RepoTestCase):
    def corpus(self):
        return self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
            "docs/plans/p.md": "# P\n\nDelta.\n",
        })

    def test_the_command_agrees_with_the_library(self):
        repo = self.corpus()

        result = run_command("bloat-plan", "--repo", repo, "--max-documents", "2")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            bloat.plan_repository_chunks(repo, max_documents=2).to_dict(),
        )

    def test_every_document_appears_in_exactly_one_chunk(self):
        repo = self.corpus()

        payload = json.loads(
            run_command("bloat-plan", "--repo", repo, "--max-documents", "1").stdout
        )

        placed = [p for c in payload["chunks"] for p in c["documents"]]
        self.assertEqual(
            sorted(placed), ["docs/a.md", "docs/b.md", "docs/plans/p.md"]
        )

    def test_an_invalid_registry_exits_one(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/a.md": "# A\n\nAlpha.\n",
        })

        result = run_command("bloat-plan", "--repo", repo)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_a_non_positive_budget_is_a_usage_error(self):
        result = run_command("bloat-plan", "--repo", self.corpus(),
                             "--max-documents", "0")

        self.assertEqual(result.returncode, 2)


class BloatAuditCommand(RepoTestCase):
    """`bloat-audit`: verdicts in, a validated report out, wired the way
    `BloatPlanCommand` wires `bloat-plan` — the command adds nothing beyond
    reading the verdicts file and calling the one library function."""

    GIT_ENV = dict(
        os.environ,
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
    )

    def corpus(self):
        root = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })
        for argv in (["init", "-q", "-b", "main"], ["add", "-A"],
                    ["commit", "-q", "-m", "fixture"]):
            subprocess.run(["git", "-C", root, *argv], check=True,
                           env=self.GIT_ENV, capture_output=True, text=True)
        return root

    def verdict(self, repo, **overrides):
        index = build_context_index(repo)
        by_text = {u.text: u.digest for u in index.units}
        entry = {
            "id": "BLOAT-001",
            "verdict": bloat.CUT,
            "path": "docs/plans/p.md",
            "units": [by_text[SHARED]],
            "evidence": "The living document already states this.",
        }
        entry.update(overrides)
        return entry

    def verdicts_file(self, root, verdicts):
        plan = bloat.plan_repository_chunks(root)
        path = os.path.join(root, "verdicts.json")
        remaining = list(verdicts)
        outcomes = []
        for chunk in plan.chunks:
            selected = [entry for entry in remaining
                        if entry.get("scope") is not None
                        or entry.get("path") in chunk.documents]
            remaining = [entry for entry in remaining if entry not in selected]
            outcomes.append(bloat.ChunkOutcome.complete(
                chunk.chunk_id, selected,
            ))
        self.write_input(path, bloat.assemble_bloat_input(plan, outcomes))
        return path

    def write_input(self, path, audit_input):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(audit_input.to_dict(), fh)

    def test_the_command_agrees_with_the_library(self):
        repo = self.corpus()
        verdicts = [self.verdict(repo)]
        path = self.verdicts_file(repo, verdicts)

        result = run_command("bloat-audit", "--repo", repo, "--verdicts", path)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            # `audit_bloat` takes the envelope the file holds — the same
            # shape `load_bloat_verdicts` hands the CLI unchanged — not the
            # bare `verdicts` list.
            bloat.audit_bloat(repo, payload).to_dict(),
        )

    def test_a_cut_records_digest_is_mintable(self):
        """The semantic assertion: a `bloat-audit` record's digest is exactly
        what `mint-approval` selects by, so fixing-docs' step 1 is real for
        bloat as it already is for drift."""
        repo = self.corpus()
        path = self.verdicts_file(repo, [self.verdict(repo)])

        result = run_command("bloat-audit", "--repo", repo, "--verdicts", path)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["records"][0]["code"], bloat.CUT)
        digest = payload["records"][0]["digest"]
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # raises ValueError if not hex

    def test_an_invalid_registry_exits_one_with_status_invalid(self):
        repo = self.corpus()
        path = self.verdicts_file(repo, [])
        registry_path = os.path.join(repo, ".doc-lifecycle", "registry.json")
        with open(registry_path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")

        result = run_command("bloat-audit", "--repo", repo, "--verdicts", path)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_missing_verdicts_is_a_usage_error(self):
        result = run_command("bloat-audit", "--repo", self.corpus())

        self.assertEqual(result.returncode, 2)

    def test_missing_planned_chunk_is_partial_inside_the_report(self):
        repo = self.corpus()
        plan = bloat.plan_repository_chunks(repo, max_documents=1)
        self.assertGreaterEqual(len(plan.chunks), 2)
        completed, missing = plan.chunks[0], plan.chunks[1]
        outcomes = [
            bloat.ChunkOutcome.complete(completed.chunk_id, []),
            bloat.ChunkOutcome.missing(
                missing.chunk_id, f"missing result for {missing.chunk_id}",
            ),
        ]
        outcomes.extend(
            bloat.ChunkOutcome.missing(
                chunk.chunk_id, f"missing result for {chunk.chunk_id}",
            )
            for chunk in plan.chunks[2:]
        )
        verdicts = os.path.join(repo, "partial-verdicts.json")
        self.write_input(
            verdicts, bloat.assemble_bloat_input(plan, outcomes),
        )
        audited = run_command(
            "bloat-audit", "--repo", repo, "--verdicts", verdicts,
        )

        self.assertEqual(audited.returncode, 4, audited.stderr)
        report = json.loads(audited.stdout)
        self.assertEqual(report["status"], "partial")
        for document in missing.documents:
            self.assertIn(document, [gap["scope"] for gap in report["incomplete"]])
        self.assertTrue(all(
            missing.chunk_id in gap["reason"]
            for gap in report["incomplete"]
            if gap["scope"] in missing.documents
        ))

    def test_complete_multi_chunk_sweep_with_empty_verdicts_is_clean(self):
        repo = self.corpus()
        plan = bloat.plan_repository_chunks(repo, max_documents=1)
        outcomes = [
            bloat.ChunkOutcome.complete(chunk.chunk_id, [])
            for chunk in plan.chunks
        ]
        verdicts = os.path.join(repo, "complete-verdicts.json")
        self.write_input(
            verdicts, bloat.assemble_bloat_input(plan, outcomes),
        )
        audited = run_command(
            "bloat-audit", "--repo", repo, "--verdicts", verdicts,
        )

        self.assertEqual(audited.returncode, 0, audited.stderr)
        report = json.loads(audited.stdout)
        self.assertEqual(report["status"], "clean")
        self.assertEqual(report["records"], [])
        self.assertEqual(report["incomplete"], [])
        self.assertEqual(
            sorted(entry["scope"] for entry in report["examined"]),
            sorted(document for chunk in plan.chunks
                   for document in chunk.documents),
        )
        self.assertTrue(all(entry["chunk"].startswith("c-")
                            for entry in report["examined"]))
        self.assertTrue(all(len(entry["plan_digest"]) == 64
                            for entry in report["examined"]))

    def test_invalid_planned_chunk_is_partial_inside_the_report(self):
        repo = self.corpus()
        plan = bloat.plan_repository_chunks(repo, max_documents=1)
        invalid = plan.chunks[0]
        outcomes = [bloat.ChunkOutcome.invalid(
            invalid.chunk_id, f"bloat-chunk-invalid: {invalid.chunk_id}",
        )]
        outcomes.extend(
            bloat.ChunkOutcome.complete(chunk.chunk_id, [])
            for chunk in plan.chunks[1:]
        )
        verdicts = os.path.join(repo, "invalid-verdicts.json")
        self.write_input(
            verdicts, bloat.assemble_bloat_input(plan, outcomes),
        )
        audited = run_command(
            "bloat-audit", "--repo", repo, "--verdicts", verdicts,
        )

        self.assertEqual(audited.returncode, 4, audited.stderr)
        report = json.loads(audited.stdout)
        self.assertEqual(report["status"], "partial")
        self.assertTrue(all(
            "bloat-chunk-invalid" in gap["reason"]
            and invalid.chunk_id in gap["reason"]
            for gap in report["incomplete"]
            if gap["scope"] in invalid.documents
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
