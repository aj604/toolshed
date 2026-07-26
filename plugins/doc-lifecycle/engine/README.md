# doc-lifecycle engine

Stdlib-only Python package (`doclifecycle`) behind the plugin's skills and workflows. No
third-party dependencies. Library functions are the implementation; the commands wrap them and
add nothing, so an import and a command cannot disagree. The one external program it runs is
`git`, and only to read a repository's identity and HEAD when checking a report's freshness.

Current surface: the registry parser, the document inventory, path authorization, and the
report contract. Segmenter, cache, approval sets, and the applier land in later slices of the
re-architecture (issue #57).

## Modules

| Module | Owns |
|---|---|
| `doclifecycle/registry.py` | registry parsing, validation, classification, glob matching, registry digest |
| `doclifecycle/inventory.py` | `build_inventory()`, the closed-world walk, document/inventory digests |
| `doclifecycle/paths.py` | `authorize_path()`, `classify_target()`, the canonical path form and target classes |
| `doclifecycle/report.py` | `validate_report()`, `load_report()`, `current_lineage()`, lineage and report digests |
| `doclifecycle/render.py` | `render_report()` — Markdown from a validated `Report`, and nothing else |
| `doclifecycle/repository.py` | repository identity and base commit, read from git |
| `doclifecycle/results.py` | `Problem`, `Invalid`, the five result states, the `ok`/`invalid` status strings |
| `doclifecycle/digest.py` | `sha256_file`, `sha256_canonical`, the canonical JSON form digests are taken over |
| `doclifecycle/cli.py`, `__main__.py`, `doc-lifecycle.py` | argv parsing and exit codes only |

`__init__.py` holds the three versions lineage pins: `ARTIFACT_SCHEMA_VERSION` (the shape of
the payloads below), `RULESET_VERSION` (the audit policy), and `PLUGIN_VERSION` (which must
track `plugins/doc-lifecycle/.claude-plugin/plugin.json`; `tests/engine/report_test.py` fails
when they drift).

## The registry

`.doc-lifecycle/registry.json` (override with `--registry`). It owns classification;
content-coupled facts (as-of, anchors, lifecycle state) stay in the documents.

```json
{
  "schema_version": 1,
  "roots": ["docs", "CLAUDE.md"],
  "exclude": ["docs/vendor"],
  "sets": ["adr"],
  "extensions": [".md"],
  "rules": [
    {"glob": "docs/**/*.md", "kind": "living"},
    {"glob": "docs/adr/*.md", "kind": "narrative", "set": "adr"}
  ]
}
```

- `roots` (required, non-empty) — declared documentation roots. A root is a subtree or a
  single file. Roots may not overlap or repeat (`registry-overlapping-root`), so a document
  belongs to exactly one root. Classification is closed-world *within* the roots: a document
  under a root that no rule claims is an `unregistered-document` finding; a file outside every
  root is not documentation and is not reported.
- `rules` (required) — evaluated in order, **last match wins**, so broad defaults go first
  and narrower overrides after. `kind` is `living`, `narrative`, or `planning`. `set` is
  optional and must be declared in `sets`.
- `exclude` (optional) — paths skipped entirely, neither inventoried nor reported. Naming a
  directory excludes everything beneath it, and the subtree is pruned rather than walked.
- `extensions` (optional, default `[".md"]`) — which files under a root are documents, and so
  what the closed-world rule covers. Files with other suffixes are not documentation and are
  not reported; widen this list rather than leaving formats silently outside coverage.
- Globs: `*` and `?` stop at `/`; `**/` spans zero or more directories, so
  `docs/**/*.md` matches both `docs/a.md` and `docs/deep/a.md`.

Validation fails closed and reports every problem it finds in one pass. An unparseable,
unreadable, or invalid registry — including a declared root that does not exist — yields
`status: "invalid"` with typed problems and **no** documents: never a partial inventory.
Symlinks under a root are reported as `symlinked-path` and never followed. The inventory walk
enumerates; `paths.authorize_path()` below decides what may be read or written, and the applier
slice (issue #69) is what routes through it.

## Inventory command

From a plugin checkout, with nothing to set up:

```bash
python3 <plugin>/engine/doc-lifecycle.py inventory --repo . --registry .doc-lifecycle/registry.json
```

Equivalently, with the engine directory on `PYTHONPATH`:

```bash
python3 -m doclifecycle inventory --repo .
```

Both flags are optional (`--repo` defaults to the current directory). Exit codes: `0` the
run completed — findings are data, not a gate; `1` the run is invalid; `2` usage error.

Real output for a repository containing exactly `.doc-lifecycle/registry.json` (root `docs`,
one rule `docs/adr/*.md → narrative, set adr`), `docs/adr/0001-use-json.md` holding
`# 1. Use JSON`, and an unregistered `docs/notes.md` holding `# Notes`:

```json
{
  "status": "ok",
  "schema_version": 1,
  "registry": {
    "path": ".doc-lifecycle/registry.json",
    "digest": "f3188f08325acfcd2522439e2678df48cedc211739046661349e49c96ee3ddb1"
  },
  "digest": "6e2d949654d63ba6792a84438718e2d91b21139a90ed00dab5f7c93cb6759b05",
  "documents": [
    {
      "path": "docs/adr/0001-use-json.md",
      "kind": "narrative",
      "set": "adr",
      "rule": "docs/adr/*.md",
      "digest": "3066549a907fd6462e87041895ef45d9e22380d7345df1e9b307c4fcc102b05d"
    }
  ],
  "findings": [
    {
      "code": "unregistered-document",
      "path": "docs/notes.md",
      "message": "docs/notes.md is under declared root 'docs' but matches no registry rule — classify it or exclude it"
    }
  ]
}
```

The registry and inventory digests above hold only for that exact registry text's *meaning*
and those file bytes; reformatting the registry leaves them unchanged.

An invalid run prints the same payload shape with `"status": "invalid"` and a `problems`
array, repeats each problem on stderr, and exits 1.

The library call behind it:

```python
from doclifecycle.inventory import build_inventory

result = build_inventory(".")          # → Inventory (status "ok") or Invalid
result.to_dict()                       # → the payload above, as a dict
```

## Path authorization

`doclifecycle/paths.py` decides what may be read or written on behalf of a record. It is the
engine's one place for that decision by design; the applier slice (issue #69) is the caller that
routes through it, and until then nothing in the engine calls it.

For a repository where `docs/architecture.md` exists as a regular non-symlinked file:

```python
from doclifecycle.paths import authorize_path

decision = authorize_path("docs/architecture.md", repo_root=".", roots=("docs",))
decision.authorized      # True
decision.path            # "docs/architecture.md" — the canonical form, or None when refused
decision.root            # "docs" — the declared root containing it, or None
decision.target_class    # "documentation"; on a class refusal, the class detected instead
decision.problem         # None, or a results.Problem with a typed code
```

`roots` are repository-relative, each a subtree or a single file. `target_class` defaults to
`"documentation"` and is the only value `DECLARABLE_TARGET_CLASSES` accepts — the dangerous
classes are not a default a record, a plan, or a consumer config can switch off.

A verdict is a function of the path, the roots, the target class, and the state of `repo_root` on
disk: the same inputs always give the same `Authorization`, and nothing else is consulted. The
disk is part of the question because an alias is only visible there — `classify_target()` below is
the half that is pure, and the rest of the checks resolve what the path actually points at.

Refusal, not repair: `docs//a.md` is refused rather than rewritten to `docs/a.md`, so one file
never has two authorizable spellings. There is no partial verdict — a refusal carries no path.

Checks run in the order below, and the first one that fires is the verdict.

| Code | Refused because |
|---|---|
| `path-empty` | empty or blank |
| `path-control-character` | a Unicode `Cc`/`Cf`/`Cs`/`Co`/`Cn` character, including invisible reordering ones |
| `path-absolute` | leading `/` or `~`, or a drive letter |
| `path-separator` | `\` used as a separator |
| `path-whitespace` | any whitespace, leading, trailing, or interior |
| `path-unicode-non-canonical` | not in Unicode NFC form |
| `path-traversal` | a `..` component |
| `path-non-canonical` | a `.` or empty component — `./`, `//`, or a trailing `/` |
| `path-leading-dash` | a component starting with `-`, which reads as an option |
| `roots-undeclared` | no roots were declared, so nothing is eligible |
| `roots-invalid` | a declared root is not itself canonically spelled |
| `target-class-undeclarable` | the caller named a class the engine never writes |
| `repo-root-missing` | `repo_root` is not a directory |
| `path-outside-root` | canonical, but under none of the declared roots |
| `root-missing` | the containing root is not in the repository |
| `path-case-mismatch` | an existing entry differs only by case |
| `path-unicode-collision` | an existing entry differs only by Unicode normalization |
| `path-unreadable` | a directory on the way cannot be listed, so collisions are unknown |
| `symlinked-path` | the path or one of its ancestors is a symlink |
| `path-not-a-file` | not a regular file — a directory, a fifo, or an ancestor that is a file |
| `path-hardlinked` | more than one name points at the file |
| `path-executable-mode` | the file is marked executable |
| `path-forbidden-class` | its class is not the declared target class |

`classify_target(path)` is the pure classifier behind `path-forbidden-class`, returning
`documentation`, `workflow`, `source`, `configuration`, `credential`, `hook`, `executable`, or
`other`. It is ordered most-dangerous-first, matches case-folded (the filesystems this runs on
fold case, so `.GIT/hooks/` is the hooks directory), and matches directory prefixes at a
component boundary anywhere in the path — so `docs/.github/workflows/ci.yml` is `workflow`, not
documentation, and living under a documentation root launders nothing. `other` is the fallback
rather than `documentation`: eligibility is a positive list, so an unrecognized shape is refused
too.

A path that does not exist yet is authorizable — `create-document` must be able to name its
target before anything is written there. Ancestors that do exist are still checked, so a new
file cannot be created behind an alias or under a case-folded twin of an existing directory.

## Report contract

A report states what an audit examined and what it found, pinned to everything that could have
changed a verdict. It is proof of examination, never authority to change anything.

```json
{
  "status": "findings",
  "schema_version": 1,
  "lineage": {
    "repository": "root-commit:78fb71f315504323f1c3f86700d59fb7ad142ce0",
    "base_commit": "78fb71f315504323f1c3f86700d59fb7ad142ce0",
    "audit_mode": "full",
    "inventory_digest": "1ffcaa227f1de698d7b215f3cb011af6b08743a30b8f7a6bc88417a4557fa511",
    "audit_config_digest": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "registry_digest": "1d9176534bcc15f5fe5062503110be01ea198bb8ce65179230af4b226f56d85e",
    "ruleset_version": 1,
    "plugin_version": "0.14.0",
    "evidence_boundary": {"sources": ["src/**"], "excluded": []}
  },
  "records": [
    {"id": "DRIFT-001", "digest": "aaaa…aaaa", "code": "STALE", "path": "docs/architecture.md"}
  ],
  "incomplete": [],
  "digest": "4ef1a371593e4ed9825e6102e9fb82230f064010b5cf77b1db320edb99a9c81b"
}
```

### Lineage

Every field below is required; omitting one is `report-missing-lineage-field`, never a default.

| Field | Is | Checked against the repository as |
|---|---|---|
| `repository` | the origin remote (`origin:host/path`) if one is declared, else `root-commit:<sha>` | `lineage-repository-mismatch` |
| `base_commit` | git HEAD when the evidence was read; 40 or 64 lowercase hex | `lineage-base-commit-mismatch` |
| `audit_mode` | `full`, `incremental`, or `chunk` — what "the declared scope" meant | not compared |
| `inventory_digest` | the corpus examined | `lineage-inventory-mismatch` |
| `audit_config_digest` | the consumer configuration the run used | `lineage-audit-config-mismatch`, only when the caller supplies the current one |
| `registry_digest` | the classification that decided the corpus | `lineage-registry-mismatch` |
| `ruleset_version` | the audit policy applied; positive integer | `lineage-ruleset-mismatch` (vs `RULESET_VERSION`) |
| `plugin_version` | the engine that applied it | `lineage-plugin-mismatch` (vs `PLUGIN_VERSION`) |
| `evidence_boundary` | `{"sources": [...], "excluded": [...]}` — the declared limit of what the run could consult; `sources` non-empty | not compared |

`schema_version` is lineage too — it pins the shape of everything above — but it lives at the
report's top level, where every other engine artifact carries it, rather than being spelled
twice in two places that could disagree. A version this engine does not read is
`report-schema-version`: migrate the report, never guess at a shape.

Path *authorization* for `evidence_boundary` globs — traversal, symlinks, forbidden target
classes — is issue #67's single owner. The contract checks shape and log hygiene only; a
boundary is lineage here, never opened.

### The five result states

| State | Means | Exit |
|---|---|---|
| `clean` | the declared scope was examined; no records | 0 |
| `findings` | the declared scope was examined; records found | 0 |
| `partial` | the scope was **not** fully examined, so a missing record proves nothing; `incomplete` names each unexamined scope and why | 4 |
| `stale` | structurally sound, but the lineage no longer matches the repository; `stale_reasons` names every field that moved, with reported and current values | 3 |
| `invalid` | cannot be trusted: typed `problems` and **no** content | 1 |

A producing run declares only `clean`, `findings`, or `partial`, and the declaration must
follow from the content — `incomplete` entries force `partial`, records force `findings`,
neither is `clean`. Declaring anything else is `report-invalid-status`; disagreeing with the
content is `report-state-inconsistent`. `stale` and `invalid` are verdicts a validator reaches
about a report, so a run cannot self-assess them. `invalid` always beats `stale`: an
unreadable report has nothing to compare against a repository.

Records are validated only as far as approval binding needs — a non-empty `id` and a sha256
`digest`, both unique within the report. Every other field a detector or the segmenter (#63)
puts on a record travels through untouched.

### Commands

```bash
python3 -m doclifecycle validate-report --report report.json --repo . \
  --audit-config-digest <sha256>
python3 -m doclifecycle render-report --report report.json
```

`--report` is required. Without `--repo` the check is structural only and can never return
`stale`: the validator does not guess at a repository state it was not shown.
`--audit-config-digest` adds configuration drift to the freshness check. Both commands exit
with the verdict's code from the table above (2 is a usage error), and repeat the reason —
problems, stale reasons, or unexamined scopes — on stderr.

`render-report` prints Markdown, and prints **nothing** when the report is invalid: rendering
takes a validated `Report` and raises `TypeError` on anything else, so malformed content
cannot reach a PR body or a CI summary wearing the appearance of a verdict.

The library calls behind them:

```python
from doclifecycle.report import current_lineage, load_report, validate_report
from doclifecycle.render import render_report

state, problems = current_lineage(".")     # the lineage a fresh report must carry
result = load_report("report.json", repo_root=".")   # → Report or Invalid
result.to_dict()                                     # → the payload above
render_report(result)                                # → Markdown, or TypeError
```

A run that cannot read the repository state — not a git repository, git unavailable, or a
registry that no longer parses — is `repository-state-unavailable` and `invalid`. Freshness is
a comparison against the world; a check that cannot see the world fails closed rather than
certifying a report it did not check.

## Digests

`digest.sha256_canonical` hashes the canonical JSON form (sorted keys, compact separators),
so reformatting a registry is not a new registry while changing a rule is. Rule order is part
of the registry digest because it decides precedence; root, exclude, set, and extension order
is normalized away. A document's digest is the sha256 of its bytes. The inventory digest covers
the registry digest, every document entry, and each finding's code and path — not finding
messages, which are prose.

A report's digest covers its schema version, lineage, records, and unexamined scopes — not its
result state or stale reasons. Approval binds to that digest, so the same report keeps one
identity whether a validator reads it fresh or long after it went stale. A report that declares
a `digest` which does not match its content is `report-digest-mismatch`: altered since it was
produced.

## Tests

`tests/engine/*_test.py` (stdlib `unittest`), run by ordinary discovery, which is also how
CI runs them (`.github/workflows/release.yml`, "Engine tests"):

```bash
python3 -m unittest discover -s tests/engine -p '*_test.py'
```

Seams under test: the library calls (`build_inventory()`, `authorize_path()`,
`validate_report()`, `load_report()`, `current_lineage()`, `render_report()`), and the commands
as subprocesses whose payload must equal the library result. Path authorization has no command
of its own — it is substrate the other components call. Shared fixtures live in
`tests/engine/support.py`; the report suites build real git repositories, because staleness is
a comparison against a repository and a mocked one would prove nothing.
