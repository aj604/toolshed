#!/usr/bin/env python3
"""Plan the doc-bloat distill lane's fan-out: report -> group manifest.

The apply-side twin of detecting-doc-bloat's plan-chunks.py (design:
docs/plans/2026-07-09-bloat-distill-lane-fanout-design.md). Selects the
distill lane's actionable records from a validated bloat report — the lane
mapping is imported from the co-located sync-gate.py, its one owner — and
groups them into bounded, independently dispatchable work orders:

- DISTILL ready records group by the artifact's directory (same-dir plans
  overwhelmingly land residue in the same target docs, so grouping them into
  one executor removes same-target merge conflicts by construction), packed
  greedily to distill.max_group_records (default 4).
- MERGE-DOC / RETIRE-DOC / POLICY records form one mechanical 'inline' group.
- DISTILL pending-implementation is never planned (the planner's exclusion is
  the headless lane's skip-with-a-note).

Group ids are content-addressed over member (record id, doc) pairs — stable
within a run; there is deliberately NO cross-run resume: a patch is a diff
against a moving base, so convergence is re-detection (an unapplied record's
artifact survives, the next sweep re-proposes it).

Usage:
    plan-distill.py --report FILE [--config PATH] [--out FILE]
    plan-distill.py --emit-prompt GID --manifest FILE   # dispatch prompt
    plan-distill.py --validate-result FILE --manifest FILE
    plan-distill.py --merge --manifest FILE --results-dir DIR
                    --patches-dir DIR [--repo DIR] --out FILE

--emit-prompt renders the full headless dispatch for one group — the record
ids (verdict + doc) verbatim as the entire approved subset, the report path,
one-commit-per-record, and the sidecar output path distill-results/<gid>.json
— so prompt templating lives here, unit-tested, never in workflow YAML.

--validate-result seam-validates one group sidecar {"group", "applied",
"skipped", "failed"}: names its group (and its filename), every group record
accounted for in exactly one array, skip/fail entries carry non-empty reasons.

--merge applies each group's git-format-patch series (one patch per record,
zipped against the sidecar's applied list) with `git am -3`, in manifest
order. A conflict whose only unmerged path is docs/decisions.md is resolved
by union (append-only log: keep both sides) and the merge continues; any
other conflict skips that record and continues. A missing/invalid sidecar or
a patch/result count mismatch drops the whole group. The summary
{"applied": [ids], "unapplied": [{"id", "reason", "stage"}]} goes to --out
(stage: "executor" = the sweep job reported it skipped/failed, "merge" = it
could not be landed here); a dropped record costs itself, never the lane, so
exit is 0 with gaps recorded loudly. Exit 2 only on structural bad input.

Config discovery: --config if given, else .github/doc-sync/audit-scope.json
under the cwd. Only the optional "distill" object is read (the rest is
plan-chunks.py's): {"max_group_records": 4, "max_groups": null}.
max_groups non-null is a hard run ceiling like chunking.max_chunks: planning
more groups than that exits 2 naming the count and the knob.
"""

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

DEFAULT_MAX_GROUP_RECORDS = 4


def die(msg):
    """Self-explaining bad-input exit (code 2)."""
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def load_sync_gate():
    """Import the co-located sync-gate.py — the lane mapping's one owner."""
    # No bytecode cache: a __pycache__/ appearing inside .github/doc-sync/
    # would be one careless `git add -A` away from a consumer's history.
    sys.dont_write_bytecode = True
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "sync-gate.py")
    spec = importlib.util.spec_from_file_location("sync_gate", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except (OSError, SyntaxError) as e:
        die(f"error: cannot load co-located sync-gate.py: {e}")
    return mod


def load_config(path):
    """Return the effective distill config; SystemExit(2) on malformed keys."""
    defaults = {"max_group_records": DEFAULT_MAX_GROUP_RECORDS,
                "max_groups": None}
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return defaults
    except OSError as e:
        die(f"error: cannot read config {path}: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"error: malformed config JSON in {path}: {e}")
    if not isinstance(data, dict):
        die(f"error: config {path} must be a JSON object")

    distill = data.get("distill", {})
    if not isinstance(distill, dict):
        die(f"error: config {path}: 'distill' must be an object")
    if "max_group_records" in distill:
        v = distill["max_group_records"]
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            die(f"error: config {path}: distill.max_group_records must be "
                f"an integer >= 1")
        defaults["max_group_records"] = v
    v = distill.get("max_groups")
    if v is not None:
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            die(f"error: config {path}: distill.max_groups must be null or "
                f"an integer >= 1")
        defaults["max_groups"] = v
    return defaults


def load_report(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read report {path}: {e}")
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        die(f"error: report {path} carries no records array")
    return records


def group_id(prefix, members):
    digest = hashlib.sha256("\n".join(
        f"{m['id']}\0{m['doc']}" for m in members).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10]}"


def member(record):
    return {"id": record["id"], "verdict": record["verdict"],
            "doc": record["doc"]}


def plan(records, cfg, in_lane):
    lane = [r for r in records if isinstance(r, dict) and in_lane(r, "distill")]
    inline = [member(r) for r in lane if r.get("verdict") != "DISTILL"]
    ready = [member(r) for r in lane if r.get("verdict") == "DISTILL"]

    groups = []
    if inline:
        groups.append({"id": group_id("i", inline), "kind": "inline",
                       "records": inline})
    by_dir = {}
    for m in ready:
        by_dir.setdefault(os.path.dirname(m["doc"]), []).append(m)
    for d in sorted(by_dir):
        pending = by_dir[d]
        for i in range(0, len(pending), cfg["max_group_records"]):
            pack = pending[i:i + cfg["max_group_records"]]
            groups.append({"id": group_id("g", pack), "kind": "distill",
                           "records": pack})
    return len(lane), groups


DISPATCH_PROMPT = """\
You are a headless apply executor. Invoke the doc-lifecycle:fixing-doc-bloat
skill and treat EXACTLY the record IDs below as the human-approved subset of
the report at {report} — this list is your entire mandate; apply nothing
else, and never re-audit or widen scope.

Group {id}:
{record_lines}

Apply each record per the skill's routing table (DISTILL records dispatch the
doc-lifecycle:doc-distiller agent; it stages, you commit). Make exactly one
commit per applied record, in the order listed, message
"docs: bloat distill <id> — <doc>". A record you cannot apply is skipped or
failed with a stated reason — never a stopper for its siblings.

Then write the group result object {{"group": "{id}", "applied": [ids],
"skipped": [{{"id": ..., "reason": ...}}], "failed": [{{"id": ...,
"reason": ...}}]}} — every listed id in exactly one array — to
distill-results/{id}.json. Done means the per-record commits plus exactly
that file; then stop. Never push, never open a PR, never touch records or
docs outside this list; merge, retries, and the draft PR belong to the
workflow.
"""


def emit_prompt(chunk, report):
    return DISPATCH_PROMPT.format(
        id=chunk["id"], report=report,
        record_lines="\n".join(f"  - {m['id']} ({m['verdict']}) {m['doc']}"
                               for m in chunk["records"]))


def load_manifest(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read manifest {path}: {e}")


def find_group(man, gid):
    for g in man.get("groups", []):
        if g.get("id") == gid:
            return g
    die(f"error: group {gid} not found in manifest")


def check_result(path, man):
    """Return (sidecar, error). error is a string; sidecar is None on error."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"unreadable result: {e}"
    if not isinstance(data, dict):
        return None, "result is not an object"
    gid = data.get("group")
    stem = os.path.splitext(os.path.basename(path))[0]
    if gid != stem:
        return None, f"result names group {gid!r} but the file is {stem!r}"
    group = next((g for g in man.get("groups", []) if g.get("id") == gid),
                 None)
    if group is None:
        return None, f"group {gid!r} not in manifest"

    applied = data.get("applied")
    if not (isinstance(applied, list)
            and all(isinstance(i, str) for i in applied)):
        return None, "'applied' must be a list of record id strings"
    noted = []
    for key in ("skipped", "failed"):
        val = data.get(key)
        if not isinstance(val, list):
            return None, f"'{key}' must be a list"
        for entry in val:
            if not (isinstance(entry, dict)
                    and isinstance(entry.get("id"), str)
                    and isinstance(entry.get("reason"), str)
                    and entry["reason"].strip()):
                return None, (f"every '{key}' entry needs an id and a "
                              f"non-empty reason")
            noted.append(entry["id"])
    seen = applied + noted
    expected = [m["id"] for m in group["records"]]
    if sorted(seen) != sorted(set(seen)):
        return None, "a record id appears in more than one array"
    if set(seen) != set(expected):
        return None, (f"records accounted for {sorted(seen)} != group's "
                      f"{sorted(expected)} — every id in exactly one array")
    return data, None


CONFLICT_RE = re.compile(r"^(<{7}( .*)?|\|{7}( .*)?|={7}|>{7}( .*)?)$")


def resolve_union(path):
    """Resolve conflict markers by keeping both sides (append-only log)."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    out, in_base = [], False
    for line in lines:
        stripped = line.rstrip("\n")
        if CONFLICT_RE.match(stripped):
            in_base = stripped.startswith("|" * 7)
            if stripped.startswith("=" * 7) or stripped.startswith(">" * 7):
                in_base = False
            continue
        if in_base:
            continue
        out.append(line)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


def run_git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=False)


def merge_patch(repo, patch):
    """Apply one patch; True if landed. Union-resolves a decisions.md-only
    conflict; anything else aborts the patch."""
    if run_git(repo, "am", "-3", patch).returncode == 0:
        return True, None
    unmerged = [p for p in run_git(
        repo, "diff", "--name-only", "--diff-filter=U"
    ).stdout.splitlines() if p]
    if unmerged == ["docs/decisions.md"]:
        resolve_union(os.path.join(repo, "docs", "decisions.md"))
        run_git(repo, "add", "docs/decisions.md")
        if run_git(repo, "am", "--continue").returncode == 0:
            return True, None
    run_git(repo, "am", "--abort")
    return False, f"merge conflict: {', '.join(unmerged) or 'apply failed'}"


def main():
    ap = argparse.ArgumentParser(
        description="Plan the doc-bloat distill lane's fan-out.")
    ap.add_argument("--report", help="validated bloat report JSON")
    ap.add_argument("--config", help="scope config JSON (default: "
                    ".github/doc-sync/audit-scope.json under the cwd)")
    ap.add_argument("--out", help="write the manifest / merge summary here")
    ap.add_argument("--manifest", help="manifest JSON for --emit-prompt/"
                    "--validate-result/--merge")
    ap.add_argument("--emit-prompt", metavar="GID",
                    help="print the dispatch prompt for one manifest group")
    ap.add_argument("--validate-result", metavar="FILE",
                    help="seam-validate one group result sidecar")
    ap.add_argument("--merge", action="store_true",
                    help="apply group patch series onto --repo")
    ap.add_argument("--results-dir", help="group result sidecar dir (merge)")
    ap.add_argument("--patches-dir", help="group patch series dir (merge)")
    ap.add_argument("--repo", default=os.getcwd(),
                    help="git tree to merge onto (default: cwd)")
    args = ap.parse_args()

    if args.emit_prompt:
        if not args.manifest:
            die("error: --emit-prompt requires --manifest")
        man = load_manifest(args.manifest)
        print(emit_prompt(find_group(man, args.emit_prompt),
                          man.get("report", "bloat-report.json")), end="")
        return 0

    if args.validate_result:
        if not args.manifest:
            die("error: --validate-result requires --manifest")
        man = load_manifest(args.manifest)
        _, err = check_result(args.validate_result, man)
        if err:
            die(f"error: {args.validate_result}: {err}")
        print(f"{args.validate_result}: valid group result")
        return 0

    if args.merge:
        for req in ("manifest", "results_dir", "patches_dir", "out"):
            if not getattr(args, req):
                die(f"error: --merge requires --{req.replace('_', '-')}")
        man = load_manifest(args.manifest)
        applied, unapplied = merge_lane(man, args.results_dir,
                                        args.patches_dir, args.repo)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"applied": applied, "unapplied": unapplied}, f,
                      indent=2)
            f.write("\n")
        print(f"merged {len(applied)} record(s); {len(unapplied)} unapplied",
              file=sys.stderr)
        return 0

    if not args.report:
        die("error: --report is required to plan")
    cfg = load_config(args.config or os.path.join(
        os.getcwd(), ".github", "doc-sync", "audit-scope.json"))
    in_lane = load_sync_gate().in_lane
    nlane, groups = plan(load_report(args.report), cfg, in_lane)

    if cfg["max_groups"] is not None and len(groups) > cfg["max_groups"]:
        die(f"error: planned {len(groups)} groups, over "
            f"distill.max_groups={cfg['max_groups']} — raise or remove the "
            f"ceiling to run this lane")

    ndistill = sum(1 for g in groups if g["kind"] == "distill")
    print(f"{nlane} record(s) in distill lane -> {len(groups)} group(s) "
          f"({ndistill} distill + {len(groups) - ndistill} inline); "
          f"projected invocations: {len(groups)}", file=sys.stderr)

    text = json.dumps({"schema": 1,
                       "report": args.report,
                       "groups": groups,
                       "pending": [g["id"] for g in groups]}, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


ID_TOKEN_RE = re.compile(r"[A-Za-z]\w*")


def map_patches_to_ids(patches, applied):
    """Pair each patch with its record id.

    The executor is told to commit in the listed order, but the sidecar's
    `applied` array order is unvalidated — mislabeling which record a
    conflicting patch belongs to would misdirect the PR's not-landed banner.
    So prefer the patch's own Subject line: if every patch's subject names
    exactly one distinct applied id, that mapping wins; otherwise fall back
    to sidecar order.
    """
    subject_ids = []
    for patch in patches:
        found = set()
        try:
            with open(patch, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("Subject:"):
                        found = set(ID_TOKEN_RE.findall(line)) & set(applied)
                        break
        except OSError:
            pass
        if len(found) != 1:
            return list(zip(patches, applied))
        subject_ids.append(found.pop())
    if sorted(subject_ids) != sorted(applied):
        return list(zip(patches, applied))
    return list(zip(patches, subject_ids))


def merge_lane(man, results_dir, patches_dir, repo):
    """Apply every group's patch series; return (applied, unapplied)."""
    applied, unapplied = [], []
    for group in man.get("groups", []):
        gid = group["id"]
        record_ids = [m["id"] for m in group["records"]]
        sidecar, err = check_result(
            os.path.join(results_dir, f"{gid}.json"), man)
        if sidecar is None:
            unapplied.extend({"id": i,
                              "reason": f"no valid group result ({err})",
                              "stage": "merge"} for i in record_ids)
            continue
        for key in ("skipped", "failed"):
            unapplied.extend({"id": e["id"],
                              "reason": f"{key} by executor: {e['reason']}",
                              "stage": "executor"} for e in sidecar[key])
        if not sidecar["applied"]:
            continue
        patches = sorted(glob.glob(os.path.join(patches_dir, gid, "*.patch")))
        if len(patches) != len(sidecar["applied"]):
            unapplied.extend(
                {"id": i,
                 "reason": (f"patch/result mismatch ({len(patches)} patches "
                            f"for {len(sidecar['applied'])} applied records)"),
                 "stage": "merge"} for i in sidecar["applied"])
            continue
        for patch, rid in map_patches_to_ids(patches, sidecar["applied"]):
            ok, reason = merge_patch(repo, patch)
            if ok:
                applied.append(rid)
            else:
                unapplied.append({"id": rid, "reason": reason,
                                  "stage": "merge"})
    return applied, unapplied


if __name__ == "__main__":
    sys.exit(main())
