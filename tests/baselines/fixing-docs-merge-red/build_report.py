#!/usr/bin/env python3
"""Regenerate fixture70/artifacts/report.json from the fixture repository.

Every digest in the report comes from the engine itself: the lineage from
`report.current_lineage()`, the unit digests from `segment.segment_document()`,
the record digests from `finding.build_finding()`, and the report digest from
`report.validate_report()`. Nothing here is hand-written.

Usage:
    python3 build_report.py [out.json]   # default: artifacts/report.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "repo")
ARTIFACTS = os.path.join(HERE, "artifacts")
ENGINE = (
    "/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/"
    "agent-af5bffefde2b11f46/plugins/doc-lifecycle/engine"
)
sys.path.insert(0, os.environ.get("DOCLIFECYCLE_ENGINE", ENGINE))

from doclifecycle.digest import sha256_canonical              # noqa: E402
from doclifecycle.finding import build_finding                # noqa: E402
from doclifecycle.report import (                             # noqa: E402
    current_lineage, parse_lineage, state_from_content, validate_report,
)
from doclifecycle.results import Invalid                      # noqa: E402
from doclifecycle.segment import segment_document             # noqa: E402

ARCH = "docs/architecture.md"
PLAN = "docs/plans/0001-fee-change.md"
AUDIT_CONFIG = os.path.join(REPO, ".doc-lifecycle", "audit-config.json")


def audit_config_digest():
    """The consumer configuration digest this run's lineage pins.

    The engine does not own the audit configuration, so the digest is the
    consumer's to compute — here, over the fixture's own config file, through
    the engine's canonical-JSON digest so reformatting the file is not a new
    configuration.
    """
    with open(AUDIT_CONFIG, encoding="utf-8") as handle:
        return sha256_canonical(json.load(handle))


def die(what, result):
    print(f"{what} failed:", file=sys.stderr)
    for problem in result.problems:
        print(f"  {problem.code}: {problem.message}", file=sys.stderr)
    raise SystemExit(1)


def units_of(path):
    """{normalized unit text: unit digest} for one document."""
    segmentation = segment_document(REPO, path)
    if isinstance(segmentation, Invalid):
        die(f"segment {path}", segmentation)
    return {unit.text: unit.digest for unit in segmentation.units}


def pick(index, path, needle):
    """The one unit in `index` whose text contains `needle`."""
    hits = [(text, digest) for text, digest in index.items() if needle in text]
    if len(hits) != 1:
        raise SystemExit(
            f"{path}: {len(hits)} units contain {needle!r}, expected exactly 1"
        )
    return hits[0][1]


def main():
    state, problems = current_lineage(
        REPO, audit_config_digest=audit_config_digest()
    )
    if problems:
        for problem in problems:
            print(f"  {problem.code}: {problem.message}", file=sys.stderr)
        raise SystemExit(1)

    # `current_lineage` supplies everything the repository decides. The two
    # fields it cannot know are the run's own: what scope the audit declared,
    # and what evidence it was allowed to consult.
    raw_lineage = dict(state)
    raw_lineage["audit_mode"] = "full"
    raw_lineage["evidence_boundary"] = {"sources": ["src/**"], "excluded": []}

    lineage, lineage_problems = parse_lineage(raw_lineage)
    if lineage_problems:
        for problem in lineage_problems:
            print(f"  {problem.code}: {problem.message}", file=sys.stderr)
        raise SystemExit(1)

    arch = units_of(ARCH)
    plan = units_of(PLAN)

    stale_unit = pick(arch, ARCH, "flat 2% fee")
    cut_units = [
        pick(arch, ARCH, "The fee rate lives in the billing service"),
        pick(arch, ARCH, "Configuration of the fee rate is handled"),
    ]
    distill_units = [
        pick(plan, PLAN, "Raise the rate to 2.5%"),
        pick(plan, PLAN, "Status: landed."),
    ]

    findings = [
        build_finding(
            lineage=lineage, code="STALE", path=ARCH,
            units=(stale_unit,), record_id="DRIFT-001",
            extra={
                "assertion_class": "factual",
                "location": f"{ARCH}:7",
                "message": (
                    "src/app.py sets FEE_RATE = 0.025, so the documented flat "
                    "2% fee is 2.5%"
                ),
                "evidence": {
                    "source": "src/app.py",
                    "observed": "FEE_RATE = 0.025",
                },
                "fix": "The service charges a flat 2.5% fee.",
            },
        ),
        build_finding(
            lineage=lineage, code="CUT", path=ARCH,
            units=tuple(cut_units), record_id="BLOAT-001",
            extra={
                "message": (
                    "two sentences restate the preceding one without adding a "
                    "checkable fact"
                ),
                "duplicate_search": {"here": 2, "elsewhere": 0},
            },
        ),
        build_finding(
            lineage=lineage, code="DISTILL", path=PLAN,
            units=tuple(distill_units), record_id="BLOAT-002",
            extra={
                "message": (
                    "the fee change landed; the durable residue belongs in "
                    "docs/architecture.md and the plan retires"
                ),
                "readiness": "ready",
            },
        ),
    ]
    for finding in findings:
        if isinstance(finding, Invalid):
            die("build_finding", finding)

    records = [finding.to_record() for finding in findings]
    payload = {
        "status": state_from_content(records, []),
        "schema_version": 1,
        "lineage": raw_lineage,
        "scope": {
            "basis": (
                "full inventory: every document the registry classifies, "
                "audited by the drift and bloat lanes together"
            ),
            "coverage": "whole-inventory",
            "documents": [ARCH, PLAN],
            "excluded": [],
        },
        "records": records,
        "incomplete": [],
    }

    # The report's own digest comes from the validator, not from this script:
    # one owner computes it, and a report that will not validate is never
    # written.
    report = validate_report(payload, repo_root=REPO)
    if isinstance(report, Invalid):
        die("validate_report", report)

    os.makedirs(ARTIFACTS, exist_ok=True)
    out = (sys.argv[1] if len(sys.argv) > 1
           else os.path.join(ARTIFACTS, "report.json"))
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, indent=2, sort_keys=False)
        handle.write("\n")

    print(f"wrote {out}")
    print(f"status: {report.status}")
    print(f"base commit: {raw_lineage['base_commit']}")
    print(f"audit config digest: {raw_lineage['audit_config_digest']}")
    print(f"report digest: {report.digest}")
    for record in report.records:
        print(f"  {record.id}  {record.extra['code']:<8} "
              f"{record.extra['path']}  {record.digest}")


if __name__ == "__main__":
    main()
