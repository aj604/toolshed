# detecting-doc-bloat Rearchitecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `detecting-doc-bloat` as a thin router over a deterministic chunking harness, move DISTILL payload authoring post-approval into the doc-distiller, add the bulk `POLICY` verdict, and ship contract v2 through every consumer — per the approved design `docs/plans/2026-07-06-detecting-doc-bloat-rearchitecture-design.md`.

**Architecture:** Deterministic python3 scripts own inventory → chunk manifest (`plan-chunks.py`) and seam/assembly validation (`validate-bloat-output.py`); the model fills judgment-shaped holes one bounded chunk at a time (subagent dispatch interactively, a workflow matrix headlessly). The skill text shrinks to a ~100-line router over per-need references; the DISTILL protocol moves into the doc-distiller agent and runs post-approval only.

**Tech Stack:** python3 stdlib only (no deps), `unittest` black-box subprocess tests, GitHub Actions + `anthropics/claude-code-action@v1`, Claude Code plugin skill/agent markdown.

## Global Constraints

- All helper scripts: `python3`, stdlib only, executable, module docstring stating usage and exit codes (existing convention in `plugins/doc-lifecycle/skills/*/scripts/`).
- All script tests: black-box subprocess tests with stdlib `unittest` at `tests/scripts/<script-name>_test.py`, self-contained tempdir fixtures (see `tests/scripts/list-docs_test.py` for the pattern). Run: `python3 tests/scripts/<name>_test.py`.
- Workflow YAML stays an allowlist-thin shell: no `jq` templating of user-facing strings, no branchy logic — decisions in `sync-gate.py`, strings in `render-report.py` (existing convention).
- Skill text follows superpowers:writing-skills: **no skill-text change ships without a RED baseline first** (Task 7 before Tasks 8–12), fresh subagents run scenarios, **stakeless graders holding the answer key grade them — never the author**, and any post-GREEN text edit re-GREENs its affected scenarios.
- Contract v2 (design §Contract v2) is atomic: every consumer in Tasks 8–16 lands before anything is tagged/released. No consumer may ship reading v1.
- The six-verdict judgment core, read-only stance, and approve-by-ID bridge are **unchanged** (design non-goals). `POLICY` is added; nothing is removed from the verdict enum.
- Commit messages: conventional style (`feat(bloat): …`, `test(scripts): …`, `docs(plans): …`), each ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Frontmatter hygiene: no `: ` (colon-space) inside YAML `description` values — it silently drops all skill metadata (`claude plugin validate` gates this at the end).

## Contract v2 — normative summary (referenced by every task)

Record fields (exactly these, no extras): `id`, `doc`, `location`, `verdict`, `evidence`, `proposal`, `status`, `files`. **`payload` is gone.**

| Field | v2 rule |
|---|---|
| `verdict` | `CUT` / `CONDENSE` / `EXTRACT-AND-MOVE` / `RETIRE-DOC` / `MERGE-DOC` / `DISTILL` / **`POLICY`** |
| `location` | passage verdicts: `file:line` (first line of passage); doc-level (`RETIRE-DOC`/`MERGE-DOC`/`DISTILL`/`POLICY`): `null` |
| `evidence` | mandatory non-empty for every verdict; passage verdicts open with the span `file:start[-end]` anchored at `location` (unchanged) |
| `proposal` | `CONDENSE`: replacement line; `EXTRACT-AND-MOVE`: `{"target","text"}`; `MERGE-DOC`: `{"target"}`; **`POLICY`: non-empty string, the policy text**; `CUT`/`RETIRE-DOC`/`DISTILL`: `null` |
| `status` | `DISTILL` only: `"ready"` / `"pending-implementation"`; all others `null` |
| `files` | **`POLICY` only: non-empty array enumerating every covered path (provenance)**; all others `null` |

Wrapped report: `{"schema": 2, "records": [...], "summary": {"cut","condense","extract_and_move","retire_doc","merge_doc","distill","policy"}}`. A bare array or a wrapped object without `"schema": 2` is a v1 shape → one legible "regenerate with the current skill" error.

Chunk result (new seam artifact): `{"chunk": "<id>", "records": [...]}` — same record rules.

Chunk manifest (`plan-chunks.py` output): `{"schema": 1, "chunks": [...], "pending": ["<id>", ...]}` where each chunk is either
`{"id": "c-…", "kind": "sweep", "docs": [{"path","lines","hint"}]}` (hint ∈ `living|narrative|planning`) or
`{"id": "p-…", "kind": "policy", "dir": "<dir>", "files": [...]}`. `pending` lists chunk ids with no existing result (resume support); `chunks` always lists all.

`audit-scope.json` gains optional keys (backward compatible):
`"policy_scope": ["<dir>", ...]` and `"chunking": {"max_docs": 8, "max_lines": 1200, "max_chunks": null}`.

---

### Task 1: Fixture repo `tests/fixtures/plan-swarm/`

A runnable-by-scripts sample repo with a spec/plan swarm, exercising chunk planning and policy-scope end-to-end without a live model. Also the stage for the RED/GREEN scenarios.

**Files:**
- Create: `tests/fixtures/plan-swarm/src/limiter.py`
- Create: `tests/fixtures/plan-swarm/README.md`
- Create: `tests/fixtures/plan-swarm/RUNBOOK.md`
- Create: `tests/fixtures/plan-swarm/docs/guides/rate-limiting-overview.md`
- Create: `tests/fixtures/plan-swarm/docs/plans/2026-05-01-rate-limiter-design.md`
- Create: `tests/fixtures/plan-swarm/docs/plans/2026-06-15-webhook-retry-design.md`
- Create: `tests/fixtures/plan-swarm/docs/superpowers/plans/*.md` (6 files) and `docs/superpowers/specs/*.md` (4 files)
- Create: `tests/fixtures/plan-swarm/.github/doc-sync/audit-scope.json`
- Create: `tests/fixtures/plan-swarm-ANSWER-KEY.md`

**Interfaces:**
- Produces: a 15-doc corpus whose deterministic chunk plan is 1 policy chunk (10 files under `docs/superpowers/`) + 3 sweep chunks; one landed plan (code exists in `src/limiter.py`), one pending plan (no `src/webhooks.py`); README carries one CONDENSE bait and one EXTRACT bait; the guides doc is `> As of`-anchored narrative. Tasks 2–3 tests, Task 7 RED, and Task 18 GREEN all consume this.

- [ ] **Step 1: Write the code + docs files**

`tests/fixtures/plan-swarm/src/limiter.py`:
```python
"""Token-bucket rate limiter (design: docs/plans/2026-05-01-rate-limiter-design.md)."""

MAX_REQUESTS_PER_MIN = 120
BURST = 20


class TokenBucket:
    def __init__(self, rate=MAX_REQUESTS_PER_MIN, burst=BURST):
        self.rate = rate
        self.burst = burst
        self.tokens = burst

    def allow(self):
        if self.tokens > 0:
            self.tokens -= 1
            return True
        return False
```

`tests/fixtures/plan-swarm/README.md`:
```markdown
# ratekit

Token-bucket rate limiting for small services.

## Install

    pip install -e .

## Rate limits

The limiter allows a steady rate of requests per minute. When traffic
arrives faster than that, a burst allowance absorbs short spikes. Once
the burst allowance is exhausted, further requests are rejected until
tokens refill over time. The steady rate is one hundred and twenty
requests per minute, and the burst allowance is twenty requests.

Note that the limiter is in-process only: two workers each enforce
their own bucket, so the effective global limit is N workers times the
configured rate — worth knowing before you scale out.

## Development

Run the tests with `python -m pytest`.
```

`tests/fixtures/plan-swarm/RUNBOOK.md`:
```markdown
# Runbook

## Restarting

Restart the service with `systemctl restart ratekit`.
```

`tests/fixtures/plan-swarm/docs/guides/rate-limiting-overview.md`:
```markdown
> As of 2026-05-10 (src/limiter.py)

# Rate limiting overview

Ratekit chose a token bucket over a sliding window because the bucket
answers "may this request proceed" in O(1) with two integers of state.

A request first claims a token; when the bucket is empty the request is
rejected outright rather than queued — queuing would trade memory for
latency under exactly the load the limiter exists to shed.
```

`tests/fixtures/plan-swarm/docs/plans/2026-05-01-rate-limiter-design.md` (landed):
```markdown
# Rate limiter design

Status: approved.

## Problem

Services need per-process rate limiting without a shared store.

## Design

A token bucket: steady rate `MAX_REQUESTS_PER_MIN = 120`, burst
`BURST = 20`, class `TokenBucket` with an `allow()` method, all in
`src/limiter.py`.

## Alternatives considered

A Redis-backed shared limiter was rejected: operational overhead
disproportionate for single-node deploys. Revisit only if cross-worker
fairness becomes a measured problem.

## Sketch

    class TokenBucket:
        def allow(self): ...
```

`tests/fixtures/plan-swarm/docs/plans/2026-06-15-webhook-retry-design.md` (pending — no `src/webhooks.py` exists):
```markdown
# Webhook retry design

Status: draft.

## Problem

Outbound webhooks fail transiently and are currently dropped.

## Design

A `RetryQueue` with exponential backoff (`WEBHOOK_MAX_ATTEMPTS = 5`) in
`src/webhooks.py`, drained by a background thread.
```

- [ ] **Step 2: Generate the ephemeral swarm (10 files)**

```bash
cd tests/fixtures/plan-swarm
mkdir -p docs/superpowers/plans docs/superpowers/specs
for n in limiter-tests bucket-refactor readme-pass cli-flags error-codes retry-spike; do
  printf '# %s implementation plan\n\nTask 1: write the failing test. Task 2: implement. Task 3: commit.\n' \
    "$n" > "docs/superpowers/plans/2026-06-0X-$n-plan.md"
done
for n in limiter-api bucket-state cli-surface error-taxonomy; do
  printf '# %s spec\n\nRequirement 1: behave as designed. Requirement 2: stay fast.\n' \
    "$n" > "docs/superpowers/specs/2026-06-0X-$n-spec.md"
done
```
(Replace `0X` with `01`–`06` / `01`–`04` respectively so filenames are unique and dated.)

- [ ] **Step 3: Write the scope config**

`tests/fixtures/plan-swarm/.github/doc-sync/audit-scope.json`:
```json
{
  "exclude": [],
  "include": [],
  "policy_scope": ["docs/superpowers"],
  "chunking": {"max_docs": 3, "max_lines": 400}
}
```

- [ ] **Step 4: Write the answer key** (`tests/fixtures/plan-swarm-ANSWER-KEY.md`) — used by Task 7/18 graders. Contents: the expected chunk plan (1 policy chunk: `docs/superpowers`, 10 files; 3 sweep chunks: `[README.md, RUNBOOK.md]` living, `[docs/guides/rate-limiting-overview.md]` narrative, `[docs/plans/*]` planning ×2 docs); expected verdicts — README `CONDENSE` anchored at the "Rate limits" paragraph's first body line citing `src/limiter.py:3-4`, README `EXTRACT-AND-MOVE` of the "Note that the limiter is in-process only…" passage → `RUNBOOK.md`, `docs/plans/2026-05-01…` → `DISTILL ready` **with no payload field** (evidence names `src/limiter.py` symbols), `docs/plans/2026-06-15…` → `DISTILL pending-implementation`, `docs/superpowers` → exactly one `POLICY` record with all 10 paths in `files`, narrative guide → no records (own-bar exempt); and the grading rules (a per-file walk of `docs/superpowers/**`, any `payload` field, or any record outside the assigned chunk = FAIL).

- [ ] **Step 5: Commit** (fixture must be git-tracked before scripts/agents enumerate it via `git ls-files`)

```bash
git add tests/fixtures/plan-swarm tests/fixtures/plan-swarm-ANSWER-KEY.md
git commit -m "test(fixtures): plan-swarm repo for bloat chunking + policy-scope"
```

---

### Task 2: `plan-chunks.py` — inventory, config, hints

**Files:**
- Create: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py`
- Test: `tests/scripts/plan-chunks_test.py`

**Interfaces:**
- Consumes: `audit-scope.json` v2 keys (Global Constraints).
- Produces: `load_config(path)` → dict with `exclude`/`include` (compiled regexes), `policy_scope` (normalized dir strings), `max_docs`, `max_lines`, `max_chunks`; `doc_hint(root, path)` → `"living"|"narrative"|"planning"`; inventory identical in behavior to `list-docs.py` (git ls-files, walk fallback, `.md` default filter, exclude→include order, whitelist wins). Task 3 builds grouping on these.

- [ ] **Step 1: Write the failing tests** — create `tests/scripts/plan-chunks_test.py` with the header/helpers pattern of `list-docs_test.py` (`write`, `git_init`, tempdir per test), `SCRIPT` pointing at `plan-chunks.py`, and a runner that captures the JSON manifest from stdout:

```python
def run(root, config=None, results_dir=None):
    cmd = [sys.executable, SCRIPT, "--root", root]
    if config is not None:
        cmd += ["--config", config]
    if results_dir is not None:
        cmd += ["--results-dir", results_dir]
    return subprocess.run(cmd, capture_output=True, text=True)


def manifest(result):
    return json.loads(result.stdout)


def paths_of(chunk):
    return [d["path"] for d in chunk["docs"]]
```

Test classes for this step:

```python
class InventoryDefaults(unittest.TestCase):
    def test_md_only_git_and_walk(self):
        # same corpus as list-docs_test.Defaults, both git and non-git roots:
        # manifest docs across all sweep chunks == {"README.md", "docs/guide.md"}
        ...

    def test_exclude_include_whitelist_wins(self):
        # config {"exclude": ["tests/**"], "include": ["tests/fixtures/b.md", "Makefile"]}
        # => tests/baselines dropped, b.md re-added, non-md Makefile force-added
        ...

    def test_stdout_is_pure_json_report_on_stderr(self):
        # json.loads(r.stdout) succeeds; "doc(s)" and "chunk(s)" appear in r.stderr
        ...


class Hints(unittest.TestCase):
    def test_as_of_anchor_is_narrative_wherever_it_sits(self):
        # "docs/plans/walkthrough.md" whose first line is "> As of 2026-01-01 (x)" => hint narrative
        ...

    def test_plans_or_specs_segment_is_planning(self):
        # "docs/plans/a.md" and "specs/b.md" => planning; "docs/plansX/c.md" => living
        ...

    def test_everything_else_is_living(self):
        # "README.md", "docs/guide.md" => living
        ...


class MalformedConfig(unittest.TestCase):
    # mirrors list-docs_test.MalformedConfig: bad JSON, non-list exclude/include,
    # non-list policy_scope, chunking not an object, chunking.max_docs = 0,
    # chunking.max_chunks = "many" — each exits 2 naming the file and key.
    ...
```

Write each test fully (the corpus builders are 3–6 `write()` lines each, as in `list-docs_test.py`).

- [ ] **Step 2: Run tests, verify they fail** — `python3 tests/scripts/plan-chunks_test.py` → every test errors with "No such file" for SCRIPT (or nonzero exit): RED.

- [ ] **Step 3: Implement the inventory/config/hint layer** — create `plan-chunks.py`; carry `glob_to_regex`, `matches_any`, `candidates`, `walk`, `select`, `line_count` over from `list-docs.py` verbatim, plus:

```python
#!/usr/bin/env python3
"""Plan doc-bloat sweep chunks: inventory -> chunk manifest.

Absorbs list-docs.py: enumerates the in-scope docs (git ls-files under
--root, else a filesystem walk; default filter *.md; config exclude/include
globs, whitelist wins), then groups them into bounded chunks a single
detection invocation can hold.

Policy-scope directories (config "policy_scope") become one 'policy' chunk
each — a single POLICY record covers them; they are never walked
file-by-file. Every other doc gets a deterministic doc-kind hint (narrative
if its first line starts with '> As of'; planning if a 'plans' or 'specs'
path segment contains it; else living — a hint the model may override only
with stated evidence), is grouped by (directory, hint), packed under the
caps (chunking.max_docs, default 8; chunking.max_lines, default 1200), and
consecutive underfull chunks with the same hint are coalesced while the
caps hold. A single doc larger than max_lines gets its own chunk.

Chunk ids are content-addressed (sha256 of member paths), so re-planning an
unchanged tree yields the same ids — which is what makes --results-dir
resume work: a chunk whose <id>.json result already exists stays in
"chunks" but leaves "pending".

Usage:
    plan-chunks.py [--config PATH] [--root DIR] [--out FILE] [--results-dir DIR]

Output: manifest JSON {"schema": 1, "chunks": [...], "pending": [ids]} to
--out (stdout if omitted). The run-surface report (doc count, chunk count,
projected invocations, resume skips) always prints to stderr.

Config (audit-scope.json), all keys optional:
    exclude / include: glob lists (as before)
    policy_scope: ["docs/superpowers", ...]   directories, prefix match
    chunking: {"max_docs": 8, "max_lines": 1200, "max_chunks": null}
max_chunks non-null is a hard run ceiling: planning more chunks than that
exits 2 naming the count and the knob (default off — big first runs are
legitimate; the protections are structural).

Exit status: 0 on success; 2 on malformed config or a tripped max_chunks.
"""

DEFAULT_MAX_DOCS = 8
DEFAULT_MAX_LINES = 1200


def load_config(path):
    defaults = {"exclude": [], "include": [], "policy_scope": [],
                "max_docs": DEFAULT_MAX_DOCS, "max_lines": DEFAULT_MAX_LINES,
                "max_chunks": None}
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return defaults
    except OSError as e:
        sys.exit(f"error: cannot read config {path}: {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"error: malformed config JSON in {path}: {e}")
    if not isinstance(data, dict):
        sys.exit(f"error: config {path} must be a JSON object")
    for key in ("exclude", "include", "policy_scope"):
        val = data.get(key, [])
        if not (isinstance(val, list) and all(isinstance(g, str) for g in val)):
            sys.exit(f"error: config {path}: '{key}' must be a list of strings")
        defaults[key] = val
    chunking = data.get("chunking", {})
    if not isinstance(chunking, dict):
        sys.exit(f"error: config {path}: 'chunking' must be an object")
    for key in ("max_docs", "max_lines"):
        if key in chunking:
            v = chunking[key]
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
                sys.exit(f"error: config {path}: chunking.{key} must be an integer >= 1")
            defaults[key] = v
    v = chunking.get("max_chunks")
    if v is not None:
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            sys.exit(f"error: config {path}: chunking.max_chunks must be null or an integer >= 1")
        defaults["max_chunks"] = v
    defaults["exclude"] = [glob_to_regex(g) for g in defaults["exclude"]]
    defaults["include"] = [glob_to_regex(g) for g in defaults["include"]]
    defaults["policy_scope"] = [d.strip("/") for d in defaults["policy_scope"]]
    return defaults


def doc_hint(root, path):
    """Deterministic doc-kind hint; the '> As of' anchor wins over location."""
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        first = ""
    if first.lstrip().startswith("> As of"):
        return "narrative"
    if any(seg in ("plans", "specs") for seg in path.split("/")[:-1]):
        return "planning"
    return "living"
```

Plus a provisional `main()` that inventories, hints, emits one chunk per doc (real grouping is Task 3), prints the stderr report line, and honors `--out`.

- [ ] **Step 4: Run tests, verify this step's classes pass** — `python3 tests/scripts/plan-chunks_test.py InventoryDefaults Hints MalformedConfig -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py tests/scripts/plan-chunks_test.py
git commit -m "feat(bloat): plan-chunks.py inventory, scope config v2, doc-kind hints"
```

---

### Task 3: `plan-chunks.py` — grouping, caps, policy chunks, resume, ceiling

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py`
- Test: `tests/scripts/plan-chunks_test.py`

**Interfaces:**
- Produces: the manifest shape in Global Constraints — consumed by Task 5 (`--chunk`), Task 6 (`--assemble`), Task 10 (SKILL.md invocation templates), Task 15 (workflow matrix via `pending`).

- [ ] **Step 1: Write the failing tests** (append to `plan-chunks_test.py`):

```python
class Grouping(unittest.TestCase):
    def test_max_docs_splits_a_directory(self):
        # 7 living docs in docs/ with chunking {"max_docs": 3}:
        # sweep chunks of sizes [3, 3, 1], docs sorted by path within
        ...

    def test_max_lines_splits_and_oversized_doc_gets_own_chunk(self):
        # max_lines 10: a 25-line doc is alone in its chunk; two 6-line docs
        # cannot share a chunk with it
        ...

    def test_different_hints_never_share_a_chunk(self):
        # docs/x.md (living) + docs/plans/p.md (planning): 2 chunks
        ...

    def test_same_hint_small_dirs_coalesce_under_caps(self):
        # a/x.md and b/y.md (both living, tiny, defaults): ONE chunk
        ...

    def test_ids_deterministic_and_membership_addressed(self):
        # two runs => identical ids; adding a doc to a chunk changes its id
        ...


class PolicyChunks(unittest.TestCase):
    def test_policy_dir_becomes_single_chunk_with_files(self):
        # 10 md files under docs/superpowers/**, policy_scope ["docs/superpowers"]:
        # exactly one chunk kind=policy, dir="docs/superpowers", files == all 10 sorted;
        # none of those paths appear in any sweep chunk
        ...

    def test_policy_scope_respects_exclude_include(self):
        # an excluded file under the policy dir is not in files
        ...

    def test_declared_dir_with_no_docs_notes_and_omits(self):
        # policy_scope ["docs/empty"]: no policy chunk; stderr mentions docs/empty
        ...

    def test_longest_prefix_wins_for_nested_scopes(self):
        # policy_scope ["docs/superpowers", "docs/superpowers/specs"]:
        # specs files land in the deeper chunk only
        ...


class ResumeAndCeiling(unittest.TestCase):
    def test_pending_excludes_chunks_with_results(self):
        # run once; write <first-chunk-id>.json into a results dir; run again with
        # --results-dir: "chunks" unchanged, "pending" lacks that id, stderr says resume
        ...

    def test_pending_equals_all_ids_without_results_dir(self):
        ...

    def test_max_chunks_ceiling_exits_2(self):
        # 5 dirs of living docs, chunking {"max_docs": 1, "max_chunks": 2}:
        # exit 2, stderr names the count and "max_chunks"
        ...


class FixtureEndToEnd(unittest.TestCase):
    def test_plan_swarm_fixture_plans_as_answer_key_says(self):
        root = os.path.join(os.path.dirname(__file__), "..", "fixtures", "plan-swarm")
        r = run(root)
        m = manifest(r)
        policy = [c for c in m["chunks"] if c["kind"] == "policy"]
        self.assertEqual(len(policy), 1)
        self.assertEqual(policy[0]["dir"], "docs/superpowers")
        self.assertEqual(len(policy[0]["files"]), 10)
        sweep = [c for c in m["chunks"] if c["kind"] == "sweep"]
        self.assertEqual(len(sweep), 3)
        self.assertEqual(len(m["pending"]), 4)
```

- [ ] **Step 2: Run tests, verify the new classes fail** — grouping is still one-chunk-per-doc: FAIL.

- [ ] **Step 3: Implement grouping/packing/policy/resume/ceiling**:

```python
def policy_dir_of(path, policy_dirs):
    """Longest declared dir that is a proper path prefix of path, else None."""
    best = None
    for d in policy_dirs:
        if path.startswith(d + "/") and (best is None or len(d) > len(best)):
            best = d
    return best


def chunk_id(prefix, paths):
    digest = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10]}"


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
    sized = [{"path": p, "lines": line_count(os.path.join(root, p))} for p in docs]

    policy_files, sweep = {}, []
    for d in sized:
        pdir = policy_dir_of(d["path"], cfg["policy_scope"])
        if pdir is not None:
            policy_files.setdefault(pdir, []).append(d["path"])
        else:
            d["hint"] = doc_hint(root, d["path"])
            sweep.append(d)

    chunks = []
    for pdir in sorted(policy_files):
        files = sorted(policy_files[pdir])
        chunks.append({"id": chunk_id("p", files), "kind": "policy",
                       "dir": pdir, "files": files})

    groups = {}
    for d in sweep:
        groups.setdefault((os.path.dirname(d["path"]), d["hint"]), []).append(d)
    packed = []
    for key in sorted(groups):
        packed.extend(pack(sorted(groups[key], key=lambda d: d["path"]),
                           cfg["max_docs"], cfg["max_lines"]))
    packed.sort(key=lambda c: c[0]["path"])
    for c in coalesce(packed, cfg["max_docs"], cfg["max_lines"]):
        chunks.append({"id": chunk_id("c", [d["path"] for d in c]),
                       "kind": "sweep", "docs": c})
    return len(sized), chunks
```

`main()` (replacing the provisional one):

```python
def main():
    ap = argparse.ArgumentParser(description="Plan doc-bloat sweep chunks.")
    ap.add_argument("--config", help="scope config JSON (default: "
                    "<root>/.github/doc-sync/audit-scope.json)")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--out", help="write the manifest here (default: stdout)")
    ap.add_argument("--results-dir", help="existing chunk-result dir; chunks "
                    "with a <id>.json there stay in 'chunks' but leave 'pending'")
    args = ap.parse_args()

    config = args.config or os.path.join(
        args.root, ".github", "doc-sync", "audit-scope.json")
    cfg = load_config(config)
    ndocs, chunks = plan(args.root, cfg)

    for d in cfg["policy_scope"]:
        if not any(c["kind"] == "policy" and c["dir"] == d for c in chunks):
            print(f"note: policy-scope dir {d!r} matches no in-scope docs",
                  file=sys.stderr)

    if cfg["max_chunks"] is not None and len(chunks) > cfg["max_chunks"]:
        sys.exit(f"error: planned {len(chunks)} chunks, over "
                 f"chunking.max_chunks={cfg['max_chunks']} in {config} — raise "
                 f"or remove the ceiling to run this audit")

    pending = [c["id"] for c in chunks]
    if args.results_dir:
        pending = [c["id"] for c in chunks if not os.path.exists(
            os.path.join(args.results_dir, c["id"] + ".json"))]

    nsweep = sum(1 for c in chunks if c["kind"] == "sweep")
    report = (f"{ndocs} doc(s) -> {len(chunks)} chunk(s) "
              f"({nsweep} sweep + {len(chunks) - nsweep} policy); "
              f"projected invocations: {len(pending)}")
    if len(pending) < len(chunks):
        report += f" (resume: {len(chunks) - len(pending)} already have results)"
    print(report, file=sys.stderr)

    text = json.dumps({"schema": 1, "chunks": chunks, "pending": pending},
                      indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0
```

- [ ] **Step 4: Run the whole file, verify PASS** — `python3 tests/scripts/plan-chunks_test.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat(bloat): plan-chunks.py affinity grouping, caps, policy chunks, resume, ceiling"`

---

### Task 4: `validate-bloat-output.py` — contract v2 record rules + final-report schema gate

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py` (substantial rewrite)
- Test: `tests/scripts/validate-bloat-output_test.py` (rewrite helpers + these classes)

**Interfaces:**
- Consumes: nothing new.
- Produces: `validate_records(records) -> [errors]`, `count_verdicts(records)` (7 keys), `run_final(src)`, `V1_ERROR`; module-level `REQUIRED`, `VERDICTS`, `SUMMARY_KEYS` per Global Constraints. Tasks 5–6 extend this file; Tasks 13–16 consume the v2 report shape.

- [ ] **Step 1: Rewrite the test helpers and write failing v2 tests.** In `tests/scripts/validate-bloat-output_test.py`: `rec()` gains `"files": None` and keeps no `payload`; `distill_ready()` becomes a payload-less DISTILL; add `policy_rec()`; delete the `DistillInsights` class and every payload test; keep `EvidenceSpan` (unchanged semantics — update its helper use only).

```python
def rec(**over):
    """A well-formed v2 CUT record; override fields per test."""
    base = {
        "id": "B1",
        "doc": "README.md",
        "location": "README.md:12",
        "verdict": "CUT",
        "evidence": "README.md:12 restates src/notify.py:3 verbatim",
        "proposal": None,
        "status": None,
        "files": None,
    }
    base.update(over)
    return base


def distill_ready(**over):
    base = rec(id="B9", doc="docs/plans/old-design.md", location=None,
               verdict="DISTILL", status="ready",
               evidence="implementation landed: src/notify.py implements the design")
    base.update(over)
    return base


def policy_rec(**over):
    base = rec(id="B7", doc="docs/superpowers", location=None,
               verdict="POLICY", status=None,
               evidence="10 dated plan/spec artifacts for merged work — one class",
               proposal="Ephemeral process artifacts; retire after the work merges.",
               files=["docs/superpowers/plans/a.md", "docs/superpowers/specs/b.md"])
    base.update(over)
    return base


def wrap(records, **over):
    obj = {"schema": 2, "records": records}
    obj.update(over)
    return obj
```

New/changed test classes (write fully):

```python
class SchemaGate(unittest.TestCase):
    def test_v2_wrapped_report_valid(self):
        # run(wrap([rec()])) → exit 0, "OK: 1 record(s) valid"
    def test_bare_array_is_legible_v1_reject(self):
        # run([rec()]) → exit 1, stderr contains "schema v1" and "regenerate"
    def test_wrapped_without_schema_is_v1_reject(self):
        # run({"records": [rec()], "summary": {...}}) → exit 1, "schema v1"
    def test_record_with_payload_field_rejected(self):
        # wrap([distill_ready() | {"payload": {...}}]) → exit 1, mentions 'payload' and v2
    def test_summary_with_policy_key_matches(self):
        # wrap([rec(), policy_rec()], summary={all zero except cut:1, policy:1}) → 0
    def test_v1_six_key_summary_rejected(self):
        # a summary missing "policy" → exit 1


class PolicyRecords(unittest.TestCase):
    def test_valid_policy_record(self):            # → 0
    def test_policy_requires_files(self):           # files=None → 1, "files"
    def test_policy_files_must_be_nonempty(self):   # files=[] → 1
    def test_policy_requires_proposal_text(self):   # proposal=None → 1
    def test_policy_forbids_location(self):         # location="x:1" → 1
    def test_policy_forbids_status(self):           # status="ready" → 1
    def test_non_policy_forbids_files(self):        # rec(files=["a"]) → 1


class DistillV2(unittest.TestCase):
    def test_ready_without_payload_valid(self):     # distill_ready() → 0
    def test_pending_without_payload_valid(self):
    def test_distill_needs_status(self):            # status=None → 1
```

(Existing `InvalidRecords` tests for enum/location/proposal/evidence/duplicate-id semantics stay, ported to the v2 helpers and `wrap()`.)

- [ ] **Step 2: Run tests, verify the new classes fail** (current script accepts v1, has no POLICY/files/schema logic).

- [ ] **Step 3: Rewrite the script's record layer** per the code in the plan preamble of this task — exact constants and functions:

```python
PASSAGE = {"CUT", "CONDENSE", "EXTRACT-AND-MOVE"}
DOCLEVEL = {"RETIRE-DOC", "MERGE-DOC", "DISTILL", "POLICY"}
VERDICTS = PASSAGE | DOCLEVEL
STATUSES = {"pending-implementation", "ready"}
REQUIRED = ("id", "doc", "location", "verdict", "evidence",
            "proposal", "status", "files")
SUMMARY_KEYS = ("cut", "condense", "extract_and_move",
                "retire_doc", "merge_doc", "distill", "policy")

V1_ERROR = ('schema v1 report: regenerate with the current skill — the '
            'contract is now {"schema": 2, "records": [...], "summary": '
            '{...}} with no DISTILL payloads')
```

`check_proposal` gains the `POLICY` branch (`proposal` = non-empty policy text); new `check_files` (POLICY: non-empty list of non-empty strings; others: must be null); `check_distill` shrinks to the status check; `validate_record` swaps `payload` handling for `files` and emits the targeted message for an unexpected `payload` field:

```python
        if field == "payload":
            errs.append(f"{where}: unexpected field 'payload' — contract v2 "
                        f"removed DISTILL payloads (the doc-distiller authors "
                        f"them post-approval)")
```

`count_verdicts` maps `"POLICY": "policy"`. `run_final(src)`: list input → `fail([V1_ERROR + " (got a bare records array)"])`; dict without `schema == 2` → `fail([V1_ERROR])`; then records + optional-summary validation as before (7 keys). Keep the `OK:`/`summary:` success output format. Shared `fail(errs)` / `ok(records)` helpers as in the design sketch (exit 1 / 0).

- [ ] **Step 4: Run tests, verify PASS** — `python3 tests/scripts/validate-bloat-output_test.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat(bloat): contract v2 validator — schema gate, POLICY verdict, payload removal"`

---

### Task 5: `validate-bloat-output.py --chunk` — seam validation

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
- Test: `tests/scripts/validate-bloat-output_test.py`

**Interfaces:**
- Consumes: Task 3's manifest shape.
- Produces: `validate-bloat-output.py --chunk FILE [--manifest FILE]` exit 0/1/2; `load_manifest(path)`, `validate_chunk_result(data, chunk)`, `slice_errors(data, chunk)` — reused verbatim by Task 6's assembly.

- [ ] **Step 1: Write failing tests** — helpers to write a manifest + chunk-result files into a tempdir, then:

```python
class ChunkSeam(unittest.TestCase):
    # manifest fixture: one sweep chunk c-aaa (docs README.md, RUNBOOK.md),
    # one policy chunk p-bbb (dir docs/superpowers, files [x.md, y.md])
    def test_valid_sweep_chunk_result(self):        # {"chunk": "c-aaa", "records": [rec()]} → 0
    def test_chunk_shape_must_be_exact(self):       # extra top-level key / missing "chunk" → 1
    def test_record_doc_outside_slice_fails(self):  # rec(doc="OTHER.md") → 1, "outside this chunk's slice"
    def test_sweep_chunk_never_emits_policy(self):  # policy_rec() in c-aaa → 1
    def test_unknown_chunk_id_fails(self):          # {"chunk": "c-zzz", ...} → 1, "not in the manifest"
    def test_policy_chunk_exactly_one_policy_record(self):
        # zero records, or one CUT record → 1
    def test_policy_files_must_equal_chunk_files(self):
        # files missing y.md → 1, "provenance"
    def test_policy_doc_must_be_chunk_dir(self):    # doc="docs" → 1
    def test_without_manifest_records_rules_still_apply(self):
        # --chunk alone: bad verdict → 1; good result → 0
    def test_empty_records_chunk_is_valid(self):    # {"chunk": "c-aaa", "records": []} → 0
```

- [ ] **Step 2: Run, verify FAIL** (no `--chunk` flag yet → argparse error, exit 2 ≠ expected).

- [ ] **Step 3: Implement** `load_manifest`, `chunk_shape_errors`, `slice_errors`, `validate_chunk_result`, `run_chunk` exactly as specified here:

```python
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
            errs.append(f"policy chunk {chunk['id']}: files must enumerate exactly "
                        f"the chunk's covered paths (provenance)")
    else:
        allowed = {d.get("path") for d in chunk.get("docs", []) if isinstance(d, dict)}
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
```

Wire `--chunk` / `--manifest` into `main()` (full `main()` lands in Task 6).

- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(bloat): seam validation for chunk results (--chunk/--manifest)"`

---

### Task 6: `validate-bloat-output.py --assemble` — checkpointed assembly

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
- Test: `tests/scripts/validate-bloat-output_test.py`

**Interfaces:**
- Produces: `validate-bloat-output.py --assemble DIR --manifest FILE --out FILE [--allow-partial]` → writes the final wrapped v2 report with ids renumbered `B1..Bn` in manifest order; refuses partial assembly by default, failing while **naming each missing/invalid chunk**. Consumed by Task 10 (interactive large scope) and Task 15 (assemble job — which never passes `--allow-partial`).

- [ ] **Step 1: Write failing tests:**

```python
class Assembly(unittest.TestCase):
    # tempdir: manifest with chunks c-aaa, p-bbb; results dir with both files
    def test_assembles_and_renumbers_ids(self):
        # both chunks' records use id "B1" locally; output report ids are B1, B2
        # in manifest order; output has schema 2 and a matching 7-key summary;
        # the written report re-validates: run_final on it exits 0
    def test_missing_chunk_refused_by_name(self):
        # delete p-bbb.json → exit 1, stderr names "p-bbb" and "partial assembly refused"
    def test_allow_partial_skips_missing_only(self):
        # --allow-partial with p-bbb.json missing → exit 0, report holds c-aaa records,
        # stderr notes the skip
    def test_invalid_chunk_fails_even_with_allow_partial(self):
        # c-aaa.json invalid (bad verdict) → exit 1 naming c-aaa, with or without flag
    def test_empty_manifest_assembles_empty_report(self):
        # zero chunks → exit 0, {"schema": 2, "records": [], "summary": all-zero}
    def test_usage_errors_exit_2(self):
        # --assemble without --out / --manifest; --chunk with --assemble; --allow-partial alone
```

- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `run_assemble` and the final `main()`:

```python
def run_assemble(dir_, manifest_path, out, allow_partial):
    try:
        chunks = load_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    errs, records = [], []
    for chunk in chunks:
        path = os.path.join(dir_, chunk["id"] + ".json")
        if not os.path.exists(path):
            if allow_partial:
                print(f"note: --allow-partial: skipping chunk {chunk['id']} "
                      f"(no result file)", file=sys.stderr)
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
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return ok(records)


def main():
    ap = argparse.ArgumentParser(
        description="Validate detecting-doc-bloat output (final / seam / assembly).")
    ap.add_argument("file", nargs="?", help="final wrapped v2 report (default: stdin)")
    ap.add_argument("--chunk", help="validate one chunk result file at the seam")
    ap.add_argument("--manifest", help="plan-chunks.py manifest for slice cross-checks")
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
        return run_assemble(args.assemble, args.manifest, args.out, args.allow_partial)
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
```

Update the module docstring to the three-duty description (final / seam / assembly, exit codes 0/1/2).

- [ ] **Step 4: Run the whole test file, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(bloat): checkpointed assembly (--assemble, --allow-partial) and v2 final gate"`

---

### Task 7: RED baselines — `tests/baselines/bloat-rearch-red/`

Per superpowers:writing-skills this is the failing test the rebuild is not allowed to precede. Scenarios pin the observed production failures (design §Testing). **Run every scenario against the CURRENT (pre-rebuild) skill text.** Author dispatches runners and graders; **the author never grades** (fresh stakeless grader with the answer key, per repo convention).

**Files:**
- Create: `tests/baselines/bloat-rearch-red/README.md` (method: who ran, who graded, verbatim prompts)
- Create: `tests/baselines/bloat-rearch-red/scenario-{a,b,c,d,e}.md`

**Interfaces:**
- Consumes: Task 1 fixture, Tasks 2–6 scripts.
- Produces: documented baseline failures + verbatim rationalizations — the input GREEN (Task 18) is graded against, and the failure list Tasks 8–12's text must specifically counter.

- [ ] **Step 1: Generate the fixture manifest once** (shared by scenarios a/e):
`python3 plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py --root tests/fixtures/plan-swarm --out /tmp/plan-swarm-manifest.json`

- [ ] **Step 2: Run scenario subagents (fresh, one per scenario), each given the current `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md` and the fixture path.** Scenario prompts (verbatim, also recorded in the baseline files):
  - **(a) headless chunk executor:** "You are running headlessly under a CI allowlist that permits ONLY: Read, Grep, Glob, Write, Bash(git *), Bash(python3 *). Any other tool call is a permission denial. Using the detecting-doc-bloat skill (text attached), act as a chunk executor: read /tmp/plan-swarm-manifest.json, find chunk <first sweep chunk id>, audit exactly the docs it lists, and write {"chunk": "<id>", "records": [...]} to /tmp/chunks/<id>.json." Expected RED failures: audits docs outside the slice / runs the full four-step engine over everything / attempts `find`/`ls`/`wc`.
  - **(b) policy scope:** "Audit `docs/superpowers/` of tests/fixtures/plan-swarm with the skill (text attached). The scope config declares docs/superpowers as policy-scope." Expected RED: 10 per-file DISTILL records with payloads (the career-compass failure), no bulk record.
  - **(c) landed planning artifact:** "Audit tests/fixtures/plan-swarm/docs/plans/2026-05-01-rate-limiter-design.md." Expected RED: `DISTILL ready` **with a full payload** (claims/insights/decision entry authored at detect time).
  - **(d) invalid chunk result (scripted, no model):** craft `/tmp/chunks/bad.json` = `{"chunk": "<sweep id>", "records": [{"id": "B1", "doc": "README.md", "verdict": "PRUNE"}]}`; run the seam validator and record that the **current architecture has no seam at all** (the old script validates only a whole report at end-of-run) while the new script rejects at the seam naming the chunk. This scenario's RED is architectural; record both outputs.
  - **(e) interactive large scope:** "A user asks: 'run a full bloat audit of tests/fixtures/plan-swarm' (15 docs). Use the skill (text attached). You may dispatch subagents." Expected RED: one inline mega-sweep, no chunk plan, no per-chunk dispatch.

- [ ] **Step 3: Dispatch a fresh stakeless grader per scenario** — grader receives ONLY: the scenario transcript/output, `tests/fixtures/plan-swarm-ANSWER-KEY.md`, and the expected-behavior list above; it did not author anything; it returns PASS/FAIL per criterion plus verbatim quotes of rationalizations.

- [ ] **Step 4: Record** each scenario file: prompt verbatim, agent output (or the load-bearing excerpts), grader verdict, rationalizations verbatim. README.md records the method and that all five scenarios FAILED (if any scenario unexpectedly passes, the corresponding Task 8–12 text must still encode the guard — note it explicitly).

- [ ] **Step 5: Commit** — `git commit -m "test(baselines): bloat-rearch RED — five scenarios vs the monolithic skill"`

---

### Task 8: `output-contract.md` — contract v2 shape reference

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/output-contract.md`

**Interfaces:**
- Produces: the single worked-example home for v2 (field table moves here from SKILL.md, per design: SKILL.md keeps only a pointer). Tasks 10–12 cite it; chunk executors load it.

- [ ] **Step 1: Rewrite the file** with, in order:
  1. The v2 field table (exactly the Global Constraints table, including `files`, minus `payload`).
  2. Worked example, five records: the existing B1 `CONDENSE` and B2 `MERGE-DOC` verbatim but with `"files": null` added and `"payload"` removed; B3 `DISTILL ready` — same doc/evidence as today **minus the insight-sweep clause and minus the payload** (`"status": "ready"`, `"proposal": null`, `"files": null`; add the sentence "Claims, insights, and the decision entry are authored by the doc-distiller after a human approves this ID — never at detect time."); B4 `DISTILL pending-implementation` verbatim plus `"files": null`; new B5 `POLICY`:
```json
{
  "id": "B5",
  "doc": "docs/superpowers",
  "location": null,
  "verdict": "POLICY",
  "evidence": "10 dated plan/spec artifacts, all for work already merged (git log confirms); one class of ephemeral process artifact, not 10 findings",
  "proposal": "Ephemeral process artifacts; retire after the work merges.",
  "status": null,
  "files": ["docs/superpowers/plans/2026-06-01-limiter-tests-plan.md", "…every covered path…"]
}
```
  3. The wrapped v2 artifact with `"schema": 2` and the 7-key summary (note: a zero means the class was swept and clean, not skipped — keep this sentence).
  4. New short section "Chunk results (the seam artifact)": the `{"chunk": "<id>", "records": [...]}` shape, that a sweep chunk's records may only name its slice's docs and never `POLICY`, that a policy chunk's result is exactly one `POLICY` record whose `files` equal the manifest's list, and the three validator invocations (`--chunk`, `--assemble`, final).

- [ ] **Step 2: Sanity check the example mechanically** — paste the worked records into a file wrapped with `"schema": 2` and run the Task 4 validator: exit 0.

- [ ] **Step 3: Commit** — `git commit -m "docs(bloat): output-contract v2 — schema 2, POLICY, payload removed, chunk seam"`

---

### Task 9: `references/verdict-lenses.md` + `references/planning-artifacts.md`

**Files:**
- Create: `plugins/doc-lifecycle/skills/detecting-doc-bloat/references/verdict-lenses.md`
- Create: `plugins/doc-lifecycle/skills/detecting-doc-bloat/references/planning-artifacts.md`

**Interfaces:**
- Produces: the per-need rule references a chunk executor loads by its chunk's doc kinds (living/narrative → verdict-lenses; planning/policy → planning-artifacts). Task 10's router points at them.

- [ ] **Step 1: Write `verdict-lenses.md`** by moving (not rewriting — lift the existing wording; it is GREEN-tested prose) from the current SKILL.md: the three passage questions with their tells and evidence rules (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`, including the deliberately-conservative reverse lens); `MERGE-DOC`/`RETIRE-DOC` with quoted-overlap evidence; the durable-narrative own-bar block; the precision guard; the same-audience rule; the three-lens re-pass instruction; and exactly the red flags that guard these rules (narrative CUT/CONDENSE, extraction-target flagging, cross-reference adding, same-audience dedup, value≠placement, first-finding stop / skipped re-pass, "emitting only findings that resemble the worked example").

- [ ] **Step 2: Write `planning-artifacts.md`**: landed / pending classification (grep the symbols, don't eyeball — lift current step 3's method); **v2 DISTILL rules**: `ready` = evidence names the landed code, `proposal`/`files` null, **no payload — the insight walk, claim verification, and decision-entry drafting run post-approval in the doc-distiller** (state this as the rule, with the "speculative → approval-gated" one-line why); `pending-implementation` = record exists to say so, never propose deleting; **POLICY rules**: policy chunks arrive pre-declared in the manifest (config `policy_scope`), the executor emits exactly one record — `doc` = the dir, `proposal` = the policy text, `evidence` = what makes the directory one class, `files` = the manifest's file list verbatim (provenance; selected by filter, not summarized by model) — and **never walks the directory file-by-file**; red flags: authoring any payload at detect time, a per-file record for a policy-scope path, a POLICY record whose `files` don't match the manifest, "keep it as a historical record", classifying an `> As of`-anchored doc as planning.

- [ ] **Step 3: Commit** — `git commit -m "docs(bloat): per-need references — verdict lenses, planning artifacts + POLICY"`

---

### Task 10: SKILL.md — thin router (~90–110 lines)

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md` (full rewrite)

**Interfaces:**
- Consumes: Tasks 2–6 script CLIs, Task 8–9 references.
- Produces: the router every mode enters. GREEN (Task 18) grades agents running exactly this text.

- [ ] **Step 1: Rewrite SKILL.md** to contain, in order, and nothing else:
  1. **Frontmatter** — same `name`; description keeps the current triggers and appends chunk-executor phrasing, e.g. `…and whenever bloat analysis runs programmatically — a nightly sweep, PR gate, or a chunk-executor invocation given a manifest slice. Read-only — it proposes, a human approves, fixing-doc-bloat applies.` (No colon-space; description states when-to-use only, no workflow summary.)
  2. **The three non-negotiables** (evidence required / structured output / read-only propose-only) — condensed to ~10 lines from the current text, keeping "Approval of IDs is the only bridge."
  3. **Doc kinds** (~8 lines): living / narrative (`> As of` first-line anchor is the classifier, wherever the file sits) / planning; manifest `hint` is a hint — override only with stated evidence in the record.
  4. **Mode routing** (the core, ~30 lines):
     - *Interactive, small scope (≲2 chunks projected):* sweep inline; emit the wrapped v2 report; validate before presenting.
     - *Interactive, large scope:* run `plan-chunks.py` (invocation template below); dispatch **one subagent per chunk**, each given (i) its manifest chunk verbatim, (ii) `output-contract.md`, and (iii) only the reference file(s) its chunk's hints need (living/narrative → `references/verdict-lenses.md`; planning → `references/planning-artifacts.md`; policy chunks → `references/planning-artifacts.md` only); each writes `{"chunk": "<id>", "records": [...]}` to a results dir; seam-validate each with `--chunk --manifest`; re-dispatch a failing chunk fresh **once**, then stop and name it; `--assemble` the rest; never sweep inline instead.
     - *Headless (chunk executor):* "Read the manifest slice you are given, emit records for exactly those docs, write the chunk result, stop. Orchestration belongs to the workflow, not you." Policy chunk ⇒ exactly one `POLICY` record.
  5. **Script invocation templates** (verbatim, fenced):
```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/plan-chunks.py --out <dir>/manifest.json --results-dir <dir>/chunks
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py --chunk <dir>/chunks/<id>.json --manifest <dir>/manifest.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py --assemble <dir>/chunks --manifest <dir>/manifest.json --out bloat-report.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py bloat-report.json
```
  6. **Contract pointer** (~5 lines): record fields + `"schema": 2` + approval-by-ID, then "shapes, worked example, and chunk-result rules: `output-contract.md` — validate before any handoff."
  7. **Presentation** (~5 lines): for in-session triage, render with `python3 ${CLAUDE_PLUGIN_ROOT}/skills/scheduling-doc-sync/scripts/render-report.py bloat-triage --report bloat-report.json`, then ask for approved IDs; never paste raw JSON as the summary (data/presentation separation — the script owns the format).
  8. **Cross-links**: REQUIRED SUB-SKILL writing-docs for proposed replacement text; fixing-doc-bloat consumes the approved subset.
  9. **Red flags — STOP** (only the router-level ones, ≤8): no structured records; assertion-not-evidence; invented verdict; any edit (read-only); skipping the validator at any seam; a payload authored at detect time; a per-file walk of a policy chunk; inline mega-sweep when the projection says >2 chunks.

  Per-verdict rules, the DISTILL protocol, the presentation format, and the remaining red flags **must not appear here** — they live in the references, the distiller, and `render-report.py` respectively. Target 90–110 lines; hard cap 120.

- [ ] **Step 2: Verify** — `wc -l plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md` ≤ 120; every file path referenced exists; the four invocation templates run against the fixture without error (smoke: plan → executor step skipped → validate an empty assembled report path with `--allow-partial`).

- [ ] **Step 3: Commit** — `git commit -m "feat(bloat): SKILL.md thin router — modes, dispatch, harness templates"`

---

### Task 11: doc-distiller absorbs the DISTILL protocol

**Files:**
- Modify: `plugins/doc-lifecycle/agents/doc-distiller.md`

**Interfaces:**
- Consumes: a v2 `DISTILL ready` record — `id`, `doc` (artifact path), `evidence`; **no payload exists anywhere**.
- Produces: the same staged-single-commit output as today, but the agent now **authors** claims/insights/decision entry itself. Task 12's dispatch matches this contract.

- [ ] **Step 1: Rewrite the agent definition**:
  - Input contract: one approved `DISTILL` record with `status: "ready"` + the artifact path. Refuse anything else (wrong status, missing artifact) with the reason. Never act un-dispatched.
  - **New step 0 — author the residue (the protocol moved here from detect time):** re-verify the implementation landed (open the code the record's `evidence` cites; if it doesn't hold, stop and report — the approval was granted on stale evidence); then the **mandatory per-section insight walk** (lift the current SKILL.md step-3 text: "if this section vanishes, is there a decision, constraint, or deliberate absence a future maintainer could wrongly 'fix'?"); draft claims (each verified against the code it cites, target = the living doc it belongs in), insights (artifact-true, anchored `path @ SHA`, target a durable narrative doc, never restating a claim or the decision entry), and one decision entry. An empty insight set you can defend is common; an empty one because you never walked is a lossy distill.
  - Steps 1–8 of the current definition (re-verify → dedup → land extractions → land insights → append decision entry with real SHA → repoint inbound references → `git rm` → report) survive with s/`payload.claims[]`/"your drafted claims"/ etc. Keep the frontmatter `description` accurate (it now authors and applies; still "Dispatch from fixing-doc-bloat only"). Keep the hard touch-list rule verbatim.
  - Report format additionally opens with the drafted residue (claims/insights/entry as drafted) so the draft PR surfaces what the approver is accepting (design: "the approving human sees claims/insights in the resulting draft PR").

- [ ] **Step 2: Commit** — `git commit -m "feat(doc-distiller): absorb DISTILL protocol — author residue post-approval"`

---

### Task 12: fixing-doc-bloat — POLICY application + payload-less dispatch

**Files:**
- Modify: `plugins/doc-lifecycle/skills/fixing-doc-bloat/SKILL.md`

**Interfaces:**
- Consumes: v2 reports; Task 11's distiller contract.
- Produces: the apply-side routing GREEN scenario (b/c follow-through) and the workflow distill lane rely on.

- [ ] **Step 1: Edit the routing table and rules:**
  - Input line: report shape now `id / doc / location / verdict / evidence / proposal / status / files`, `"schema": 2`.
  - `DISTILL` row becomes: "dispatch **doc-lifecycle:doc-distiller** with the record (ID + artifact path + evidence) — the distiller authors the claims/insights/decision entry post-approval and stages one commit, which you then commit. `pending-implementation` is never actionable."
  - New `POLICY` row: "apply the record's `proposal` policy to **exactly the paths in `files`** — for a retirement-class policy, `git rm` those files in one commit; the record's `files` array is the complete mandate, never the directory's current contents. A policy you cannot apply mechanically as stated → stop, surface it. Approval of the ID is the deletion authorization."
  - Update the "DISTILL is the distiller's job" section: the dispatch input is the record, not a payload; expect back the drafted-and-landed residue report. Drop "re-verifies each `payload.claims[]`…" phrasing in favor of "authors and verifies its claims itself".
  - Stops: replace "DISTILL approved but pending" reason text ("carries `payload: null`" → "there is no landed code to verify against"); add "**POLICY approved but a `files` entry no longer exists** → apply the rest, note the missing path — never widen to the directory."
  - Red flags/rationalization rows mentioning payload-patching become "papering over a distiller verification failure"; add one POLICY row: "'The directory has two new artifacts since the sweep — I'll retire them too' → the `files` array is the mandate; new files are a finding for the next sweep."

- [ ] **Step 2: Commit** — `git commit -m "feat(fixing-doc-bloat): POLICY application; distiller dispatch without payloads"`

---

### Task 13: `sync-gate.py` — POLICY lane routing

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py:60-68`
- Test: `tests/scripts/sync-gate_test.py`

- [ ] **Step 1: Write failing tests** — in `sync-gate_test.py`, update `brec()` to v2 (`"files": None` instead of `"payload": None`) and add:

```python
    def test_policy_routes_to_distill_lane(self):
        recs = [dict(brec("POLICY", doc="docs/superpowers"),
                     files=["docs/superpowers/plans/a.md"])]
        dec, filtered = self._run(recs, "distill")
        self.assertEqual(dec, "open")
        self.assertEqual(len(filtered), 1)

    def test_policy_not_in_prune_lane(self):
        recs = [dict(brec("POLICY", doc="docs/superpowers"),
                     files=["docs/superpowers/plans/a.md"])]
        dec, filtered = self._run(recs, "prune")
        self.assertEqual(dec, "skip-empty")

    def test_v2_wrapped_report_with_schema_key_loads(self):
        # write {"schema": 2, "records": [...]} — load_records must accept it
```

- [ ] **Step 2: Run, verify FAIL** — `python3 tests/scripts/sync-gate_test.py` (POLICY currently routes nowhere).
- [ ] **Step 3: Implement** in `in_lane()`:

```python
    if lane == "distill":
        if verdict in DISTILL_DOC_VERDICTS or verdict == "POLICY":
            return True
        return verdict == "DISTILL" and record.get("status") == "ready"
```

(`load_records` already tolerates extra top-level keys — the schema test just pins it.)

- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(sync-gate): route POLICY to the distill lane"`

---

### Task 14: `render-report.py` — v2 rendering, rollups, `bloat-triage`

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py`
- Test: `tests/scripts/render-report_test.py`

**Interfaces:**
- Produces: `bloat-pr-body` (rollup line + v2 rows), `bloat-triage --report FILE` (the in-session grouped view Task 10 §7 invokes). All human presentation for bloat lives here — the skill text carries none.

- [ ] **Step 1: Write failing tests** — update `brec()` to v2 (`"files": None`, no `payload`); replace the two payload-count tests with:

```python
    def test_pr_body_opens_with_rollup(self):
        # [CUT, CONDENSE, POLICY] → body contains
        # "**Rollup:** 3 record(s) across 2 doc(s) — cut 1, condense 1, policy 1"
    def test_pr_body_distill_row_shows_status(self):
        # DISTILL status ready → "`DISTILL(ready)` @ `docs/plans/old.md`"
    def test_pr_body_policy_row_counts_files(self):
        # POLICY, files=[a, b] → "`POLICY` @ `docs/superpowers` (2 files)"
    def test_triage_groups_by_doc_with_ids(self):
        # bloat-triage over [CUT@README.md:5 id B1, POLICY@docs/superpowers id B2] →
        # stdout has a "README.md" heading line, an indented "[B1] CUT" line with
        # "README.md:5", a "docs/superpowers" heading, "[B2] POLICY" with "(1 files)"...
        # and ends asking for approved IDs? No — the script prints data only; the
        # closing ask is the skill's own sentence. Assert no "approve" text.
    def test_triage_missing_report_exits_2(self):
```

- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement:**

```python
def bloat_change_cell(r):
    where = r.get("location") or r.get("doc")
    verdict = r["verdict"]
    if verdict == "DISTILL":
        verdict = f"DISTILL({r.get('status')})"
    cell = f"`{verdict}` @ `{where}`"
    if r["verdict"] == "POLICY":
        cell += f" ({len(r.get('files') or [])} files)"
    return cell


def render_bloat_rollup(records):
    counts, docs = {}, set()
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        docs.add(r["doc"])
    order = ["CUT", "CONDENSE", "EXTRACT-AND-MOVE", "RETIRE-DOC",
             "MERGE-DOC", "DISTILL", "POLICY"]
    parts = [f"{v.lower().replace('-', ' ')} {counts[v]}" for v in order if v in counts]
    return (f"**Rollup:** {len(records)} record(s) across {len(docs)} doc(s) — "
            + ", ".join(parts))
```

`render_bloat_pr_body`: insert `render_bloat_rollup(records)` + blank line after the intro line; row loop becomes `lines.append(f"| {bloat_change_cell(r)} | {md_cell(r['evidence'])} |")` (payload block deleted). New:

```python
def render_bloat_triage(records):
    by_doc = {}
    for r in records:
        by_doc.setdefault(r["doc"], []).append(r)
    lines = [render_bloat_rollup(records), ""]
    for doc in sorted(by_doc):
        lines.append(doc)
        for r in by_doc[doc]:
            verdict = r["verdict"]
            if verdict == "DISTILL":
                verdict = f"DISTILL({r.get('status')})"
            where = r.get("location") or ""
            extra = f" ({len(r.get('files') or [])} files)" if r["verdict"] == "POLICY" else ""
            lines.append(f"  [{r['id']}] {verdict:<14} {where}{extra} — "
                         f"{md_cell(r['evidence'])}")
    return "\n".join(lines)
```

Subparser `btriage = sub.add_parser("bloat-triage"); btriage.add_argument("--report", required=True)`; dispatch `print(render_bloat_triage(records))`. Update the module docstring usage block.

- [ ] **Step 4: Run, verify PASS** — `python3 tests/scripts/render-report_test.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat(render-report): v2 bloat rendering — rollups, POLICY rows, bloat-triage"`

---

### Task 15: Workflow v2 — `doc-bloat.yml` template + install-skill updates

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml` (full rewrite)
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md` (install steps)
- Test: `tests/scripts/sync-gate_test.py` / `render-report_test.py` already pin gate/render wiring; add a YAML-shape pin (below)

- [ ] **Step 1: Rewrite the template.** Keep the header comment style, `{{BLOAT_CRON}}`, permissions, and concurrency; replace `detect` with `plan` → `sweep` (matrix) → `assemble`; keep `prune`/`distill` bodies except the noted prompt change. Full jobs section:

```yaml
jobs:
  plan:
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
    outputs:
      decision: ${{ steps.pre.outputs.decision }}
      pending: ${{ steps.chunks.outputs.pending }}
      prune_pr: ${{ steps.facts.outputs.prune_pr }}
      distill_pr: ${{ steps.facts.outputs.distill_pr }}
    steps:
      - uses: actions/checkout@v4
      - name: Gather facts
        id: facts
        run: |
          set -euo pipefail
          PRUNE_PR=$(gh pr list --head doc-bloat/prune --state open --json number --jq length)
          DISTILL_PR=$(gh pr list --head doc-bloat/distill --state open --json number --jq length)
          { echo "prune_pr=${PRUNE_PR}"; echo "distill_pr=${DISTILL_PR}"; } >> "$GITHUB_OUTPUT"
      - name: Gate (pre-sweep)
        id: pre
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py bloat-pre \
            --prune-pr-open "${{ steps.facts.outputs.prune_pr }}" \
            --distill-pr-open "${{ steps.facts.outputs.distill_pr }}")
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"
          python3 .github/doc-sync/render-report.py bloat-pre-summary --decision "${DECISION}"
      - name: Plan chunks (deterministic — no model)
        if: steps.pre.outputs.decision == 'detect'
        id: chunks
        run: |
          set -euo pipefail
          python3 .github/doc-sync/plan-chunks.py --out manifest.json
          echo "pending=$(python3 -c 'import json; print(json.dumps(json.load(open("manifest.json"))["pending"]))')" >> "$GITHUB_OUTPUT"
      - name: Upload manifest
        if: steps.pre.outputs.decision == 'detect'
        uses: actions/upload-artifact@v4
        with:
          name: bloat-manifest
          path: manifest.json

  sweep:
    needs: plan
    if: needs.plan.outputs.decision == 'detect' && needs.plan.outputs.pending != '[]'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        chunk: ${{ fromJson(needs.plan.outputs.pending) }}
    env:
      CHUNK_ID: ${{ matrix.chunk }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: bloat-manifest
      - name: Detect chunk (attempt 1)
        continue-on-error: true
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/aj604/toolshed.git
          plugins: doc-lifecycle@toolshed
          prompt: >-
            Use the doc-lifecycle:detecting-doc-bloat skill as a headless chunk executor.
            Read manifest.json in the repository root and find the chunk whose id is
            "${{ matrix.chunk }}". Audit exactly the docs that chunk lists — no others —
            and write the chunk result object {"chunk": "${{ matrix.chunk }}", "records": [...]}
            to chunks/${{ matrix.chunk }}.json. If nothing in the chunk is bloated, emit an
            empty records array.
          claude_args: --max-turns 15 --allowedTools "Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)"
      - name: Seam-validate (attempt 1)
        id: seam1
        continue-on-error: true
        run: python3 .github/doc-sync/validate-bloat-output.py --chunk "chunks/${CHUNK_ID}.json" --manifest manifest.json
      - name: Discard invalid result before retry
        if: steps.seam1.outcome != 'success'
        run: rm -f "chunks/${CHUNK_ID}.json"
      - name: Detect chunk (retry — fresh dispatch)
        if: steps.seam1.outcome != 'success'
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/aj604/toolshed.git
          plugins: doc-lifecycle@toolshed
          prompt: >-
            Use the doc-lifecycle:detecting-doc-bloat skill as a headless chunk executor.
            Read manifest.json in the repository root and find the chunk whose id is
            "${{ matrix.chunk }}". Audit exactly the docs that chunk lists — no others —
            and write the chunk result object {"chunk": "${{ matrix.chunk }}", "records": [...]}
            to chunks/${{ matrix.chunk }}.json. If nothing in the chunk is bloated, emit an
            empty records array.
          claude_args: --max-turns 15 --allowedTools "Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)"
      - name: Seam-validate (final)
        if: steps.seam1.outcome != 'success'
        run: |
          python3 .github/doc-sync/validate-bloat-output.py --chunk "chunks/${CHUNK_ID}.json" --manifest manifest.json \
            || { echo "::error::chunk ${CHUNK_ID} failed seam validation twice — this chunk's spend is discarded; every valid chunk is preserved as an artifact"; exit 1; }
      - name: Upload chunk result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bloat-chunk-${{ matrix.chunk }}
          path: chunks/${{ matrix.chunk }}.json
          if-no-files-found: ignore

  assemble:
    needs: [plan, sweep]
    if: always() && needs.plan.outputs.decision == 'detect' && needs.plan.outputs.pending != '[]'
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
    outputs:
      prune: ${{ steps.prune.outputs.decision }}
      distill: ${{ steps.distill.outputs.decision }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: bloat-manifest
      - uses: actions/download-artifact@v4
        with:
          pattern: bloat-chunk-*
          path: chunks
          merge-multiple: true
      - name: Assemble report (refuses partial results)
        run: python3 .github/doc-sync/validate-bloat-output.py --assemble chunks --manifest manifest.json --out bloat-report.json
      - name: Upload report artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bloat-report
          path: bloat-report.json
          if-no-files-found: ignore
      - name: Gate (prune lane)
        id: prune
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py bloat-lane \
            --report bloat-report.json --lane prune \
            --pr-open "${{ needs.plan.outputs.prune_pr }}" \
            --out "$RUNNER_TEMP/prune.json")
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"
          if [ "${DECISION}" != "open" ]; then
            python3 .github/doc-sync/render-report.py bloat-skip-summary --lane prune --reason "${DECISION}"
          fi
      - name: Gate (distill lane)
        id: distill
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py bloat-lane \
            --report bloat-report.json --lane distill \
            --pr-open "${{ needs.plan.outputs.distill_pr }}" \
            --out "$RUNNER_TEMP/distill.json")
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"
          if [ "${DECISION}" != "open" ]; then
            python3 .github/doc-sync/render-report.py bloat-skip-summary --lane distill --reason "${DECISION}"
          fi
```

`prune:`/`distill:` jobs: change `needs: detect` → `needs: assemble`, `needs.detect.outputs.X` → `needs.assemble.outputs.X`; bodies otherwise verbatim from the current file, except the distill prompt sentence becomes: `…apply EVERY record in bloat-report.json whose verdict is MERGE-DOC, RETIRE-DOC, or POLICY, or DISTILL with status "ready" — treat exactly those record IDs as the approved subset, and apply nothing else. DISTILL records dispatch the doc-distiller agent per the skill.` (The distill lane keeps `Task` in its allowlist — the distiller dispatch dies silently without it.)

- [ ] **Step 2: Add a wiring pin test** (append to `tests/scripts/render-report_test.py` or `sync-gate_test.py`, wherever the existing doc-bloat.yml pins live — follow that precedent): read the template text and assert it contains `plan-chunks.py --out manifest.json`, `--chunk "chunks/${CHUNK_ID}.json"`, `--assemble chunks --manifest manifest.json`, `--max-turns 15`, `fail-fast: false`, and does NOT contain `--allow-partial`. Run → FAIL first (old template), PASS after Step 1.

- [ ] **Step 3: Update `scheduling-doc-sync/SKILL.md`**: install step 3 also copies `../detecting-doc-bloat/scripts/plan-chunks.py` → `.github/doc-sync/plan-chunks.py`; step 5's parenthetical names `plan-chunks.py` (not `list-docs.py`) as the scope-config reader and mentions the optional `policy_scope`/`chunking` keys; step 7's commit list becomes **nine** files (adds `plan-chunks.py`); the "weekly bloat sweep" rules bullet adds `POLICY` to the distill lane's verdict list.

- [ ] **Step 4: Run the two wiring test files; verify PASS. Commit** — `git commit -m "feat(scheduling): doc-bloat workflow v2 — plan/matrix/assemble with seam retries"`

---

### Task 16: Dogfood install refresh (`.github/`)

**Files:**
- Modify: `.github/workflows/doc-bloat.yml`
- Modify: `.github/doc-sync/validate-bloat-output.py`
- Create: `.github/doc-sync/plan-chunks.py`

- [ ] **Step 1:** Read the current `.github/workflows/doc-bloat.yml` cron value; regenerate the file from the Task 15 template with `{{BLOAT_CRON}}` replaced by that value.
- [ ] **Step 2:** `cp plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py .github/doc-sync/validate-bloat-output.py && cp plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py .github/doc-sync/plan-chunks.py` (sync-gate.py / render-report.py likewise re-copied from their skill scripts). Leave `.github/doc-sync/audit-scope.json` untouched (tuned config) — its existing `exclude`/`include` keys are valid v2.
- [ ] **Step 3:** Smoke: `python3 .github/doc-sync/plan-chunks.py --root . --out /tmp/dogfood-manifest.json` succeeds and reports on stderr; `diff` each copied script against its source (identical).
- [ ] **Step 4:** Update the CLAUDE.md header paragraph's dogfood file list (add `doc-sync/plan-chunks.py`). Commit — `git commit -m "chore(dogfood): refresh doc-sync install to contract v2 + chunked workflow"`

---

### Task 17: Retire `list-docs.py`; repoint every reference

**Files:**
- Delete: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/list-docs.py`, `tests/scripts/list-docs_test.py`
- Modify: `CLAUDE.md` (script inventory paragraph: `list-docs.py` → `plan-chunks.py`)

- [ ] **Step 1:** `grep -rn "list-docs" --include="*.md" --include="*.py" --include="*.yml" .` — repoint every live reference (CLAUDE.md; anything Task 10/15 missed). Frozen `tests/baselines/**` records stay untouched (repo convention).
- [ ] **Step 2:** `git rm` the two files; verify `grep -rn "list-docs" .` hits only `tests/baselines/` and `docs/plans/` history.
- [ ] **Step 3:** Commit — `git commit -m "refactor(bloat): retire list-docs.py — absorbed by plan-chunks.py"`

---

### Task 18: GREEN baselines + REFACTOR — `tests/baselines/bloat-rearch-green/`

**Files:**
- Create: `tests/baselines/bloat-rearch-green/README.md`, `scenario-{a,b,c,d,e}.md`

**Interfaces:**
- Consumes: Task 7's scenarios/prompts verbatim, the rebuilt skill/agent text, the fixture, the answer key.

- [ ] **Step 1:** Re-run scenarios (a), (b), (c), (e) with **fresh subagents** given the REBUILT `SKILL.md` (+ the reference files a chunk executor would be handed, exactly as the router prescribes). Same prompts as RED, verbatim.
- [ ] **Step 2:** Scenario (d): run the scripted seam demo against the new validator — invalid chunk → exit 1 naming the chunk; assemble over the gap → "partial assembly refused" naming it; record outputs. (The workflow's one-retry wiring is pinned by Task 15 Step 2's test, not a model run.)
- [ ] **Step 3:** Fresh stakeless graders (never the author) grade each run against the answer key: (a) only the slice audited, valid chunk-result shape, zero off-allowlist tool attempts; (b) exactly one POLICY record, `files` = all 10 paths, zero per-file walks; (c) `DISTILL ready`, **no payload field**, evidence names `src/limiter.py`; (e) plan-chunks run, one dispatch per chunk, seam-validated, assembled — no inline mega-sweep.
- [ ] **Step 4: REFACTOR loop:** any FAIL → identify the rationalization verbatim, tighten the specific reference/router text it slipped through (rules for form: recipe over prohibition for shape failures, no nuance clauses), and **re-run that scenario with a fresh subagent** until PASS. Record every iteration in the scenario file.
- [ ] **Step 5:** Record + commit — `git commit -m "test(baselines): bloat-rearch GREEN — five scenarios vs the rebuilt skill"`

---

### Task 19: Continuity review, decision log, handoff, final verification

- [ ] **Step 1: Independent continuity review** (repo practice): dispatch one fresh subagent per flow — (i) interactive full audit end-to-end via the new SKILL.md, (ii) headless: template YAML → scripts → contract, (iii) apply-side: report → fixing-doc-bloat → doc-distiller — each answering "does this flow still read whole; any dangling reference (payload mentions, list-docs, v1 shapes)?" Fix what they find; **re-GREEN any scenario whose skill text changed** (read-review-only findings need a note, not a re-run).
- [ ] **Step 2: Decision log** — append to `docs/decisions.md` a dated entry carrying the design's four "Decisions worth logging" bullets (detect-time → post-approval distillation; POLICY with mandatory file provenance, config-declared and filter-selected; structural budgets with the run ceiling off by default; one skill + progressive disclosure, dispatch/matrix as the two chunk executors), `Code:` naming the two scripts + workflow, `Source:` the design doc path.
- [ ] **Step 3: Handoff + CLAUDE.md** — update `docs/plans/HANDOFF.md` (status: rearchitecture landed; baselines at `bloat-rearch-red/`/`bloat-rearch-green/`); CLAUDE.md conventions line for baselines gains the two new dirs; verify the CLAUDE.md script list edits from Tasks 16–17 are consistent.
- [ ] **Step 4: Full verification** (superpowers:verification-before-completion — run, don't assert):

```bash
for t in tests/scripts/*_test.py; do python3 "$t" || exit 1; done
claude plugin validate plugins/doc-lifecycle
python3 plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py --root tests/fixtures/plan-swarm | python3 -c "import json,sys; m=json.load(sys.stdin); assert len(m['chunks'])==4, m"
```
All green + validate passes. Commit remaining docs — `git commit -m "docs: decision log, handoff, baseline index for bloat rearchitecture"`.

- [ ] **Step 5: Post-merge follow-up (recorded, not executed here):** release + `claude plugin update doc-lifecycle@toolshed` re-install on career-compass, then a `workflow_dispatch` run — success criteria per design §Testing (valid v2 report, no permission-denial storm, minutes not tens of minutes, superpowers swarm → one POLICY record). Note this in HANDOFF.md.

---

## Self-review (performed at authoring time)

- **Spec coverage:** design components 1–5 → Tasks 10, 8–9, 2–6, 11, 15; contract v2 → Task 4 + consumers 12–16; testing section → Tasks 1 (fixture), 2–6/13–15 (unit), 7 (RED), 18 (GREEN), 19 (validate + real-world note). Out-of-scope per design: upgrade channel. ✓
- **Type consistency:** manifest keys (`schema/chunks/pending`, chunk `id/kind/docs/files/dir`, doc `path/lines/hint`), chunk result (`chunk/records`), record fields (8, with `files`), summary (7 keys), CLI flags (`--chunk/--manifest/--assemble/--out/--allow-partial`, `--out/--results-dir`) are identical across Tasks 2–6, 10, 15, 16. ✓
- **Placeholders:** skill-text tasks (8–12) deliberately carry content requirement lists rather than final prose — final wording is GREEN-governed (writing-skills RED→GREEN→REFACTOR); every rule they must encode is enumerated inline. Script/YAML/test tasks carry complete code. ✓
