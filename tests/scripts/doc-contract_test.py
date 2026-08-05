#!/usr/bin/env python3
"""Guards the three documentation contracts the implementation can falsify.

Issue #194: the operational documentation stops contradicting the engine.
Three claims are checkable mechanically rather than by review, and each was
wrong in the tree before this suite existed:

1. **The writer boundary.** The applier is the only component that writes a
   repository document; `cache.put()` and `approval.write_approval_set()`
   write artifacts. The docs said "the only component that writes", full stop.
2. **The minting doors.** `mint_approval_set` is human-only, `policy.
   mint_policy_approval_set` is the sole producer of a `policy` brand, and
   `validate_approval_set` re-asks the mint-time refusals of the file.
3. **Scheduled write behavior.** The audit lanes are read-only, and an
   opted-in standing policy makes `doc-policy-apply.yml` a schedule-reachable
   job that authors a real review PR.

A wiring suite, like engine-capability_test.py: it reads source and prose, not
behavior. It deliberately pins phrases and code-derived facts rather than whole
files — a full-file snapshot would fail on every wording change and teach the
next author to re-baseline it.

Run: python3 tests/scripts/doc-contract_test.py
"""

import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

ENGINE = os.path.join(ROOT, "plugins", "doc-lifecycle", "engine")
PACKAGE = os.path.join(ENGINE, "doclifecycle")
ENGINE_README = os.path.join(ENGINE, "README.md")
VENDORED_README = os.path.join(
    ROOT, ".doc-lifecycle", "wiring", "engine", "README.md")
CONTEXT = os.path.join(ROOT, "CONTEXT.md")
DISTILLER = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "agents", "doc-distiller.md")
DRIFT_SKILL = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "detecting-doc-drift",
    "SKILL.md")
SCHEDULING_SKILL_DIR = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync")
SCHEDULING_GUIDE = os.path.join(
    ROOT, "docs", "guides", "scheduling-doc-sync.md")
BLOAT_GUIDE = os.path.join(ROOT, "docs", "guides", "auditing-doc-bloat.md")
TOP_README = os.path.join(ROOT, "README.md")

# Every marker that mutates the filesystem. Deliberately the same shape of
# check engine-capability_test.py makes: a substring scan over source, so a
# module that starts writing is noticed the moment the call lands.
WRITE_MARKERS = (
    'open(tmp_path, "w"', 'open(path, "w"', 'open(full, "wb"',
    "os.makedirs(", "os.replace(", "os.remove(", "os.rmdir(",
)

# `open(...)` in a write mode, whatever the target is spelled. Bound to the
# mode argument rather than to a variable name, so `open(dest, "w")` in a new
# module is caught the same as `cache.py`'s `open(tmp_path, "w")` — the claim
# below is that the *package* has three writers, and a name-bound pattern
# could only support the weaker claim that three known writers still write.
WRITE_OPEN = re.compile(r"""open\([^)]*,\s*["'][wxa]""")

# Which module owns which half of the boundary the docs must state.
DOCUMENT_WRITER = "applier.py"
ARTIFACT_WRITERS = ("cache.py", "approval.py")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def flat(path):
    """One line of prose, so an assertion survives a re-wrap.

    These files are hard-wrapped, so a phrase that must be present today can
    land across a line break tomorrow. Collapsing runs of whitespace keeps the
    assertion about the claim rather than about the column it broke at.
    """
    return re.sub(r"\s+", " ", read(path))


class TheWriterBoundaryMatchesWhoActuallyWrites(unittest.TestCase):
    """The engine's writer claim is a claim about the package's source."""

    def test_exactly_three_modules_write_anything(self):
        # The premise the prose rests on. If a fourth module gains a write
        # call, this fails first and the sentences below are re-derived from
        # the code rather than re-asserted from memory.
        writing = set()
        for name in sorted(os.listdir(PACKAGE)):
            if not name.endswith(".py"):
                continue
            source = read(os.path.join(PACKAGE, name))
            if (WRITE_OPEN.search(source)
                    or any(marker in source for marker in WRITE_MARKERS)):
                writing.add(name)
        self.assertEqual(
            writing, {DOCUMENT_WRITER} | set(ARTIFACT_WRITERS),
            "the set of modules that write moved; the engine README's writer "
            "boundary is now a claim about a different package")

    def test_no_document_claims_an_unqualified_sole_writer(self):
        # "the only component that writes" is false: cache.put() and
        # write_approval_set() write too. Every occurrence of the phrase must
        # carry the qualifier that makes it true.
        pattern = re.compile(r"component that writes(?!\s+a\s+repository\s+"
                             r"document)")
        for path in (ENGINE_README, VENDORED_README, CONTEXT, DISTILLER):
            text = flat(path)
            self.assertIsNone(
                pattern.search(text),
                f"{os.path.relpath(path, ROOT)} claims a sole writer without "
                f"scoping it to repository documents")

    def test_the_engine_readme_names_both_artifact_writers(self):
        text = flat(ENGINE_README)
        for needle in ("`cache.put()`", "`approval.write_approval_set()`",
                       "artifact writer"):
            self.assertIn(needle, text, needle)

    def test_the_cache_entry_path_is_documented_as_the_code_derives_it(self):
        # cache.py builds `<cache_dir>/<key.digest>.json`; the README says so,
        # and says the directory is the caller's.
        self.assertIn(
            'os.path.join(cache_dir, key.digest + ".json")',
            read(os.path.join(PACKAGE, "cache.py")))
        text = flat(ENGINE_README)
        self.assertIn("`<cache_dir>/<key digest>.json`", text)
        self.assertIn("`cache_dir` is the caller's to name", text)

    def test_the_approval_writer_is_documented_as_never_repository_state(self):
        source = read(os.path.join(PACKAGE, "approval.py"))
        for code in ("approval-set-tracked-path",
                     "approval-set-would-be-tracked"):
            self.assertIn(code, source, code)
            self.assertIn(code, flat(ENGINE_README), code)

    def test_the_working_tree_claim_stays_paired_with_never_the_index(self):
        # The applier writes the working tree and never stages: no git write
        # verb reaches the package at all.
        source = read(os.path.join(PACKAGE, "applier.py"))
        for verb in ("git add", "update-index", "git commit"):
            self.assertNotIn(verb, source, verb)
        for path in (ENGINE_README, CONTEXT):
            self.assertIn("never the index", flat(path),
                          os.path.relpath(path, ROOT))


class TheMintingDoorsAreDocumentedAsTheEngineSplitsThem(unittest.TestCase):
    """Human minting, policy-derived minting, and read-back validation."""

    def setUp(self):
        self.approval = read(os.path.join(PACKAGE, "approval.py"))
        self.policy = read(os.path.join(PACKAGE, "policy.py"))
        self.report = read(os.path.join(PACKAGE, "report.py"))
        self.readme = flat(ENGINE_README)

    def test_the_documented_approval_schema_version_is_the_engine_s(self):
        match = re.search(r"^SCHEMA_VERSION = (\d+)$", self.approval,
                          re.MULTILINE)
        self.assertIsNotNone(match, "approval.SCHEMA_VERSION not found")
        version = match.group(1)
        self.assertIn(f'"schema_version": {version},', self.readme)
        self.assertIn(f"at **{version}**", self.readme)

    def test_the_pre_provenance_refusal_is_documented(self):
        self.assertIn("approval-schema-pre-provenance", self.approval)
        self.assertIn("approval-schema-pre-provenance", self.readme)

    def test_the_generic_door_is_documented_as_human_only(self):
        # The refusal exists in mint_approval_set, and the docs name its code.
        self.assertIn("approval-policy-minter-not-generic", self.approval)
        for path in (ENGINE_README, CONTEXT):
            self.assertIn("approval-policy-minter-not-generic", flat(path),
                          os.path.relpath(path, ROOT))

    def test_the_policy_door_is_documented_as_the_only_policy_producer(self):
        self.assertIn("def mint_policy_approval_set(", self.policy)
        self.assertIn("the only producer of the brand", self.readme)
        self.assertIn("mint_policy_approval_set", flat(CONTEXT))

    def test_the_policy_door_takes_no_selection_and_the_docs_say_so(self):
        signature = re.search(
            r"def mint_policy_approval_set\((.*?)\):", self.policy, re.DOTALL)
        self.assertIsNotNone(signature)
        self.assertNotIn("selected", signature.group(1))
        self.assertIn("There is no parameter through which a caller names a "
                      "record", self.readme)

    def test_the_structural_recheck_is_located_at_the_shared_construction(self):
        # The bloat restriction's mint-time half lives in the private
        # construction both doors reach — a policy mint never enters the
        # public door, so documenting it there would describe a check the one
        # restricted kind never passes through.
        self.assertIn("def _mint_approval_set(", self.approval)
        self.assertIn("_mint_approval_set(", self.policy)
        self.assertIn("once at mint time inside `_mint_approval_set`",
                      self.readme)
        self.assertNotIn("once at mint time inside `mint_approval_set` itself",
                         self.readme)

    def test_validation_is_documented_as_re_running_the_mint_refusals(self):
        self.assertIn("def validate_approval_set(", self.approval)
        self.assertIn("The minter's refusals are re-run on read-back",
                      self.readme)
        self.assertIn("`validate_approval_set`'s unconditional structural "
                      "layer", self.readme)

    def test_the_lineage_carries_neither_the_minter_nor_the_policy_id(self):
        # The premise: report.Lineage's own field list. `minter` is a
        # top-level key of the approval set's digested content beside it
        # (approval.py), and a policy's `id` becomes `minter.id` (policy.py).
        lineage = re.search(r"class Lineage:(.*?)\n\n", self.report,
                            re.DOTALL)
        self.assertIsNotNone(lineage, "report.Lineage not found")
        fields = re.findall(r"^\s{4}(\w+):", lineage.group(1), re.MULTILINE)
        self.assertNotIn("minter", fields)
        self.assertNotIn("id", fields)
        self.assertIn('"minter": self.minter.to_dict(),', self.approval)
        self.assertIn("id=policy.id,", self.policy)

    def test_no_document_places_the_minter_or_the_id_inside_the_lineage(self):
        # Widened deliberately. This assertion first guarded CONTEXT.md alone
        # — the *derived* document — so two occurrences of the same falsehood
        # in the engine README, which owns the contract, survived a green run
        # (PR #219 review). A guard that skips the owning document is not a
        # guard; every form the claim took in this repository is listed here.
        forbidden = (
            r"minter in (?:the approval set's )?lineage",
            r"`?id`? is what lineage records",
            r"lineage records the (?:policy's )?`?id`?",
            r"minter (?:is |lives )?(?:recorded )?in the lineage",
        )
        for path in (ENGINE_README, VENDORED_README, CONTEXT, DISTILLER):
            text = flat(path)
            for pattern in forbidden:
                self.assertIsNone(
                    re.search(pattern, text),
                    f"{os.path.relpath(path, ROOT)} places the minter or the "
                    f"policy id inside the report lineage, which carries "
                    f"neither")

    def test_the_owning_and_derived_docs_both_place_it_beside_the_lineage(self):
        placed = re.compile(r"(?:beside|alongside) the lineage, not inside it")
        for path in (ENGINE_README, VENDORED_README, CONTEXT):
            self.assertIsNotNone(
                placed.search(flat(path)), os.path.relpath(path, ROOT))

    def test_the_drift_skill_does_not_route_the_auto_lane_through_mint(self):
        text = flat(DRIFT_SKILL)
        self.assertIn("policy-mint", text)
        self.assertNotIn("`mint-approval` takes them (an optional "
                         "auto-trigger layer", text)


class TheScheduledLanesWriteBehaviourIsStated(unittest.TestCase):
    """Read-only audits, and the opted-in policy job the schedule reaches."""

    def lane_templates(self):
        return sorted(
            name for name in os.listdir(SCHEDULING_SKILL_DIR)
            if name.startswith("doc-") and name.endswith(".yml"))

    def test_the_repo_installs_every_shipped_lane(self):
        installed = sorted(
            name for name in os.listdir(
                os.path.join(ROOT, ".github", "workflows"))
            if name.startswith("doc-") and name.endswith(".yml"))
        self.assertEqual(installed, self.lane_templates())

    def test_the_top_readme_counts_the_lanes_it_runs(self):
        # The count is prose; the templates are the fact behind it.
        counts = {3: "three", 4: "four", 5: "five", 6: "six"}
        word = counts[len(self.lane_templates())]
        text = flat(TOP_README)
        self.assertIn(f"the {word} this repo now runs on itself", text)
        self.assertIn("auto-apply-policy.json", text)

    def test_no_guide_says_the_schedule_authors_nothing(self):
        # The exact sentences that let a consumer read an enabled standing
        # policy as leaving the schedule read-only.
        forbidden = (
            "no scheduled job authors a change",
            "no scheduled lane applies its findings",
        )
        for path in (SCHEDULING_GUIDE, BLOAT_GUIDE, TOP_README, CONTEXT,
                     os.path.join(SCHEDULING_SKILL_DIR, "SKILL.md")):
            text = flat(path).lower()
            for phrase in forbidden:
                self.assertNotIn(
                    phrase, text,
                    f"{os.path.relpath(path, ROOT)} says {phrase!r}, which an "
                    f"enabled standing policy falsifies")

    def test_the_guide_names_the_schedule_reachable_authoring_job(self):
        text = flat(SCHEDULING_GUIDE)
        section = text.split("## Reviewing and applying", 1)
        self.assertEqual(len(section), 2, "section heading moved")
        body = section[1].split("## ", 1)[0]
        for needle in ("doc-policy-apply.yml", "successful scheduled drift "
                       "audit", "real pull request"):
            self.assertIn(needle, body, needle)

    def test_the_bloat_guides_claim_is_the_engine_s_closed_code_set(self):
        # "no scheduled lane applies a bloat finding" is true because every
        # bloat verdict code is permanently policy-ineligible.
        approval = read(os.path.join(PACKAGE, "approval.py"))
        self.assertIn("POLICY_NEVER_ELIGIBLE_CODES = BLOAT_VERDICTS", approval)
        text = flat(BLOAT_GUIDE)
        self.assertIn("No scheduled lane applies a bloat finding", text)
        self.assertIn("POLICY_NEVER_ELIGIBLE_CODES", text)


if __name__ == "__main__":
    unittest.main()
