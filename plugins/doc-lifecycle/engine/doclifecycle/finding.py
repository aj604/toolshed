"""Finding identity, and the assertion classes a model records against units.

Two things live here, and the line between them is the point of the module.

**Identity is deterministic.** A finding groups one or more assertion units in
one document under one finding code, and its digest is taken over exactly
that, plus the report lineage it was produced under. Nothing else is in it —
not the display id, not the message, not what a model concluded — so an
approval selecting `DRIFT-001` by digest can never land on a differently
numbered, differently worded, or differently classified finding, and re-running
an audit against unchanged content under unchanged lineage reproduces the same
digest. The group is *normalized* (sorted, deduplicated) before hashing,
because it is a set of units, not a sequence: listing the same two units in the
other order is the same finding.

**Judgment is data.** `record_classifications` takes what a model says each
unit is — factual, normative, rationale, or non-assertive — and validates it
hard before it is written down anywhere: unknown classes, unknown units, double
classifications, and skipped units are all refused, and a class other than
`non-assertive` against a structurally non-assertive-capable unit (a heading, a
code example, an HTML comment) is refused outright. That last check is what
keeps structure from being turned into a fake claim and then "verified".
Recording a class changes no digest.
"""

from dataclasses import dataclass, field
from typing import Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .digest import sha256_canonical
from .report import DIGEST, Lineage, lineage_digest
from .results import Invalid, Problem

# What a model may say an assertion unit is. Closed, and exhaustive by design:
# every unit gets exactly one of these, and `non-assertive` is a real answer
# rather than the absence of one — prose that connects, illustrates, or signposts
# is not a claim, and must not be recorded as a claim nobody made.
FACTUAL = "factual"            # asserts a fact; carries an evidence obligation
NORMATIVE = "normative"        # states a rule; carries an owner/source obligation
RATIONALE = "rationale"        # explains why; obligation is coherence, not evidence
NON_ASSERTIVE = "non-assertive"  # connective, illustrative, or signposting prose

ASSERTION_CLASSES = (FACTUAL, NORMATIVE, RATIONALE, NON_ASSERTIVE)

# Fields the record shape owns. Reviewable extras may not shadow them: a
# finding that could overwrite its own digest or path in `extra` would let
# prose decide identity.
RESERVED_RECORD_FIELDS = ("id", "digest", "code", "path", "units")

CLASSIFICATION_FIELDS = ("unit", "assertion_class")


@dataclass(frozen=True)
class Classification:
    """One unit, and what a model said it is."""

    unit: str
    assertion_class: str

    def to_dict(self):
        return {"unit": self.unit, "assertion_class": self.assertion_class}


@dataclass(frozen=True)
class Classifications:
    """A validated set of assertion classes over one segmentation.

    Keyed to the segmentation digest, so a classification set cannot be read
    back against a document that has since changed.
    """

    segmentation_digest: str
    classifications: Tuple[Classification, ...]

    def by_unit(self):
        return {c.unit: c.assertion_class for c in self.classifications}

    def to_dict(self):
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "segmentation_digest": self.segmentation_digest,
            "classifications": [c.to_dict() for c in self.classifications],
        }


@dataclass(frozen=True)
class Finding:
    """One audited finding, and the digest an approval set selects it by."""

    record_id: str
    code: str
    path: str
    units: Tuple[str, ...]
    lineage: Lineage
    digest: str
    extra: dict = field(default_factory=dict)

    def to_record(self):
        """The report record for this finding.

        `report.validate_report` owns `id` and `digest`; everything else here
        travels as record data, which is why none of it is in the digest.
        """
        return {
            "id": self.record_id,
            "digest": self.digest,
            "code": self.code,
            "path": self.path,
            "units": list(self.units),
            **self.extra,
        }


def _normalize_units(units):
    """A finding's group: sorted and deduplicated, because it is a set.

    Sorted so two audits that walked the document in different orders produce
    one digest; deduplicated because a unit named twice is the same unit —
    identical content is one identity, so a repeated sentence legitimately
    resolves to one digest.
    """
    return tuple(sorted(set(units)))


def finding_digest(lineage, code, path, units):
    """A finding's identity: the run, the document, the code, and the group.

    Canonical JSON over exactly those four things. What moves it: unit content
    (a unit digest is its content), the grouping, the document, the finding
    code, and any lineage field. What cannot move it: the display id, the
    message, the evidence prose, the recorded assertion classes, and the order
    the units were listed in.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": lineage_digest(lineage),
        "code": code,
        "path": path,
        "units": list(_normalize_units(units)),
    })


def build_finding(lineage, code, path, units, record_id, extra=None):
    """Build a validated `Finding`, or `Invalid` naming every problem.

    A non-`Lineage` is a `TypeError` rather than a problem: binding a finding
    to something that is not a run's lineage is a programming error in the
    audit engine, not malformed data it read.
    """
    if not isinstance(lineage, Lineage):
        raise TypeError(
            f"a finding binds to a report Lineage, not {type(lineage).__name__} — "
            f"identity that is not pinned to a run is not identity"
        )

    problems = []

    def bad(problem_code, message, where=None):
        problems.append(
            Problem(code=problem_code, message=message, location=where)
        )

    for name, value in (("code", code), ("path", path), ("id", record_id)):
        if not (isinstance(value, str) and value.strip()):
            bad("finding-invalid-field",
                f"a finding's {name} must be a non-empty string", name)

    if not units:
        bad("finding-no-units",
            "a finding must group at least one assertion unit — a finding that "
            "names no unit cannot be checked, applied, or re-derived",
            "units")
    else:
        for unit in units:
            if not (isinstance(unit, str) and DIGEST.match(unit)):
                bad("finding-invalid-unit",
                    f"unit {unit!r} is not an assertion-unit digest — a finding "
                    f"groups units by digest, so that its identity does not "
                    f"depend on where the text happens to sit",
                    "units")

    extra = dict(extra or {})
    for name in extra:
        if name in RESERVED_RECORD_FIELDS:
            bad("finding-reserved-field",
                f"{name!r} is the record's own field and cannot be supplied as "
                f"reviewable data — prose must not be able to overwrite what a "
                f"finding is",
                name)

    if problems:
        return Invalid(tuple(problems))

    return Finding(
        record_id=record_id,
        code=code,
        path=path,
        units=_normalize_units(units),
        lineage=lineage,
        digest=finding_digest(lineage, code, path, units),
        extra=extra,
    )


def record_classifications(segmentation, entries):
    """Validate and record what a model said each unit is.

    Returns `Classifications`, or `Invalid` naming every problem in the whole
    response — a model's output is checked exhaustively, so one re-prompt can
    address all of it. Fails closed: a response with any problem records
    nothing, because a partially trusted classification set is one nobody can
    tell the trustworthy half of.
    """
    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    if not isinstance(entries, list):
        return Invalid((Problem(
            code="classification-invalid-shape",
            message=(
                f"assertion classes must be a list of "
                f"{list(CLASSIFICATION_FIELDS)} objects, not "
                f"{type(entries).__name__}"
            ),
            location="classifications",
        ),))

    capable = {u.digest for u in segmentation.units if u.assertion_capable}
    known = {u.digest: u for u in segmentation.units}

    recorded, seen = [], set()
    for i, entry in enumerate(entries):
        where = f"classifications[{i}]"
        if not isinstance(entry, dict) or set(entry) != set(CLASSIFICATION_FIELDS):
            bad("classification-invalid-shape",
                f"classifications[{i}] must be an object with exactly "
                f"{list(CLASSIFICATION_FIELDS)}",
                where)
            continue
        unit, assertion_class = entry["unit"], entry["assertion_class"]
        valid = True
        if assertion_class not in ASSERTION_CLASSES:
            bad("classification-unknown-class",
                f"{assertion_class!r} is not an assertion class — a unit is one "
                f"of {list(ASSERTION_CLASSES)}, and an unrecognized answer says "
                f"nothing about the unit's obligation",
                where)
            valid = False
        if unit not in known:
            bad("classification-unknown-unit",
                f"no unit in this segmentation has digest {unit!r} — a class "
                f"recorded against a unit the document does not contain would "
                f"describe nothing",
                where)
            valid = False
        elif unit not in capable and assertion_class != NON_ASSERTIVE:
            bad("classification-not-assertion-capable",
                f"a {known[unit].kind} cannot carry a {assertion_class} claim — "
                f"it is structure, not prose, so the only class it may have is "
                f"{NON_ASSERTIVE!r}",
                where)
            valid = False
        if unit in seen:
            bad("classification-duplicate",
                f"unit {unit!r} is classified more than once — a unit has one "
                f"class, and two answers is no answer",
                where)
            valid = False
        seen.add(unit)
        if valid:
            recorded.append(Classification(unit=unit, assertion_class=assertion_class))

    for unit in sorted(capable - seen):
        bad("classification-missing",
            f"assertion unit {unit!r} was not classified — an unclassified unit "
            f"is indistinguishable from one nobody found a claim in, so the run "
            f"cannot say what it examined",
            "classifications")

    if problems:
        return Invalid(tuple(problems))

    return Classifications(
        segmentation_digest=segmentation.digest,
        classifications=tuple(recorded),
    )
