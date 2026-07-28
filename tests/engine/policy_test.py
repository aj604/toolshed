"""The auto-apply policy: what may be minted without a human.

Every fixture is a real git repository with real documents, because minting is
`approval.mint_approval_set` and nothing else — the policy decides *which*
record digests are handed to it, never how authority is produced. So a suite
that mocked the repository would be testing the eligibility table twice and the
seam that matters not at all.
"""

import unittest

from support import ENGINE, RepoTestCase  # noqa: F401 (engine onto sys.path)

from approval_test import (
    CONFIG_DIGEST,
    DOC_A,
    DOC_B,
    FILES,
    PLAN_DOC,
    ApprovalTestCase,
)

from doclifecycle import approval as approval_mod
from doclifecycle.applier import (
    OP_CREATE,
    OP_MOVE,
    OP_RETIRE,
    RECORD_REMEDIES,
)
from doclifecycle.approval import ApprovalSet, MINTER_POLICY
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
from doclifecycle.results import Invalid

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
        return self.finding(
            record_id, code, DOC_B, self.units(self.repo, DOC_B)[:1], **fields
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

    def test_the_never_eligible_codes_are_every_bloat_operation(self):
        self.assertEqual(
            set(NEVER_ELIGIBLE_CODES),
            {"CUT", "CONDENSE", "EXTRACT-AND-MOVE", "MERGE-DOC", "RETIRE-DOC",
             "DISTILL"},
        )

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
        # and rewrites this document, and the preimage pins the passage.
        eligibility = self.eligibility([self.repointing(
            assertion="The fee is documented in docs/a.md.",
            fix="The 2.5% fee is documented in docs/a.md.",
        )])

        self.assertEqual(refusals(eligibility), {"R-1": None})

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
        # preimage refusals could be forgotten.
        calls = []
        original = approval_mod.mint_approval_set

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        approval_mod.mint_approval_set = spy
        self.addCleanup(setattr, approval_mod, "mint_approval_set", original)

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


if __name__ == "__main__":
    unittest.main()
