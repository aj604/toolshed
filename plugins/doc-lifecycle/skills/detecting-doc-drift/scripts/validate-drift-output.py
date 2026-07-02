#!/usr/bin/env python3
"""Validate a detecting-doc-drift drift report against the output contract.

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
SUMMARY_KEYS = ("verified", "stale", "unverifiable")
# location is `file:line` — exactly one line, numbered from 1, no ranges,
# e.g. CLAUDE.md:24. It is the only field fixing-doc-drift uses to place an
# edit, so its shape is enforced.
LOCATION_RE = re.compile(r"^.+:[1-9]\d*$")


def load(src):
    raw = sys.stdin.read() if src is None else open(src, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        summary = data.get("summary")
        if summary is not None and not isinstance(summary, dict):
            raise ValueError(
                "summary must be an object with integer verified/stale/unverifiable"
            )
        return data["records"], summary
    raise ValueError(
        "input must be a JSON array of records, or an object with a 'records' array"
    )


def nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def real_int(v):
    # `bool` is an `int` subclass and `1.0 == 1`, so a bare equality/membership
    # check would wave through `true` / `1.0`. Require a real (non-bool) int.
    return isinstance(v, int) and not isinstance(v, bool)


def validate_record(i, r):
    where = f"record[{i}]"
    if not isinstance(r, dict):
        return [f"{where}: not a JSON object"]
    if nonempty_str(r.get("location")):
        where += f" ({r['location']})"

    errs = []
    missing = set()
    for field in REQUIRED:
        if field not in r:
            missing.add(field)
            errs.append(f"{where}: missing required field '{field}'")
    for field in r:
        if field not in REQUIRED:
            errs.append(f"{where}: unexpected field '{field}'")

    if "claim" not in missing and not nonempty_str(r.get("claim")):
        errs.append(f"{where}: claim must be a non-empty string")
    if "kind" not in missing and r.get("kind") not in KINDS:
        errs.append(f"{where}: kind {r.get('kind')!r} not in {sorted(KINDS)}")
    if "verdict" not in missing and r.get("verdict") not in VERDICTS:
        errs.append(f"{where}: verdict {r.get('verdict')!r} not in {sorted(VERDICTS)}")
    if "tier" not in missing:
        tier = r.get("tier")
        if not (real_int(tier) and tier in TIERS):
            errs.append(f"{where}: tier {tier!r} not in {sorted(TIERS)}")
    if "evidence" not in missing and not nonempty_str(r.get("evidence")):
        errs.append(f"{where}: evidence is mandatory for every verdict (incl. VERIFIED)")

    if "location" not in missing:
        loc = r.get("location")
        if not (isinstance(loc, str) and LOCATION_RE.match(loc.strip())):
            errs.append(
                f"{where}: location {loc!r} must be 'file:line' — a single line "
                f"numbered from 1, no ranges (e.g. CLAUDE.md:24)"
            )

    if "fix" not in missing:
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
    if len(sys.argv) > 2:
        print("usage: validate-drift-output.py [FILE]", file=sys.stderr)
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

    counts = count_verdicts(records)
    if summary is not None:
        if not all(real_int(summary.get(k)) for k in SUMMARY_KEYS):
            errs.append(
                f"summary {summary} must have integer verified/stale/unverifiable counts"
            )
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
