#!/usr/bin/env python3
"""Validate detecting-doc-bloat output — final reports, chunk seams, assembly.

The contract (v2) lives in ../output-contract.md. This script enforces the
mechanical rules an agent self-checks unreliably: enum values, per-verdict
proposal/location/status/files rules, unique ids, mandatory evidence (for
passage verdicts, evidence must open with the passage span 'file:start-end'
anchored at location), and summary counts. It does NOT judge whether a
verdict is *correct*. Three duties:

1. Final report (default):
       validate-bloat-output.py [FILE]          # FILE, or stdin if omitted
   Input must be the wrapped v2 object
       {"schema": 2, "records": [...], "summary": {...seven counts...}}
   (summary optional; recomputed and printed on success). A v1-shaped input
   — a bare records array, or a wrapped object without "schema": 2 — fails
   with one legible error: regenerate with the current skill.

2. Chunk seam:
       validate-bloat-output.py --chunk FILE [--manifest FILE]
   Validates one chunk result {"chunk": "<id>", "records": [...]} where it
   is produced. With --manifest (plan-chunks.py output), also cross-checks
   the slice: a sweep chunk's records may only name docs the chunk lists
   (and never POLICY); a policy chunk's result is exactly one POLICY record
   whose doc is the chunk's dir and whose files equal the chunk's file list.

3. Assembly:
       validate-bloat-output.py --assemble DIR --manifest FILE --out FILE
                                [--allow-partial]
   Reads DIR/<id>.json for every chunk in the manifest, seam-validates each,
   renumbers ids B1..Bn in manifest order, and writes the final wrapped v2
   report to --out. A missing or invalid chunk fails the assembly naming the
   chunk; --allow-partial (what CI passes, so one dead chunk cannot hold the
   report hostage) instead skips MISSING chunks with a stderr note and
   records them in the report's "unswept" list ({chunk, docs} entries —
   the loud gap the PR banner renders; the next run's resume sweeps them) —
   an invalid chunk still fails.

Exit status: 0 valid; 1 contract violation; 2 bad input/usage.
On success prints the authoritative summary (recomputed from the records).
"""

import argparse
import json
import os
import re
import sys

PASSAGE = {"CUT", "CONDENSE", "EXTRACT-AND-MOVE"}
DOCLEVEL = {"RETIRE-DOC", "MERGE-DOC", "DISTILL", "POLICY"}
VERDICTS = PASSAGE | DOCLEVEL
STATUSES = {"pending-implementation", "ready"}
REQUIRED = ("id", "doc", "location", "verdict", "evidence",
            "proposal", "status", "files")
SUMMARY_KEYS = ("cut", "condense", "extract_and_move",
                "retire_doc", "merge_doc", "distill", "policy")
LOCATION_RE = re.compile(r"^.+:[1-9]\d*$")
SPAN_RE = re.compile(r"^(\S+):([1-9]\d*)(?:-([1-9]\d*))?")

V1_ERROR = ('schema v1 report: regenerate with the current skill — the '
            'contract is now {"schema": 2, "records": [...], "summary": '
            '{...}} with no DISTILL payloads')


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
    elif verdict == "POLICY":
        if not nonempty_str(proposal):
            errs.append(f"{where}: POLICY requires proposal = the policy text")
    else:  # CUT / RETIRE-DOC / DISTILL
        if proposal is not None:
            errs.append(f"{where}: proposal must be null for {verdict}")


def check_files(where, verdict, files, errs):
    if verdict == "POLICY":
        ok = (isinstance(files, list) and len(files) > 0
              and all(nonempty_str(f) for f in files))
        if not ok:
            errs.append(f"{where}: POLICY requires files = a non-empty list of "
                        f"every covered path — a bulk record that cannot name "
                        f"its files is unfalsifiable")
    elif files is not None:
        errs.append(f"{where}: files must be null unless verdict is POLICY")


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
            if field == "payload":
                errs.append(f"{where}: unexpected field 'payload' — contract v2 "
                            f"removed DISTILL payloads (the doc-distiller "
                            f"authors them post-approval)")
            else:
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
        if "files" not in missing:
            check_files(where, verdict, r.get("files"), errs)

        if verdict == "DISTILL":
            if r.get("status") not in STATUSES:
                errs.append(f"{where}: DISTILL requires status in {sorted(STATUSES)}")
        elif r.get("status") is not None:
            errs.append(f"{where}: status must be null unless verdict is DISTILL")
    return errs


def check_unique_ids(records):
    errs, seen = [], {}
    for i, r in enumerate(records):
        if isinstance(r, dict) and nonempty_str(r.get("id")):
            rid = r["id"]
            if rid in seen:
                errs.append(f"record[{i}]: duplicate id {rid!r} "
                            f"(first at record[{seen[rid]}])")
            else:
                seen[rid] = i
    return errs


def validate_records(records):
    errs = []
    for i, r in enumerate(records):
        errs.extend(validate_record(i, r))
    errs.extend(check_unique_ids(records))
    return errs


def count_verdicts(records):
    counts = dict.fromkeys(SUMMARY_KEYS, 0)
    key = {"CUT": "cut", "CONDENSE": "condense",
           "EXTRACT-AND-MOVE": "extract_and_move", "RETIRE-DOC": "retire_doc",
           "MERGE-DOC": "merge_doc", "DISTILL": "distill", "POLICY": "policy"}
    for r in records:
        v = r.get("verdict") if isinstance(r, dict) else None
        if v in key:
            counts[key[v]] += 1
    return counts


def summary_errors(summary, counts):
    if summary is None:
        return []
    if (not isinstance(summary, dict)
            or not all(real_int(summary.get(k)) for k in SUMMARY_KEYS)):
        return [f"summary {summary} must have integer counts for {list(SUMMARY_KEYS)}"]
    if summary != counts:
        return [f"summary {summary} does not match record counts {counts}"]
    return []


def fail(errs):
    for e in errs:
        print(e, file=sys.stderr)
    print(f"\nFAILED: {len(errs)} contract violation(s)", file=sys.stderr)
    return 1


def ok(records):
    counts = count_verdicts(records)
    print(f"OK: {len(records)} record(s) valid")
    print(f"summary: {json.dumps(counts)}")
    return 0


def read_json(src):
    raw = sys.stdin.read() if src is None else open(src, encoding="utf-8").read()
    return json.loads(raw)


def chunk_doc_paths(chunk):
    """The doc paths a chunk covers: sweep doc list or policy files."""
    if chunk.get("kind") == "policy":
        return list(chunk.get("files", []))
    return [d.get("path") for d in chunk.get("docs", []) if isinstance(d, dict)]


def unswept_errors(unswept):
    """Shape-check a report's optional 'unswept' gap list."""
    if unswept is None:
        return []
    if not (isinstance(unswept, list) and all(
            isinstance(u, dict) and nonempty_str(u.get("chunk"))
            and isinstance(u.get("docs"), list)
            and all(isinstance(p, str) for p in u["docs"])
            for u in unswept)):
        return ["'unswept' must be a list of {chunk, docs} gap entries"]
    return []


def run_final(src):
    try:
        data = read_json(src)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if isinstance(data, list):
        return fail([V1_ERROR + " (got a bare records array)"])
    if not isinstance(data, dict):
        print("error: input must be a JSON object", file=sys.stderr)
        return 2
    if data.get("schema") != 2:
        return fail([V1_ERROR])
    if not isinstance(data.get("records"), list):
        print("error: report must carry a 'records' array", file=sys.stderr)
        return 2
    records = data["records"]
    errs = validate_records(records)
    errs.extend(summary_errors(data.get("summary"), count_verdicts(records)))
    errs.extend(unswept_errors(data.get("unswept")))
    return fail(errs) if errs else ok(records)


def load_manifest(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    chunks = data.get("chunks") if isinstance(data, dict) else None
    if not isinstance(chunks, list) or not all(
            isinstance(c, dict) and nonempty_str(c.get("id")) for c in chunks):
        raise ValueError(f"manifest {path}: expected {{'chunks': [{{'id': ...}}, ...]}}")
    return chunks


def chunk_shape_errors(data):
    if not (isinstance(data, dict) and set(data) == {"chunk", "records"}
            and nonempty_str(data.get("chunk"))
            and isinstance(data.get("records"), list)):
        return ['chunk result must be exactly {"chunk": "<id>", "records": [...]}']
    return []


def slice_errors(data, chunk):
    """Cross-check a chunk result against its manifest slice."""
    errs = []
    records = [r for r in data["records"] if isinstance(r, dict)]
    if chunk.get("kind") == "policy":
        if len(records) != 1 or records[0].get("verdict") != "POLICY":
            return [f"policy chunk {chunk['id']}: result must be exactly one "
                    f"POLICY record covering {chunk.get('dir')!r} — never a "
                    f"file-by-file walk"]
        r = records[0]
        if r.get("doc") != chunk.get("dir"):
            errs.append(f"policy chunk {chunk['id']}: record doc must be the "
                        f"covered dir {chunk.get('dir')!r}, got {r.get('doc')!r}")
        files = r.get("files")
        if isinstance(files, list) and sorted(files) != sorted(chunk.get("files", [])):
            errs.append(f"policy chunk {chunk['id']}: files must enumerate "
                        f"exactly the chunk's covered paths (provenance)")
    else:
        allowed = {d.get("path") for d in chunk.get("docs", [])
                   if isinstance(d, dict)}
        for i, r in enumerate(records):
            if r.get("verdict") == "POLICY":
                errs.append(f"record[{i}]: sweep chunks never emit POLICY")
            if r.get("doc") not in allowed:
                errs.append(f"record[{i}]: doc {r.get('doc')!r} is outside this "
                            f"chunk's slice")
    return errs


def validate_chunk_result(data, chunk):
    errs = chunk_shape_errors(data)
    if errs:
        return errs
    errs = validate_records(data["records"])
    if chunk is not None:
        if data["chunk"] != chunk["id"]:
            errs.append(f"result names chunk {data['chunk']!r} but was matched "
                        f"to {chunk['id']!r}")
        errs.extend(slice_errors(data, chunk))
    return errs


def run_chunk(path, manifest_path):
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    chunk = None
    if manifest_path:
        try:
            chunks = load_manifest(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if isinstance(data, dict) and nonempty_str(data.get("chunk")):
            chunk = next((c for c in chunks if c["id"] == data["chunk"]), None)
            if chunk is None:
                return fail([f"chunk {data['chunk']!r} is not in the manifest"])
    errs = validate_chunk_result(data, chunk)
    return fail(errs) if errs else ok(data["records"])


def run_assemble(dir_, manifest_path, out, allow_partial):
    try:
        chunks = load_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    errs, records, unswept = [], [], []
    for chunk in chunks:
        path = os.path.join(dir_, chunk["id"] + ".json")
        if not os.path.exists(path):
            if allow_partial:
                print(f"note: --allow-partial: skipping chunk {chunk['id']} "
                      f"(no result file)", file=sys.stderr)
                unswept.append({"chunk": chunk["id"],
                                "docs": chunk_doc_paths(chunk)})
                continue
            errs.append(f"chunk {chunk['id']}: no result file at {path} — "
                        f"partial assembly refused")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errs.append(f"chunk {chunk['id']}: unreadable result: {e}")
            continue
        chunk_errs = validate_chunk_result(data, chunk)
        if chunk_errs:
            errs.extend(f"chunk {chunk['id']}: {e}" for e in chunk_errs)
            continue
        records.extend(data["records"])
    if errs:
        return fail(errs)
    for n, r in enumerate(records, 1):
        r["id"] = f"B{n}"
    report = {"schema": 2, "records": records, "summary": count_verdicts(records)}
    if unswept:
        report["unswept"] = unswept
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return ok(records)


def main():
    ap = argparse.ArgumentParser(
        description="Validate detecting-doc-bloat output (final / seam / assembly).")
    ap.add_argument("file", nargs="?",
                    help="final wrapped v2 report (default: stdin)")
    ap.add_argument("--chunk", help="validate one chunk result file at the seam")
    ap.add_argument("--manifest",
                    help="plan-chunks.py manifest for slice cross-checks")
    ap.add_argument("--assemble", metavar="DIR",
                    help="assemble every manifest chunk's DIR/<id>.json into --out")
    ap.add_argument("--out", help="where --assemble writes the final report")
    ap.add_argument("--allow-partial", action="store_true",
                    help="--assemble only: skip missing chunks (CI never passes this)")
    args = ap.parse_args()

    if args.chunk and args.assemble:
        print("usage: --chunk and --assemble are mutually exclusive", file=sys.stderr)
        return 2
    if args.assemble:
        if not (args.manifest and args.out):
            print("usage: --assemble requires --manifest and --out", file=sys.stderr)
            return 2
        return run_assemble(args.assemble, args.manifest, args.out,
                            args.allow_partial)
    if args.chunk:
        if args.file:
            print("usage: --chunk takes no positional report", file=sys.stderr)
            return 2
        return run_chunk(args.chunk, args.manifest)
    if args.allow_partial or args.manifest or args.out:
        print("usage: --manifest/--out/--allow-partial apply only to "
              "--chunk/--assemble", file=sys.stderr)
        return 2
    return run_final(args.file)


if __name__ == "__main__":
    sys.exit(main())
