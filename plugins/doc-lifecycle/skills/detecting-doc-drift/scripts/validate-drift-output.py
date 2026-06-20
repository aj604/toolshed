#!/usr/bin/env python3
"""Validate a detecting-doc-drift result against the output contract.

The contract lives in ../SKILL.md ("The output contract"). This script enforces
the mechanical rules an agent self-checks unreliably: enum values, the
fix-null-unless-STALE rule, mandatory evidence, and summary counts. It does NOT
judge whether a verdict is *correct* — only whether the record is well-formed.

Usage:
    validate-drift-output.py [FILE]        # reads FILE, or stdin if omitted

Input: either a bare JSON array of records, or an object
    {"records": [...], "summary": {"verified": N, "stale": N, "unverifiable": N}}

Exit status: 0 if valid, 1 if any record violates the contract, 2 on bad input.
On success, prints the authoritative summary (recomputed from the records) so
callers never rely on a hand-counted one.
"""

import json
import re
import sys

KINDS = {"command", "path", "symbol", "behavior", "structure", "value"}
VERDICTS = {"VERIFIED", "STALE", "UNVERIFIABLE"}
TIERS = {1, 2, 3}
REQUIRED = ("claim", "location", "kind", "tier", "verdict", "evidence", "fix")
# location is `file:line` (single line or a range), e.g. CLAUDE.md:24 or worker.js:17-19.
# It is the only field fixing-doc-drift uses to place an edit, so its shape is enforced.
LOCATION_RE = re.compile(r"^.+:\d+(-\d+)?$")


def load(src):
    raw = sys.stdin.read() if src is None else open(src, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"], data.get("summary")
    raise ValueError(
        "input must be a JSON array of records, or an object with a 'records' array"
    )


def nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def validate_record(i, r):
    where = f"record[{i}]"
    if isinstance(r, dict) and nonempty_str(r.get("location")):
        where += f" ({r['location']})"
    if not isinstance(r, dict):
        return [f"{where}: not a JSON object"]

    errs = []
    for field in REQUIRED:
        if field not in r:
            errs.append(f"{where}: missing required field '{field}'")

    if r.get("kind") not in KINDS:
        errs.append(f"{where}: kind {r.get('kind')!r} not in {sorted(KINDS)}")
    if r.get("verdict") not in VERDICTS:
        errs.append(f"{where}: verdict {r.get('verdict')!r} not in {sorted(VERDICTS)}")
    if r.get("tier") not in TIERS:
        errs.append(f"{where}: tier {r.get('tier')!r} not in {sorted(TIERS)}")
    if not nonempty_str(r.get("evidence")):
        errs.append(f"{where}: evidence is mandatory for every verdict (incl. VERIFIED)")

    loc = r.get("location")
    if nonempty_str(loc) and not LOCATION_RE.match(loc.strip()):
        errs.append(f"{where}: location {loc!r} must be 'file:line' (e.g. CLAUDE.md:24)")

    verdict, fix = r.get("verdict"), r.get("fix")
    if verdict == "STALE":
        if not nonempty_str(fix):
            errs.append(f"{where}: STALE requires a non-empty 'fix'")
    elif verdict in ("VERIFIED", "UNVERIFIABLE"):
        if fix is not None:
            errs.append(f"{where}: fix must be null unless verdict is STALE (got {fix!r})")
    return errs


def count_verdicts(records):
    counts = {"verified": 0, "stale": 0, "unverifiable": 0}
    key = {"VERIFIED": "verified", "STALE": "stale", "UNVERIFIABLE": "unverifiable"}
    for r in records:
        v = r.get("verdict") if isinstance(r, dict) else None
        if v in key:
            counts[key[v]] += 1
    return counts


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        records, summary = load(src)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    errs = []
    for i, r in enumerate(records):
        errs.extend(validate_record(i, r))

    counts = count_verdicts(records)
    if summary is not None and summary != counts:
        errs.append(f"summary {summary} does not match record counts {counts}")

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"\nFAILED: {len(errs)} contract violation(s)", file=sys.stderr)
        return 1

    print(f"OK: {len(records)} record(s) valid")
    print(f"summary: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
