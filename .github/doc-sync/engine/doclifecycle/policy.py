"""The auto-apply policy: which findings may be minted without a human.

Semantic approval is a person selecting record digests. An **auto-apply
policy** is the one other minter: a standing, consumer-configured declaration
that a narrow class of *mechanical* remedies may have approval sets minted
without waiting for that person, so the scheduled lane keeps producing
autonomous fix PRs. The policy is named as the minter in the approval set's
lineage, and PR review is the designated semantic review for what it mints —
change approval, a person merging the real pull request the apply lane opens,
still lands everything.

Four properties, and each one is a way this module refuses to become a second
authority:

**It decides eligibility, never authority.** `mint_policy_approval_set` selects
digests and hands them to `approval.mint_approval_set` — the same call a human
dispatch makes, through the same reconciliation, path-authorization, and
preimage refusals. There is no policy-shaped approval set and no second
producer of one; a policy mint differs from a human mint in exactly one field.

**Its vocabulary is closed, and the closure is the restriction.** A consumer
enables named classes, and the only names that exist are mechanical ones. A
repository cannot configure its way to auto-applied bloat cuts, moves,
retirements, or document creations, because there is no class name for them —
and the bloat codes are refused structurally besides, so a future class that
tried to reach one is refused rather than admitted.

**An absent policy is not an empty policy.** No configuration file means no
autonomous minting at all: `load_auto_apply_policy` refuses, loudly, rather
than returning a permissive default. Failing open here would turn every
repository that has not thought about the question into one that fixes itself.

**A refusal is typed and per-record.** Deciding produces a decision for every
record the report carries — the eligible ones, and each refused one with the
reason — so a run surface can say what the policy declined and why, rather than
reporting a silent no-op. Nothing here raises on data.

*Why "mechanical" is narrower than "deterministic".* A remedy is mechanical
when the text to change is pinned exactly (the finding names the assertion
units, and a unit digest *is* its content) and someone can follow the pointer
that says why (`evidence.source`). Everything the policy admits satisfies both;
everything a bloat audit produces is a judgment about whether a passage should
exist at all, which no pointer settles.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from . import approval as approval_mod
from .bloat import CONDENSE, CUT, DISTILL, EXTRACT_AND_MOVE, MERGE_DOC, RETIRE_DOC
from .drift import CODE_ANCHOR_STALE, VERDICT_STALE
from .inventory import DEFAULT_REGISTRY_PATH
from .report import Report
from .results import STATUS_OK, Invalid, Problem

# What the artifact says it is, for the same reason an approval set does: a
# payload that does not declare itself could be handed over where another is
# required and parse far enough to matter.
ARTIFACT_KIND = "auto-apply-policy"

# Beside the registry, because both are the consumer's standing declarations
# about their documentation and both are reviewed as repository state.
DEFAULT_POLICY_PATH = ".doc-lifecycle/auto-apply-policy.json"

FIELDS = ("artifact", "schema_version", "id", "classes")
REQUIRED_FIELDS = ("artifact", "schema_version", "id")

# The eligibility classes. Closed, and short on purpose: this tuple is the
# entire surface a consumer can enable, so adding a name here is the only way
# to widen what any repository may auto-apply.
CLASS_DRIFT_STALE = "drift-stale-mechanical"
CLASS_ANCHOR_REFRESH = "narrative-anchor-refresh"
ELIGIBILITY_CLASSES = (CLASS_DRIFT_STALE, CLASS_ANCHOR_REFRESH)

# Which finding codes each class admits.
#
# `drift-stale-mechanical` is a living document's claim that no longer holds,
# against a passage the finding pins exactly. UNVERIFIABLE is deliberately
# absent: "nobody could check this" is a question, and a policy that answered
# it would be inventing the fact nobody could find.
#
# `narrative-anchor-refresh` is the one anchor code that is a refresh — the
# `> As of` line is honest about a date that has been overtaken by a change to
# what it names. The other anchor codes are out for the same reason:
# ANCHOR-MISSING and ANCHOR-MALFORMED need an anchor *authored*,
# ANCHOR-FUTURE-DATED and ANCHOR-UNRESOLVABLE-REFERENCE say the anchor names
# something nobody can resolve, and ANCHOR-UNVERIFIABLE is a question again.
CLASS_CODES = {
    CLASS_DRIFT_STALE: (VERDICT_STALE,),
    CLASS_ANCHOR_REFRESH: (CODE_ANCHOR_STALE,),
}

# The codes no class may ever reach, refused by name rather than merely left
# out. Leaving them out would make the restriction a property of a table that
# someone could extend by accident; naming them makes extending it a
# contradiction two lines apart. Every one is a bloat verdict, and every bloat
# verdict is a judgment that a passage or a whole document should stop existing
# or move — approving that is what a person is for.
NEVER_ELIGIBLE_CODES = (
    CUT, CONDENSE, EXTRACT_AND_MOVE, MERGE_DOC, RETIRE_DOC, DISTILL,
)

# What a consumer gets by configuring a policy without narrowing it: the
# spec's defaults, which are every class that exists.
DEFAULT_CLASSES = ELIGIBILITY_CLASSES

# The record fields a mechanical remedy needs, and what each one is for.
# `assertion` is the exact preimage — the text the finding was written about —
# and `evidence` is the pointer that says where the contradicting fact was
# observed. A record missing either is a paraphrase or an unsourced assertion,
# and neither is mechanical.
PREIMAGE_FIELD = "assertion"
EVIDENCE_FIELD = "evidence"
EVIDENCE_SOURCE_FIELD = "source"
# Where a move writes. A mechanical remedy touches the document the finding is
# about and nothing else, so a record carrying one is refused before its code
# is even consulted.
DESTINATION_FIELD = "destination"
# A human's dispute, recorded by the drift audit and never removed from the
# report. It reaches any finding code, so a STALE record can carry one.
WAIVED_FIELD = "waived"


@dataclass(frozen=True)
class AutoApplyPolicy:
    """A consumer's standing declaration of what may be minted without them."""

    id: str
    classes: Tuple[str, ...]

    def codes(self):
        """Every finding code the enabled classes admit, by code."""
        return {
            code: name
            for name in self.classes
            for code in CLASS_CODES[name]
        }

    def to_dict(self):
        return {"id": self.id, "classes": list(self.classes)}


@dataclass(frozen=True)
class Decision:
    """What the policy concluded about one record, and why.

    A refused record carries its `Problem` rather than merely being absent:
    an autonomous lane that reported "nothing to do" without saying what it
    declined is one nobody can tell from a lane that never ran.
    """

    digest: str
    record_id: str
    code: str
    eligible_class: Optional[str] = None
    refusal: Optional[Problem] = None

    def to_dict(self):
        return {
            "digest": self.digest,
            "id": self.record_id,
            "code": self.code,
            "eligible_class": self.eligible_class,
            "refusal": None if self.refusal is None else {
                "code": self.refusal.code,
                "message": self.refusal.message,
                "location": self.refusal.location,
            },
        }


@dataclass(frozen=True)
class Eligibility:
    """One policy's verdict on one report: a decision per record.

    `ok` even when nothing is eligible. A report full of bloat findings is not
    a failed run — it is a run whose answer is "a human decides all of these",
    and turning that into an error would make the ordinary night noisy.
    """

    policy: AutoApplyPolicy
    report_digest: str
    decisions: Tuple[Decision, ...]
    status: str = STATUS_OK

    @property
    def eligible_digests(self):
        return tuple(
            d.digest for d in self.decisions if d.eligible_class is not None
        )

    @property
    def refusals(self):
        return tuple(d.refusal for d in self.decisions if d.refusal is not None)

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "policy": self.policy.to_dict(),
            "report_digest": self.report_digest,
            "decisions": [d.to_dict() for d in self.decisions],
            "eligible": list(self.eligible_digests),
        }


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def _describe(payload):
    """What the consumer put at the policy path instead of a policy."""
    if not isinstance(payload, dict):
        return f"a {type(payload).__name__}"
    kind = payload.get("artifact")
    return (
        f"an object declaring artifact {kind!r}" if kind is not None
        else "an object that does not say what artifact it is"
    )


def load_auto_apply_policy(repo_root, path=DEFAULT_POLICY_PATH):
    """Read a consumer's auto-apply policy. `AutoApplyPolicy`, or `Invalid`.

    An absent file is `policy-not-configured` — a refusal, not a default. The
    permissive reading of "no policy" is the failure this whole component is
    built to avoid: it would make every repository that has never considered
    autonomous minting into one that performs it.
    """
    full = os.path.join(repo_root, path)
    if not os.path.isfile(full):
        return Invalid((Problem(
            code="policy-not-configured",
            message=(
                f"no auto-apply policy at {path}, so no approval set is minted "
                f"without a human: autonomous minting is something a consumer "
                f"declares, and its absence is a declaration too"
            ),
            location=path,
        ),))

    try:
        with open(full, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return Invalid((Problem(
            code="policy-unreadable",
            message=(
                f"the auto-apply policy at {path} cannot be read ({exc}) — a "
                f"policy nobody can parse authorizes nothing, and a typo must "
                f"not read as no policy"
            ),
            location=path,
        ),))

    return _parse(payload, location=path)


def _parse(payload, location=DEFAULT_POLICY_PATH):
    """Validate a policy payload exhaustively. `AutoApplyPolicy` or `Invalid`."""
    problems = []

    def bad(code, message, where=location):
        problems.append(Problem(code=code, message=message, location=where))

    if not isinstance(payload, dict) or payload.get("artifact") != ARTIFACT_KIND:
        bad("policy-not-a-policy",
            f"an auto-apply policy declares artifact {ARTIFACT_KIND!r}; this "
            f"is {_describe(payload)}")
        return Invalid(tuple(problems))

    unknown = sorted(set(payload) - set(FIELDS))
    if unknown:
        bad("policy-unknown-field",
            f"unknown field(s) {unknown}: a policy is exactly {list(FIELDS)}, "
            f"and a field nobody reads is a permission nobody granted")
    missing = [f for f in REQUIRED_FIELDS if f not in payload]
    if missing:
        bad("policy-missing-field",
            f"missing required field(s) {missing}: the id is the minter's id, "
            f"and an unattributable policy mint is not attribution")

    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        bad("policy-invalid-schema-version",
            f"schema_version must be {ARTIFACT_SCHEMA_VERSION}, not "
            f"{payload.get('schema_version')!r}")

    identifier = payload.get("id")
    if "id" in payload and not _name(identifier):
        bad("policy-invalid-id",
            "id must be a non-empty single-line string naming this policy — it "
            "is what the approval set's lineage records as the minter")

    classes = payload.get("classes", list(DEFAULT_CLASSES))
    if not isinstance(classes, list) or not classes or len(set(classes)) != len(
            classes):
        bad("policy-invalid-classes",
            f"classes must be a non-empty list of distinct class names from "
            f"{list(ELIGIBILITY_CLASSES)}; omit it to get the defaults "
            f"{list(DEFAULT_CLASSES)}. An empty list is not 'the defaults' — "
            f"it is a policy that would mint nothing, said the confusing way")
        classes = []
    unknown_classes = [c for c in classes if c not in ELIGIBILITY_CLASSES]
    if unknown_classes:
        bad("policy-unknown-class",
            f"unknown eligibility class(es) {sorted(unknown_classes)}: the "
            f"vocabulary is closed to {list(ELIGIBILITY_CLASSES)}, so a class "
            f"nobody defined is refused rather than ignored — quietly dropping "
            f"it would turn a typo into a narrower policy and an invented name "
            f"into a wider one")

    if problems:
        return Invalid(tuple(problems))
    return AutoApplyPolicy(id=identifier, classes=tuple(classes))


def _name(value):
    return (
        isinstance(value, str) and value.strip() != ""
        and not any(c in value for c in "\n\r\x00")
    )


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------

def _never_eligible(code, record_id):
    return Problem(
        code="policy-never-eligible",
        message=(
            f"record {record_id} is {code}, a bloat verdict: cuts, condenses, "
            f"moves, merges, retirements, and distillations decide that a "
            f"passage or a document should stop existing or move, which is a "
            f"judgment a person makes. No policy configuration reaches it"
        ),
        location=record_id,
    )


def _decide(policy, record, enabled):
    """The policy's verdict on one record. `(eligible_class, Problem or None)`.

    `enabled` is `policy.codes()`, computed once by the caller: it is a fact
    about the policy, not about the record.

    Order matters, and it runs outward-in: the refusals that hold regardless of
    configuration come first, so a repository that enabled every class still
    cannot reach a bloat verdict or a record a human disputed, and only then is
    the enabled-class question asked.
    """
    code = record.extra.get("code")
    record_id = record.id

    if code in NEVER_ELIGIBLE_CODES:
        return None, _never_eligible(code, record_id)

    if record.extra.get(WAIVED_FIELD) is not None:
        waived = record.extra[WAIVED_FIELD]
        source = waived.get("source") if isinstance(waived, dict) else None
        return None, Problem(
            code="policy-record-waived",
            message=(
                f"record {record_id} is disputed by a waiver"
                + (f" in {source}" if source else "")
                + " — a human has already said this finding is accepted, and "
                  "a policy that applied it anyway would overrule the only "
                  "person who looked"
            ),
            location=record_id,
        )

    if record.extra.get(DESTINATION_FIELD) is not None:
        return None, Problem(
            code="policy-record-has-destination",
            message=(
                f"record {record_id} names a destination, so its remedy writes "
                f"a second document — a mechanical remedy changes the document "
                f"the finding is about and nothing else"
            ),
            location=record_id,
        )

    admitted = enabled.get(code)
    if admitted is None:
        mechanical = {c for codes in CLASS_CODES.values() for c in codes}
        code_known = code in mechanical
        return None, Problem(
            code="policy-class-not-enabled" if code_known
            else "policy-code-not-mechanical",
            message=(
                f"record {record_id} is {code}, which "
                + (
                    f"this policy's classes {list(policy.classes)} do not "
                    f"enable"
                    if code_known else
                    f"no eligibility class admits: {list(ELIGIBILITY_CLASSES)} "
                    f"cover remedies that rewrite a pinned passage, and "
                    f"nothing else is mechanical"
                )
            ),
            location=record_id,
        )

    if not record.extra.get("units") or not _name(
            record.extra.get(PREIMAGE_FIELD)):
        return None, Problem(
            code="policy-missing-preimage",
            message=(
                f"record {record_id} does not carry the exact text it was "
                f"written about, so there is nothing pinned to replace — a "
                f"remedy without a preimage is a model's paraphrase"
            ),
            location=record_id,
        )

    evidence = record.extra.get(EVIDENCE_FIELD)
    if not isinstance(evidence, dict) or not _name(
            evidence.get(EVIDENCE_SOURCE_FIELD)):
        return None, Problem(
            code="policy-missing-evidence",
            message=(
                f"record {record_id} carries no evidence pointer naming where "
                f"the contradicting fact was observed — PR review is the "
                f"semantic review for what a policy mints, and a reviewer with "
                f"nothing to follow cannot perform it"
            ),
            location=record_id,
        )

    return admitted, None


def policy_eligibility(policy, report):
    """Decide every record in `report` under `policy`. Always an `Eligibility`.

    Never `Invalid`: "nothing is eligible" is a verdict about a report, not a
    failure to reach one. A non-`Report` or a non-`AutoApplyPolicy` is a
    `TypeError`, for the same reason minting raises on one — deciding
    eligibility from unvalidated content is a programming error in the caller.
    """
    if not isinstance(report, Report):
        raise TypeError(
            f"policy_eligibility takes a validated Report, not "
            f"{type(report).__name__} — eligibility is decided about records "
            f"bound to a lineage, and unvalidated content has none"
        )
    if not isinstance(policy, AutoApplyPolicy):
        raise TypeError(
            f"policy_eligibility takes an AutoApplyPolicy, not "
            f"{type(policy).__name__} — an unvalidated policy is a dict "
            f"somebody wrote, and this one decides what happens without a human"
        )

    decisions = []
    enabled = policy.codes()
    for record in report.records:
        admitted, refusal = _decide(policy, record, enabled)
        decisions.append(Decision(
            digest=record.digest,
            record_id=record.id,
            code=record.extra.get("code"),
            eligible_class=admitted,
            refusal=refusal,
        ))
    return Eligibility(
        policy=policy,
        report_digest=report.digest,
        decisions=tuple(decisions),
    )


def mint_policy_approval_set(report, policy, *, repo_root,
                             registry_path=DEFAULT_REGISTRY_PATH):
    """Mint an approval set for everything `policy` rules eligible in `report`.

    `ApprovalSet`, or `Invalid`. The selection is *derived* — there is no
    parameter through which a caller could name a record the policy did not
    admit — and it is handed to `approval.mint_approval_set`, which is the one
    producer of approval sets in this engine. Every refusal that function owns
    (reconciliation groups, path authorization, preimage) applies unchanged:
    the policy is a narrower gate in front of the same door, never a second
    door.
    """
    eligibility = policy_eligibility(policy, report)
    selected = eligibility.eligible_digests
    if not selected:
        return Invalid((Problem(
            code="policy-nothing-eligible",
            message=(
                f"policy {policy.id!r} mints nothing from this report: "
                f"{len(report.records)} record(s), none eligible under "
                f"{list(policy.classes)}. Every record's own reason follows; a "
                f"human dispatch is how any of them is approved"
            ),
            location="records",
        ),) + eligibility.refusals)

    return approval_mod.mint_approval_set(
        report, list(selected), repo_root=repo_root,
        minter=approval_mod.Minter(
            kind=approval_mod.MINTER_POLICY, id=policy.id
        ),
        registry_path=registry_path,
    )
