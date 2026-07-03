#!/usr/bin/env python3
"""Validate a detecting-doc-bloat report against the output contract.

The contract lives in ../SKILL.md ("The output contract"). Enforces the
mechanical rules an agent self-checks unreliably: enum values, per-verdict
proposal/location/status/payload rules, unique ids, mandatory evidence (for
passage verdicts, evidence must open with the passage span 'file:start-end'
anchored at location), and summary counts. It does NOT judge whether a
verdict is *correct*.

Usage:
    validate-bloat-output.py [FILE]        # reads FILE, or stdin if omitted

Input: either a bare JSON array of records, or an object
    {"records": [...], "summary": {"cut": N, "condense": N, "extract_and_move": N,
                                   "retire_doc": N, "merge_doc": N, "distill": N}}

Exit status: 0 if valid, 1 if any record violates the contract, 2 on bad input.
On success, prints the authoritative summary (recomputed from the records).
"""

import json
import re
import sys

PASSAGE = {"CUT", "CONDENSE", "EXTRACT-AND-MOVE"}
DOCLEVEL = {"RETIRE-DOC", "MERGE-DOC", "DISTILL"}
VERDICTS = PASSAGE | DOCLEVEL
STATUSES = {"pending-implementation", "ready"}
REQUIRED = ("id", "doc", "location", "verdict", "evidence",
            "proposal", "status", "payload")
SUMMARY_KEYS = ("cut", "condense", "extract_and_move",
                "retire_doc", "merge_doc", "distill")
LOCATION_RE = re.compile(r"^.+:[1-9]\d*$")
SPAN_RE = re.compile(r"^(\S+):([1-9]\d*)(?:-([1-9]\d*))?")


def load(src):
    raw = sys.stdin.read() if src is None else open(src, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        summary = data.get("summary")
        if summary is not None and not isinstance(summary, dict):
            raise ValueError("summary must be an object with the six verdict counts")
        return data["records"], summary
    raise ValueError(
        "input must be a JSON array of records, or an object with a 'records' array"
    )


def nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def real_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_proposal(where, verdict, proposal, errs):
    if verdict == "CONDENSE":
        if not nonempty_str(proposal):
            errs.append(f"{where}: CONDENSE requires proposal = replacement text")
    elif verdict == "EXTRACT-AND-MOVE":
        ok = (isinstance(proposal, dict) and set(proposal) == {"target", "text"}
              and nonempty_str(proposal.get("target"))
              and nonempty_str(proposal.get("text")))
        if not ok:
            errs.append(f"{where}: EXTRACT-AND-MOVE proposal must be "
                        f"{{'target': doc, 'text': text}}, both non-empty")
    elif verdict == "MERGE-DOC":
        ok = (isinstance(proposal, dict) and set(proposal) == {"target"}
              and nonempty_str(proposal.get("target")))
        if not ok:
            errs.append(f"{where}: MERGE-DOC proposal must be {{'target': doc}}")
    else:  # CUT / RETIRE-DOC / DISTILL
        if proposal is not None:
            errs.append(f"{where}: proposal must be null for {verdict}")


def check_evidence_span(where, verdict, location, evidence, errs):
    """Passage-verdict evidence must open with the passage's extent —
    'file:start-end' ('file:start' if one line) — anchored at location."""
    m = SPAN_RE.match(evidence.strip())
    if not m:
        errs.append(f"{where}: {verdict} evidence must open with the passage "
                    f"span 'file:start-end' ('file:start' if one line)")
        return
    file, start, end = m.group(1), int(m.group(2)), m.group(3)
    if f"{file}:{start}" != location.strip():
        errs.append(f"{where}: evidence span opens {file}:{start} but the "
                    f"passage's anchor (location) is {location!r} — the span "
                    f"must start at location")
    if end is not None and int(end) < start:
        errs.append(f"{where}: evidence span end {end} precedes start {start}")


def check_distill(where, status, payload, errs):
    if status not in STATUSES:
        errs.append(f"{where}: DISTILL requires status in {sorted(STATUSES)}")
        return
    if status == "pending-implementation":
        if payload is not None:
            errs.append(f"{where}: pending-implementation forbids payload "
                        f"(no landed code to verify against)")
        return
    ok = (isinstance(payload, dict) and set(payload) == {"claims", "decision_entry"}
          and nonempty_str(payload.get("decision_entry"))
          and isinstance(payload.get("claims"), list) and payload["claims"]
          and all(isinstance(c, dict) and set(c) == {"claim", "target", "evidence"}
                  and all(nonempty_str(c[k]) for k in c)
                  for c in payload["claims"]))
    if not ok:
        errs.append(f"{where}: DISTILL ready requires payload = "
                    f"{{'claims': [{{claim,target,evidence}}, ...] (>=1), "
                    f"'decision_entry': text}} — claims all non-empty")


def validate_record(i, r):
    where = f"record[{i}]"
    if not isinstance(r, dict):
        return [f"{where}: not a JSON object"]
    if nonempty_str(r.get("id")):
        where += f" ({r['id']})"

    errs = []
    missing = set()
    for field in REQUIRED:
        if field not in r:
            missing.add(field)
            errs.append(f"{where}: missing required field '{field}'")
    for field in r:
        if field not in REQUIRED:
            errs.append(f"{where}: unexpected field '{field}'")

    if "id" not in missing and not nonempty_str(r.get("id")):
        errs.append(f"{where}: id must be a non-empty string")
    if "doc" not in missing and not nonempty_str(r.get("doc")):
        errs.append(f"{where}: doc must be a non-empty string")
    verdict = r.get("verdict")
    if "verdict" not in missing and verdict not in VERDICTS:
        errs.append(f"{where}: verdict {verdict!r} not in {sorted(VERDICTS)}")
    if "evidence" not in missing and not nonempty_str(r.get("evidence")):
        errs.append(f"{where}: evidence is mandatory for every verdict")

    if verdict in VERDICTS:
        loc = r.get("location")
        if verdict in PASSAGE:
            if not (isinstance(loc, str) and LOCATION_RE.match(loc.strip())):
                errs.append(f"{where}: {verdict} requires location 'file:line' "
                            f"(single line, no ranges); got {loc!r}")
            elif nonempty_str(r.get("evidence")):
                check_evidence_span(where, verdict, loc, r["evidence"], errs)
        elif loc is not None:
            errs.append(f"{where}: location must be null for doc-level {verdict}")

        if "proposal" not in missing:
            check_proposal(where, verdict, r.get("proposal"), errs)

        if verdict == "DISTILL":
            check_distill(where, r.get("status"), r.get("payload"), errs)
        else:
            if r.get("status") is not None:
                errs.append(f"{where}: status must be null unless verdict is DISTILL")
            if r.get("payload") is not None:
                errs.append(f"{where}: payload must be null unless verdict is DISTILL")
    return errs


def check_unique_ids(records):
    errs, seen = [], {}
    for i, r in enumerate(records):
        if isinstance(r, dict) and nonempty_str(r.get("id")):
            rid = r["id"]
            if rid in seen:
                errs.append(f"record[{i}]: duplicate id {rid!r} (first at record[{seen[rid]}])")
            else:
                seen[rid] = i
    return errs


def count_verdicts(records):
    counts = dict.fromkeys(SUMMARY_KEYS, 0)
    key = {"CUT": "cut", "CONDENSE": "condense", "EXTRACT-AND-MOVE": "extract_and_move",
           "RETIRE-DOC": "retire_doc", "MERGE-DOC": "merge_doc", "DISTILL": "distill"}
    for r in records:
        v = r.get("verdict") if isinstance(r, dict) else None
        if v in key:
            counts[key[v]] += 1
    return counts


def main():
    if len(sys.argv) > 2:
        print("usage: validate-bloat-output.py [FILE]", file=sys.stderr)
        return 2
    src = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        records, summary = load(src)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    errs = []
    for i, r in enumerate(records):
        errs.extend(validate_record(i, r))
    errs.extend(check_unique_ids(records))

    counts = count_verdicts(records)
    if summary is not None:
        if not all(real_int(summary.get(k)) for k in SUMMARY_KEYS):
            errs.append(f"summary {summary} must have integer counts for {list(SUMMARY_KEYS)}")
        elif summary != counts:
            errs.append(f"summary {summary} does not match record counts {counts}")

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"\nFAILED: {len(errs)} contract violation(s)", file=sys.stderr)
        return 1

    print(f"OK: {len(records)} record(s) valid")
    print(f"summary: {json.dumps(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
