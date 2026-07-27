# doc-lifecycle engine

Stdlib-only Python package (`doclifecycle`) behind the plugin's skills and workflows. No
third-party dependencies. Library functions are the implementation; the commands wrap them and
add nothing, so an import and a command cannot disagree. The one external program it runs is
`git`, and only to read: a repository's identity and HEAD, which paths a commit range changed,
and when a path last changed. Nothing here writes to a repository.

Current surface: the registry parser, the document inventory, path authorization, the report
contract, the lineage-keyed cache, the segmenter, finding identity, the context index, the
bloat lane, and the drift audit. Approval sets and the applier land in later slices of the
re-architecture (issue #57).

## Modules

| Module | Owns |
|---|---|
| `doclifecycle/registry.py` | registry parsing, validation, classification, glob matching, registry digest |
| `doclifecycle/inventory.py` | `build_inventory()`, the closed-world walk, document/inventory digests |
| `doclifecycle/paths.py` | `authorize_path()`, `classify_target()`, the canonical path form and target classes |
| `doclifecycle/segment.py` | `segment_text()`, `segment_document()`, the unit kinds and unit digests |
| `doclifecycle/finding.py` | `build_finding()`, `record_classifications()`, finding digests, the assertion classes |
| `doclifecycle/context.py` | `build_context_index()`, occurrences, ownership, the index and per-document context digests |
| `doclifecycle/bloat.py` | `plan_chunks()`, `plan_repository_chunks()`, `merge_contention()`, `enumerate_scope()`, `record_verdicts()`, the chunk cache seam |
| `doclifecycle/drift.py` | `plan_drift_audit()`, `audit_drift()`, `load_verdicts()`, the verdicts and anchor checks |
| `doclifecycle/report.py` | `validate_report()`, `load_report()`, `current_lineage()`, `state_from_content()`, lineage and report digests |
| `doclifecycle/render.py` | `render_report()` — Markdown from a validated `Report`, and nothing else |
| `doclifecycle/repository.py` | `lineage()`, `resolve_commit()`, `changed_paths()`, `last_change()` — everything read from git |
| `doclifecycle/cache.py` | `cache_key()`, `put()`, `get()` — the lineage-keyed cache and its payload revalidation |
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

## Assertion units

Segmentation splits a document into the smallest pieces an audit can reach a verdict about. It
is a fixed structural parser and nothing else: no model, no network, no subprocess, so the same
bytes always produce the same units and the same digests.

| Kind | Is | Can carry a claim |
|---|---|---|
| `sentence` | one sentence of a paragraph | yes |
| `list_item` | one list item, its continuation lines folded in | yes |
| `table_row` | one body row of a pipe table | yes |
| `block_quote` | one sentence inside a block quote | yes |
| `heading` | an ATX or setext heading | no |
| `table_header` | a table's header row | no |
| `code_block` | a fenced or indented block | no |
| `front_matter` | the metadata fence at the top of a file | no |
| `html_block` | an HTML block or comment | no |

The right-hand column is the point. A heading names a section, a code block is an example, an
HTML comment is not prose: those kinds are *non-assertive capable*, and
`record_classifications()` below refuses any class but `non-assertive` against them — so
structure cannot be turned into a claim and then "verified". What a capable unit actually
asserts is the model's call, never the parser's: connective prose ("For example:", "See the
runbook.") is structurally a sentence, and reaches `non-assertive` as a recorded class rather
than by being detected here — the parser has no way to tell connective prose from a claim, and
a parser that guessed would be the judgment this module exists to keep out. Fence markers,
table delimiter rows, and thematic breaks carry no content and are not units at all.

Unit text is whitespace-normalized (runs collapse to one space), so re-wrapping a paragraph,
renumbering a list, and repadding a table column all preserve identity. `code_block` and
`front_matter` keep their text verbatim, because there the whitespace is content.

Sentence boundaries follow one fixed rule: a terminator run (`.`, `!`, `?`) plus any closing
quotes or brackets ends a sentence when it is followed by whitespace or the end of the text,
the word it closes is neither a known abbreviation nor an initial, and the next visible
character opens a sentence (a capital, a digit, or an opening delimiter). Terminators inside an
inline code span are invisible to it. Everything else is one sentence.

A unit's digest covers its kind and its normalized text, and nothing else — not the document,
not the line, not the schema version, not what a model said. Two documents holding the same
sentence therefore hold one unit identity, which is exactly what a duplication audit needs;
`ordinal`, `line`, and `end_line` travel alongside for a reader and never inside the digest. A
segmentation's own digest covers the ordered list of unit digests, so moving a sentence keeps
that sentence's identity and re-keys the document.

### Segment command

```bash
python3 -m doclifecycle segment --repo . --path docs/architecture.md
```

`--path` must be a document in the inventory: the registry decides what a document is, so an
unregistered, excluded, or symlinked path is `document-not-inventoried` and exits 1 rather than
being opened, and an invalid registry invalidates the run as it does everywhere else. A
document that is not valid UTF-8 is `document-unreadable`.

Real output for a repository whose registry declares root `docs` with one rule
`docs/**/*.md → living`, and whose `docs/architecture.md` holds `# Architecture`, a blank line,
and `The service charges a flat 2% fee.`:

```json
{
  "status": "ok",
  "schema_version": 1,
  "path": "docs/architecture.md",
  "kind": "living",
  "document_digest": "58202ed1a03a7f70aa61f0aa04ac8ca05daf1e51d97f7eaf4be24e4f4f8ffe04",
  "digest": "ce97bf28f7e9ac2a1a10ea750e0c1d5a49f344cc735d7eeb170e99b4022ebbf2",
  "units": [
    {
      "ordinal": 0,
      "kind": "heading",
      "text": "Architecture",
      "line": 1,
      "end_line": 1,
      "assertion_capable": false,
      "digest": "fa282a374fb12b2e52801ec0daf273b933c41a5d2304f5936bd3bd53608de415"
    },
    {
      "ordinal": 1,
      "kind": "sentence",
      "text": "The service charges a flat 2% fee.",
      "line": 3,
      "end_line": 3,
      "assertion_capable": true,
      "digest": "b99ecee54f68805635513f5e2e8a93d4e7d6ae037d0d05fa0a3426254b7b155a"
    }
  ]
}
```

`document_digest` is the sha256 of the file's bytes — the same digest the inventory reports for
that document.

The library calls behind it:

```python
from doclifecycle.segment import segment_document, segment_text

segment_text("Fees are 2%.\n")                   # → Segmentation; pure and model-free
segment_document(".", "docs/architecture.md")    # → Segmentation or Invalid
```

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
    "plugin_version": "0.19.0",
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
| `inventory_digest` | the document inventory examined | `lineage-inventory-mismatch` |
| `audit_config_digest` | the consumer configuration the run used | `lineage-audit-config-mismatch`, only when the caller supplies the current one |
| `registry_digest` | the classification that decided the inventory | `lineage-registry-mismatch` |
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

### Declared scope

A result state says whether the *declared* scope completed. Only the optional
`scope` block says what was declared:

```json
"scope": {
  "basis": "full inventory: every living and narrative document the registry classifies",
  "documents": ["docs/architecture.md", "docs/guides/onboarding.md"]
}
```

`basis` states how the scope was derived, `documents` enumerates it, and both are checked:
exactly those two fields, a non-empty single-line basis, and single-line paths no two of which
repeat (`report-invalid-scope`). An empty `documents` list is a real answer — a diff-scoped run
whose range touched no document declared nothing.

The block is part of the report's digest, because two runs finding the same records over
different scopes are not the same report: one examined more than the other. It is optional, and
a report that declares no scope digests exactly as it did before the field existed — so a
producing run that says nothing about scope is not silently re-keyed, and the reader falls back
to `audit_mode`, which is required.

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
neither is `clean`. Disagreeing with the content is `report-state-inconsistent`. "The declared
scope" is the one `audit_mode` names: a `chunk` run that finished its chunk is `clean` about
that chunk, and a reader who needs more must read the mode.

`stale` and `invalid` are verdicts a validator reaches about a report, so a producing run
cannot self-assess them, and `invalid` always beats `stale` — an unreadable report has nothing
to compare against a repository. A payload may still carry `stale` with its `stale_reasons`,
because `validate-report` emits exactly that and a pipeline must be able to re-check the file
it persisted: re-validating without `--repo` keeps the verdict (nothing can disprove it), and
re-validating against a repository that matches on every field this run actually compared
clears it. `invalid` never appears in a report at all — an invalid run has no content to
report — so declaring it is `report-invalid-status`.

Note that `plugin_version` is compared, so every plugin release marks prior reports stale.
That is deliberate: cheaper than reasoning about which releases could have changed a verdict,
and re-running an audit is cheap.

Records are validated only as far as approval binding needs — a non-empty `id` and a sha256
`digest`, both unique within the report; no `NaN`/`Infinity` anywhere inside (JSON defines
neither, and the digest is taken over that encoding); and no nesting past 64 levels
(`report-nesting-too-deep`), since the digest and the renderer both walk the structure and a
few kilobytes of brackets must be a verdict rather than a stack overflow. Every other field the
audit engine or `finding.py` puts on a record travels through untouched — and is
neutralized at the rendering boundary rather than at the contract boundary; see Commands below.

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

These codes are the engine's own. The scripts it is absorbing (`scheduling-doc-sync`'s
`sync-gate.py` and friends) use `2` for "cannot read the report" where the engine uses `1` and
reserves `2` for a usage error; the two conventions coexist until #57 finishes absorbing them.

`render-report` prints Markdown, and prints **nothing** when the report is invalid: rendering
takes a validated `Report` and raises `TypeError` on anything else.

Type-checking is not the whole guarantee, because the contract deliberately does not police
record internals, and those fields carry text a model read out of repository documents. So
every string the renderer interpolates — lineage, scopes, record ids, and every record field,
**key as well as value** — is emitted inside a Markdown code span. There are exactly two ways
out of such a span and both are shut: a backtick run as long as the fence, so the fence is
fitted one longer than the longest run inside; and a line break, so control characters
(`U+2028` and `U+2029` included) are escaped rather than emitted. The span builder does this
itself rather than trusting its callers, because a caller that forgets is precisely how the
key path stayed open once. The records section is one line per record, always.

A record therefore cannot add a heading, a link, a table, a second `## Records` section, or a
`**Result:**` line to what a human reads before approving. Nothing is withheld to achieve
that: keys and values are shown as the canonical JSON the digest is taken over, and anything
too long to show inline is truncated with a marker naming how many characters were elided and
the sha256 of the whole value.

The library calls behind them:

```python
from doclifecycle.report import current_lineage, load_report, validate_report
from doclifecycle.render import render_report

state, problems = current_lineage(".")     # the lineage a fresh report must carry
result = load_report("report.json", repo_root=".")   # → Report or Invalid
result.to_dict()                                     # → the payload above
render_report(result)                                # → Markdown, or TypeError
```

A run that cannot read the repository state — not a git repository, git unavailable, git
hanging past 30s, or a registry that no longer parses — is `repository-state-unavailable` and
`invalid`. Freshness is a comparison against the world; a check that cannot see the world fails
closed rather than certifying a report it did not check. The repository is the one `--repo`
names and no other: `git` runs with `GIT_DIR`, `GIT_WORK_TREE`, and the rest of the redirecting
variables scrubbed from its environment, so an exported variable cannot walk around the
check that `--repo` is a repository root.

Clearing a stale verdict is as thorough as setting it. A carried reason is only dropped when
this run actually compared the lineage field that produced it — so re-validating a
config-mismatch-stale report *without* `--audit-config-digest` leaves it stale rather than
laundering it clean with a weaker check.

Identity note: the `root-commit:` fallback is only as stable as the history it reads. A
`--depth 1` clone of a remoteless repository reports its shallow boundary and so reads as a
different repository — safe (stale, never certified), but a repository audited in CI wants
either an origin remote or full history.

## Cache

A cached semantic result is a derived artifact: it cannot outlive the inputs that could have
changed the judgment it records. `cache.cache_key()` folds every one of them into a single
lookup key — document bytes, source-evidence bytes, the document inventory, the consumer's audit
configuration, the registry, the ruleset version, the artifact schema version, the plugin
version, and the repository/base-commit identity (`report.current_lineage()` supplies everything
but the first two). Two keys differing in exactly one of those fields hash to different cache
slots, so changing any one of them is a miss, never a stale hit.

```python
from doclifecycle.cache import cache_key, get, put
from doclifecycle.report import current_lineage

state, problems = current_lineage(".", audit_config_digest=my_config_digest)
key = cache_key(document_digest, source_digest, state)

put(cache_dir, key, {"id": "DRIFT-001", "digest": "..."})   # store one result
result = get(cache_dir, key, repo_root=".")                 # result.hit, result.record
```

A key match alone is not a hit. On read, the stored entry is wrapped in the same shape a report
is and run through `report.validate_report` — the landed validator, not a parallel one — so a
parseable-but-invalid record, a lineage that no longer matches the repository (a different
repository or commit, a moved registry or inventory, a bumped ruleset or plugin, a changed audit
configuration), or a result admitting it did not finish are each a miss (`MISS_INVALID`,
`MISS_STALE`, `MISS_INCOMPLETE`). Because a cache entry is about one document checked against one
piece of source evidence — which the report contract's lineage does not model — the entry's
declared `document_digest`/`source_digest` are also compared against the key's, so a payload that
validates cleanly but names a different document or source (a mismatched chunk sitting at the
right path) is `MISS_IDENTITY` rather than a false hit. Every other way to fail — the entry was
never written (`MISS_NOT_FOUND`), or its JSON does not parse (`MISS_CORRUPT`) — is a miss too.
There is no path that returns a stale or unverified payload; a hit is exactly the case where every
check above passed.

## Finding identity

A finding groups one or more assertion units in one document under one finding code. Its digest
is taken over exactly that, plus the report lineage it was produced under
(`report.lineage_digest()`, the lineage digested alone — a record cannot use the report's own
digest, which covers the records).

| Moves a finding digest | Cannot move it |
|---|---|
| a unit's content (a unit digest *is* its content) | the display id |
| the grouping — which units, how many | the message and any evidence prose |
| the document | the recorded assertion classes |
| the finding code | the order the units were listed in |
| any lineage field | listing the same unit twice |
| `ARTIFACT_SCHEMA_VERSION` | |

The document and the finding code are in there because unit identity deliberately is not:
the same sentence in two documents is one unit, and a drift finding and a bloat finding can
group the same units — without both fields those would collide into one digest, which the
report contract rejects as `report-duplicate-record` and an approval set could not tell apart.
Both err toward a digest that moves too readily, and the failure that produces is an approval
honestly refused.

The group is normalized — sorted and deduplicated — before hashing, because it is a set of
units rather than a sequence. That split is what approval rests on: an approval set selects a
record by digest, and no renumbering, rewording, or re-classification can point that selection
at a different finding.

```python
from doclifecycle.finding import build_finding, record_classifications

finding = build_finding(lineage=lineage, code="STALE", path="docs/architecture.md",
                        units=(unit_digest,), record_id="DRIFT-001",
                        extra={"message": "the rate is 2.5%, not 2%"})
finding.digest        # the identity approval binds to
finding.to_record()   # the report record: id, digest, code, path, units, and extra
```

`build_finding()` returns a `Finding` or an `Invalid` naming every problem
(`finding-invalid-field`, `finding-no-units`, `finding-invalid-unit`,
`finding-reserved-field`); a `lineage` that is not a `Lineage` is a `TypeError`, because
identity not pinned to a run is a programming error rather than bad data. `extra` is the
reviewable data the record carries and may not shadow a field the record owns.

### Assertion classes

The model's only role in the document model is saying what each capable unit is: `factual`
(needs evidence), `normative` (needs an owner or source), `rationale` (explains why), or
`non-assertive` (connective, illustrative, or signposting prose — a real answer, not the
absence of one). `record_classifications(segmentation, entries)` validates that answer before
it is written down anywhere, over entries shaped `{"unit": <digest>, "assertion_class": <one of
the four>}`.

| Code | Refused because |
|---|---|
| `classification-invalid-shape` | not a list of `{unit, assertion_class}` objects |
| `classification-unknown-class` | not one of the four |
| `classification-unknown-unit` | no unit in this segmentation has that digest |
| `classification-not-assertion-capable` | a class other than `non-assertive` against structure |
| `classification-duplicate` | one unit, two answers |
| `classification-missing` | a capable unit nobody classified |

Every problem in one response is reported in one pass, and any problem records nothing: a
partially trusted classification set is one nobody can tell the trustworthy half of. The result
is keyed to the segmentation digest, and recording a class changes no unit or finding digest.

## Context index

A bloat verdict is a judgment about value, and value is never local: a passage is redundant
only relative to the rest of the corpus, and content is misplaced only relative to which
document owns the subject. So the whole repository is indexed *before* any slicing.
`build_context_index()` walks the inventory, runs the segmenter over each document, and builds
the reverse map from each unit's content digest to every place it occurs.

```bash
python3 -m doclifecycle context-index --repo .
```

Real output for a repository whose registry declares root `docs`, rules `docs/*.md → living`
and `docs/plans/*.md → planning, set plans`, and whose `docs/fee-policy.md` and
`docs/plans/p.md` each hold a heading and the same sentence
`Every fee change ships with a migration note.` (abridged to the duplicated unit's entry;
`documents`, `units`, and the other `occurrences` keys are omitted here, not from the output):

```json
{
  "status": "ok",
  "schema_version": 1,
  "registry_digest": "3613c1c8335b019b9685af1346bf6a78c86f1bf553f70b459fb7c613fd2179dc",
  "inventory_digest": "4720cbf9091d991c78db3f4538130d4549bc7daa6574c8733c8fa84143d26a5a",
  "digest": "1e41b25c195eb3b2f18ad46fd46368ead7e047950a6810b90b777659988dcf40",
  "occurrences": {
    "3bb14dce3f2909ce16065f0777ce8f1cd40e50c7dea80b9e5a7030956c5efdd6": [
      {"path": "docs/fee-policy.md", "ordinal": 1, "line": 3, "end_line": 3},
      {"path": "docs/plans/p.md", "ordinal": 1, "line": 3, "end_line": 3}
    ]
  },
  "unexamined": []
}
```

- **Occurrences are the pointer a unit group cannot carry.** A unit's digest is its content, so
  the same sentence written five times is one unit; a finding's group is a deduplicated set of
  those digests. `occurrences_of()` is what lets a duplication finding say *which* copies it
  means, including two copies inside one document.
- **`owner_of()` is deterministic.** Among the documents holding one unit, the owner is decided
  by document kind first (`context.KIND_PRECEDENCE`: living, then narrative, then planning) and
  by path second. A living document must be currently true, so it is where a durable claim
  belongs; a planning document ends in distillation or retirement, so nothing is moved into one.
  No model and no prose heuristics: a destination a reviewer cannot re-derive is one nobody can
  check.
- **`unexamined` is the coverage gap.** An unregistered or symlinked path the inventory reported,
  and any inventoried document that will not decode, are named here rather than skipped —
  `bloat.BloatResult.report_payload()` turns each into an `incomplete` scope, which forces
  `partial`.
- The index is a pure function of the inventory, so it needs no lineage field of its own; its
  digest covers the inventory digest, each document's ordered units, and the unexamined scopes.

```python
from doclifecycle.context import build_context_index

index = build_context_index(".")            # → ContextIndex or Invalid
index.occurrences_of(unit_digest)           # every place that content appears
index.duplicated_units()                    # units occurring more than once
index.owner_of(unit_digest)                 # the document it belongs in
index.context_digest(path)                  # the corpus, as it bears on one document
```

## Bloat audit

`doclifecycle/bloat.py` is the value lane. The model supplies judgment — is this worth keeping,
and what should replace it — and nothing else; every fact comes from the index.

| Verdict | Means | Names a destination |
|---|---|---|
| `CUT` | restates what is self-evident; delete | no |
| `CONDENSE` | many lines spent on one checkable fact | no |
| `EXTRACT-AND-MOVE` | right content, wrong document | yes |
| `MERGE-DOC` | near-duplicate; fold into the survivor | yes |
| `RETIRE-DOC` | carries nothing another document lacks | no |
| `DISTILL` | planning artifact; `ready` or `pending-implementation` | no |

The legacy skill's `POLICY` verdict is deliberately absent. A bulk judgment no longer rides on
a hand-declared directory whose file list the model echoes back: it declares an enumerable
inclusion rule and the engine expands it (see *Deterministic scopes* below).

### Chunk planning

```bash
python3 -m doclifecycle bloat-plan --repo . --max-documents 1
```

Real output for the same two-document repository as above:

```json
{
  "status": "ok",
  "schema_version": 1,
  "index_digest": "1e41b25c195eb3b2f18ad46fd46368ead7e047950a6810b90b777659988dcf40",
  "digest": "bbb951e48f788577b11a086923b16bdbd86ea2d2abf0f57cbd8711a0bd89679e",
  "chunks": [
    {"id": "c-135e93546e086eef", "documents": ["docs/fee-policy.md"], "unit_count": 2},
    {"id": "c-77f609c2fb738ce5", "documents": ["docs/plans/p.md"], "unit_count": 2}
  ]
}
```

Documents are grouped by directory and kind, then packed greedily within both budgets
(`--max-documents`, default 8; `--max-units`, default 400). Every indexed document lands in
exactly one chunk: a document that exceeds the unit budget on its own gets a chunk to itself
rather than being split or dropped, because a dropped document is a silent coverage gap. A
chunk's id is a sha256 over its members and their current contents, so an unchanged chunk keeps
its id across re-plans and an edited document re-keys only the chunk holding it.

### Destinations, and two chunks competing for one

`record_verdicts(index, lineage, verdicts, chunk=None)` validates a model's answer and builds
findings, or returns `Invalid` naming every problem in the whole response. It fails closed: any
problem records nothing, because a half-trusted set of deletion proposals is one nobody can tell
the trustworthy half of.

Destinations are resolved, not asserted. For content the global search found elsewhere the
destination *is* `index.owner_of()`, so a worker that proposed a different one was guessing from
a partial view and is refused (`bloat-destination-contradicts-index`); a group whose units are
owned in *two* places has no single right destination, so the grouping is refused rather than
falling back to what the worker proposed (`bloat-destination-ambiguous`). For content occurring
nowhere else the model names one and the index checks it: it must be an inventoried document
(`bloat-destination-not-a-document`), not the document being judged
(`bloat-destination-is-source`), and of a kind that accepts content
(`bloat-destination-kind-ineligible` — `bloat.DESTINATION_KINDS` is living and narrative). The
checks that held travel on the record, under `destination.constraints`.

`chunk`, when supplied, binds the record's *own* document to the slice
(`bloat-document-outside-chunk`). Destinations are deliberately not bound that way: a
destination outside the slice is the normal case, and the whole reason the index exists.

`merge_contention(index)` answers "who else is merging into this document?" from global data —
every destination in the corpus with its complete claimant list, ordered by source path. Two
workers in different chunks get the same list in the same order, including claimants from slices
they were never shown, so their independently produced findings compose instead of colliding.
When a destination has more than one claimant, each finding carries `contention` with the full
claimant list and its own rank.

Every finding also carries `duplicate_search`: the index digest the search ran against, how many
documents it covered, and every occurrence found, split into `here` and `elsewhere`. A finding
that says "this is redundant" is making a statement about the whole corpus, and a reader must be
able to tell whether the whole corpus was actually consulted. The split is the half a unit group
cannot express: the group is a deduplicated set of content digests, so `here` is what says which
copies *in this document* the finding is about — two identical sentences are one group member and
two `here` entries — and `elsewhere` is what makes the redundancy claim checkable.

### Deterministic scopes

`enumerate_scope(index, rule)` expands exactly one of `{"set": …}`, `{"glob": …}`, or
`{"kind": …}` into every document it covers, sorted, with a digest over the rule and the
membership. A rule nobody can expand is `bloat-scope-not-enumerable`; one covering nothing is
`bloat-scope-empty`.

A verdict carrying `scope` is a bulk judgment. Only `RETIRE-DOC` is eligible
(`bloat.SCOPE_VERDICTS`) — anything else would be a per-passage judgment nobody made — and it
expands into **one finding per enumerated member**, each carrying the enumeration it came from.
So a reviewer sees every affected file as its own approvable record, and an approval bound to a
finding digest cannot silently widen when the set grows.

Sampling survives only as review prioritization: a `sample` list is recorded under
`scope.sample`, alongside `scope.sample_is_not_authority`, and never narrows the enumeration. A
`sample` on a single-document verdict is `bloat-sampling-not-authority` — there it would stand in
for reading the subject — and a sample naming a path the enumeration does not cover is
`bloat-sample-outside-scope`. So is any attempt to supply `files`, `members`, `occurrences`, or
`contention` (`bloat.FORBIDDEN_VERDICT_FIELDS`): those are the engine's answers, and a model that
could assert them could authorize a mutation nobody enumerated.

A finding binds to assertion units, so an enumerated member holding none is
`bloat-scope-member-empty` — named, with the fix, rather than quietly dropped from a judgment that
claims to cover every affected file.

### Chunk results and the cache

A bloat verdict about a document is checked against the rest of the corpus, so the corpus *is*
its source evidence: `chunk_cache_keys()` builds one `cache.CacheKey` per document in the chunk
with `source_digest` set to `index.context_digest(path)`: for each of the document's units, in
order, every *other* place that content occurs and the kind of the document holding it — which is
exactly what duplication and ownership are decided from. An unrelated document changing leaves it
alone; the other copy of a duplicated sentence being rewritten moves it.

Note that #64's lineage already carries `inventory_digest`, which moves on any corpus edit at all,
so today the narrower digest buys no extra hits. It is still the honest description of what a
cached bloat verdict was judged against — a cache entry naming a different context slice is
`MISS_IDENTITY` rather than a false hit — and it is what a later slice would need in order to
narrow the lineage without re-deriving the rule.

```python
from doclifecycle import bloat

cached = bloat.load_chunk(cache_dir, ".", index, lineage, chunk)
cached.hits      # {path: (finding records, …)} — revalidated, not merely found
cached.misses    # paths the model must still be asked about
bloat.store_chunk(cache_dir, index, lineage, chunk, {path: records})
```

Granularity is one document, not one chunk, because that is what the cache contract models — a
chunk is re-judged exactly for the documents whose entries missed. An empty record list is a
real answer ("judged, nothing found") and is stored as such, so a clean document is not
re-judged every run. Storing a document outside the chunk raises `ValueError`: its result was
produced under different evidence.

Scope enumerations are not cached. They are derived from the index with no model in the loop, so
recomputing one is cheaper than revalidating it.

### Coverage

`BloatResult.report_payload(lineage)` produces a payload for `report.validate_report()`. The
bloat lane declares coverage in the shared contract's terms rather than inventing a second
vocabulary: each of the index's unexamined scopes becomes an `incomplete` entry, and an
`incomplete` entry forces `partial`. A corpus with an unregistered or symlinked path therefore
never reports `clean` about it, and the absence of a bloat finding for a document nobody read
cannot be mistaken for a verdict that it is lean. The state is derived from the content, for the
same reason the contract re-derives it.

## Drift audit

Is what the documentation says still true of the code? `doclifecycle/drift.py` answers that and
nothing else, read-only: it opens documents, asks `git` what changed and when, and returns a
validated report. The replacement line a STALE verdict carries is recorded for the applier
(issue #69) and never applied — the audit has no writer at all.

### Planning the scope

`plan_drift_audit()` derives what a run will examine from the inventory, with no model in the
loop, so the scope a report declares can be re-derived rather than trusted.

| Mode | Declares |
|---|---|
| `full` | every living and narrative document in the inventory |
| `incremental` | the documents a `<since>..HEAD` range changed, plus those naming a path it changed |

Each declared document carries the obligation its kind owes: `assertions` for a living document
(every unit that can carry a claim needs a verdict), `anchor` for a narrative one. A planning
document is *excluded* — listed with its reason rather than dropped, because a scope is only
checkable when what it leaves out is visible beside what it takes in. Drift never examines one:
its obligation is distillation or retirement.

Diff scope is a lower bound, and the basis says so: a document is affected when the range
changed it, when its text contains a path the range changed, or when it cannot be read at all
(planning errs toward examining). That is a text search — deterministic, cheap, and exactly why
a diff-scoped report declares a narrower scope instead of claiming coverage.

A document the registry claims no rule for is neither declared nor walked past: classification
is closed-world, so its obligation is unknown and it cannot be examined. The plan lists it under
`unclassified` and the audit turns each one into a coverage gap, which is what an unexaminable
document in the corpus is. A `symlinked-path` is not one — it is not a document at all, and the
inventory says so.

| Code | Refused because |
|---|---|
| `drift-unknown-mode` | not `full` or `incremental` |
| `drift-missing-baseline` | `incremental` with no commit to scope against |
| `drift-baseline-not-applicable` | `full` with one — a full audit that accepted a baseline would be claiming a coverage it did not have |
| `drift-unknown-baseline` | the revision is not a commit in this repository |

An invalid registry invalidates the plan, as it does everywhere else.

```bash
python3 -m doclifecycle drift-plan --repo . --mode incremental --since <commit>
```

### Answers about a living document

Two answers per assertion unit, and the split is the document model's: *what the unit is* — its
assertion class — and, when the class carries an obligation, *whether it is still true*. A lane
returns one entry per declared living document:

```json
{"documents": [
  {"path": "docs/architecture.md", "status": "ok", "verdicts": [
    {"unit": "<assertion-unit digest>", "assertion_class": "factual",
     "verdict": "STALE", "kind": "value", "tier": 3,
     "evidence": {"source": "src/payment_service.py", "line": 7,
                  "observed": "FLAT_FEE_RATE = 0.025"},
     "fix": "The payment service charges a flat 2.5% rate."},
    {"unit": "<another digest>", "assertion_class": "non-assertive"}
  ]},
  {"path": "docs/runbook.md", "status": "failed", "chunk": "chunk-2",
   "reason": "the chunk worker failed twice"}
]}
```

The classes are `finding.py`'s four, and `record_classifications()` — their landed owner —
validates them: an unknown class, a class against a unit the document lacks or against
structure, one unit answered twice, and a unit nobody answered for are all its verdicts
(`classification-*`), not a second set derived here.

Which of them are judged follows from the obligation each carries. Only `factual` owes evidence,
so only it *must* be judged — a factual unit nobody judged is a hole in coverage. `non-assertive`
prose asserts nothing the code could contradict, so a verdict against it is refused outright:
that is the same category error a narrative document is protected from, inside a living one.
`normative` and `rationale` sit between — a rule or an explanation can go stale, but neither
owes evidence, so a verdict is accepted and not required.

The verdicts themselves are the legacy skill's three, unchanged, because consumers switch on the
strings: `VERIFIED` (someone read the code and the assertion holds — coverage, not a finding),
`STALE` (it is wrong and there is a true value to restore), `UNVERIFIABLE` (nothing checkable is
named; that *is* the finding). `kind` is one of `command`, `path`, `symbol`, `behavior`,
`structure`, `value`; `tier` is 1 static, 2 shallow, 3 deep.

Evidence is mandatory for every verdict, VERIFIED included, and carries the fact separately from
the pointer: `observed` is required, and `source` is required for VERIFIED and STALE — both
assert that a place in the repository was read. UNVERIFIABLE may omit it, because there is
nothing to point at. A `source` outside the run's declared evidence boundary is
`drift-evidence-outside-boundary`: a verdict resting on something the report says was not
consulted is not checkable.

What the document says is never the model's to report. A record's `assertion` and `location`
come from the segmentation — the unit's own text and line — so a verdict cannot misquote the
passage it is about. The recorded class travels on the record too, as `assertion_class`.

| Code | Refused because |
|---|---|
| `drift-verdict-invalid-shape` | not `{unit, assertion_class}` plus, when judged, all of `{verdict, kind, tier, evidence}` |
| `drift-verdict-not-obligated` | a `non-assertive` unit was given a verdict |
| `drift-verdict-owed` | a `factual` unit was left unjudged |
| `drift-unknown-verdict` | not one of the three |
| `drift-verdict-unknown-kind` | not one of the six subject kinds |
| `drift-verdict-invalid-tier` | not 1, 2, or 3 (and `true` is not tier 1) |
| `drift-verdict-invalid-evidence` | missing, malformed, or unpointed where a pointer is owed |
| `drift-evidence-outside-boundary` | the source is outside the declared evidence boundary |
| `drift-verdict-invalid-fix` | STALE without a replacement line, or a fix on a verdict proposing no edit |

Any of these — or any `classification-*` problem — means that document was **not validly
examined**, so it becomes a coverage gap rather than a silently missing finding, and the run is
partial, not clean.

Five things invalidate the whole run instead, because they leave the report unable to describe
what happened: `drift-verdicts-invalid-shape` (the payload is not
`{"documents": [...]}`), `drift-verdicts-invalid-entry` (an entry with no path, no status, or a
failure that will not say why), `drift-verdict-duplicate-document` (two entries for one
document), `drift-verdict-undeclared-document` (an entry for a document the plan did not
declare), and `drift-verdict-on-narrative-document`.

### Narrative documents

A narrative document must be honestly dated, never line-verified — so no model is asked about
one, and a verdict offered for one is refused. Its `> As of <YYYY-MM-DD> (<anchors>)` line
(growing-docs' convention) is checked here instead, deterministically.

| Code | Means |
|---|---|
| `ANCHOR-MISSING` | no `As of` line, so nothing says what the document was true of |
| `ANCHOR-MALFORMED` | no readable `YYYY-MM-DD` date, or no parenthesized anchors |
| `ANCHOR-FUTURE-DATED` | dated after the repository's latest commit — nothing could have been checked then |
| `ANCHOR-STALE` | a path the anchor names is gone, or last changed after the as-of date |
| `ANCHOR-UNVERIFIABLE` | a path the anchor names has no commit history to check against |

Honest dating has two directions, which is why the future-dated check exists at all: no
reference comparison would catch it, since every file's last change is behind such a date. What
is deliberately *not* checked is the document's own last-change date — an as-of line says when
the code it describes was current, not when the file was last touched, so a typo fix would
otherwise read as drift.

The anchor's references are its backticked tokens, and only those: reading unbackticked prose as
filenames would open paths a sentence merely mentioned. A token is a path when it contains a `/`
or ends in an extension starting with a letter, which is what keeps `` `v1.2` `` from being read
as a file that has gone missing. A trailing `:<line>` is trimmed, and an absolute path or one
containing `..` is not a repository reference at all. Anchor findings group the anchor's own
unit, so they point at the line to fix; the prose around it is never read as an assertion.

### Coverage gaps

`incomplete` names every document the run did not examine, and each entry forces `partial` —
where a missing record proves nothing and no rendering reads as clean. A document becomes a gap
when the registry classifies it under no rule, when the lane returned nothing for it, returned
`status: "failed"` (with the chunk id folded into the reason, when it named one), returned
answers that did not validate (the reason names their codes), or when it can no longer be
segmented. A document that failed stays in the declared scope it failed inside: dropping it
would turn a gap into a silence.

### Waivers

`--waivers <repo-relative path>` reads the shape a scheduled install carries,
`{"waivers": [{"file", "claim", ...}]}`. A matching record gains a `waived` annotation naming
the acceptance; it is **never** removed from the report. Matching is `file` equality plus claim
containment, because a waiver quotes the text a human read on a line and a unit is the sentence
that line sits in — so a waiver is exactly as broad as the text it quotes.

An acceptance reaches any finding code, not only UNVERIFIABLE: on a STALE record it is a human
disputing the verdict, and a dispute the report did not show is one an auto-apply policy would
act straight through. Waivers are deliberately **not** part of the audit configuration digest —
accepting a claim changes what a reader is asked to look at, never what the audit found, so it
neither expires prior reports (the lineage is untouched) nor re-keys the finding digests an
approval set selects. The *report* digest does move, because the annotated report says something
the unannotated one did not, and a report's digest covers what it says. The evidence boundary,
by contrast, is in the configuration digest: narrowing it could change a verdict.

An absent waivers file is simply no waivers; a malformed one is `drift-waivers-invalid` and
invalidates the run, since a typo that silently un-waived everything would defeat the mechanism.

### Audit command

```bash
python3 -m doclifecycle drift-audit --repo . --mode full \
  --verdicts verdicts.json --waivers .github/doc-sync/drift-waivers.json \
  --evidence 'src/**' --exclude-evidence 'src/vendor/**'
```

Every flag is optional. Without `--verdicts` no living document is examined and the run is
partial — the narrative anchors are still checked. `--evidence` and `--exclude-evidence` are
repeatable and declare the run's evidence boundary; the default is `**`, because a boundary must
be honest before it is narrow. Exit codes are the report states: 0 clean or findings, 1 invalid,
2 usage, 4 partial.

The library calls behind them:

```python
from doclifecycle.drift import audit_drift, load_verdicts, plan_drift_audit

plan = plan_drift_audit(".", mode="incremental", since="<commit>")  # → DriftPlan or Invalid
verdicts = load_verdicts("verdicts.json")                           # → payload or Invalid
audit_drift(".", mode="full", verdicts=verdicts)                    # → Report or Invalid
```

## Digests

`digest.sha256_canonical` hashes the canonical JSON form (sorted keys, compact separators),
so reformatting a registry is not a new registry while changing a rule is. Rule order is part
of the registry digest because it decides precedence; root, exclude, set, and extension order
is normalized away. A document's digest is the sha256 of its bytes. The inventory digest covers
the registry digest, every document entry, and each finding's code and path — not finding
messages, which are prose.

A report's digest covers its schema version, lineage, records, unexamined scopes, and the
declared scope when it carries one — not its result state or stale reasons. Approval binds to that digest, so the same report keeps one
identity whether a validator reads it fresh or long after it went stale. A report that declares
a `digest` which does not match its content is `report-digest-mismatch`: altered since it was
produced.

A unit digest covers a unit's kind and normalized text; a segmentation digest covers its
ordered unit digests; a lineage digest covers the lineage alone; and a finding digest covers
the lineage digest, the finding code, the document, and the normalized unit group. What each
one deliberately leaves out is in the two sections above, and it is always the same kind of
thing: position, prose, and judgment.

A context-index digest covers the inventory digest, each document's ordered units, and the
scopes it could not examine; a chunk id covers its members and their document digests; a chunk
plan's digest covers the index digest and every chunk; and a scope enumeration's digest covers
the inclusion rule and the members it expanded to. Each is a fact about the corpus, so none of
them carries prose or a model's verdict either.

## Tests

`tests/engine/*_test.py` (stdlib `unittest`), run by ordinary discovery, which is also how
CI runs them (`.github/workflows/release.yml`, "Engine tests"):

```bash
python3 -m unittest discover -s tests/engine -p '*_test.py'
```

Seams under test: the library calls (`build_inventory()`, `authorize_path()`,
`validate_report()`, `load_report()`, `current_lineage()`, `render_report()`, `cache.cache_key()`,
`cache.put()`, `cache.get()`, `segment_text()`, `segment_document()`, `build_finding()`,
`record_classifications()`, `build_context_index()`, `bloat.plan_chunks()`,
`bloat.merge_contention()`, `bloat.enumerate_scope()`, `bloat.record_verdicts()`,
`bloat.load_chunk()`, `bloat.store_chunk()`, `plan_drift_audit()`, `audit_drift()`,
`load_verdicts()`), and the commands as subprocesses whose payload must equal the library
result. Path authorization, the cache, finding identity, and verdict recording have no command
of their own — they are substrate the other components (and, for the cache, the bloat lane)
call. `tests/engine/support.py` holds what every suite needs — the engine on `sys.path`,
`RepoTestCase.repo()`, and `run_command()` for the subprocess seam; report fixtures live in
`report_test.py`, which `report_cli_test.py`, `cache_test.py`, and `bloat_test.py` all import
(`GitRepoTestCase`, for a real repository to check freshness against). The report, cache,
bloat-cache, and drift suites build real git repositories, because staleness is a comparison
against a repository — and a diff-scoped scope is a question about a commit range — so a mocked
one would prove nothing. `drift_cli_test.py` imports `drift_test.py`'s repository fixture rather
than rebuilding it.

`tests/engine/acceptance/` is the repository-level fixture (a real `git init`, real commits,
real symlinks, real prompt-injection content) and the scenarios built on it: scenario one is
inventory, scenario two is the document model — segmentation, the four assertion classes, and
finding identity bound to a lineage read from actual git — `scenario_cache_test.py` is the
cache's (issue #64): changing only source evidence, or only configuration/ruleset, prevents
reuse of a prior semantic result. `scenario_bloat_test.py` is the bloat lane's (issue #66), one
class per acceptance criterion: the fixture's living `docs/fee-policy.md` owns two claims that
two *different* planning documents copy, so a chunk plan puts each copy and its destination in
different chunks and no answer reachable from one slice is correct. `scenario_drift_test.py` is
the drift audit's (issue #65): a diff-scoped and a full-corpus run over the same fixture
declaring different truthful scopes, a simulated failed chunk that no rendering can read as
clean, the narrative anchor going stale against the module the second commit changed, the
install's own waiver surfacing on a finding without erasing it, and the whole tree unchanged
after every run, refusal paths included.
