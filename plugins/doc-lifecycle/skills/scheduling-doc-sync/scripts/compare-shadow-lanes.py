#!/usr/bin/env python3
"""Compare a shadow run of the new audit lane against the legacy drift lane.

While a repository migrates from the legacy `doc-sync` lane to the engine's
read-only audit, both lanes look at the same documentation and only one of them
may write. Before the legacy lane is switched off, somebody has to answer four
questions with numbers rather than impressions: what the two lanes agree on,
what each saw that the other did not, how their coverage and cost differ, and
whether the new lane manufactures findings the old one refuted.

This script answers them from the two lanes' own artifacts, so the answer is
reproducible and cannot be assembled to suit a verdict. It judges nothing: a
false positive is a claim about the repository, and only a reader with the
repository open can settle one. What it produces is the candidate set and the
adjudication worklist, split by whether a record could land without a human.

    compare-shadow-lanes.py compare \
        --legacy drift-report.json --legacy-meta legacy-meta.json \
        --shadow report.json --shadow-meta shadow-meta.json \
        --segments segments.json
    compare-shadow-lanes.py render --comparison comparison.json

Exit status: 0 on success, 2 on unreadable or unusable input.

The two lanes describe assertions differently — the legacy record is a
model-written paraphrase at `file:line`, the engine's is a content digest of a
deterministically segmented unit — so `file:line` is the only key both carry.
It is a key across *commits*, though, and the legacy lane's newest report
generally describes an older one. A legacy record whose line no longer holds a
unit is therefore reported as unresolved rather than counted as unique: an
unmatched record proves the lanes disagreed only if the two lanes were looking
at the same text.

This script exists for the migration and leaves with it (aj604/toolshed#77).
"""

import argparse
import json
import sys

SCHEMA_VERSION = 1
# The class #57's auto-apply policy may mint an approval set for without a
# human: a STALE record carrying the exact replacement line and a pointer to
# the evidence that moved. Nothing else lands unattended, so nothing else
# shares its error budget.
AUTO_APPLY_CODE = "STALE"


class Unusable(Exception):
    """Input the comparison cannot run on. Reported, never worked around."""


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Unusable(f"cannot read {path}: {exc}") from exc


def legacy_records(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    raise Unusable(
        "the legacy report must be a JSON array of records, or an object with "
        "a 'records' array"
    )


def split_location(location):
    """('README.md', 7) from 'README.md:7'. The one key both lanes carry."""
    if not isinstance(location, str) or ":" not in location:
        raise Unusable(
            f"a legacy record's location must be 'file:line'; got {location!r}"
        )
    path, _, line = location.rpartition(":")
    if not path or not line.isdigit() or int(line) < 1:
        raise Unusable(
            f"a legacy record's location must be 'file:line' with a line "
            f"numbered from 1; got {location!r}"
        )
    return path, int(line)


def tally(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def summarize_legacy(records, meta):
    documents = sorted({split_location(r.get("location"))[0] for r in records})
    return {
        "run": meta.get("run"),
        "base_commit": meta.get("base_commit"),
        "records": len(records),
        "verdicts": tally(r.get("verdict") for r in records),
        "documents": documents,
    }


def summarize_shadow(report, meta):
    if report.get("status") == "invalid":
        raise Unusable(
            "the shadow report is invalid, so it carries no content to "
            "compare — re-run the audit before comparing"
        )
    scope = report.get("scope") or {}
    lineage = report.get("lineage") or {}
    incomplete = [entry.get("scope") for entry in report.get("incomplete", [])]
    verified = sum(
        len(entry.get("verified", [])) for entry in report.get("examined", [])
    )
    return {
        "status": report.get("status"),
        "base_commit": lineage.get("base_commit"),
        "audit_mode": lineage.get("audit_mode"),
        "plugin_version": lineage.get("plugin_version"),
        "records": len(report.get("records", [])),
        "codes": tally(r.get("code") for r in report.get("records", [])),
        "declared": sorted(scope.get("documents", [])),
        "excluded": sorted(e.get("path") for e in scope.get("excluded", [])),
        "incomplete": sorted(x for x in incomplete if x),
        "verified_units": verified,
    }


def coverage(legacy, shadow, report):
    """Which documents each lane looked at, and why the other one did not."""
    declared = set(shadow["declared"])
    cited = set(legacy["documents"])
    excluded = {
        entry.get("path"): {
            "code": entry.get("code"),
            "reason": entry.get("reason"),
        }
        for entry in (report.get("scope") or {}).get("excluded", [])
    }
    legacy_only = sorted(cited - declared)
    reasons = {}
    for path in legacy_only:
        reasons[path] = excluded.get(path) or {
            "code": "outside-inventory",
            "reason": (
                "not in the shadow registry's inventory — neither declared "
                "nor excluded by the audit's scope"
            ),
        }
    return {
        "both": sorted(cited & declared),
        "legacy_only": legacy_only,
        "legacy_only_reasons": reasons,
        "shadow_only": sorted(declared - cited),
    }


def unit_index(payload):
    """{path: {line: digest}} from the shadow run's segmentations."""
    index = {}
    for document in payload.get("documents", []):
        index[document.get("path")] = {
            unit.get("line"): unit.get("digest")
            for unit in document.get("units", [])
        }
    return index


def shadow_verdicts(report):
    """{unit digest: (verdict, record or None)} for every unit the run judged."""
    judged = {}
    for entry in report.get("examined", []):
        for unit in entry.get("verified", []):
            judged[unit.get("unit")] = ("VERIFIED", None)
    for record in report.get("records", []):
        for unit in record.get("units", []):
            judged[unit] = (record.get("code"), record)
    return judged


def correspond(records, report, segments):
    """Match the two lanes assertion by assertion, and say what did not match."""
    index = unit_index(segments)
    judged = shadow_verdicts(report)
    agreed, disagreed, unresolved, candidates = [], [], [], []
    matched_units = set()

    for record in records:
        location = record.get("location")
        path, line = split_location(location)
        lines = index.get(path)
        if lines is None:
            unresolved.append({
                "path": path, "line": line,
                "reason": "the document was not segmented by the shadow run",
            })
            continue
        unit = lines.get(line)
        if unit is None or unit not in judged:
            unresolved.append({
                "path": path, "line": line,
                "reason": (
                    "no assertion unit at that line in the shadow commit's "
                    "segmentation"
                    if unit is None else
                    "the shadow run recorded no verdict for the unit at that "
                    "line"
                ),
            })
            continue
        matched_units.add(unit)
        legacy_verdict = record.get("verdict")
        shadow_verdict, shadow_record = judged[unit]
        pair = {"path": path, "line": line, "location": location, "unit": unit}
        if legacy_verdict == shadow_verdict:
            agreed.append({**pair, "verdict": legacy_verdict})
            continue
        disagreed.append({
            **pair,
            "legacy_verdict": legacy_verdict,
            "shadow_verdict": shadow_verdict,
            "shadow_record": shadow_record.get("id") if shadow_record else None,
        })
        if legacy_verdict == "VERIFIED" and shadow_record is not None:
            candidates.append({
                "id": shadow_record.get("id"),
                "code": shadow_record.get("code"),
                "path": path,
                "line": line,
                "legacy_verdict": legacy_verdict,
                "legacy_evidence": record.get("evidence"),
            })

    shadow_only = [
        {
            "id": record.get("id"),
            "code": record.get("code"),
            "path": record.get("path"),
            "location": record.get("location"),
        }
        for record in report.get("records", [])
        if not matched_units.intersection(record.get("units", []))
    ]
    return {
        "assertions": {
            "agreed": agreed,
            "disagreed": disagreed,
            "legacy_unresolved": unresolved,
            "shadow_only": sorted(shadow_only, key=lambda r: str(r["id"])),
        },
        "false_positive_candidates": sorted(
            candidates, key=lambda c: str(c["id"])
        ),
    }


def auto_apply_eligible(record):
    """Could #57's auto-apply policy mint an approval set for this record?

    Deliberately the narrow reading: the remedy must be mechanical (an exact
    replacement line), the finding must be checkable (an evidence pointer), and
    no human disposition may already be attached.
    """
    if record.get("code") != AUTO_APPLY_CODE:
        return False
    if "waived" in record:
        return False
    fix = record.get("fix")
    if not isinstance(fix, str) or not fix.strip():
        return False
    evidence = record.get("evidence")
    return isinstance(evidence, dict) and bool(evidence.get("source"))


def adjudication(report):
    eligible, human = [], []
    for record in report.get("records", []):
        target = eligible if auto_apply_eligible(record) else human
        target.append(str(record.get("id")))
    return {
        "records_to_adjudicate": len(report.get("records", [])),
        "auto_apply_eligible": sorted(eligible),
        "human_approval_required": sorted(human),
    }


def per_document(usd, documents):
    """A cost figure only exists when something was examined."""
    if not documents or usd is None:
        return None
    return round(usd / documents, 6)


def cost(legacy, shadow, legacy_meta, shadow_meta):
    legacy_documents = len(legacy["documents"])
    shadow_documents = len(set(shadow["declared"]) - set(shadow["incomplete"]))
    legacy_rate = per_document(legacy_meta.get("cost_usd"), legacy_documents)
    shadow_rate = per_document(shadow_meta.get("cost_usd"), shadow_documents)
    # A ratio needs both figures, and a legacy rate of zero has none to give.
    ratio = None
    if shadow_rate is not None and legacy_rate:
        ratio = round(shadow_rate / legacy_rate, 6)
    return {
        "legacy": {
            "usd": legacy_meta.get("cost_usd"),
            "turns": legacy_meta.get("turns"),
            "duration_ms": legacy_meta.get("duration_ms"),
            "documents": legacy_documents,
            "usd_per_document": legacy_rate,
        },
        "shadow": {
            "usd": shadow_meta.get("cost_usd"),
            "turns": shadow_meta.get("turns"),
            "duration_ms": shadow_meta.get("duration_ms"),
            "documents": shadow_documents,
            "usd_per_document": shadow_rate,
        },
        "ratio_per_document": ratio,
    }


def compare(legacy_payload, legacy_meta, report, shadow_meta, segments):
    records = legacy_records(legacy_payload)
    legacy = summarize_legacy(records, legacy_meta)
    shadow = summarize_shadow(report, shadow_meta)
    return {
        "schema_version": SCHEMA_VERSION,
        "lanes": {"legacy": legacy, "shadow": shadow},
        "coverage": coverage(legacy, shadow, report),
        **correspond(records, report, segments),
        "adjudication": adjudication(report),
        "cost": cost(legacy, shadow, legacy_meta, shadow_meta),
    }


def joined(paths):
    return ", ".join(f"`{p}`" for p in paths) if paths else "none"


def render(comparison):
    if (
        not isinstance(comparison, dict)
        or comparison.get("schema_version") != SCHEMA_VERSION
        or not {"lanes", "coverage", "assertions", "cost"} <= set(comparison)
    ):
        raise Unusable(
            "not a comparison this script produced — render takes the output "
            "of its own compare subcommand"
        )
    legacy = comparison["lanes"]["legacy"]
    shadow = comparison["lanes"]["shadow"]
    assertions = comparison["assertions"]
    money = comparison["cost"]
    lines = [
        "## Shadow parity comparison",
        "",
        "| | Legacy | Shadow |",
        "|---|---|---|",
        f"| base commit | `{legacy['base_commit']}` | `{shadow['base_commit']}` |",
        f"| result | {len(legacy['verdicts'])} verdict kinds | {shadow['status']} |",
        f"| records | {legacy['records']} | {shadow['records']} |",
        f"| verdicts / codes | {legacy['verdicts']} | {shadow['codes']} |",
        f"| documents | {len(legacy['documents'])} | {len(shadow['declared'])} |",
        f"| unexamined | not declared | {len(shadow['incomplete'])} |",
        f"| cost (USD) | {money['legacy']['usd']} | {money['shadow']['usd']} |",
        f"| USD per document | {money['legacy']['usd_per_document']} "
        f"| {money['shadow']['usd_per_document']} |",
        f"| turns | {money['legacy']['turns']} | {money['shadow']['turns']} |",
        "",
        f"Cost ratio per document: {money['ratio_per_document']}",
        "",
        "### Coverage",
        "",
        f"- Both lanes: {joined(comparison['coverage']['both'])}",
        f"- Legacy only: {joined(comparison['coverage']['legacy_only'])}",
    ]
    lines += [
        f"  - `{path}`: {why['code']} — {why['reason']}"
        for path, why in sorted(
            comparison["coverage"]["legacy_only_reasons"].items()
        )
    ]
    lines += [
        f"- Shadow only: {joined(comparison['coverage']['shadow_only'])}",
        "",
        "### Assertion correspondence",
        "",
        f"- Agreed: {len(assertions['agreed'])}",
        f"- Disagreed: {len(assertions['disagreed'])}",
        f"- Legacy records unresolvable at the shadow commit: "
        f"{len(assertions['legacy_unresolved'])}",
        f"- Shadow records with no legacy counterpart: "
        f"{len(assertions['shadow_only'])}",
        "",
        "### Records to adjudicate",
        "",
    ]
    eligible = set(comparison["adjudication"]["auto_apply_eligible"])
    for record in assertions["shadow_only"] + [
        {"id": pair["shadow_record"], "code": pair["shadow_verdict"],
         "location": pair["location"]}
        for pair in assertions["disagreed"] if pair["shadow_record"]
    ]:
        gate = "auto-apply-eligible" if record["id"] in eligible else "human"
        lines.append(
            f"- `{record['id']}` ({record['code']}, {gate}) "
            f"`{record.get('location')}`"
        )
    if not assertions["shadow_only"] and not assertions["disagreed"]:
        lines.append("- none")
    candidates = comparison.get("false_positive_candidates", [])
    lines += [
        "",
        f"### False-positive candidates ({len(candidates)})",
        "",
    ]
    lines += [
        f"- `{c['id']}` at `{c['path']}:{c['line']}` — the legacy lane called "
        f"this assertion {c['legacy_verdict']}"
        for c in candidates
    ] or ["- none"]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare a shadow audit run against the legacy drift lane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    comparison = commands.add_parser(
        "compare", help="emit the comparison as JSON"
    )
    comparison.add_argument("--legacy", required=True,
                            help="the legacy lane's drift-report.json")
    comparison.add_argument("--legacy-meta", required=True,
                            help="the legacy run's cost/turns/duration")
    comparison.add_argument("--shadow", required=True,
                            help="the new lane's validated report")
    comparison.add_argument("--shadow-meta", required=True,
                            help="the shadow run's cost/turns/duration")
    comparison.add_argument("--segments", required=True,
                            help="the shadow run's segmentations, by document")

    rendering = commands.add_parser(
        "render", help="render a comparison as Markdown"
    )
    rendering.add_argument("--comparison", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            payload = compare(
                read_json(args.legacy),
                read_json(args.legacy_meta),
                read_json(args.shadow),
                read_json(args.shadow_meta),
                read_json(args.segments),
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False,
                             allow_nan=False))
        else:
            print(render(read_json(args.comparison)))
    except Unusable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
