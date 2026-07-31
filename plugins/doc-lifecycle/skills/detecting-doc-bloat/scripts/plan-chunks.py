#!/usr/bin/env python3
"""Plan doc-bloat sweep chunks: inventory -> chunk manifest.

Absorbs list-docs.py: enumerates the in-scope docs (git ls-files under
--root, else a filesystem walk; default filter *.md; config exclude/include
globs, whitelist wins), then groups them into bounded chunks a single
detection invocation can hold.

Every doc gets a deterministic doc-kind hint (narrative if it opens with
'> As of' — the file's first line, or the first non-blank line under a
leading title; planning if a 'plans' or 'specs' path segment contains it;
else living — a hint the model may override only with stated evidence), is
grouped by (directory, hint), packed under the caps (chunking.max_docs,
default 8; chunking.max_lines, default 1200), and consecutive underfull
chunks with the same hint are coalesced while the caps hold. A single doc
larger than max_lines gets its own chunk.

`policy_scope` is retired, with the `POLICY` verdict it fed: bulk retirement
is now an enumerable-scope `RETIRE-DOC` verdict, whose members the engine
expands from the corpus-wide context index (`bloat.enumerate_scope`,
`bloat.SCOPE_VERDICTS`) rather than from a hand-declared directory. A config
still declaring the key plans normally — its docs are swept like any other,
and the run says so on stderr — because a consumer's audit-scope.json is
never rewritten for them.

Chunk ids are content-addressed (sha256 over member (path, content-sha256)
pairs, the content hash computed during the same read that counts lines), so
re-planning an unchanged tree yields the same ids — which is what makes
--results-dir resume work: a chunk whose <id>.json result already exists,
parses, names the chunk, and passes the same public verdict shape check as
assembly stays in "chunks" but leaves "pending" — an edited doc changes its
chunk's id and an invalid leftover never counts, so stale or invalid work is
scheduled again.

Every chunk carries a "turns" budget for the model invocation that will sweep
it: 12 + 2 per doc (4 per planning doc) + 1 per full 600 lines, clamped to
[20, 40]. A dispatcher passes it to --max-turns; retry escalation above it is
the dispatcher's job, not the planner's.

Usage:
    plan-chunks.py [--config PATH] [--root DIR] [--out FILE] [--results-dir DIR]
    plan-chunks.py --emit-prompt ID --manifest FILE --results-dir DIR  # dispatch prompt
    plan-chunks.py --emit-readonly-prompt ID --manifest FILE  # return-only prompt
    plan-chunks.py --emit-turns ID --manifest FILE     # print turn budget

--emit-prompt renders the full dispatch prompt for one chunk — the doc list
verbatim, where the unit digests a verdict names come from, the output path,
and the definition of done — so prompt templating lives here, unit-tested,
never in a caller's YAML or prose. The output path is always absolute:
`--results-dir`'s value, resolved with `os.path.abspath` and joined with the
chunk id, so the rendered prompt tells the executor to write outside the work
tree (the confinement rule every other audit artifact already follows — see
detecting-doc-bloat/SKILL.md) rather than the bare `chunks/<id>.json` a
work-tree-rooted executor would resolve into the tree itself. The executor is
handed its slice; it never opens the manifest.

`--emit-readonly-prompt` is the scheduled cadence's stricter sibling: it runs
the public `segment` contract before the model turn, embeds those trusted unit
identities, names the pinned skill/contract references to read, and requires the
chunk object as the Task's final response. It names no output path and requires
no command or mutation tool; the trusted scheduler owns extraction and files.

All three emission modes accept a manifest from either
planner: this script's own (`{"docs": [{"path","lines","hint"}, ...]}` per
chunk) or the engine's `bloat-plan` (`{"documents": [<path>, ...]}`, no
per-doc lines/hint and no per-chunk `turns`). Both prompt modes render
whichever fields a chunk's dialect actually carries; `--emit-turns` returns
the stamped `turns` when present, the floor for a pre-`turns` manifest of
this script's own dialect (`docs` present), and fails loudly (exit 2) for a
`bloat-plan` manifest, which was never sized by this script's turn formula.

Output (plan mode): manifest JSON {"schema": 1, "index_digest": "...",
"engine_plan": {...}, "chunks": [...], "pending": [ids]} to --out (stdout if
omitted). A registered repository carries the full public `bloat-plan`
artifact; its exact ids and membership drive the decorated scheduler chunks.
Without that authentic plan, completion assembly refuses. A scheduler chunk is
{"id", "turns": N, "docs": [{"path", "lines", "hint"}]}. The run-surface
report (doc count, chunk count, projected invocations, resume skips) always
prints to stderr.

Config discovery: --config if given, else <root>/.doc-lifecycle/audit-scope.json.
All keys optional; an absent file is pure defaults:
    exclude / include: glob lists ('*' stays within a path segment, '**'
        crosses segments; include re-adds anything it matches — whitelist wins)
    chunking: {"max_docs": 8, "max_lines": 1200, "max_chunks": null}
A retired key (`policy_scope`) is noted on stderr and otherwise ignored,
whatever shape it holds — see above.
max_chunks non-null is a hard run ceiling: planning more chunks than that
exits 2 naming the count and the knob (default off — big first runs are
legitimate; the protections are structural).

Exit status: 0 on success; 2 on malformed config or a tripped max_chunks.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

DEFAULT_MAX_DOCS = 8
DEFAULT_MAX_LINES = 1200
ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "engine",
))
VERDICT_VALIDATOR = os.path.join(
    os.path.dirname(__file__), "validate-bloat-output.py",
)

# Keys a config may still carry from the legacy contract. Noted, never read:
# `policy_scope` declared the directories one POLICY record covered, and both
# retired together when bulk retirement became an enumerable engine scope.
RETIRED_KEYS = ("policy_scope",)
RETIRED_NOTE = {
    "policy_scope": "declared directories swept as one POLICY record; POLICY "
                    "is retired — bulk retirement is now a RETIRE-DOC verdict "
                    "over an enumerable scope the engine expands from the "
                    "index. These docs are planned like any other.",
}


def die(msg):
    """Self-explaining bad-input exit (code 2)."""
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def glob_to_regex(glob):
    """Translate a glob into an anchored regex over POSIX paths.

    '**' matches across segments (including '/'); '*' matches within a segment
    (not '/'); '?' matches one non-'/' char. Everything else is literal.
    fnmatch is avoided deliberately: it treats '**' as two '*' and lets '*'
    cross '/', which is wrong for path-segment semantics.
    """
    i, n = 0, len(glob)
    out = ["(?s:"]
    while i < n:
        c = glob[i]
        if c == "*":
            if i + 1 < n and glob[i + 1] == "*":
                # Consume the run of '*' as a single '**'.
                while i < n and glob[i] == "*":
                    i += 1
                out.append(".*")
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    out.append(")\\Z")
    return re.compile("".join(out))


def matches_any(path, patterns):
    return any(p.match(path) for p in patterns)


def load_config(path):
    """Return the effective config dict; SystemExit(2) on any malformed key.

    A retired key is collected under "retired" and never validated: the knob
    is dead, so no shape of it may fail a run that would otherwise plan.
    """
    defaults = {"exclude": [], "include": [], "retired": [],
                "max_docs": DEFAULT_MAX_DOCS, "max_lines": DEFAULT_MAX_LINES,
                "max_chunks": None}
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
        die(f"error: config {path} must be a JSON object, got {type(data).__name__}")

    for key in ("exclude", "include"):
        val = data.get(key, [])
        if not (isinstance(val, list) and all(isinstance(g, str) for g in val)):
            die(f"error: config {path}: '{key}' must be a list of strings")
        defaults[key] = val
    defaults["retired"] = [k for k in RETIRED_KEYS if k in data]

    chunking = data.get("chunking", {})
    if not isinstance(chunking, dict):
        die(f"error: config {path}: 'chunking' must be an object")
    for key in ("max_docs", "max_lines"):
        if key in chunking:
            v = chunking[key]
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
                die(f"error: config {path}: chunking.{key} must be an integer >= 1")
            defaults[key] = v
    v = chunking.get("max_chunks")
    if v is not None:
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            die(f"error: config {path}: chunking.max_chunks must be null "
                     f"or an integer >= 1")
        defaults["max_chunks"] = v

    defaults["exclude"] = [glob_to_regex(g) for g in defaults["exclude"]]
    defaults["include"] = [glob_to_regex(g) for g in defaults["include"]]
    return defaults


def candidates(root):
    """Repo-relative POSIX paths under root: git ls-files, else a tree walk."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
        return [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return walk(root)


def walk(root):
    paths = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            paths.append(rel.replace(os.sep, "/"))
    return paths


def select(paths, exclude, include):
    result = []
    for p in paths:
        keep = p.lower().endswith(".md")
        if keep and matches_any(p, exclude):
            keep = False
        if matches_any(p, include):
            keep = True
        if keep:
            result.append(p)
    return sorted(result)


def read_doc(full):
    """(line count, content sha256) in one read. Unreadable => (0, '')."""
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            text = f.read()
        return len(text.splitlines()), hashlib.sha256(
            text.encode("utf-8", "replace")).hexdigest()
    except OSError:
        return 0, ""


def doc_hint(root, path):
    """Deterministic doc-kind hint; the '> As of' anchor wins over location.

    growing-docs' template puts the anchor on the first line under the title;
    older narrative docs carry it as the file's literal first line. Accept
    both: the anchor counts on line 1, or as the first non-blank line after
    a leading '#' title. Any other first line means not-narrative.
    """
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as f:
            head = [f.readline().lstrip() for _ in range(6)]
    except OSError:
        head = []
    anchored = bool(head) and head[0].startswith("> As of")
    if not anchored and head and head[0].startswith("#"):
        for line in head[1:]:
            if not line.strip():
                continue
            anchored = line.startswith("> As of")
            break
    if anchored:
        return "narrative"
    if any(seg in ("plans", "specs") for seg in path.split("/")[:-1]):
        return "planning"
    return "living"


def chunk_id(prefix, members):
    """Content-address a chunk by its members' (path, content-sha) pairs."""
    digest = hashlib.sha256("\n".join(
        f"{path}\0{sha}" for path, sha in members).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10]}"


TURNS_BASE = 12
TURNS_PER_DOC = {"planning": 4}          # every other hint costs 2
TURNS_PER_LINES = 600
TURNS_FLOOR, TURNS_CEIL = 20, 40


def turn_budget(docs):
    """Deterministic per-chunk model-invocation budget."""
    turns = TURNS_BASE
    turns += sum(TURNS_PER_DOC.get(d["hint"], 2) for d in docs)
    turns += sum(d["lines"] for d in docs) // TURNS_PER_LINES
    return max(TURNS_FLOOR, min(TURNS_CEIL, turns))


def pack(docs, max_docs, max_lines):
    """Greedy pack of one (dir, hint) group; docs pre-sorted by path."""
    chunks, cur, cur_lines = [], [], 0
    for d in docs:
        if cur and (len(cur) + 1 > max_docs or cur_lines + d["lines"] > max_lines):
            chunks.append(cur)
            cur, cur_lines = [], 0
        cur.append(d)
        cur_lines += d["lines"]
    if cur:
        chunks.append(cur)
    return chunks


def coalesce(chunks, max_docs, max_lines):
    """Merge consecutive underfull chunks sharing a hint while the caps hold."""
    merged = []
    for c in chunks:
        if merged:
            prev = merged[-1]
            if (prev[0]["hint"] == c[0]["hint"]
                    and len(prev) + len(c) <= max_docs
                    and sum(d["lines"] for d in prev + c) <= max_lines):
                merged[-1] = prev + c
                continue
        merged.append(c)
    return merged


def plan(root, cfg):
    docs = select(candidates(root), cfg["exclude"], cfg["include"])
    sized, shas = [], {}
    for p in docs:
        lines, sha = read_doc(os.path.join(root, p))
        sized.append({"path": p, "lines": lines})
        shas[p] = sha

    for d in sized:
        d["hint"] = doc_hint(root, d["path"])

    chunks = []
    groups = {}
    for d in sized:
        groups.setdefault((os.path.dirname(d["path"]), d["hint"]), []).append(d)
    packed = []
    for key in sorted(groups):
        packed.extend(pack(sorted(groups[key], key=lambda d: d["path"]),
                           cfg["max_docs"], cfg["max_lines"]))
    packed.sort(key=lambda c: c[0]["path"])
    for c in coalesce(packed, cfg["max_docs"], cfg["max_lines"]):
        chunks.append({"id": chunk_id("c", [(d["path"], shas[d["path"]])
                                            for d in c]),
                       "turns": turn_budget(c), "docs": c})
    return len(sized), chunks


def current_engine_plan(root, max_documents):
    """The audit engine's authentic chunk plan, or None if unavailable.

    A registered scheduler run dispatches the exact chunk identities and
    membership emitted by the public engine planner.  The scheduler adds only
    prompt metadata; assembly preserves the engine artifact byte-for-value and
    the audit independently re-derives it from the current index.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = (ENGINE + os.pathsep + env["PYTHONPATH"]
                         if env.get("PYTHONPATH") else ENGINE)
    result = subprocess.run(
        [sys.executable, "-m", "doclifecycle", "bloat-plan", "--repo", root,
         "--max-documents", str(max_documents)],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if (not isinstance(payload, dict) or payload.get("status") != "ok"
            or not isinstance(payload.get("chunks"), list)
            or not isinstance(payload.get("digest"), str)):
        return None
    return payload


def dispatch_chunks(root, engine_plan):
    """Decorate engine chunks with scheduler-only prompt and turn metadata."""
    chunks = []
    for chunk in engine_plan["chunks"]:
        docs = []
        for path in chunk["documents"]:
            lines, _digest = read_doc(os.path.join(root, path))
            docs.append({"path": path, "lines": lines,
                         "hint": doc_hint(root, path)})
        chunks.append({
            "id": chunk["id"], "turns": turn_budget(docs), "docs": docs,
        })
    return chunks


SWEEP_PROMPT = """\
You are a chunk executor. Invoke the doc-lifecycle:detecting-doc-bloat
skill for the verdict rules and output contract, then audit exactly the docs
listed below — no others. This list is your entire scope; do not enumerate or
open anything outside it.

Chunk {id}:
{doc_lines}

The kind hints are the planner's; override one only with stated evidence, per
the skill. Every verdict about one document names the assertion units it
covers: read them with `python3 -m doclifecycle segment --repo . --path
<path>` and copy the unit digests verbatim — never invent, abbreviate, or
paraphrase one. Write the chunk result object
{{"chunk": "{id}", "verdicts": [...]}} to {out_path} — an empty verdicts
array if nothing is bloated. That path is outside the work tree; do not
write it, or anything else, into the repository. Done means exactly that
file, in the chunk-result shape the skill's contract defines; then stop.
Orchestration, retries, and assembly belong to whoever dispatched you.
"""

READ_ONLY_SWEEP_PROMPT = """\
You are a read-only chunk executor. Use only Read, Grep, and Glob. Never run a
command and never write, edit, stage, or delete a file. Read the following
pinned rule sources before judging the chunk:
  - {skill_path}
  - {contract_path}
  - {lenses_path}
  - {planning_path}

Audit exactly the documents listed below and no others. This list is your
entire document scope; do not enumerate or open documents outside it.

Chunk {id}:
{doc_lines}

The kind hints are the planner's; override one only with stated evidence, per
the skill. The trusted segmentation evidence below was produced before this
model turn by the public engine. Use its digest values verbatim for verdict
`units`; never invent, abbreviate, or paraphrase an identity.

{segmentation}

Return exactly one JSON object as your final Task response, with no Markdown
fence or surrounding prose: {{"chunk": "{id}", "verdicts": [...]}}. Return
an empty `verdicts` array when nothing in this chunk is bloated. Do not author
completion evidence, retry, or inspect orchestration state; the trusted caller
owns validation, retries, and assembly.
"""


def usable_result(results_dir, cid, manifest_path):
    """True only for a parseable *current-shape* result that names this chunk.

    An invalid file surviving a failed CI retry must not mask the chunk as
    done — and neither must a legacy one. Chunk ids are content-addressed, so
    an unchanged sweep keeps its id across the `records` -> `verdicts` schema
    migration: a stale `{"chunk": id, "records": [...]}` file matched on
    `chunk` alone, dropped the chunk from `pending`, and was then refused by
    the assembler for carrying no `verdicts` — a resume that could not
    redispatch without someone deleting the cached file by hand.
    """
    path = os.path.join(results_dir, cid + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    shaped = (isinstance(data, dict) and data.get("chunk") == cid
              and isinstance(data.get("verdicts"), list))
    if not shaped:
        return False
    checked = subprocess.run(
        [sys.executable, VERDICT_VALIDATOR, "--chunk", path,
         "--manifest", manifest_path],
        capture_output=True, text=True,
    )
    return checked.returncode == 0


def load_manifest(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read manifest {path}: {e}")


def find_chunk(man, cid):
    for c in man.get("chunks", []):
        if c.get("id") == cid:
            return c
    die(f"error: chunk {cid} not found in manifest")


def chunk_doc_lines(chunk):
    """Render each document's dispatch-prompt line, for either planner's manifest.

    This script's own manifest carries "docs": [{"path", "lines", "hint"}];
    the engine's `bloat-plan` carries "documents": [<path>, ...] — a bare
    path, no per-doc lines or hint, because bloat-plan sizes chunks by
    assertion-unit count, not lines, and does not hint doc-kind at all.
    validate-bloat-output.py's chunk_doc_paths() reads the same two dialects
    for the same reason: both are legitimate work orders for this seam, and
    reading only one would silently narrow the rendered scope. Render
    whichever fields the chunk actually has rather than assume the first
    sender's shape.
    """
    docs = chunk.get("docs")
    if isinstance(docs, list):
        return [f"  - {d['path']} ({d['lines']} lines, hint: {d['hint']})"
                for d in docs]
    documents = chunk.get("documents")
    if isinstance(documents, list):
        return [f"  - {p}" for p in documents]
    die(f"error: chunk {chunk.get('id')!r} carries neither 'docs' nor "
        "'documents' — not a recognized chunk-manifest dialect")


def outside_the_work_tree(results_dir, root):
    """Whether `results_dir` really lies outside the repository at `root`.

    `os.path.abspath` makes a path absolute, which is not the same as making
    it external: a `--results-dir` under `--root` (the `chunks` resume
    directory, say) absolutizes happily and stays in the worktree. The
    rendered prompt then *states* the path is outside and tells the executor
    not to write into the repository — so the one claim the executor is given
    no way to check would be false, and its result lands as an unaccounted
    repository change the applier refuses.
    """
    results = os.path.realpath(results_dir)
    repo = os.path.realpath(root)
    return os.path.commonpath([results, repo]) != repo


def emit_prompt(chunk, results_dir):
    out_path = os.path.join(os.path.abspath(results_dir), chunk["id"] + ".json")
    return SWEEP_PROMPT.format(
        id=chunk["id"],
        doc_lines="\n".join(chunk_doc_lines(chunk)),
        out_path=out_path)


def segmentation_evidence(root, chunk):
    """Public-engine segment artifacts rendered before a read-only model turn."""
    env = dict(os.environ)
    env["PYTHONPATH"] = (ENGINE + os.pathsep + env["PYTHONPATH"]
                         if env.get("PYTHONPATH") else ENGINE)
    evidence = []
    docs = chunk.get("docs")
    paths = ([doc["path"] for doc in docs] if isinstance(docs, list)
             else chunk.get("documents"))
    if not isinstance(paths, list):
        die(f"error: chunk {chunk.get('id')!r} carries no recognized docs")
    for path in paths:
        result = subprocess.run(
            [sys.executable, "-m", "doclifecycle", "segment", "--repo", root,
             "--path", path],
            capture_output=True, text=True, env=env,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            die(f"error: cannot render trusted segmentation for {path}: "
                f"{detail or 'segment failed'}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            die(f"error: segment returned malformed JSON for {path}: {exc}")
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            die(f"error: segment returned no usable evidence for {path}")
        evidence.append(payload)
    return evidence


def emit_readonly_prompt(chunk, root):
    skill_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return READ_ONLY_SWEEP_PROMPT.format(
        id=chunk["id"],
        doc_lines="\n".join(chunk_doc_lines(chunk)),
        skill_path=os.path.join(skill_dir, "SKILL.md"),
        contract_path=os.path.join(skill_dir, "output-contract.md"),
        lenses_path=os.path.join(skill_dir, "references", "verdict-lenses.md"),
        planning_path=os.path.join(
            skill_dir, "references", "planning-artifacts.md",
        ),
        segmentation=json.dumps(
            segmentation_evidence(root, chunk), indent=2, sort_keys=True,
        ),
    )


def emit_turns(chunk):
    """This chunk's model-invocation turn budget, for either planner's manifest.

    This script's own manifest stamps "turns" on every chunk it plans; a
    v0.7.0 manifest of that same dialect ("docs" present) predates the field,
    and the floor is the safe default there. The engine's `bloat-plan`
    manifest ("documents", no "docs") never carries "turns" at all: it sizes
    chunks by assertion-unit count, an axis this script's per-doc
    lines/hint formula (turn_budget(), above) was never fit to, so guessing
    the floor for it would be silent, not safe. Fail loudly instead.
    """
    if "turns" in chunk:
        return chunk["turns"]
    if isinstance(chunk.get("docs"), list):
        # v0.7.0 manifests of this script's own dialect predate 'turns'.
        return TURNS_FLOOR
    die(f"error: chunk {chunk.get('id')!r} carries no 'turns' budget and is "
        "not this script's own manifest dialect (no 'docs') — it looks like "
        "an engine bloat-plan manifest, which this script's turn formula was "
        "never fit to (bloat-plan sizes chunks by unit_count, not lines); "
        "pass --max-turns explicitly for a bloat-plan-dispatched chunk")


def main():
    ap = argparse.ArgumentParser(description="Plan doc-bloat sweep chunks.")
    ap.add_argument("--config", help="scope config JSON (default: "
                    "<root>/.doc-lifecycle/audit-scope.json)")
    ap.add_argument("--root", default=os.getcwd(),
                    help="repo root to enumerate (default: cwd)")
    ap.add_argument("--out", help="write the manifest here (default: stdout)")
    ap.add_argument("--results-dir", help="in plan mode: existing chunk-result "
                    "dir; chunks with a <id>.json there stay in 'chunks' but "
                    "leave 'pending'. With --emit-prompt: required — the "
                    "out-of-work-tree dir the rendered prompt tells the "
                    "executor to write its result into")
    dispatch = ap.add_mutually_exclusive_group()
    dispatch.add_argument("--emit-prompt", metavar="ID",
                    help="print the dispatch prompt for one manifest chunk "
                    "(requires --results-dir)")
    dispatch.add_argument("--emit-readonly-prompt", metavar="ID",
                    help="print a return-only prompt with trusted segmentation "
                    "evidence for a Read/Grep/Glob worker")
    dispatch.add_argument("--emit-turns", metavar="ID",
                    help="print the turn budget for one manifest chunk")
    ap.add_argument("--manifest", help="manifest JSON for --emit-prompt/"
                    "--emit-turns")
    args = ap.parse_args()

    if args.emit_prompt or args.emit_readonly_prompt or args.emit_turns:
        if not args.manifest:
            die("error: prompt/turn emission requires --manifest")
        man = load_manifest(args.manifest)
        chunk = find_chunk(
            man, args.emit_prompt or args.emit_readonly_prompt or args.emit_turns,
        )
        if args.emit_prompt:
            if not args.results_dir:
                die("error: --emit-prompt requires --results-dir — the "
                    "out-of-work-tree directory the rendered prompt tells "
                    "the executor to write its result into")
            if not outside_the_work_tree(args.results_dir, args.root):
                die(f"error: --results-dir {args.results_dir} is inside the "
                    f"repository at {args.root} — the rendered prompt tells "
                    f"the executor that path is outside the work tree and to "
                    f"write nothing into the repository, so a contained "
                    f"directory makes that instruction false and leaves an "
                    f"unaccounted change the applier refuses. Pass a path "
                    f"outside the repository (${{TMPDIR:-/tmp}}/...)")
            print(emit_prompt(chunk, args.results_dir), end="")
        elif args.emit_readonly_prompt:
            print(emit_readonly_prompt(chunk, args.root), end="")
        else:
            print(emit_turns(chunk))
        return 0

    config = args.config or os.path.join(
        args.root, ".doc-lifecycle", "audit-scope.json")
    cfg = load_config(config)
    engine_plan = current_engine_plan(args.root, cfg["max_docs"])
    if engine_plan is None:
        ndocs, chunks = plan(args.root, cfg)
    else:
        chunks = dispatch_chunks(args.root, engine_plan)
        ndocs = sum(len(chunk["documents"])
                    for chunk in engine_plan["chunks"])

    for key in cfg["retired"]:
        print(f"note: config {config} declares {key!r}, a retired key — "
              f"{RETIRED_NOTE[key]}", file=sys.stderr)

    if cfg["max_chunks"] is not None and len(chunks) > cfg["max_chunks"]:
        die(f"error: planned {len(chunks)} chunks, over "
                 f"chunking.max_chunks={cfg['max_chunks']} in {config} — raise "
                 f"or remove the ceiling to run this audit")

    pending = [c["id"] for c in chunks]
    if args.results_dir:
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", encoding="utf-8") as manifest_file:
            json.dump({"chunks": chunks}, manifest_file)
            manifest_file.flush()
            pending = [c["id"] for c in chunks if not usable_result(
                args.results_dir, c["id"], manifest_file.name,
            )]

    report = (f"{ndocs} doc(s) -> {len(chunks)} chunk(s); "
              f"projected invocations: {len(pending)}")
    if len(pending) < len(chunks):
        report += f" (resume: {len(chunks) - len(pending)} already have results)"
    print(report, file=sys.stderr)

    manifest = {"schema": 1, "chunks": chunks, "pending": pending}
    if engine_plan is not None:
        manifest["index_digest"] = engine_plan["index_digest"]
        manifest["engine_plan"] = engine_plan
    text = json.dumps(manifest, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
