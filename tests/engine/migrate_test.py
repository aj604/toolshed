"""The migration door: inferring a draft registry from a legacy install.

Every test builds a real legacy consumer on disk — the `.github/doc-sync/`
config and state a scheduled install carries, plus the documents it managed —
and asks the door what the new contract would look like. Nothing here writes to
the consumer; the suite asserts that, byte for byte.

`CoverageNarrowingTest` builds that consumer as a real git repository, because
what a repository *tracks* is the question the door asks there, and a fixture
that mocked it would prove nothing about the answer.
"""

import json
import os
import unittest

from report_test import GitRepoTestCase
from support import RepoTestCase

from doclifecycle import PLUGIN_VERSION
from doclifecycle.migrate import (
    MIGRATION_CONTRACT,
    draft_registry,
    dry_run_migration,
)
from doclifecycle.results import Invalid

MARKER = "e63285c4a4c2b35183aab492f459bbeb63eed22e\n"

ARCHITECTURE = """# Architecture

The billing service calculates fees at a flat 2% rate. Invoices settle nightly.
"""

ONBOARDING = """# Onboarding

> As of 2026-01-04 (src/billing.py:12)

New engineers start with the billing walkthrough.
"""

PLAN = """# Migration plan

Move the ledger to the new schema before the quarter closes.
"""

VENDOR = """# Upstream notes

Vendored from the upstream project and never edited here.
"""

README = """# Ledger

Run `make dev` to start the service.
"""

SCOPE_RECORD = """# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- guide: billing walkthrough — promote when: a second engineer asks.

## Done
- 2026-01-02 `docs/guides/` ← onboarding gap.
"""

AUDIT_SCOPE = '{"exclude": ["docs/vendor/**"], "include": []}\n'

WAIVERS = """{
  "waivers": [
    {"file": "docs/architecture.md",
     "claim": "calculates fees at a flat 2% rate",
     "reason": "the rate is set per-tenant in config",
     "date": "2026-01-03"}
  ]
}
"""


def legacy_consumer(extra=None):
    """The files a pre-registry doc-sync install carries, plus its documents."""
    files = {
        ".github/doc-sync-marker": MARKER,
        ".github/doc-sync/audit-scope.json": AUDIT_SCOPE,
        ".github/doc-sync/drift-waivers.json": WAIVERS,
        ".github/doc-sync/installed-version": "0.12.0\n",
        "README.md": README,
        "docs/doc-scope.md": SCOPE_RECORD,
        "docs/architecture.md": ARCHITECTURE,
        "docs/guides/onboarding.md": ONBOARDING,
        "docs/plans/2026-01-01-ledger.md": PLAN,
        "docs/vendor/upstream.md": VENDOR,
    }
    files.update(extra or {})
    return files


def tree_digest(root):
    """Every file under `root`, with its bytes — the preservation oracle."""
    seen = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                seen[os.path.relpath(path, root)] = fh.read()
    return seen


class DraftRegistryTest(RepoTestCase):
    def draft(self, files=None):
        root = self.repo(files or legacy_consumer())
        result = draft_registry(root)
        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        return root, result

    def test_drafts_one_glob_rule_per_directory_not_one_per_file(self):
        _, draft = self.draft()
        self.assertEqual(
            [(r["glob"], r["kind"], r.get("set"))
             for r in draft.to_dict()["registry"]["rules"]],
            [
                ("README.md", "living", None),
                ("docs/*.md", "living", None),
                ("docs/guides/*.md", "narrative", None),
                ("docs/plans/*.md", "planning", "plans"),
            ],
        )

    def test_declares_the_roots_the_legacy_install_evidenced(self):
        _, draft = self.draft()
        self.assertEqual(draft.to_dict()["registry"]["roots"], ["README.md", "docs"])

    def test_carries_the_audit_scope_exclusions_into_the_registry(self):
        _, draft = self.draft()
        self.assertEqual(
            draft.to_dict()["registry"]["exclude"], ["docs/vendor/**"]
        )

    def test_declares_the_set_a_planning_directory_forms(self):
        _, draft = self.draft()
        self.assertEqual(draft.to_dict()["registry"]["sets"], ["plans"])

    def test_the_drafted_registry_is_one_the_engine_accepts(self):
        from doclifecycle import registry as registry_mod

        _, draft = self.draft()
        parsed, problems = registry_mod.parse(draft.registry_text)
        self.assertEqual(problems, [])
        self.assertEqual(parsed.digest, draft.registry_digest)

    def test_names_the_basis_and_documents_behind_every_rule(self):
        _, draft = self.draft()
        by_glob = {r["glob"]: r for r in draft.to_dict()["rules"]}
        self.assertEqual(by_glob["docs/guides/*.md"]["basis"], "narrative-anchor")
        self.assertEqual(
            by_glob["docs/guides/*.md"]["documents"], ["docs/guides/onboarding.md"]
        )
        self.assertEqual(by_glob["docs/plans/*.md"]["basis"], "planning-location")
        self.assertEqual(by_glob["docs/*.md"]["basis"], "living-default")
        self.assertFalse(by_glob["docs/*.md"]["override"])

    def test_records_which_legacy_sources_it_read(self):
        _, draft = self.draft()
        sources = {s["path"]: s for s in draft.to_dict()["sources"]}
        self.assertTrue(sources[".github/doc-sync/audit-scope.json"]["present"])
        self.assertTrue(sources["docs/doc-scope.md"]["present"])
        self.assertTrue(sources[".github/doc-sync/drift-waivers.json"]["present"])

    def test_overrides_the_directory_rule_for_the_odd_document_out(self):
        _, draft = self.draft(legacy_consumer({
            "docs/history.md": "# History\n\n> As of 2026-01-05 (src/billing.py)\n",
        }))
        self.assertEqual(
            [(r["glob"], r["kind"]) for r in draft.to_dict()["registry"]["rules"]],
            [
                ("README.md", "living"),
                ("docs/*.md", "living"),
                ("docs/history.md", "narrative"),
                ("docs/guides/*.md", "narrative"),
                ("docs/plans/*.md", "planning"),
            ],
        )

    def test_a_dot_directory_is_not_mangled_into_a_different_root(self):
        _, draft = self.draft(legacy_consumer({
            ".docs/guide.md": "# Guide\n\nRun the migration first.\n",
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": ".docs/guide.md", "claim": "Run the migration first"},
            ]}),
        }))
        self.assertEqual(draft.to_dict()["registry"]["roots"],
                         [".docs", "README.md", "docs"])

    def test_an_unsafe_waiver_path_is_not_read_as_root_evidence(self):
        root = self.repo({
            "elsewhere/notes.md": "# Notes\n\nOutside any root.\n",
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": "../elsewhere/notes.md", "claim": "Outside any root"},
            ]}),
        })
        result = draft_registry(root)
        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["migration-no-roots"])

    def test_refuses_a_draft_whose_rules_do_not_classify_what_it_claims(self):
        # `?` is a wildcard to the registry's glob compiler, so a literal
        # override rule for this file would also claim `docs/faqs.md` — and
        # overrides sort last, so it would silently win.
        _, _ = self.draft()  # the uniform corpus still drafts fine
        root = self.repo(legacy_consumer({
            "docs/faq?.md": "# FAQ\n\n> As of 2026-01-07 (src/billing.py)\n",
            "docs/faqs.md": "# FAQs\n\nBilling questions land in the ledger.\n",
        }))
        result = draft_registry(root)
        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems],
                         ["migration-draft-inconsistent"])
        self.assertIn("docs/faqs.md", result.problems[0].message)

    def test_notes_a_document_it_cannot_read_rather_than_guessing_its_kind(self):
        root = self.repo(legacy_consumer())
        with open(os.path.join(root, "docs/binary.md"), "wb") as fh:
            fh.write(b"# Broken\n\n\xff\xfe not utf-8\n")
        draft = draft_registry(root)
        self.assertNotIsInstance(draft, Invalid, getattr(draft, "problems", None))
        notes = {n["location"]: n for n in draft.to_dict()["notes"]}
        self.assertEqual(notes["docs/binary.md"]["code"], "migration-unreadable-document")

    def test_an_override_sorts_after_its_directory_rule_whatever_it_is_called(self):
        # Precedence is rule order, and a filename sorting before `*` would put
        # the override first and let the directory rule overwrite it.
        _, draft = self.draft(legacy_consumer({
            "docs/(draft)-ledger.md": "# Ledger\n\n> As of 2026-01-06 (src/x.py)\n",
        }))
        globs = [r["glob"] for r in draft.to_dict()["registry"]["rules"]]
        self.assertLess(globs.index("docs/*.md"), globs.index("docs/(draft)-ledger.md"))

    def test_refuses_a_declared_root_that_is_not_inside_the_repository(self):
        root = self.repo(legacy_consumer())
        result = draft_registry(root, roots=["../elsewhere"])
        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["migration-unsafe-root"])

    def test_refuses_a_declared_root_that_does_not_exist(self):
        root = self.repo(legacy_consumer())
        result = draft_registry(root, roots=["handbook"])
        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["migration-missing-root"])

    def test_refuses_when_no_documentation_root_can_be_inferred(self):
        root = self.repo({"src/billing.py": "RATE = 0.02\n"})
        result = draft_registry(root)
        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["migration-no-roots"]
        )

    def test_writes_nothing_to_the_consumer(self):
        root = self.repo(legacy_consumer())
        before = tree_digest(root)
        draft_registry(root)
        self.assertEqual(tree_digest(root), before)


class CoverageNarrowingTest(GitRepoTestCase):
    """What the drafted roots leave behind that the legacy drift lane reached.

    Roots come from evidence the consumer wrote down, and every one of those
    sources describes the bloat corpus or narrower. The legacy drift lane had no
    root concept at all — it was diff-scoped over the whole repository — so any
    drafted registry narrows it. The draft must say so; it must not respond by
    inferring the missing tree, which is a decision only the human can make.
    """

    def tracked(self, files=None):
        """A legacy consumer whose files the repository actually tracks."""
        return self.git_repo(files or legacy_consumer())

    def notes(self, root, **kwargs):
        draft = draft_registry(root, **kwargs)
        self.assertNotIsInstance(draft, Invalid, getattr(draft, "problems", None))
        return {n["code"]: n for n in draft.to_dict()["notes"]}

    def test_counts_and_names_the_documents_outside_the_drafted_roots(self):
        root = self.tracked(legacy_consumer({
            "plugins/one/SKILL.md": "# One\n\nDoes a thing.\n",
            "plugins/two/SKILL.md": "# Two\n\nDoes another thing.\n",
        }))

        note = self.notes(root)["migration-coverage-narrowed"]

        self.assertIn("2", note["message"])
        self.assertIn("plugins/one/SKILL.md", note["message"])
        self.assertIn("plugins/two/SKILL.md", note["message"])

    def test_says_the_legacy_drift_lane_reached_them_so_this_is_a_narrowing(self):
        root = self.tracked(legacy_consumer({
            "plugins/one/SKILL.md": "# One\n\nDoes a thing.\n",
        }))

        message = self.notes(root)["migration-coverage-narrowed"]["message"]

        self.assertIn("drift", message)
        self.assertIn("narrow", message)

    def test_the_omission_is_reported_rather_than_inferred_into_a_root(self):
        """The whole constraint: roots come from written-down evidence, and
        `--root` is the override. A sweep that adopted the tree would decide for
        the human the thing this note exists to put in front of them."""
        root = self.tracked(legacy_consumer({
            "plugins/one/SKILL.md": "# One\n\nDoes a thing.\n",
        }))

        draft = draft_registry(root)

        self.assertEqual(draft.to_dict()["registry"]["roots"],
                         ["README.md", "docs"])

    def test_says_nothing_when_the_drafted_roots_reach_every_document(self):
        """`docs/vendor/upstream.md` is tracked and the draft drops it, but the
        exclusion doing that is the consumer's own and is printed in the draft's
        `exclude`. This note is for the narrowing nothing else in the draft
        shows — a document under no root at all."""
        root = self.tracked()

        self.assertTrue(
            os.path.isfile(os.path.join(root, "docs/vendor/upstream.md"))
        )
        self.assertNotIn("migration-coverage-narrowed", self.notes(root))

    def test_reads_as_a_sentence_when_exactly_one_document_is_left_behind(self):
        """This note reaches a reviewer verbatim, in a PR body."""
        root = self.tracked(legacy_consumer({
            "plugins/one/SKILL.md": "# One\n\nDoes a thing.\n",
        }))

        message = self.notes(root)["migration-coverage-narrowed"]["message"]

        self.assertIn("1 tracked .md file is under no drafted root", message)
        self.assertNotIn("files are", message)
        self.assertNotIn("they are", message)

    def test_a_document_excluded_from_outside_every_root_is_still_reported(self):
        """An exclusion is not root evidence, so a subtree named only in
        `exclude` is under no root — and the legacy drift lane still reached
        it, since the audit scope only ever filtered that lane's writes."""
        root = self.tracked(legacy_consumer({
            ".github/doc-sync/audit-scope.json":
                '{"exclude": ["vendor/**"], "include": []}\n',
            "vendor/upstream/NOTES.md": "# Upstream\n\nVendored.\n",
        }))

        message = self.notes(root)["migration-coverage-narrowed"]["message"]

        self.assertIn("vendor/upstream/NOTES.md", message)

    def test_caps_the_sample_of_paths_however_many_are_left_behind(self):
        root = self.tracked(legacy_consumer({
            f"handbook/page-{i:03d}.md": f"# Page {i}\n\nSomething.\n"
            for i in range(60)
        }))

        message = self.notes(root)["migration-coverage-narrowed"]["message"]

        self.assertIn("60", message)
        self.assertEqual(message.count("handbook/page-"), 10)

    def test_counts_only_files_the_drafted_registry_calls_documents(self):
        root = self.tracked(legacy_consumer({
            "plugins/one/SKILL.md": "# One\n\nDoes a thing.\n",
            "plugins/one/run.py": "print('hi')\n",
            "plugins/one/logo.svg": "<svg/>\n",
        }))

        message = self.notes(root)["migration-coverage-narrowed"]["message"]

        self.assertNotIn("run.py", message)
        self.assertNotIn("logo.svg", message)

    def test_an_untracked_document_is_not_counted_against_the_draft(self):
        """Generated and ignored markdown is not something the repository
        claims, and the legacy drift lane never saw it either."""
        root = self.tracked()
        with open(os.path.join(root, "BUILD-OUTPUT.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("# Generated\n\nWritten by the build.\n")

        self.assertNotIn("migration-coverage-narrowed", self.notes(root))

    def test_says_coverage_is_unchecked_when_the_tree_is_not_a_repository(self):
        """Silence would read as "nothing was left behind" — the one reading
        this note exists to prevent."""
        root = self.repo(legacy_consumer())

        notes = self.notes(root)

        self.assertNotIn("migration-coverage-narrowed", notes)
        self.assertIn("migration-coverage-unchecked", notes)


class DryRunTest(RepoTestCase):
    def migrated(self, files=None):
        """A legacy consumer that has landed the draft registry, and nothing else."""
        root = self.repo(files or legacy_consumer())
        draft = draft_registry(root)
        self.assertNotIsInstance(draft, Invalid, getattr(draft, "problems", None))
        path = os.path.join(root, draft.registry_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(draft.registry_text)
        return root

    def run_dry(self, root):
        result = dry_run_migration(root)
        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        return result.to_dict()

    def test_enumerates_the_obligation_each_document_kind_takes_on(self):
        payload = self.run_dry(self.migrated())
        obligations = {o["kind"]: o for o in payload["obligations"]}
        self.assertEqual(obligations["living"]["obligation"], "assertions")
        self.assertEqual(
            obligations["living"]["documents"],
            ["README.md", "docs/architecture.md", "docs/doc-scope.md"],
        )
        self.assertEqual(obligations["narrative"]["obligation"], "anchor")
        self.assertEqual(
            obligations["narrative"]["documents"], ["docs/guides/onboarding.md"]
        )
        self.assertEqual(obligations["planning"]["obligation"], "lifecycle")
        self.assertEqual(obligations["planning"]["count"], 1)

    def test_re_keys_a_waiver_onto_the_assertion_unit_it_now_names(self):
        payload = self.run_dry(self.migrated())
        self.assertEqual(payload["waivers"]["needs_rewaiving"], [])
        rekeyed = payload["waivers"]["rekeyed"]
        self.assertEqual(len(rekeyed), 1)
        self.assertEqual(rekeyed[0]["file"], "docs/architecture.md")
        self.assertEqual(rekeyed[0]["matched"], 1)
        self.assertEqual(len(rekeyed[0]["units"][0]["digest"]), 64)
        self.assertIn("flat 2% rate", rekeyed[0]["units"][0]["text"])

    def test_a_waiver_on_a_document_outside_the_corpus_needs_re_waiving(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": "docs/vendor/upstream.md",
                 "claim": "Vendored from the upstream project"},
            ]}),
        }))
        stuck = self.run_dry(root)["waivers"]["needs_rewaiving"]
        self.assertEqual([w["code"] for w in stuck],
                         ["waiver-document-not-inventoried"])

    def test_a_waiver_whose_claim_no_longer_appears_needs_re_waiving(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": "docs/architecture.md", "claim": "settles fees hourly"},
            ]}),
        }))
        stuck = self.run_dry(root)["waivers"]["needs_rewaiving"]
        self.assertEqual([w["code"] for w in stuck], ["waiver-claim-not-found"])

    def test_a_waiver_matching_two_units_re_keys_onto_both(self):
        # The audit this migrates *to* accepts a waiver reaching several units
        # and reports how far it reached, so a dry run that called this
        # ambiguous would overstate the cost of migrating.
        root = self.migrated(legacy_consumer({
            "docs/architecture.md": (
                "# Architecture\n\n"
                "The billing service settles invoices at a flat rate today. "
                "The ledger settles invoices at a flat rate as well.\n"
            ),
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": "docs/architecture.md",
                 "claim": "settles invoices at a flat rate"},
            ]}),
        }))
        payload = self.run_dry(root)["waivers"]
        self.assertEqual(payload["needs_rewaiving"], [])
        self.assertEqual(payload["rekeyed"][0]["matched"], 2)
        self.assertEqual(len(payload["rekeyed"][0]["units"]), 2)

    def test_a_waiver_reaching_past_the_audits_limit_needs_re_waiving(self):
        from doclifecycle.drift import MAX_WAIVER_UNITS

        sentences = " ".join(
            f"Release {i} settles invoices at a flat rate."
            for i in range(MAX_WAIVER_UNITS + 1)
        )
        root = self.migrated(legacy_consumer({
            "docs/architecture.md": f"# Architecture\n\n{sentences}\n",
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": "docs/architecture.md",
                 "claim": "settles invoices at a flat rate"},
            ]}),
        }))
        stuck = self.run_dry(root)["waivers"]["needs_rewaiving"]
        self.assertEqual([w["code"] for w in stuck], ["waiver-claim-too-broad"])

    def test_a_waiver_on_a_narrative_document_needs_re_waiving(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/drift-waivers.json": json.dumps({"waivers": [
                {"file": "docs/guides/onboarding.md",
                 "claim": "New engineers start with the billing walkthrough"},
            ]}),
        }))
        stuck = self.run_dry(root)["waivers"]["needs_rewaiving"]
        self.assertEqual([w["code"] for w in stuck],
                         ["waiver-document-carries-no-assertions"])

    def test_an_unclassified_document_blocks_the_upgrade_and_is_named(self):
        root = self.migrated()
        os.makedirs(os.path.join(root, "docs/notes"))
        for name in ("scratch.md", "later.md"):
            with open(os.path.join(root, "docs/notes", name), "w") as fh:
                fh.write("# Notes\n\nSomething nobody classified.\n")
        result = dry_run_migration(root)
        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [(p.code, p.location) for p in result.problems],
            [("migration-unclassified-document", "docs/notes/later.md"),
             ("migration-unclassified-document", "docs/notes/scratch.md")],
        )

    def test_rejects_a_legacy_report_with_a_regeneration_instruction(self):
        root = self.migrated(legacy_consumer({
            "drift-report.json": '{"records": []}\n',
        }))
        classes = {a["class"]: a for a in self.run_dry(root)["artifacts"]}
        self.assertEqual(classes["report"]["found"], ["drift-report.json"])
        self.assertIn("drift-audit", classes["report"]["regenerate"])

    def test_rejects_an_uncarried_file_in_the_legacy_state_directory(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/approval-set.json": '{"approved": []}\n',
            ".github/doc-sync/last-stales.json": '{"stales": []}\n',
        }))
        classes = {a["class"]: a for a in self.run_dry(root)["artifacts"]}
        self.assertEqual(classes["approval"]["found"],
                         [".github/doc-sync/approval-set.json"])
        self.assertEqual(classes["cache"]["found"],
                         [".github/doc-sync/last-stales.json"])

    def test_rejects_the_bloat_lanes_working_files(self):
        root = self.migrated(legacy_consumer({
            "manifest.json": '{"pending": []}\n',
            "distill-manifest.json": '{"pending": []}\n',
        }))
        classes = {a["class"]: a for a in self.run_dry(root)["artifacts"]}
        self.assertEqual(classes["cache"]["found"],
                         ["distill-manifest.json", "manifest.json"])

    def test_every_artifact_class_says_it_is_not_carried_across(self):
        payload = self.run_dry(self.migrated())
        self.assertEqual(sorted(a["class"] for a in payload["artifacts"]),
                         ["approval", "cache", "report"])
        self.assertTrue(all(a["carried"] is False for a in payload["artifacts"]))
        self.assertTrue(all(a["regenerate"] for a in payload["artifacts"]))

    def test_a_vendored_script_is_not_mistaken_for_an_uncarried_artifact(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/sync-gate.py": "# gate\n",
        }))
        found = [p for a in self.run_dry(root)["artifacts"] for p in a["found"]]
        self.assertEqual(found, [])

    def test_names_the_versions_the_migration_spans(self):
        payload = self.run_dry(self.migrated())
        self.assertEqual(payload["migration"], {
            "contract": MIGRATION_CONTRACT,
            "from_version": "0.12.0",
            "to_version": PLUGIN_VERSION,
        })

    def test_a_fresh_install_migrates_from_no_version_at_all(self):
        files = legacy_consumer()
        del files[".github/doc-sync/installed-version"]
        payload = self.run_dry(self.migrated(files))
        self.assertIsNone(payload["migration"]["from_version"])

    def test_refuses_an_install_ahead_of_this_engine(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/installed-version": "99.0.0\n",
        }))
        result = dry_run_migration(root)
        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems],
                         ["migration-version-ahead"])

    def test_refuses_an_installed_version_it_cannot_read(self):
        root = self.migrated(legacy_consumer({
            ".github/doc-sync/installed-version": "nightly\n",
        }))
        result = dry_run_migration(root)
        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems],
                         ["migration-version-unreadable"])

    def test_lists_the_consumer_configuration_it_preserves_untouched(self):
        payload = self.run_dry(self.migrated())
        preserved = {p["path"]: p for p in payload["preserved"]}
        self.assertEqual(
            sorted(preserved),
            [".github/doc-sync-marker",
             ".github/doc-sync/audit-scope.json",
             ".github/doc-sync/drift-waivers.json",
             ".github/doc-sync/installed-version"],
        )
        self.assertTrue(all(p["present"] for p in preserved.values()))
        self.assertEqual(len(preserved[".github/doc-sync-marker"]["digest"]), 64)
        self.assertEqual(preserved[".github/doc-sync-marker"]["disposition"],
                         "unchanged")
        # The one consumer file the migration does move, and it says so.
        self.assertEqual(
            preserved[".github/doc-sync/installed-version"]["disposition"],
            "set-to-target",
        )

    def test_writes_nothing_to_the_consumer(self):
        root = self.migrated()
        before = tree_digest(root)
        dry_run_migration(root)
        self.assertEqual(tree_digest(root), before)


if __name__ == "__main__":
    unittest.main()
