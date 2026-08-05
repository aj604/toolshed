"""The auto-apply policy: what may be minted without a human.

Every fixture is a real git repository with real documents, because minting is
`approval.mint_approval_set` and nothing else — the policy decides *which*
record digests are handed to it, never how authority is produced. So a suite
that mocked the repository would be testing the eligibility table twice and the
seam that matters not at all.
"""

import json
import os
import unittest

from support import ENGINE, RepoTestCase  # noqa: F401 (engine onto sys.path)

from approval_test import (
    CONFIG_DIGEST,
    DOC_A,
    DOC_B,
    FILES,
    HUMAN,
    PLAN_DOC,
    ApprovalTestCase,
    resigned,
)

from doclifecycle import approval as approval_mod
from doclifecycle import bloat
from doclifecycle.applier import (
    OP_CREATE,
    OP_MOVE,
    OP_RETIRE,
    RECORD_REMEDIES,
)
from doclifecycle.approval import (
    MINTER_POLICY,
    ApprovalSet,
    validate_approval_set,
)
from doclifecycle.policy import (
    CLASS_ANCHOR_REFRESH,
    CLASS_DRIFT_STALE,
    DEFAULT_CLASSES,
    DEFAULT_POLICY_PATH,
    ELIGIBILITY_CLASSES,
    NEVER_ELIGIBLE_CODES,
    AutoApplyPolicy,
    Eligibility,
    load_auto_apply_policy,
    mint_policy_approval_set,
    policy_eligibility,
)
from doclifecycle.results import STATE_CLEAN, STATE_STALE, Invalid

POLICY_ID = "nightly-doc-sync"

REGISTRY = """{
  "schema_version": 1,
  "roots": ["docs"],
  "sets": ["plans"],
  "rules": [
    {"glob": "docs/*.md", "kind": "living"},
    {"glob": "docs/guides/*.md", "kind": "narrative"},
    {"glob": "docs/plans/*.md", "kind": "planning", "set": "plans"}
  ]
}
"""

GUIDE = "docs/guides/tour.md"
GUIDE_TEXT = """# Tour

> As of 2026-01-01 (`docs/a.md`)

Welcome to the payment service.
"""

POLICY_JSON = """{
  "artifact": "auto-apply-policy",
  "schema_version": 1,
  "id": "%s"
}
""" % POLICY_ID

POLICY_FILES = dict(
    FILES,
    **{
        ".doc-lifecycle/registry.json": REGISTRY,
        GUIDE: GUIDE_TEXT,
        DEFAULT_POLICY_PATH: POLICY_JSON,
    }
)

EVIDENCE = {"source": "src/fees.py", "line": 7, "observed": "RATE = 0.025"}


def codes(result):
    return sorted(p.code for p in result.problems)


def refusals(eligibility):
    """Every refusal code, by record id — what the run surface reports."""
    return {
        d.record_id: (None if d.refusal is None else d.refusal.code)
        for d in eligibility.decisions
    }


class PolicyTestCase(ApprovalTestCase):
    """The approval-set fixture, plus a narrative document and a policy file."""

    def setUp(self):
        self.repo = self.git_repo(POLICY_FILES)
        self.lineage = self.lineage_for(self.repo)

    def policy(self, **overrides):
        fields = dict(id=POLICY_ID, classes=DEFAULT_CLASSES)
        fields.update(overrides)
        return AutoApplyPolicy(**fields)

    def anchor_unit(self, path=GUIDE):
        """The digest of the `> As of ...` anchor unit, as it is on disk."""
        from doclifecycle.segment import segment_document

        segmentation = segment_document(self.repo, path)
        self.assertNotIsInstance(segmentation, Invalid, segmentation)
        anchor = [u for u in segmentation.units if u.text.startswith("As of")]
        self.assertEqual(len(anchor), 1, [u.text for u in segmentation.units])
        return anchor[0].digest

    def stale(self, record_id="R-1", path=DOC_A, **extra):
        fields = dict(
            assertion="The payment service charges a flat 2% fee.",
            assertion_class="factual",
            location=f"{path}:3",
            kind="value",
            tier=3,
            evidence=dict(EVIDENCE),
            fix="The payment service charges a flat 2.5% fee.",
        )
        fields.update(extra)
        return self.finding(
            record_id, "STALE", path, self.units(self.repo, path)[:1], **fields
        )

    def anchor_stale(self, record_id="R-2", **extra):
        fields = dict(
            assertion="As of 2026-01-01 (`docs/a.md`)",
            location=f"{GUIDE}:3",
            as_of="2026-01-01",
            evidence={"source": DOC_A, "observed": "last changed 2026-07-01"},
        )
        fields.update(extra)
        return self.finding(
            record_id, "ANCHOR-STALE", GUIDE, [self.anchor_unit()], **fields
        )

    def bloat(self, record_id="R-3", code="CUT", **extra):
        fields = dict(rationale="restates the heading")
        fields.update(extra)
        units = (
            self.whole_units(self.repo, DOC_B)
            if code in bloat.WHOLE_DOCUMENT_VERDICTS
            else self.units(self.repo, DOC_B)[:1]
        )
        return self.finding(
            record_id, code, DOC_B, units, **fields
        )

    def eligibility(self, records, policy=None):
        return policy_eligibility(
            self.policy() if policy is None else policy, self.report(records)
        )

    def mint(self, records, policy=None, **kwargs):
        kwargs.setdefault("repo_root", self.repo)
        return mint_policy_approval_set(
            self.report(records), self.policy() if policy is None else policy,
            **kwargs
        )


# --------------------------------------------------------------------------
# Acceptance criterion 3: eligibility classes are consumer configuration, and
# an absent policy means no autonomous minting at all.
# --------------------------------------------------------------------------

class AnAbsentPolicyMintsNothing(PolicyTestCase):
    def test_a_repository_with_no_policy_file_refuses_to_configure_one(self):
        root = self.git_repo({k: v for k, v in POLICY_FILES.items()
                              if k != DEFAULT_POLICY_PATH})

        loaded = load_auto_apply_policy(root)

        self.assertIsInstance(loaded, Invalid, loaded)
        self.assertEqual(codes(loaded), ["policy-not-configured"])

    def test_the_refusal_says_no_autonomous_minting_happens_without_one(self):
        root = self.git_repo({k: v for k, v in POLICY_FILES.items()
                              if k != DEFAULT_POLICY_PATH})

        loaded = load_auto_apply_policy(root)

        self.assertIn("no approval set is minted without a human",
                      loaded.problems[0].message)

    def test_an_absent_policy_is_not_an_empty_policy(self):
        # Fail closed: the absence of configuration must not read as "the
        # defaults", which is exactly the mistake that would turn an
        # unconfigured repository into an autonomously-fixed one.
        root = self.git_repo({k: v for k, v in POLICY_FILES.items()
                              if k != DEFAULT_POLICY_PATH})

        loaded = load_auto_apply_policy(root)

        self.assertNotIsInstance(loaded, AutoApplyPolicy)


class TheConfiguredClasses(PolicyTestCase):
    def test_a_policy_that_names_no_classes_gets_the_specs_defaults(self):
        loaded = load_auto_apply_policy(self.repo)

        self.assertIsInstance(loaded, AutoApplyPolicy, loaded)
        self.assertEqual(loaded.classes, DEFAULT_CLASSES)

    def test_the_defaults_are_the_two_mechanical_classes_and_nothing_else(self):
        self.assertEqual(
            DEFAULT_CLASSES, (CLASS_DRIFT_STALE, CLASS_ANCHOR_REFRESH)
        )
        self.assertEqual(set(DEFAULT_CLASSES), set(ELIGIBILITY_CLASSES))

    def test_a_consumer_may_narrow_the_classes(self):
        self.write(self.repo, DEFAULT_POLICY_PATH, """{
          "artifact": "auto-apply-policy", "schema_version": 1,
          "id": "narrowed", "classes": ["drift-stale-mechanical"]
        }""")

        loaded = load_auto_apply_policy(self.repo)

        self.assertEqual(loaded.classes, (CLASS_DRIFT_STALE,))

    def test_a_narrowed_policy_refuses_the_class_it_left_out(self):
        anchor = self.anchor_stale()

        eligibility = self.eligibility(
            [anchor], policy=self.policy(classes=(CLASS_DRIFT_STALE,))
        )

        self.assertEqual(refusals(eligibility),
                         {"R-2": "policy-class-not-enabled"})

    def test_a_class_nobody_defined_is_refused_rather_than_ignored(self):
        # The vocabulary is closed, so a consumer cannot widen the policy by
        # inventing a class name — and a typo is loud rather than silently
        # narrowing the policy to nothing.
        self.write(self.repo, DEFAULT_POLICY_PATH, """{
          "artifact": "auto-apply-policy", "schema_version": 1,
          "id": "typo", "classes": ["drift-stale-mechanicl"]
        }""")

        loaded = load_auto_apply_policy(self.repo)

        self.assertIsInstance(loaded, Invalid, loaded)
        self.assertEqual(codes(loaded), ["policy-unknown-class"])

    def test_a_bloat_class_cannot_be_configured_at_all(self):
        self.write(self.repo, DEFAULT_POLICY_PATH, """{
          "artifact": "auto-apply-policy", "schema_version": 1,
          "id": "greedy", "classes": ["bloat-cut", "drift-stale-mechanical"]
        }""")

        loaded = load_auto_apply_policy(self.repo)

        self.assertEqual(codes(loaded), ["policy-unknown-class"])

    def test_an_empty_class_list_is_refused_rather_than_defaulted(self):
        self.write(self.repo, DEFAULT_POLICY_PATH, """{
          "artifact": "auto-apply-policy", "schema_version": 1,
          "id": "empty", "classes": []
        }""")

        loaded = load_auto_apply_policy(self.repo)

        self.assertEqual(codes(loaded), ["policy-invalid-classes"])

    def test_something_that_is_not_a_policy_is_named_as_what_it_is(self):
        self.write(self.repo, DEFAULT_POLICY_PATH,
                   '{"artifact": "approval-set", "schema_version": 1}')

        loaded = load_auto_apply_policy(self.repo)

        self.assertEqual(codes(loaded), ["policy-not-a-policy"])

    def test_a_policy_without_a_name_is_refused(self):
        # The id is the minter's id: an unattributable policy mint is an
        # approval set whose lineage says nothing about who stood behind it.
        self.write(self.repo, DEFAULT_POLICY_PATH,
                   '{"artifact": "auto-apply-policy", "schema_version": 1}')

        loaded = load_auto_apply_policy(self.repo)

        self.assertEqual(codes(loaded), ["policy-missing-field"])

    def test_an_unreadable_policy_file_is_a_refusal_not_an_absent_one(self):
        self.write(self.repo, DEFAULT_POLICY_PATH, "{not json")

        loaded = load_auto_apply_policy(self.repo)

        self.assertEqual(codes(loaded), ["policy-unreadable"])


# --------------------------------------------------------------------------
# Acceptance criterion 1: the policy mints for an eligible drift STALE finding.
# --------------------------------------------------------------------------

class AnEligibleDriftFinding(PolicyTestCase):
    def test_a_stale_finding_with_preimage_and_evidence_is_eligible(self):
        eligibility = self.eligibility([self.stale()])

        self.assertIsInstance(eligibility, Eligibility, eligibility)
        self.assertEqual(refusals(eligibility), {"R-1": None})

    def test_the_decision_names_the_class_that_admitted_it(self):
        eligibility = self.eligibility([self.stale()])

        self.assertEqual(eligibility.decisions[0].eligible_class,
                         CLASS_DRIFT_STALE)

    def test_the_policy_mints_an_approval_set_for_it(self):
        record = self.stale()

        approval = self.mint([record])

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual([r.digest for r in approval.records], [record["digest"]])

    def test_the_policy_is_named_as_the_minter_in_the_lineage(self):
        approval = self.mint([self.stale()])

        self.assertEqual(approval.minter.kind, MINTER_POLICY)
        self.assertEqual(approval.minter.id, POLICY_ID)

    def test_a_narrative_anchor_refresh_is_eligible_too(self):
        eligibility = self.eligibility([self.anchor_stale()])

        self.assertEqual(refusals(eligibility), {"R-2": None})
        self.assertEqual(eligibility.decisions[0].eligible_class,
                         CLASS_ANCHOR_REFRESH)

    def test_an_ineligible_record_beside_an_eligible_one_is_left_skipped(self):
        stale, bloat = self.stale(), self.bloat()

        approval = self.mint([stale, bloat])

        self.assertEqual([r.digest for r in approval.records],
                         [stale["digest"]])
        self.assertEqual([r.digest for r in approval.skipped],
                         [bloat["digest"]])


# --------------------------------------------------------------------------
# Acceptance criterion 2: the policy provably cannot mint for a bloat finding,
# a create/retire operation, or a waiver-disputed record.
# --------------------------------------------------------------------------

class WhatAPolicyMayNeverMint(PolicyTestCase):
    def test_every_bloat_code_is_refused_as_never_eligible(self):
        for code in NEVER_ELIGIBLE_CODES:
            with self.subTest(code=code):
                eligibility = self.eligibility([self.bloat(code=code)])

                self.assertEqual(refusals(eligibility),
                                 {"R-3": "policy-never-eligible"})

    def test_a_bloat_finding_produces_a_typed_refusal_not_an_exception(self):
        result = self.mint([self.bloat()])

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("policy-nothing-eligible", codes(result))
        self.assertIn("policy-never-eligible", codes(result))

    def test_a_bloat_finding_produces_no_approval_set(self):
        self.assertNotIsInstance(self.mint([self.bloat()]), ApprovalSet)

    def test_the_generic_minter_refuses_a_bloat_record_too(self):
        # The release-gate criterion — "provably cannot mint for a bloat
        # finding" — has to hold against both doors: the restricted
        # policy-mint door above, and the generic `mint_approval_set` any
        # caller can reach directly with a policy `Minter`. Since #186 the
        # generic door refuses the brand before the record, so the answer is
        # the same refusal for a stronger reason.
        record = self.bloat()

        result = approval_mod.mint_approval_set(
            self.report([record]), [record["digest"]], repo_root=self.repo,
            minter=approval_mod.Minter(kind=MINTER_POLICY, id=POLICY_ID),
        )

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("approval-policy-minter-not-generic", codes(result))

    def test_the_never_eligible_codes_are_every_bloat_operation(self):
        # Issue #57 review: this asserted the same six literals the tuple was
        # hand-written from, so a seventh bloat verdict would have been
        # policy-approvable through the generic door with the guard still
        # green. The property is the *derivation* — every bloat verdict, by
        # construction — so that is what is asserted.
        self.assertEqual(tuple(NEVER_ELIGIBLE_CODES), bloat.VERDICTS)

    def test_no_eligible_code_may_be_planned_as_a_create_move_or_retire(self):
        # The operation half of the restriction, and the applier owns it: a
        # policy-minted record whose remedy table admitted `create-document`
        # would let a plan bring a document into being with nobody's approval.
        forbidden = {OP_CREATE, OP_RETIRE, OP_MOVE}
        for code in self.eligible_codes():
            with self.subTest(code=code):
                self.assertEqual(
                    set(RECORD_REMEDIES.get(code, ())) & forbidden, set()
                )

    def test_every_eligible_code_has_a_remedy_the_applier_can_plan(self):
        # The other half of the same coupling, and the one that fails silently:
        # a class whose code is absent from the remedy table mints approval
        # sets no edit plan can act on, so the lane would produce authority and
        # then refuse itself. Fail-shut, but a dead default is not a default.
        for code in self.eligible_codes():
            with self.subTest(code=code):
                self.assertIn(code, RECORD_REMEDIES)
                self.assertNotEqual(RECORD_REMEDIES[code], ())

    def eligible_codes(self):
        from doclifecycle.policy import CLASS_CODES

        return sorted({c for codes_ in CLASS_CODES.values() for c in codes_})

    def test_a_waiver_disputed_record_is_refused(self):
        waived = self.stale(waived={
            "claim": "charges a flat 2% fee", "source": ".github/waivers.json",
            "source_digest": "d" * 64, "matched": 1,
        })

        eligibility = self.eligibility([waived])

        self.assertEqual(refusals(eligibility), {"R-1": "policy-record-waived"})

    def test_a_waiver_disputed_record_produces_no_approval_set(self):
        waived = self.stale(waived={
            "claim": "charges a flat 2% fee", "source": ".github/waivers.json",
            "source_digest": "d" * 64, "matched": 1,
        })

        result = self.mint([waived])

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("policy-record-waived", codes(result))

    def test_a_stale_finding_without_an_exact_preimage_is_refused(self):
        # "Exact preimage" is the text the finding was written about. Without
        # it there is nothing mechanical to replace, only a model's paraphrase.
        eligibility = self.eligibility([self.stale(assertion="")])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-missing-preimage"})

    def test_a_stale_finding_without_an_evidence_pointer_is_refused(self):
        eligibility = self.eligibility([self.stale(evidence=None)])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-missing-evidence"})

    def test_evidence_that_names_no_source_is_no_pointer(self):
        eligibility = self.eligibility(
            [self.stale(evidence={"observed": "RATE = 0.025"})]
        )

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-missing-evidence"})

    def test_a_finding_settled_by_running_a_tool_is_refused(self):
        """A command citation is a real pointer, but not one the repository
        contains: nobody re-deriving the change from this commit can settle it,
        so the semantic review a PR provides is the wrong one to skip."""
        eligibility = self.eligibility([self.stale(evidence={
            "command": "gh pr list --json bogus",
            "observed": "authorAssociation is not an available field"})])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-external-evidence"})

    def test_a_record_that_writes_a_second_document_is_refused(self):
        # A destination is where a move puts content, so a record carrying one
        # would widen the mutation scope past the document the finding is about.
        eligibility = self.eligibility([self.stale(
            destination={"path": DOC_B, "kind": "living", "set": None}
        )])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-record-has-destination"})

    def test_an_anchor_code_that_needs_authoring_is_not_a_refresh(self):
        missing = self.finding(
            "R-4", "ANCHOR-MISSING", GUIDE, [self.anchor_unit()],
            assertion="Tour", location=f"{GUIDE}:1",
        )

        eligibility = self.eligibility([missing])

        self.assertEqual(refusals(eligibility),
                         {"R-4": "policy-code-not-mechanical"})

    def test_nothing_eligible_names_every_records_own_refusal(self):
        result = self.mint([self.bloat(), self.stale(evidence=None)])

        self.assertEqual(
            codes(result),
            ["policy-missing-evidence", "policy-never-eligible",
             "policy-nothing-eligible"],
        )


# --------------------------------------------------------------------------
# Acceptance criterion 5 (#123): a fix that asserts something about another
# document is a finding for a human, whatever the record pins about its own.
# --------------------------------------------------------------------------

# DRIFT-023 of the second shadow-parity cycle, verbatim
# (`tests/baselines/shadow-parity-gate-rerun/shadow-report.json`). The verdict
# is right — the pointer was superseded — and the fix asserts the successor
# "carries criteria and verdict", which the worker never opened it to check. At
# the audited commit that file's Verdict section read "Not yet run".
DRIFT_023_ASSERTION = (
    "This repository's own gate record, criteria and verdict, is "
    "`docs/plans/2026-07-26-shadow-parity-gate.md`."
)
DRIFT_023_FIX = (
    "This repository's own gate record, criteria and verdict, is "
    "`docs/plans/2026-07-27-shadow-parity-gate-rerun.md` (the first cycle's, "
    "now superseded, is `docs/plans/2026-07-26-shadow-parity-gate.md`)."
)
DRIFT_023_EVIDENCE = {
    "source": "docs/plans/2026-07-27-shadow-parity-gate-rerun.md",
    "line": 5,
    "observed": "the rerun file's header reads Supersedes: "
                "docs/plans/2026-07-26-shadow-parity-gate.md",
}


class AFixThatSpeaksForAnotherDocument(PolicyTestCase):
    def repointing(self, **extra):
        fields = dict(
            assertion=DRIFT_023_ASSERTION,
            fix=DRIFT_023_FIX,
            evidence=dict(DRIFT_023_EVIDENCE),
        )
        fields.update(extra)
        return self.stale(**fields)

    def test_a_fix_naming_a_document_the_claim_did_not_is_refused(self):
        eligibility = self.eligibility([self.repointing()])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-fix-names-other-document"})

    def test_the_refusal_names_the_document_nobody_read(self):
        eligibility = self.eligibility([self.repointing()])

        message = eligibility.decisions[0].refusal.message
        self.assertIn("docs/plans/2026-07-27-shadow-parity-gate-rerun.md",
                      message)

    def test_an_evidence_pointer_at_that_document_does_not_settle_it(self):
        # The whole of the DRIFT-023 failure: the record *does* cite the new
        # file. A citation pins one line; the fix asserted what the file
        # contains, which no pointer to its header settles.
        eligibility = self.eligibility([self.repointing()])

        self.assertIsNotNone(eligibility.decisions[0].refusal)

    def test_the_repointing_record_reaches_no_approval_set(self):
        result = self.mint([self.repointing()])

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("policy-fix-names-other-document", codes(result))
        self.assertIn("policy-nothing-eligible", codes(result))

    def test_a_bare_filename_the_claim_did_not_name_is_refused_too(self):
        # The same assertion, spelled without a directory.
        eligibility = self.eligibility([self.repointing(
            assertion="The output contract is SKILL.md.",
            fix="The output contract is output-contract.md.",
        )])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-fix-names-other-document"})

    def test_a_fix_that_only_rewords_a_document_the_claim_names_is_eligible(self):
        # DRIFT-022's shape: both spellings name the same two build artifacts,
        # so the fix asserts nothing about a document the record did not pin.
        eligibility = self.eligibility([self.repointing(
            assertion="Never let a hand edit reintroduce `drift-report.json`"
                      "/`pr-body.md` into a commit.",
            fix="Never let a hand edit reintroduce `drift-report.json`"
                "/`pr-body.md` into the sync PR commit.",
        )])

        self.assertEqual(refusals(eligibility), {"R-1": None})

    def test_a_fix_may_name_the_document_the_finding_lives_in(self):
        # Self-reference is not a cross-document assertion: the applier reads
        # and rewrites this document, and the preimage pins the passage. The
        # preimage deliberately does *not* name it, so the carve-out is the
        # only thing that admits this record.
        eligibility = self.eligibility([self.repointing(
            assertion="The fee is documented here.",
            fix="The 2.5% fee is documented in docs/a.md.",
        )])

        self.assertEqual(refusals(eligibility), {"R-1": None})

    def test_the_carve_out_is_the_path_and_not_the_bare_filename(self):
        # `a.md` is not this document — a bare filename names no one document,
        # and seven files in this repository are called SKILL.md. Refusing is
        # the conservative reading, and it is the one that holds when a fix
        # names a *sibling* whose filename happens to match.
        eligibility = self.eligibility([self.repointing(
            assertion="The fee is documented here.",
            fix="The 2.5% fee is documented in a.md.",
        )])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-fix-names-other-document"})

    def test_a_preimage_that_merely_mentions_a_file_has_not_pinned_it(self):
        # The subtler DRIFT-023: the claim mentions the successor in passing,
        # so a rule about *new* names would admit a fix that swaps which
        # document the sentence is about. The preimage pins this passage's
        # text, never that file's contents.
        eligibility = self.eligibility([self.repointing(
            assertion="The gate record is `docs/plans/a.md` (a rerun is "
                      "planned at `docs/plans/b.md`).",
            fix="The gate record, criteria and verdict, is `docs/plans/b.md`.",
        )])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-fix-names-other-document"})

    def test_dropping_a_document_the_claim_named_is_a_claim_too(self):
        eligibility = self.eligibility([self.repointing(
            assertion="Both `docs/plans/a.md` and `docs/plans/b.md` apply.",
            fix="Only `docs/plans/a.md` applies.",
        )])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-fix-names-other-document"})

    def test_a_fix_that_is_not_text_is_read_rather_than_skipped(self):
        # Fail shut on a shape this module does not know: #77's item 2 may give
        # `fix` a multi-line form, and a guard that skipped what it could not
        # read would hand that form straight through.
        eligibility = self.eligibility([self.repointing(
            assertion="The gate record is `docs/plans/a.md`.",
            fix=["The gate record is", "`docs/plans/b.md`."],
        )])

        self.assertEqual(refusals(eligibility),
                         {"R-1": "policy-fix-names-other-document"})

    def test_a_fix_that_rewrites_a_symbol_stays_eligible(self):
        # DRIFT-014's shape, and the reason the recognizer must not read a
        # dotted symbol as a file: this is the class the policy exists for.
        eligibility = self.eligibility([self.repointing(
            assertion="one record authorizes (`approval.Record.targets()`)",
            fix="one record authorizes (`approval.ApprovedRecord.targets()`)",
        )])

        self.assertEqual(refusals(eligibility), {"R-1": None})

    def test_a_fix_editing_a_slash_separated_knob_list_stays_eligible(self):
        # DRIFT-021's shape: slashes, no file.
        eligibility = self.eligibility([self.repointing(
            assertion="beyond the cron/cap/bloat-cron/upgrade-cron knobs",
            fix="beyond the cron/cap/bloat-cron/upgrade-cron/audit-cron knobs",
        )])

        self.assertEqual(refusals(eligibility), {"R-1": None})

    def test_an_anchor_refresh_is_not_put_through_the_fix_check(self):
        # A narrative anchor names the files it is dated against, and its
        # refresh is the engine's own arithmetic on a date — there is no
        # model-authored fix to read a new document out of.
        eligibility = self.eligibility([self.anchor_stale()])

        self.assertEqual(refusals(eligibility), {"R-2": None})


# --------------------------------------------------------------------------
# Acceptance criterion 4: the identical applier and confinement path, no bypass.
# --------------------------------------------------------------------------

class NoBypass(PolicyTestCase):
    def test_the_policy_mints_through_the_one_minting_function(self):
        # Not "an equivalent artifact": the call itself. A second producer of
        # approval sets would be a second place the reconciliation, path, and
        # preimage refusals could be forgotten. The shared construction is
        # private since #186 — the public generic door is human-only — and
        # this is the assertion that it is still shared.
        calls = []
        original = approval_mod._mint_approval_set

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        approval_mod._mint_approval_set = spy
        self.addCleanup(setattr, approval_mod, "_mint_approval_set", original)

        approval = self.mint([self.stale()])

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["minter"].kind, MINTER_POLICY)

    def test_a_policy_mint_is_the_human_mint_with_a_different_minter(self):
        record = self.stale()
        report = self.report([record])

        by_policy = mint_policy_approval_set(
            report, self.policy(), repo_root=self.repo)
        by_hand = approval_mod.mint_approval_set(
            report, [record["digest"]], repo_root=self.repo,
            minter=approval_mod.Minter(kind="human", id="avery@example.com"))

        policy_payload = by_policy.to_dict()
        human_payload = by_hand.to_dict()
        for payload in (policy_payload, human_payload):
            payload.pop("minter")
            payload.pop("digest")
        self.assertEqual(policy_payload, human_payload)

    def test_a_refusal_the_minter_owns_is_not_relaxed_for_a_policy(self):
        # The exclusive pair: one leg is an eligible STALE finding, the other a
        # rival remedy for the same passage. The minter refuses the half
        # selection, and the policy does not get a softer answer than a human.
        units = self.units(self.repo, DOC_A)[:1]
        one = self.stale()
        rival = self.finding(
            "R-9", "CUT", DOC_A, units, rationale="cut the passage instead"
        )

        result = self.mint([one, rival])

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("approval-exclusive-group", codes(result))

    def test_the_policy_module_never_writes(self):
        # The applier is the only component that writes, and a policy is a
        # declaration about minting. Statically: no shell, no process, no
        # filesystem mutation — reading its own configuration file is the whole
        # of its contact with the disk.
        import inspect

        from doclifecycle import policy as policy_mod

        source = inspect.getsource(policy_mod)
        for forbidden in ("subprocess", "os.system", "shutil", "os.remove",
                          "os.replace", "os.rename", "\"w\"", "'w'"):
            self.assertNotIn(forbidden, source,
                             f"policy.py must not reference {forbidden}")

    def test_a_policy_minted_set_carries_no_extra_authority(self):
        approval = self.mint([self.stale()])

        self.assertEqual(approval.scope.paths, (DOC_A,))

    def test_minting_from_something_that_is_not_a_report_is_a_type_error(self):
        with self.assertRaises(TypeError):
            mint_policy_approval_set(
                {"records": []}, self.policy(), repo_root=self.repo)

    def test_minting_with_something_that_is_not_a_policy_is_a_type_error(self):
        with self.assertRaises(TypeError):
            mint_policy_approval_set(
                self.report([self.stale()]), {"id": "x"}, repo_root=self.repo)


class TheEligibilityPayload(PolicyTestCase):
    def test_it_reports_every_record_the_report_carried(self):
        eligibility = self.eligibility([self.stale(), self.bloat()])

        payload = eligibility.to_dict()
        self.assertEqual(
            sorted(d["id"] for d in payload["decisions"]), ["R-1", "R-3"]
        )

    def test_it_names_the_policy_that_decided(self):
        payload = self.eligibility([self.stale()]).to_dict()

        self.assertEqual(payload["policy"]["id"], POLICY_ID)
        self.assertEqual(payload["policy"]["classes"], list(DEFAULT_CLASSES))

    def test_a_refused_record_carries_its_reason_in_the_payload(self):
        payload = self.eligibility([self.bloat()]).to_dict()

        refusal = payload["decisions"][0]["refusal"]
        self.assertEqual(refusal["code"], "policy-never-eligible")
        self.assertIn("bloat", refusal["message"])

    def test_a_report_with_nothing_eligible_is_a_verdict_not_a_failure(self):
        eligibility = self.eligibility([self.bloat()])

        self.assertIsInstance(eligibility, Eligibility)
        self.assertEqual(eligibility.eligible_digests, ())


# --------------------------------------------------------------------------
# Policy provenance (#186): the brand is producible only from the standing
# declaration, and stays revalidatable against it.
# --------------------------------------------------------------------------

class ProvenanceTestCase(PolicyTestCase):
    """A real policy on disk, and the two ways to reach a branded artifact."""

    def declared(self):
        """The declaration the repository holds right now."""
        loaded = load_auto_apply_policy(self.repo)
        self.assertIsInstance(loaded, AutoApplyPolicy, loaded)
        return loaded

    def declare(self, *, identifier=POLICY_ID, classes=None):
        """Write a standing declaration and return it as the engine reads it."""
        payload = {
            "artifact": "auto-apply-policy", "schema_version": 1,
            "id": identifier,
        }
        if classes is not None:
            payload["classes"] = list(classes)
        self.write(self.repo, DEFAULT_POLICY_PATH, json.dumps(payload))
        return self.declared()

    def check(self, payload, report):
        return validate_approval_set(
            payload, report=report, repo_root=self.repo,
            audit_config_digest=CONFIG_DIGEST,
        )

    def forge(self, records, selected=None):
        """`(report, payload)`: a branded artifact no policy derived.

        Minted honestly as a *human* — through every refusal minting owns —
        then re-branded with the repository's real declaration and re-signed.
        That is the whole of what a text editor or an alternate producer can
        do, and it is exactly the artifact the applier would be handed.
        """
        report = self.report(records)
        digests = (
            [r["digest"] for r in records] if selected is None else selected
        )
        approval = approval_mod.mint_approval_set(
            report, digests, repo_root=self.repo, minter=HUMAN,
        )
        self.assertIsInstance(approval, ApprovalSet, approval)
        declared = self.declared()
        payload = approval.to_dict()
        payload["minter"] = {
            "kind": MINTER_POLICY, "id": declared.id,
            "policy_digest": declared.digest,
        }
        return report, resigned(payload)


class TheOnlyProducerOfAPolicyBrand(ProvenanceTestCase):
    def test_the_policy_mint_records_the_declaration_it_derived_from(self):
        approval = self.mint([self.stale()])

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual(approval.minter.policy_digest, self.declared().digest)

    def test_the_declaration_digest_is_over_what_it_authorizes(self):
        # Not over the file's bytes: reformatting the JSON, or spelling out the
        # classes it would have defaulted to, is the same delegation.
        spelled_out = self.declare(classes=DEFAULT_CLASSES)

        self.assertEqual(spelled_out.digest, self.policy().digest)

    def test_narrowing_the_classes_is_a_different_declaration(self):
        self.assertNotEqual(
            self.policy(classes=(CLASS_DRIFT_STALE,)).digest,
            self.policy().digest,
        )

    def test_renaming_the_policy_is_a_different_declaration(self):
        self.assertNotEqual(
            self.policy(id="someone-elses-nightly").digest,
            self.policy().digest,
        )

    def test_the_generic_door_mints_no_brand_at_all(self):
        record = self.stale()

        result = approval_mod.mint_approval_set(
            self.report([record]), [record["digest"]], repo_root=self.repo,
            minter=approval_mod.Minter(
                kind=MINTER_POLICY, id=POLICY_ID,
                policy_digest=self.declared().digest,
            ),
        )

        # Even with the real declaration's digest in hand: the selection came
        # from the caller, and provenance is a claim about who selected.
        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(codes(result), ["approval-policy-minter-not-generic"])

    def test_a_policy_minted_set_validates_against_its_declaration(self):
        # The honest path, end to end: mint from the standing policy, then
        # revalidate with the report and the repository.
        record = self.stale()
        report = self.report([record])
        approval = mint_policy_approval_set(
            report, self.declared(), repo_root=self.repo)
        self.assertIsInstance(approval, ApprovalSet, approval)

        result = self.check(approval.to_dict(), report)

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.status, STATE_CLEAN)
        self.assertEqual(result.stale_reasons, ())


class AnArtifactNoPolicyDerived(ProvenanceTestCase):
    """Every policy refusal, re-reached through the artifact (#186 AC2).

    Each record here is one a *person* may legitimately approve, so each mints
    cleanly through the human door and can then be re-branded. What must not
    differ is the authority outcome: the standing declaration does not derive
    the selection, so the artifact is refused for the same reason eligibility
    refused the record.
    """

    def mutations(self):
        """Every mutation class, with the eligibility refusal it earns."""
        return {
            "waived": (self.stale(waived={
                "claim": "charges a flat 2% fee",
                "source": ".github/waivers.json",
                "source_digest": "d" * 64, "matched": 1,
            }), "policy-record-waived"),
            "destination-bearing": (self.stale(destination={
                "path": DOC_B, "kind": "living", "set": None,
            }), "policy-record-has-destination"),
            "command-evidenced": (self.stale(evidence={
                "command": "gh pr list --json bogus",
                "observed": "authorAssociation is not an available field",
            }), "policy-external-evidence"),
            "missing-evidence": (self.stale(evidence=None),
                                 "policy-missing-evidence"),
            "missing-preimage": (self.stale(assertion=""),
                                 "policy-missing-preimage"),
            "redirected-document": (self.stale(
                assertion=DRIFT_023_ASSERTION, fix=DRIFT_023_FIX,
                evidence=dict(DRIFT_023_EVIDENCE),
            ), "policy-fix-names-other-document"),
        }

    def test_eligibility_refuses_every_one_of_them(self):
        # The authority outcome the artifact side must match, stated once.
        for name, (record, refusal) in self.mutations().items():
            with self.subTest(mutation=name):
                self.assertEqual(refusals(self.eligibility([record])),
                                 {record["id"]: refusal})

    def test_the_policy_mint_produces_nothing_for_any_of_them(self):
        for name, (record, refusal) in self.mutations().items():
            with self.subTest(mutation=name):
                result = self.mint([record])

                self.assertIsInstance(result, Invalid, result)
                self.assertIn(refusal, codes(result))

    def test_the_generic_mint_refuses_the_brand_for_any_of_them(self):
        for name, (record, _) in self.mutations().items():
            with self.subTest(mutation=name):
                result = approval_mod.mint_approval_set(
                    self.report([record]), [record["digest"]],
                    repo_root=self.repo,
                    minter=approval_mod.Minter(
                        kind=MINTER_POLICY, id=POLICY_ID,
                        policy_digest=self.declared().digest,
                    ),
                )

                self.assertIsInstance(result, Invalid, result)
                self.assertEqual(codes(result),
                                 ["approval-policy-minter-not-generic"])

    def test_a_branded_artifact_selecting_one_fails_closed(self):
        for name, (record, _) in self.mutations().items():
            with self.subTest(mutation=name):
                report, payload = self.forge([record])

                result = self.check(payload, report)

                self.assertIsInstance(result, Invalid, result)
                self.assertEqual(
                    codes(result), ["approval-policy-selection-not-derived"]
                )

    def test_the_refusal_names_the_record_the_declaration_did_not_admit(self):
        record, _ = self.mutations()["waived"]
        report, payload = self.forge([record])

        result = self.check(payload, report)

        self.assertIn(record["digest"], result.problems[0].message)

    def test_a_bloat_record_is_refused_structurally_as_well(self):
        # Defense in depth, and it answers first: the bloat restriction is a
        # pure function of the artifact's own fields, so it needs neither the
        # report nor the repository the derivation check depends on.
        record = self.bloat()
        report, payload = self.forge([record])

        self.assertEqual(
            codes(validate_approval_set(payload)),
            ["approval-policy-ineligible-record"],
        )
        self.assertIn("approval-policy-ineligible-record",
                      codes(self.check(payload, report)))

    def test_a_class_the_consumer_disabled_is_refused_on_the_artifact(self):
        # Repository configuration is the authority, so the artifact is judged
        # against the declaration in force, not the one that was in force.
        self.declare(classes=(CLASS_DRIFT_STALE,))
        report, payload = self.forge([self.anchor_stale()])

        result = self.check(payload, report)

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(
            codes(result), ["approval-policy-selection-not-derived"]
        )

    def test_a_set_that_hides_an_eligible_record_is_refused_too(self):
        # The other direction: a policy mint takes every record the
        # declaration admits, so a narrower branded selection was derived by
        # something that is not this policy either.
        one, two = self.stale(), self.stale("R-8", path=DOC_B)
        report, payload = self.forge([one, two], selected=[one["digest"]])

        result = self.check(payload, report)

        self.assertEqual(
            codes(result), ["approval-policy-selection-not-derived"]
        )

    def test_the_derivation_check_is_invalid_rather_than_stale(self):
        # Eligibility is a pure function of the declaration and the report,
        # and this artifact pins the digest of both — so no repository state
        # could make an honest policy mint have chosen this selection.
        record, _ = self.mutations()["waived"]
        report, payload = self.forge([record])

        self.assertNotIsInstance(self.check(payload, report), ApprovalSet)


class TheDeclarationTheBrandDelegatesFrom(ProvenanceTestCase):
    def minted(self):
        record = self.stale()
        report = self.report([record])
        approval = mint_policy_approval_set(
            report, self.declared(), repo_root=self.repo)
        self.assertIsInstance(approval, ApprovalSet, approval)
        return report, approval

    def test_a_declaration_that_moved_is_stale_not_a_forgery(self):
        # A consumer narrowing their policy is the world moving: re-run the
        # lane against the policy in force. Calling it a forgery would accuse
        # the consumer of forging their own approval set.
        report, approval = self.minted()
        self.declare(classes=(CLASS_ANCHOR_REFRESH,))

        result = self.check(approval.to_dict(), report)

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual([r.code for r in result.stale_reasons],
                         ["approval-policy-changed"])

    def test_the_stale_reason_names_both_declarations(self):
        report, approval = self.minted()
        self.declare(classes=(CLASS_ANCHOR_REFRESH,))

        reason = self.check(approval.to_dict(), report).stale_reasons[0]

        self.assertEqual(reason.reported, approval.minter.policy_digest)
        self.assertEqual(reason.current, self.declared().digest)

    def test_a_repository_that_revoked_its_policy_is_stale_too(self):
        # An absent declaration delegates nothing, and "the policy cannot be
        # read" is an unanswered question about the authority — never a pass.
        report, approval = self.minted()
        os.remove(os.path.join(self.repo, DEFAULT_POLICY_PATH))

        result = self.check(approval.to_dict(), report)

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual([r.code for r in result.stale_reasons],
                         ["approval-policy-changed"])
        self.assertEqual(result.stale_reasons[0].current,
                         "policy-not-configured")

    def test_a_changed_declaration_stands_the_derivation_check_down(self):
        # Under some other declaration the derived set differs *as a
        # consequence*, so running the comparison anyway would report a
        # forgery at every honest re-run whose consumer narrowed a class.
        report, approval = self.minted()
        self.declare(classes=(CLASS_ANCHOR_REFRESH,))

        result = self.check(approval.to_dict(), report)

        self.assertNotIn("approval-policy-selection-not-derived",
                         [r.code for r in result.stale_reasons])

    def test_without_a_repository_the_declaration_is_not_consulted(self):
        # And the verdict says so: `unchecked` already names the repository
        # check, which is the one this provenance rides in.
        _, approval = self.minted()

        result = validate_approval_set(approval.to_dict())

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertIn("repository", result.unchecked)

    def test_a_human_minted_set_needs_no_policy_at_all(self):
        record = self.stale()
        report = self.report([record])
        approval = approval_mod.mint_approval_set(
            report, [record["digest"]], repo_root=self.repo, minter=HUMAN)
        os.remove(os.path.join(self.repo, DEFAULT_POLICY_PATH))

        result = self.check(approval.to_dict(), report)

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.stale_reasons, ())


if __name__ == "__main__":
    unittest.main()
