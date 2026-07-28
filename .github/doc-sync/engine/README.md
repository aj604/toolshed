# doc-lifecycle engine

Stdlib-only Python package (`doclifecycle`) behind the plugin's skills and workflows. No
third-party dependencies. Library functions are the implementation; the commands wrap them and
add nothing, so an import and a command cannot disagree. The one external program it runs is
`git`, and only to read: a repository's identity and HEAD, which paths a commit range changed,
and when a path last changed. Nothing here writes to a repository.

Current surface: the registry parser, the document inventory, path authorization, the report
contract, the lineage-keyed cache, the segmenter, finding identity, the context index, the
bloat lane, the drift audit, the migration door, reconciliation, approval sets, and the
applier — the only component that writes.

## Modules

| Module | Owns |
|---|---|
| `doclifecycle/registry.py` | registry parsing, validation, classification, glob matching, `without_rules()`, registry digest |
| `doclifecycle/inventory.py` | `build_inventory()`, `load_registry()`, the closed-world walk, document/inventory digests |
| `doclifecycle/paths.py` | `authorize_path()`, `classify_target()`, `repository_relative_problem()`, `write_target_problem()`, the canonical path form and target classes |
| `doclifecycle/segment.py` | `segment_text()`, `segment_document()`, the unit kinds and unit digests |
| `doclifecycle/finding.py` | `build_finding()`, `record_classifications()`, finding digests, the assertion classes |
| `doclifecycle/context.py` | `build_context_index()`, occurrences, ownership, the index and per-document context digests |
| `doclifecycle/bloat.py` | `plan_chunks()`, `plan_repository_chunks()`, `merge_contention()`, `enumerate_scope()`, `record_verdicts()`, the chunk cache seam |
| `doclifecycle/drift.py` | `plan_drift_audit()`, `audit_drift()`, `load_verdicts()`, the verdicts and anchor checks |
| `doclifecycle/migrate.py` | `draft_registry()`, `dry_run_migration()`, the legacy-install inference and the migration contract |
| `doclifecycle/report.py` | `validate_report()`, `load_report()`, `current_lineage()`, `parse_lineage()`, `parse_stale_reasons()`, `compare_lineage()`, `state_from_content()`, the declared scope and recorded coverage, lineage and report digests |
| `doclifecycle/reconcile.py` | `reconcile()`, the four relation kinds, the three group dispositions, group and reconciliation digests |
| `doclifecycle/approval.py` | `mint_approval_set()`, `validate_approval_set()`, `load_approval_set()`, `write_approval_set()`, `derived_scope_paths()`, the allowed mutation scope and the minter kinds |
| `doclifecycle/policy.py` | `load_auto_apply_policy()`, `policy_eligibility()`, `mint_policy_approval_set()`, the eligibility classes and the never-eligible codes |
| `doclifecycle/applier.py` | `apply_edit_plan()`, `load_edit_plan()`, `load_approval_payload()`, the edit-plan vocabulary, the record-code remedy table, and the whole-diff confinement check |
| `doclifecycle/render.py` | `render_report()`, `render_approval_set()`, `approval_trailers()` — Markdown and git trailers from validated artifacts, and nothing else |
| `doclifecycle/repository.py` | `lineage()`, `resolve_commit()`, `changed_paths()`, `last_change()`, `tracking()`, `tracked_files()`, `worktree_changes()`, `head_bytes()` — everything read from git |
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
enumerates; `paths.authorize_path()` below decides what may be read or written, and the
approval set and the applier are what route through it.

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
engine's one place for that decision by design. Approval-set minting and validation route
through `authorize_path()`, so every path the applier may write was authorized here.

The spelling rules are already shared, through `repository_relative_problem(path)` — returns
`(code, reason)` or `None`. `authorize_path` answers the question an *applier* asks (may I write
here), which is inseparable from the declared roots, the target class, and the state of the
filesystem. A read-only audit asks the smaller question: is this string a path inside the
repository at all? Both rest on the same list, so `..`, a leading `/`, a drive letter, a
backslash separator, a control character, whitespace, a non-canonical `//`, and a leading-dash
component mean the same thing to a drift record's evidence pointer as they do to an edit
target — and cannot mean two things, because there is only one list. Existence is not part of
it: a create-document target and a pointer at a deleted file are both legitimate.

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
    "evidence_boundary": {"sources": ["src/**"], "excluded": [], "commands": ["gh"]}
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
| `evidence_boundary` | `{"sources": [...], "excluded": [...], "commands": [...]}` — the declared limit of what the run could consult; `sources` non-empty | not compared |

`schema_version` is lineage too — it pins the shape of everything above — but it lives at the
report's top level, where every other engine artifact carries it, rather than being spelled
twice in two places that could disagree. A version this engine does not read is
`report-schema-version`: migrate the report, never guess at a shape.

Path *authorization* for `evidence_boundary` globs — traversal, symlinks, forbidden target
classes — is issue #67's single owner. The contract checks shape and log hygiene only; a
boundary is lineage here, never opened.

`commands` is the boundary's second half and answers a different question: not what the run
could *open*, but what it could *run*. Documentation makes claims no file in the repository can
settle — a document that documents another program's flags is checked against that program, and
nowhere else — and the verification method's tier 2 has always sanctioned settling those by
running a local read-only tool (`--help`, `--version`, a dry run). Before #115 the boundary was
paths alone, so a verdict resting on one had no contract-legal expression and `UNVERIFIABLE`
was the only answer available: on this repository's own corpus that produced six false findings
and hid one genuine `STALE` (`docs/agents/issue-tracker.md`'s `gh pr list --json
…,authorAssociation,…`, a field `gh pr list --json bogus` shows does not exist).

Each entry is a **bare executable name** — `^[A-Za-z0-9][A-Za-z0-9._+-]*$`, so `gh` and
`python3` pass and `gh pr list`, `/usr/bin/gh`, and `../gh` do not. The boundary says which
*programs* a verdict could rest on, and a reader who cannot tell the program from its arguments
cannot tell that. The list is **empty by default**: a run that declares no tool cannot cite one,
so the closed world stays closed unless a consumer opens it (`--evidence-command NAME`,
repeatable). The engine never executes anything a boundary declares or a verdict cites — a
citation is an instruction to whoever checks the verdict, and the checks below are about what
that instruction says.

**Re-key, not a break.** `evidence_boundary` now always states `commands`, so a run's
`audit_config_digest` differs from what the same repository and boundary produced before this
field existed, and reports do not compare across the change. Reports persisted from before it
still validate (an absent `commands` is the empty declaration); they are simply not the same
configuration as anything produced since.

### Reading the repository

`doclifecycle/repository.py` is the only place that runs `git`, and only to read.
`lineage(root)` gives identity and HEAD, `resolve_commit(root, revision)` turns a revision into
a full object id, `changed_paths(root, since)` lists what a range touched,
`last_change(root, path)` gives the committer date and commit of a path's last change, and
`tracked_files(root)` lists every path the repository tracks beneath it. Each
returns `(answer, problem)`; a problem means the repository state is unknown, and the caller
fails closed rather than certifying what it could not read. For `tracked_files` that distinction
is the whole point: reading "nothing is tracked" off a directory that is not a repository
(`repository-listing-unavailable`) would report a corpus as fully covered exactly when nothing
could be checked. It reads `ls-files -z` and, alone among these, does not trim git's output:
quoting is git's default for an unusual path, and trimming a whole listing would eat a leading
space off the first path in it — either mangling makes a tracked file look absent.

Two disciplines make "only to read" true rather than intended. The environment is **scrubbed**
of every variable that could point git at another tree (`GIT_DIR`, `GIT_WORK_TREE`, and the six
others in `REDIRECTING_VARS`), so an earlier workflow step cannot make a freshness check answer
about someone else's repository. And an argument that reaches git in **flag position** is
validated before it gets there: `changed_paths` interpolates its baseline into `<since>..HEAD`,
so it requires an already-resolved object id — `changed_paths(root, "--output=PWNED")` is a
redirect, not a revision, and would have written a file. Put revisions through `resolve_commit`
first; that is what makes them ids. `--end-of-options` and a trailing `--` back the check up,
but they do not replace it: a trailing `--` only marks where pathspecs begin, and by then the
option has already been parsed.

### Declared scope

A result state says whether the *declared* scope completed. Only the optional
`scope` block says what was declared:

```json
"scope": {
  "basis": "full inventory: every living and narrative document the registry classifies",
  "coverage": "whole-inventory",
  "documents": ["docs/architecture.md", "docs/guides/onboarding.md"],
  "excluded": [{"path": "docs/plans/next.md", "reason": "a planning document carries lifecycle state", "code": "planning-kind"}]
}
```

The claim is deliberately in two halves. `basis` is prose for a reader: how the scope was
derived. `coverage` is the token a validator acts on — `whole-inventory` (every document the
registry classifies is accounted for, either declared or excluded) or `declared-only` (the scope
names part of the inventory and claims nothing about the rest). Prose cannot carry the coverage
claim, because "every living and narrative document" is a sentence a scope listing one of six
documents can also carry.

Each exclusion is split the same way. `reason` is prose for a reader; `code` is the token a
validator acts on, one of `planning-kind` (the document is currently classified `planning`, which
drift never examines) or `unaffected-by-range` (a living or narrative document an incremental
run's commit range did not touch). Free prose alone let a living document be moved into
`excluded` with a reason like "not relevant to this run" and validate as `whole-inventory`
coverage with no stale reason — the coverage token was closed, but what it was allowed to leave
out was not (independent Fable review of PR #87, finding N1). The code is what closes that: given a
`repo_root`, it is checked against the document's actual current kind (below), not just its shape.

**This is a breaking shape change, not a re-key.** Earlier reports' `scope.excluded` entries
carried only `path` and `reason`; `code` is now required, so a report holding the old two-field
shape is `report-invalid-scope` outright, not merely digested under a new identity. Every producer
in this repository (`drift.audit_drift`) emits `code` alongside this change, so nothing produced
here breaks — a persisted report from before it, or an external consumer still writing the old
shape, must re-run to get a validating one.

Shape is checked exactly: those four `Scope` fields and no others, a non-empty single-line basis,
a `coverage` from the closed set, single-line paths no two of which repeat, and exclusions —
each exactly `path`, `reason`, and a `code` from the closed set, never a path `documents` also
declares (`report-invalid-scope`). An empty `documents` list is a real answer — a diff-scoped run
whose range touched no document declared nothing. `declared-only` coverage may not carry any
exclusions at all: the token means the scope "claims nothing about the rest", and naming a
specific exclusion with a reason is claiming something about it — only `whole-inventory` accounts
for what it leaves out that way.

**Given a `repo_root`, the scope is re-derived against the current inventory.** Shape alone
would let a report claim full-corpus coverage over one document, or enumerate documents the
repository does not contain, and be certified fresh — the one field added to make coverage
claims truthful would be the one field nothing checked. So:

| Stale reason | Raised when |
|---|---|
| `scope-document-unknown` | a declared or excluded path is not in the current inventory |
| `scope-inventory-unaccounted` | `coverage` is `whole-inventory` and some inventory document is neither declared nor excluded |
| `scope-exclusion-kind-mismatch` | an exclusion's `code` disagrees with the document it names — a `planning-kind` exclusion whose current kind is not `planning`, or (regardless of code) a living or narrative document excluded from a `full`-mode `whole-inventory` report |

`scope-exclusion-kind-mismatch` is deliberately narrower than "no living/narrative exclusion
ever": an incremental audit's `whole-inventory` claim legitimately excludes living and narrative
documents its commit range did not touch (`unaffected-by-range`), so the rule only refuses that
shape under `full`, where every living and narrative document is declared and nothing of that
kind is ever legitimately left out.

The verdict is `stale`, not `invalid`, and the direction is deliberate: the check needs a
repository in hand, and from there a document that was deleted and a document that never existed
are the same observation, with the same remedy — re-run the audit. `invalid` stays what a
payload says about itself, decidable with no repository. Like every stale reason, a carried one
is only cleared by a run that actually re-checked it: a validator given a repository but no
scope did not look, so the reason stands.

The block is part of the report's digest, because two runs finding the same records over
different scopes are not the same report: one examined more than the other. It is optional, and
a report that declares no scope digests exactly as it did before the field existed — so a
producing run that says nothing about scope is not silently re-keyed, and the reader falls back
to `audit_mode`, which is required.

**Residual gap, honestly stated (independent Fable review of PR #87, finding N2):** `coverage` is the closed token a validator acts
on precisely because `basis` cannot be. Nothing stops a payload from pairing an accurate
`declared-only` token with a `basis` string that still reads like a full-coverage description —
turning `basis` into a parsed language to catch that would trade one unconstrained-prose problem
for another. What the contract does catch mechanically (above) is the shape-level contradiction —
`declared-only` cannot carry exclusions at all. The prose-level contradiction is disclosed, not
caught: `render_report` puts `- Basis:` directly above `- Coverage:` in the same section
specifically so a reviewer sees them side by side. A validator that cannot tell truth from a
forged sentence is not a gap in this check; it is the reason `coverage` exists as a separate
field in the first place.

### Recorded coverage

`examined` is the mirror of `incomplete`: what the run *did* look at, and what it saw.

```json
"examined": [
  {"scope": "docs/architecture.md", "obligation": "assertions", "units": 9,
   "classes": {"factual": 2, "non-assertive": 7}, "verdicts": {"VERIFIED": 2},
   "verified": [{"unit": "…", "assertion_class": "factual", "location": "docs/architecture.md:14",
                 "kind": "behavior", "tier": 2, "evidence": {"source": "src/app.py", "observed": "…"}}]}
]
```

Without it, positive coverage rests entirely on an absence — a document with no finding and no
gap is indistinguishable from one nobody looked at, and a report is supposed to be proof of
examination. Evidence is mandatory for VERIFIED precisely so it can be checked, so it is kept
rather than validated and dropped.

The contract owns only `scope`; everything else on an entry travels untouched, exactly as a
record's fields do. It is checked for a printable scope, no two entries covering one scope, no
NaN/Infinity, and nesting within `MAX_NESTING` (`report-invalid-examined`) — and, when a scope
is declared, that each entry names a document that scope declared: recorded coverage must not be
able to inflate a scope. Like `scope`, it is in the digest and omitted when empty, so a report
that records no coverage digests exactly as it did before the field existed.

A non-empty `examined` requires a declared `scope` (`report-invalid-examined`). The containment
check above needs one to check against; without it, it was simply skipped, so a scope-less report
could record coverage of arbitrary paths nothing had enumerated (independent Fable review of
PR #87, finding N3). Requiring a scope is the structural fix rather than constraining `examined` to the
current inventory, because the latter would need a `repo_root` this validation phase does not
have — and costs nothing in practice, because `audit_drift` always emits a scope alongside its
recorded coverage.

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
index.repo_root, index.registry             # what it was built from; how an unwritten path classifies
```

`repo_root` and `registry` are not part of the index's identity (the digest already covers
everything they produced). They are there for the one question the indexed documents cannot
answer: whether a path holding *no* document could hold one — which is what a distillation's
residue destination is. Either being `None` (an index assembled without it) must read as
"unanswerable", never as "no objection". The registry is the one the inventory classified by,
carried on `inventory.Inventory.registry` rather than parsed a second time.

## Bloat audit

`doclifecycle/bloat.py` is the value lane. The model supplies judgment — is this worth keeping,
and what should replace it — and nothing else; every fact comes from the index, including
whether a path holding no document could hold one, which the index answers from the registry
and repository it was built from.

| Verdict | Means | Names a destination |
|---|---|---|
| `CUT` | restates what is self-evident; delete | no |
| `CONDENSE` | many lines spent on one checkable fact | no |
| `EXTRACT-AND-MOVE` | right content, wrong document | yes |
| `MERGE-DOC` | near-duplicate; fold into the survivor | yes |
| `RETIRE-DOC` | carries nothing another document lacks | no |
| `DISTILL` | planning artifact; `ready` or `pending-implementation` | optional — the residue document it authors |

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

`DISTILL` (`bloat.RESIDUE_VERDICTS`) names the document its residue is authored into. Two things
make it unlike every other destination. It is **optional** — a distillation whose residue already
has a home retires the artifact alone, which is lossy only if the residue was never landed, a
judgment for the person approving. And it must name a document that **does not exist yet**:
inventory membership is checked and refused rather than required, which is the opposite of every
other destination.

Create-only is a bound on authority, not a limitation. `DISTILL`'s remedy set includes the span
edits (an approved distillation legitimately rewrites the artifact it retires), and a positioned
edit is bounded by the passage the record's approved units are — units that segment the record's
*own* document. A destination that already existed would therefore take `replace`/`insert`/
`delete` at any line of it: naming a decision log as the residue destination would authorize
deleting an unrelated sentence from it. An unwritten path cannot, because its whole content is
the `create-document` text the approval covers. Residue belonging in a document that does exist
is unplaceable under this record and needs its own. The checks, recorded on the record as
`selected_by: model-proposed-residue` with `is_inventoried_document: false` and
`is_authorized_new_document: true`:

| Refusal | Why |
|---|---|
| `bloat-destination-is-source` | the residue cannot be the artifact the same record retires |
| `bloat-destination-unauthorized` | `paths.authorize_path` refused it — canonical spelling, containment in a declared root, no symlinked component, no case-folded collision, documentation class. The same owner the approval set's scope is authorized by, so a record that could never be applied is never minted |
| `bloat-destination-occupied` | a document is already there — in the index, or on disk since it was built (the index may predate the file) |
| `bloat-destination-unclassified` / `bloat-destination-kind-ineligible` | no registry rule claims the path (classification is closed-world), or the kind it assigns is not one content durably lives in |

`bloat-destination-uncheckable` is the fail-closed case: an index missing the repository it was
built from or its registry cannot answer any of them, and an unanswered safety question is a
refusal. `build_context_index` always carries both, and the registry it carries is the one the
inventory classified by (`inventory.Inventory.registry`) — not a second parse of the same file,
which could answer differently.

The applier accepts a `create-document` whose path is exactly that destination and nothing else
(`plan-target-not-record-target`) — a record with no destination authorizes no creation at all —
and refuses a creation over a document that is there (`apply-create-exists`), so a path occupied
between audit and apply fails closed rather than overwriting. It also re-classifies the
destination against the registry at create time, refusing one no rule claims
(`apply-destination-unclassified`) or of a kind residue is never authored into
(`apply-destination-kind-ineligible`) — the same reading the audit uses
(`bloat.residue_destination_ineligibility`, the single owner both share), because the record digest
does not cover the destination and a tampered or stale report could otherwise repoint an approved
create at a planning or unclassified path. Confinement is re-answered too, through the approval
scope (`paths.authorize_path`). So all four audit-time destination refusals hold at apply as well —
a destination the audit rejects is not creatable by any downstream stage — and an unreadable
registry is `apply-destination-unclassifiable`, the fail-closed case.

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
and never applied here — the audit has no writer at all.

### Planning the scope

`plan_drift_audit()` derives what a run will examine from the inventory, with no model in the
loop, so the scope a report declares can be re-derived rather than trusted — and, given a
`repo_root`, `validate_report` does re-derive it (*Declared scope* above).

Both modes partition the inventory: every document is either declared or excluded with its
reason, so a drift report's scope claims `coverage: "whole-inventory"` in either mode. A
diff-scoped run is narrower, not less accountable. What a diff-scoped run cannot prove
post-hoc is its *basis* — whether the range really is the one the report names, and whether the
affected-document search found everything — so that half stays prose a reader checks against
the commit range, not a claim the validator re-derives.

| Mode | Declares |
|---|---|
| `full` | every living and narrative document in the inventory |
| `incremental` | the documents a `<since>..HEAD` range changed, plus those naming a path it changed |

Each declared document carries the obligation its kind owes: `assertions` for a living document
(every unit that can carry a claim needs a verdict), `anchor` for a narrative one. A planning
document is *excluded* — listed with its reason rather than dropped, because a scope is only
checkable when what it leaves out is visible beside what it takes in. Drift never examines one:
its obligation is distillation or retirement. Every exclusion also carries the closed `code`
`report.py` cross-checks against the repository (*Declared scope* above): `planning-kind` for a
planning document, `unaffected-by-range` for a living or narrative one an incremental run's
commit range did not touch — a full run never emits the latter, since it declares every living
and narrative document.

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
    {"unit": 4, "assertion_class": "factual",
     "verdict": "STALE", "kind": "value", "tier": 3,
     "evidence": {"source": "src/payment_service.py", "line": 7,
                  "observed": "FLAT_FEE_RATE = 0.025"},
     "fix": "The payment service charges a flat 2.5% rate."},
    {"unit": 7, "assertion_class": "non-assertive"}
  ]},
  {"path": "docs/runbook.md", "status": "failed", "chunk": "chunk-2",
   "reason": "the chunk worker failed twice"}
]}
```

`unit` names which assertion unit an answer is about by the small integer that `segment` prints
alongside each one (`AssertionUnit.ordinal`, fixed per document) — never the 64-character digest
directly. The engine resolves the ordinal back to the unit itself before anything downstream sees
a digest at all (`drift-verdict-unknown-ordinal` if the document has no unit at that ordinal). This
is what removes the transcription failure the shadow-parity gate measured (#116, G3 in
`docs/plans/2026-07-26-shadow-parity-gate.md`): of 1329 first-round answers over this repository's
own corpus, 39 (2.9%) named a digest no unit had — 36 of those a real digest truncated to 57–63
characters or one or two characters off — and because the engine fails a document closed on any
classification problem, that error rate invalidated 48% of the corpus in one pass. An ordinal is a
small integer copied from a command's own output, not composed from memory, so there is nothing
left to truncate or mistype into naming the wrong unit. A caller that already holds a unit's digest
directly (a library caller, not a model lane) may still pass it as `unit` — the two forms are never
ambiguous, since JSON distinguishes an integer from a string — but the model-facing lane
(`doc-audit.yml`) now asks for the ordinal exclusively.

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
the pointer: `observed` is required, and a **citation** — `source` or `command` — is required
for VERIFIED and STALE, which both assert that something was actually checked. UNVERIFIABLE may
omit it, because there is nothing to point at. Exactly one citation, never both: a verdict rests
on one place a reader goes, and two pointers leave nobody able to say which one settled it
(`drift-verdict-invalid-evidence`).

`{"source": "src/fees.py", "line": 7, "observed": "…"}` cites a place in the repository.
`{"command": "gh pr list --json bogus", "observed": "…"}` cites a local tool that was run,
for a claim no file in the repository can answer. A command citation takes no `line` — a line
number points into a file, and a tool's output is not one.

A `command` is checked as a command line *before* it is matched against the boundary, and the
order is the check, exactly as it is for a source. It must be one non-empty single line free of
shell syntax — `;&|<>()$`, a backtick, or a backslash — because chaining, redirection,
substitution, and escaping make it a shell program, and the report must not present one as a
single read-only command a reader re-runs; and because the boundary matches its first token,
which says nothing about what a shell program would run. Only then is that first token matched
against `evidence_boundary.commands`; a command outside it is
`drift-evidence-outside-boundary`, the same code and the same reason as a path outside it.
Globbing characters are deliberately allowed: they change an argument, not what runs.

A verdict resting on a command is a real, checkable pointer — but a weaker one than a path, and
in a specific way worth naming. A `source` is pinned by `base_commit`: a reader gets the exact
bytes the verdict was about. A `command` is pinned only to the environment that ran it, and
nothing in the report says which version of the program that was — a digest of the output would
not fix that, since it would expire on the next upgrade of a program this repository does not
pin, while reading as though it pinned something. So the citation records the command and the
`observed` fact, and a reader re-runs it against whatever they have. That weaker guarantee is
exactly why the [auto-apply policy](#the-auto-apply-policy) refuses a command-cited record by
name (`policy-external-evidence`): nobody re-deriving the change from the commit can settle it,
and a remedy whose reason lives outside the closed world is the one a human should approve.

A `source` is checked as a path *before* it is matched against the boundary, and the order is
the check. `paths.py` — the single owner of path safety — decides what a repository-relative
path is: no `..`, no leading `/` or `~`, no backslash separator, no control character or
whitespace, no `//` or `./`, no leading-dash component, NFC only. Anything else is
`drift-verdict-invalid-evidence`, naming which rule the spelling broke. Only then does the
boundary apply, because a boundary is a glob and a glob is a string match: `src/**` matches
`src/../../../etc/passwd` exactly as happily as it matches `src/fees.py`. A source that is a
well-formed path but outside the boundary is `drift-evidence-outside-boundary` — a verdict
resting on something the report says was not consulted is not checkable.

Existence is deliberately *not* part of the check: a pointer at a file a commit deleted is
exactly what a STALE finding reports, and refusing it would refuse the finding.

What the document says is never the model's to report. A record's `assertion` and `location`
come from the segmentation — the unit's own text and line — so a verdict cannot misquote the
passage it is about. The recorded class travels on the record too, as `assertion_class`.

| Code | Refused because |
|---|---|
| `drift-verdict-invalid-shape` | not `{unit, assertion_class}` plus, when judged, all of `{verdict, kind, tier, evidence}` |
| `drift-verdict-unknown-ordinal` | `unit` is an integer, but this document has no assertion unit at that ordinal |
| `drift-verdict-not-obligated` | a `non-assertive` unit was given a verdict |
| `drift-verdict-owed` | a `factual` unit was left unjudged |
| `drift-unknown-verdict` | not one of the three |
| `drift-verdict-unknown-kind` | not one of the six subject kinds |
| `drift-verdict-invalid-tier` | not 1, 2, or 3 (and `true` is not tier 1) |
| `drift-verdict-invalid-evidence` | missing, malformed, unpointed where a pointer is owed, citing both a `source` and a `command`, or a `command` that is not one shell-free line |
| `drift-evidence-outside-boundary` | the cited source or command is outside the declared evidence boundary |
| `drift-verdict-invalid-fix` | STALE without a replacement line, or a fix on a verdict proposing no edit |

Any of these — or any `classification-*` problem — means that document was **not validly
examined**, so it becomes a coverage gap rather than a silently missing finding, and the run is
partial, not clean. `incomplete[].reason` is codes only, by design — no prose drift — with one
exception: for `drift-verdict-invalid-evidence` and `drift-evidence-outside-boundary` the
offending `evidence.source` — or `evidence.command`, folded in the same way under its own label
— is folded into the reason too, because the code alone says a citation broke a rule, not which
one — losing that is exactly the detail an operator debugging
the gap needs first (independent Fable review of PR #87, finding N4). The fixture's own hostile
filenames (a leading dash, `; rm -rf ~`) are documents drift declares and examines that cannot
ever be cited as evidence sources; before this, the gap they produced named only the code.

Five things invalidate the whole run instead, because they leave the report unable to describe
what happened: `drift-verdicts-invalid-shape` (the payload is not
`{"documents": [...]}`), `drift-verdicts-invalid-entry` (an entry with no path, no status, or a
failure that will not say why), `drift-verdict-duplicate-document` (two entries for one
document), `drift-verdict-undeclared-document` (an entry for a document the plan did not
declare), and `drift-verdict-on-narrative-document`.

Fail-closed is right for all five — none is a document that went unexamined, and a report that
could not say which run it describes is worse than no report. Note the consequence for a
chunked headless lane: **one stray worker entry produces no report at all, rather than one
coverage gap**, which without a self-explaining terminal state on the run surface is a silent
nightly no-op. A scheduler adapter running this unattended must report the `Invalid` problems,
not just its exit code.

### Narrative documents

A narrative document must be honestly dated, never line-verified — so no model is asked about
one, and a verdict offered for one is refused. Its `> As of <YYYY-MM-DD> (<anchors>)` line
(growing-docs' convention) is checked here instead, deterministically.

| Code | Means |
|---|---|
| `ANCHOR-MISSING` | no `As of` line, so nothing says what the document was true of |
| `ANCHOR-MALFORMED` | no readable `YYYY-MM-DD` date, or no parenthesized anchors |
| `ANCHOR-FUTURE-DATED` | dated after the repository's latest commit — nothing could have been checked then |
| `ANCHOR-STALE` | a path the anchor names last changed after the as-of date |
| `ANCHOR-UNVERIFIABLE` | a path the anchor names has no commit history to check against |
| `ANCHOR-UNRESOLVABLE-REFERENCE` | a reference that is no path in the repository — an abbreviation, or a target that has moved |

Honest dating has two directions, which is why the future-dated check exists at all: no
reference comparison would catch it, since every file's last change is behind such a date. What
is deliberately *not* checked is the document's own last-change date — an as-of line says when
the code it describes was current, not when the file was last touched, so a typo fix would
otherwise read as drift.

The anchor's references are its backticked tokens, and only those: reading unbackticked prose as
filenames would open paths a sentence merely mentioned. A token is a path when it contains a `/`
or ends in an extension starting with a letter, which is what keeps `` `v1.2` `` from being
opened as a path at all. A trailing `:<line>` is trimmed, and an absolute path or one
containing `..` is not a repository reference at all. Anchor findings group the anchor's own
unit, so they point at the line to fix; the prose around it is never read as an assertion.

References are repository-relative and complete: a token that resolves to nothing is reported as
unresolvable, never as a removal, and a shorthand is not resolved against a prefix an earlier
token established. Both halves of that are the same refusal to guess — the engine cannot see the
difference between `doc-sync.yml` written for a file three directories down and one that was
deleted, and carrying a prefix forward would make an anchor's meaning depend on token order and
silently pick between same-named files whose histories differ — and history is what the date
check reads.

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

Deliberately `{file, claim}` text, not a unit digest, and the #116 ordinal-keyed verdict fix above
is an argument for keeping it that way rather than a stepping stone toward changing it. A verdict
answers by ordinal precisely because a garbled 64-character digest was measured (G3,
`docs/plans/2026-07-26-shadow-parity-gate.md`) to fail a document **closed and loudly** —
`classification-unknown-unit`, `partial`, nothing silently lost. A waiver keyed to a digest instead
of quoted text would fail the opposite way: a garbled digest matches no finding, so the waiver
simply never fires, and an accepted claim quietly stops being waived with no typed problem anywhere
to catch it. Text-keyed waivers stay the more robust shape while a model can be the one transcribing
the key.

Which is why the text is bounded, in both directions. A fragment shorter than **12 characters**
is `drift-waivers-invalid` when the file is read: under containment, one word — or one
character — accepts every assertion in the document rather than the line a human read. A waiver
that annotates more than **10 findings** is `drift-waiver-too-broad` once the run is drafted,
which is the earliest its reach is knowable. Both refuse the run rather than over-waive quietly,
because both failures are silent: an auto-apply policy that declines waiver-disputed records is
switched off document-wide, and one that does not is told a human disputed findings nobody
looked at.

Every annotation states its blast radius. A `waived` block carries `claim`, `source` (the
waivers path), `source_digest` (sha-256 of that file as it was read), `matched` (how many
findings this waiver reached across the whole run), and `reason`/`date` when the entry gives
them. The digest is what makes the annotation reproducible: without it a `waived` block names a
path and nothing else, and nobody holding the report can tell whether that file said that —
annotations being the one part of a report not otherwise derivable from the repository.

An acceptance reaches any finding code, not only UNVERIFIABLE: on a STALE record it is a human
disputing the verdict, and a dispute the report did not show is one an auto-apply policy would
act straight through. Waivers are deliberately **not** part of the audit configuration digest —
the waivers digest included. Accepting a claim changes what a reader is asked to look at, never
what the audit found, so it neither expires prior reports (the lineage is untouched) nor re-keys
the finding digests an approval set selects. The *report* digest does move, because the
annotated report says something the unannotated one did not, and a report's digest covers what
it says. The evidence boundary, by contrast, is in the configuration digest: narrowing it could
change a verdict.

An absent waivers file is simply no waivers; a malformed one is `drift-waivers-invalid` and
invalidates the run, since a typo that silently un-waived everything would defeat the mechanism.

### Audit command

```bash
python3 -m doclifecycle drift-audit --repo . --mode full \
  --verdicts verdicts.json --waivers .github/doc-sync/drift-waivers.json \
  --evidence 'src/**' --exclude-evidence 'src/vendor/**' --evidence-command gh
```

Every flag is optional. Without `--verdicts` no living document is examined and the run is
partial — the narrative anchors are still checked. A `--verdicts` file that cannot be read or
parsed is `drift-verdicts-unreadable` and invalidates the run, rather than being mistaken for
no verdicts at all. `--evidence` and `--exclude-evidence` are
repeatable and declare the run's evidence boundary; the default is `**`, because a boundary must
be honest before it is narrow. `--evidence-command` is repeatable too and declares the local
tools a verdict may be settled by running, named as bare executables; its default is *empty*,
the opposite way round, because a boundary that admitted every program on the machine would say
nothing. Exit codes are the report states: 0 clean or findings, 1 invalid,
2 usage, 4 partial.

The library calls behind them:

```python
from doclifecycle.drift import audit_drift, load_verdicts, plan_drift_audit

plan = plan_drift_audit(".", mode="incremental", since="<commit>")  # → DriftPlan or Invalid
verdicts = load_verdicts("verdicts.json")                           # → payload or Invalid
audit_drift(".", mode="full", verdicts=verdicts)                    # → Report or Invalid
```

## Migration door

Issue #74. How a consumer already running the pre-registry doc-sync install adopts the registry
contract, and how a fresh install gets a registry at all. Two commands, neither of which writes
anything: the migration itself is a human landing a file and a workflow bump.

### Drafting a registry

```bash
python3 -m doclifecycle migration-draft --repo . > draft.json
mkdir -p .doc-lifecycle && python3 -m doclifecycle migration-draft --repo . \
  --registry-only > .doc-lifecycle/registry.json
```

`draft_registry()` infers classification from what the consumer already wrote down, and emits it
as **glob rules**: one rule per directory carrying that directory's dominant classification, plus
a per-file rule for each document that disagrees with it. That is the point of the door — the
adoption review is a dozen globs in a normal PR diff, not a line per markdown file.

Four sources of evidence, in precedence order per document: a `> As of` marker on the first line,
or on the first non-blank line under a `#` title (within the first six lines either way), is
`narrative` (`narrative-anchor`); a directory under a legacy `policy_scope` is
`planning` (`policy-scope`); a `plans` or `specs` path segment is `planning`
(`planning-location`); everything else is `living` (`living-default`). Living last is the safe
default — it is the kind that owes the most, so a wrong guess over-audits rather than quietly
exempting a document. The precedence is the legacy bloat planner's, and `ANCHOR_LINE` is built
from `drift.ANCHOR_PREFIX`, so the door and the audit cannot disagree about what marks a document
narrative.

A document the door cannot read still gets a kind from its location, because refusing a whole
migration over one unreadable file would block it on something the audit refuses anyway — but it
is never silent: `migration-unreadable-document` names the path in `notes`, so the classification
is reviewed rather than trusted.

Roots are bounded by what the consumer wrote, not by a walk of the tree: every markdown file at
the top level of the repository, the directory the scope-record path names (`docs/` by default)
when that directory exists, and any directory the waivers, `policy_scope`, or audit-scope
`include` entries reach into. Nothing below the top level is discovered on its own. Exclusions
are deliberately
not evidence — naming a subtree to keep it out is not a declaration that it is a root. Evidence
is filtered through `paths.repository_relative_problem()`, path safety's one owner, so a waiver
naming `../elsewhere/x.md` declares no root; a trailing `/` on a directory prefix is repaired
first, since it is the obvious spelling. A root inside another is dropped, because the registry
refuses overlapping roots outright. `--root` (repeatable) replaces inference entirely, and is
checked before anything is walked: `migration-unsafe-root` for a spelling outside the repository,
`migration-missing-root` for a tree that is not there. No inferable root is `migration-no-roots`.

**The draft states what its roots leave behind.** Every source they are inferred from describes
the legacy *bloat* corpus or narrower; the legacy *drift* lane had no root concept at all — it
was diff-scoped over the whole repository, and `audit-scope.json` reached it only through
`authorize-paths.py`, as a write-authorization filter. So a drafted registry all but always
narrows drift coverage, and one that said nothing would be ratified as if it changed nothing.
`migration-coverage-narrowed` counts the tracked files carrying a drafted extension that no root
claims, and names up to `COVERAGE_SAMPLE` (10) of them, sorted: the count is exact and the paths
are an example, so five thousand unclaimed files are not five thousand lines. A note, never a
refusal and never an inferred root — dropping vendored, generated, and third-party markdown is
usually the right call, so the reviewer ratifies the narrowing or re-drafts with `--root`.
Enumeration is `repository.tracked_files()`, so generated and ignored markdown does not count;
the legacy lane never saw it either. Exclusions do not enter into the check, which cuts both
ways on purpose: a path excluded from *inside* a root stays claimed and unreported, because the
draft prints that exclusion in its own `exclude` for the reviewer to read, while a subtree named
only in `exclude` is under no root at all — an exclusion is not root evidence — and is reported
like any other omission. When the repository cannot be listed, `migration-coverage-unchecked`
says so; silence would read as nothing-left-behind, the one conclusion this note exists to
prevent. It stays a note rather than a problem downgraded into one: a draft does not need this
answer to be a draft, so what cannot be established is the coverage statement, not the registry.

`audit-scope.json`'s `exclude` becomes the registry's `exclude`; a planning directory becomes a
declared set named after it; an `include` entry that names neither `.md` nor a wildcard suffix is
a note, since the draft declares `.md` only. An audit scope or waivers file that will not parse invalidates the draft
rather than defaulting: the exclusions are the only record of what a consumer kept out, and a
draft that lost them proposes auditing vendored documentation.

Three things make the draft trustworthy. Every rule carries the `basis` it was inferred from and
the `documents` it claims, so a wrong rule is traceable to its evidence. The drafted text is run
back through `registry.parse()` before it is returned — the review is of glob rules, not of
whether the file parses — so `--registry-only` on an invalid draft prints nothing at all. And
every claim is then re-derived through the *parsed* registry: a per-file override is still a
glob, so a document whose name contains `*` or `?` emits a rule that also claims its neighbours,
and overrides sort last, so it would win silently. Parsing cannot catch that — the file is
perfectly well formed — so a rule that classifies something other than what the draft says is
`migration-draft-inconsistent`, naming the document.

The draft walks the corpus through `registry.without_rules()` and `inventory.walk_root()`, the
same enumeration `build_inventory()` uses, so the documents a draft proposes rules for are
exactly the documents the resulting inventory will hold.

### The dry run

```bash
python3 -m doclifecycle migration-dry-run --repo .
```

`dry_run_migration()` reads the registry the human landed and states what adopting it costs:

- **`migration`** — the contract (`legacy-doc-sync-to-registry`) and the versions it spans, read
  from `.github/doc-sync/installed-version` and `PLUGIN_VERSION`. Absent is a fresh install
  (`from_version: null`). Unparseable is `migration-version-unreadable`; ahead of this engine is
  `migration-version-ahead`. The comparison is numeric, like the upgrade lane's gate.
- **`obligations`** — one row per document kind, always all three: `living` owes `assertions`,
  `narrative` owes `anchor`, `planning` owes `lifecycle` and carries the drift audit's own
  out-of-scope reason. A kind with no documents is still a row, because "nothing here is
  narrative" is part of what the registry commits the consumer to.
- **`waivers`** — which acceptances survive the move onto assertion-unit identity. A legacy
  waiver names a file and quotes claim text; the new contract keys a finding to a document and a
  group of units identified by content digest. So an acceptance re-keys cleanly when its text
  lands on determinate assertion-capable units, and needs re-waiving otherwise:
  `waiver-document-not-inventoried`, `waiver-document-carries-no-assertions` (narrative and
  planning documents are never line-verified), `waiver-document-unreadable`,
  `waiver-claim-not-found`, `waiver-claim-too-broad`. Each carries the message saying what to do.
  The waivers file is read through `drift.load_waivers()` — the audit's own reader, so a dry run
  cannot promise the audit something else.
- **`artifacts`** — the three classes of old artifact, each stating `carried: false`, why it
  stops here, how to regenerate it, and every instance found. Closed-world over
  `.github/doc-sync/`: anything there the contract does not carry across and that is not a
  vendored script is an artifact of the old world. The repository root is not a directory this
  contract owns, so there the scan is the named list of working files the legacy workflows write
  into it (`drift-report.json`, `bloat-report.json`, `manifest.json`, `distill-manifest.json`).
  Every class reports its disposition whether or not an instance was found — a reader learns that
  approvals do not survive the move without having to leave one lying around. Nothing is coerced:
  a report that predates lineage cannot be given one after the fact.
- **`preserved`** — every consumer file the contract accounts for, with the digest it had when
  read and what happens to it: `audit-scope.json`, `drift-waivers.json`, and
  `.github/doc-sync-marker` are `unchanged`; `installed-version` is `set-to-target`, the one
  consumer file the migration moves. `tests/engine/migrate_test.py` compares the whole tree byte
  for byte before and after every call, refusal paths included.

A re-keyed waiver reports the **units** its acceptance now names and how many (`matched`), not a
finding digest: a finding digest also covers the report lineage and the finding code, which are
bound when an audit runs. Naming them here would be a promise about a run nobody has made; the
document-and-unit half is the part that has to be stable, and is what "re-keys cleanly" can mean
before an audit. The breadth bound is the audit's own `MAX_WAIVER_UNITS`, not a stricter one:
calling anything past a single unit ambiguous would report waivers as broken that will keep
working, overstating the very cost this dry run exists to state accurately.

**Unclassified documents block the upgrade.** Every `unregistered-document` the inventory found
becomes a `migration-unclassified-document` problem naming the path, and the run is `invalid`
with no payload. There is no unclassified bucket, because a bucket is how a corpus quietly stops
being audited. Problems are reported exhaustively — the version and every unclassified path in
one pass — so one fix round can address all of them.

```python
from doclifecycle.migrate import draft_registry, dry_run_migration

draft = draft_registry(".")          # → Draft (has .registry_text) or Invalid
dry_run_migration(".")               # → DryRun or Invalid
```

## Reconciliation

`reconcile(report)` groups a validated report's records by what they would change, so an
approval selection is answerable to the relationships between records rather than to a flat
list. Deterministic and model-free; a `Report` is the only accepted input (anything else is a
`TypeError`).

Two definitions do the work. A **target** is `(document, unit digests)` — a unit digest is
content, so the same sentence in two documents is two targets. A **remedy** is what the record
writes and where: the replacement text (`fix` or `proposal`, read as one slot) and the
destination document. Not the finding code: two lanes proposing the same replacement for one
passage are one edit described twice, and a `STALE` fix and a `CONDENSE` proposal that write
the same string reconcile as duplicates.

Two refinements keep those definitions honest against real lane output. The document is
compared as a *canonical* repository-relative spelling (`paths.repository_relative_problem`),
because `./docs/a.md` and `docs/a.md` are one document and a report that spelled one leg of a
contradictory pair the other way would split the pair into two independent groups —
`reconcile-record-path-not-canonical`. And a record that records no replacement text has an
*unknown* remedy rather than an empty one: bloat's `CUT`, `RETIRE-DOC`, and `DISTILL` all carry
no proposal and drift emits a fix only for `STALE`, so collapsing them onto one signature made
a `CUT` and a `DISTILL` over one passage read as one edit described twice. Unknown remedies are
distinguished by finding code, which makes that pair `exclusive` — the fail-closed answer —
while two unknowns under one code stay comparable.

`WRITTEN_FIELDS` is the whole vocabulary for replacement text, and that is an assumption about
the producers rather than something the report contract enforces: `report.py` deliberately does
not police `extra`, so a new lane carrying its replacement under a third key must add its slot
there. Both shipped lanes have closed verdict field sets (`drift.VERDICT_FIELDS`,
`bloat.VERDICT_FIELDS`), and the unknown-remedy rule is what keeps the failure fail-closed
until a third one lands.

Every pair whose targets intersect gets one of four relation kinds, and every group gets the
selection rule that follows from them:

| Targets | Remedy | Relation | Group disposition |
|---|---|---|---|
| equal | same | `duplicate` | `atomic` |
| equal | different | `same-target` | `exclusive` |
| overlap | same | `overlapping` | `atomic` |
| overlap | different | `mutually-exclusive` | `exclusive` |

A record related to nothing is a singleton group with disposition `independent`. Groups are
connected components, so a conflict anywhere in a chain makes the whole group `exclusive`.
`atomic` means the group is selected whole or not at all — applying part of it would leave the
rest describing text that is no longer there. `exclusive` means no member may be selected at
all: approving one leg silently decides against the other, and approving both cannot be
applied.

A duplicate within one report is always cross-code, because one code, document, and unit set is
one finding — the finding digest says so, and `report.validate_report` refuses a report
carrying it twice. Reconciliation therefore checks identity before it groups: a record that is
not a finding (no `code`, `path`, `units`), whose document is not a canonical
repository-relative spelling, or whose digest does not equal
`finding_digest(lineage, code, path, units)`, makes the whole reconciliation `invalid`. The
guarantee is over every pair, so a record it cannot read is not a group left out.

Group ids are the sha256 of their sorted members, so a group keeps its id when unrelated
records are added to the report. The reconciliation digest covers the report digest and every
group.

```bash
python3 -m doclifecycle reconcile-report --report report.json --repo .
```

Reconciliation is a property of the records, so it is answered for any report that validates;
whether the report is still fresh enough to act on is `validate-report`'s question, and
minting's gate.

## Approval sets

A report authorizes nothing. An **approval set** is the artifact that does: a selection of
record digests from one report, bound to that report's lineage and to an enumerated allowed
mutation scope, minted by a named minter. The applier accepts nothing else.

```json
{
  "artifact": "approval-set",
  "schema_version": 1,
  "status": "clean",
  "minter": {"kind": "human", "id": "avery@example.com"},
  "report_digest": "<sha256 of the report this selects from>",
  "report_state": "findings",
  "lineage": {"...": "the report's lineage, verbatim"},
  "reconciliation_digest": "<sha256 of the grouping the selection satisfied>",
  "records": [
    {"digest": "<record digest>", "id": "DRIFT-001", "code": "STALE",
     "path": "docs/architecture.md", "destination": null,
     "units": ["<unit digest>"]}
  ],
  "skipped": [{"digest": "<record digest>", "id": "DRIFT-002"}],
  "scope": {"roots": ["docs"], "paths": ["docs/architecture.md"]},
  "digest": "<sha256 of everything above except status and stale reasons>"
}
```

`minter.kind` is `human` (semantic approval — a person selecting digests) or `policy` (a
standing auto-apply policy, named so PR review knows what it is reviewing). `mint-approval
--minter-kind policy` is the raw flag and mints for any record class a human names: it credits
a policy without consulting one. The gated door is `policy-mint` below, whose selection is
derived from a policy's own decisions and cannot be widened by a caller — that is the one to
wire into a lane. `status` is `clean` or `stale`; a stale one carries `stale_reasons` in the
shape a report's do.

`digest` is **required** on the way in, unlike a report's — an approval set is authority, and
its digest is the only part of it that reaches the repository, so a file that declines to say
what it hashes to makes every tamper "delete one field". It is `approval-digest-mismatch` if it
disagrees with the content, and `approval-missing-field` if it is absent. Pass
`expected_digest=` (CLI `--expected-digest`) to bind the file to the
`Doc-Lifecycle-Approval` trailer of the change claiming it: a different file is
`approval-digest-unexpected`, however well-formed it is.

`report_state` is the report's own state when the set was minted, inside the digest. It is
there because a `partial` report's absent records are the *unexamined* ones and reconciliation
only groups records that were present — so a coverage gap can hide a finding that would have
grouped exclusively with something approved here, and the change reviewer has to be able to see
that. A `report_state` outside `findings`/`partial` is `approval-report-not-approvable` on
read-back, re-running the minter's refusal.

`records` and `skipped` are listed in ascending digest order, and read back only in that order
(`approval-records-not-sorted`, `approval-skipped-not-sorted`). Both arrays are inside the
digest, so an order that may vary would give one selection two identities.

**Minting.** `mint_approval_set(report, digests, repo_root=…, minter=…)` refuses before it
mints, in this order, because each phase rests on the one before:

- the report must be `findings` or `partial` — `clean` has nothing to approve and `stale`
  describes a state that no longer exists (`approval-report-not-approvable`);
- the selection must be non-empty, repeat nothing, and name only records the report carries
  (`approval-empty-selection`, `approval-duplicate-selection`, `approval-unknown-record`);
- it must respect the reconciliation groups (`approval-exclusive-group`,
  `approval-partial-group`), which is why the refusal is structural rather than advisory;
- every target — each record's document, plus the destination of a move — must authorize as
  `documentation` inside a declared root, through `paths.authorize_path` (the refusal is that
  module's own code: `path-outside-root`, `symlinked-path`, `path-forbidden-class`, …);
- every target's text must still be what the record was written about
  (`approval-preimage-mismatch`, `approval-preimage-unreadable`).

**Nothing rides along.** The allowed mutation scope is a *derivation* of the selection —
`derived_scope_paths()`: each selected record's document, plus the `destination` a move writes
to, and nothing else. A report's coverage claim contributes nothing: `whole-inventory` means
every document is accounted for, which says nothing about what may be changed, so the
strongest coverage claim a report can make authorizes exactly what the weakest one does.

Because it is a derivation, validation recomputes it rather than believing it, and a scope
naming one document more than the selection justifies is `approval-scope-not-derived` — an
approval set is a file, and a hand-widened `scope.paths` would otherwise make an unselected
finding's document writable. `skipped` is derived the same way and checked the same way
against the report (`approval-skipped-not-derived`): it is every record not taken, and a short
one hides what the approver declined.

**The minter's refusals are re-run on read-back.** `mint_approval_set` is not the gate — the
applier sees only what validation says about the artifact in front of it. So when `report` is
supplied, `validate_approval_set` re-reconciles and re-applies the group discipline:
`approval-exclusive-group` and `approval-partial-group` come back as `invalid`, not `stale`,
because nothing in the world moved — the selection is one no minter would have produced. The
applier requires the report, so this is the only path it takes.

Every one of those re-runs is a comparison against the report the artifact *names*. Supplied
that report, a selected record it does not carry, a lineage it did not run under, a hidden
`skipped` entry, or an invented `destination` is `invalid`
(`approval-record-not-reported`, `approval-lineage-not-reported`,
`approval-skipped-not-derived`, `approval-destination-not-reported`) — the report digest pins
all four, so none of them can be the world moving. Supplied a *different* report — the
ordinary result of an honest re-run — none of them can be derived truthfully, so every check
stands down behind the one fact a reader can act on: `stale` `approval-report-changed`, re-run
the audit and mint afresh. Standing down is safe because `stale` authorizes nothing and cannot
heal: no report digests to a corrupted claim, so corrupting `report_digest` buys a forger a
verdict that only a fresh mint replaces.

**A record's target is re-derived, not believed.** A finding's digest *is* its lineage, code,
document, and units, so `validate_approval_set` recomputes `finding_digest()` over every
approved record and refuses `approval-record-digest-mismatch` on any mismatch — the same check
`reconcile.py` runs over a report's records, and like that one it needs neither the report nor
the repository. Without it, keeping an approved digest while rewriting `path` and `units` and
repairing `scope.paths` produced an artifact whose every derivation faithfully computed the
wrong document.

`destination` is the one part of the write set that check cannot reach: where a move puts
content is the lane's proposal, not the finding's identity, so it is outside the finding
digest. It is compared against the report instead (`approval-destination-not-reported`), which
is why an applier must supply one.

Record `path`, record `destination`, and every `scope` path are checked as canonical
repository-relative spellings in the structural layer, through the one owner
`paths.repository_relative_problem` — `..`, a leading `/`, a backslash, whitespace, and a
non-NFC spelling are `approval-invalid-record`/`approval-invalid-scope`. They are `invalid`
rather than `stale` on purpose: `../../../tmp/evil.md` is a forgery, not a repository that
moved, and the refusal must not need a repository to reach.

**A verdict says what it was in a position to check.** `report` and `repo_root` are both
optional, so the returned `ApprovalSet` carries `unchecked` — the named checks that did not
run, each with what it leaves unverified — and the payload, the rendered summary ("Not
checked"), and the trailers all show it. `clean` from a structural read and `clean` from a full
one are different claims, and an applier supplies both. `observed_report_state` reports the
supplied report's state now, beside the `report_state` the set was minted with; it is reported
rather than judged, because a report goes stale the moment any document changes — including by
the applier's own writes — and turning that into a verdict would make the second subset of one
report unapplyable.

**Expiry.** `validate_approval_set(payload, report=…, repo_root=…)` is structural first and
exhaustive; `invalid` always beats `stale`. With `report` it compares the report digest and,
when that matches, that the report still reconciles the same way — selection membership is the
`invalid` re-derivation above, not expiry. With `repo_root` it names every field that moved:

| Stale reason | What moved |
|---|---|
| `approval-repository-changed` | the repository identity |
| `approval-base-commit-changed` | HEAD |
| `approval-registry-changed` | the registry digest |
| `approval-ruleset-changed` | `RULESET_VERSION` |
| `approval-plugin-changed` | `PLUGIN_VERSION` |
| `approval-audit-config-changed` | the consumer's audit configuration digest |
| `approval-scope-changed` | a scope path no longer authorizes, or the declared roots moved |
| `approval-preimage-mismatch` | a selected record's units are no longer in its document |
| `approval-preimage-unreadable` | a selected record's document cannot be read as one |
| `approval-report-changed` | the report supplied is not the one this binds to |
| `approval-reconciliation-changed` | the report's records no longer group the same way |

The inventory digest is deliberately **not** compared, and it is the one exception. It covers
document content, so the applier's own writes move it — and a second subset of one report could
then never be applied, which is exactly the partial-approval case this contract exists to
support. The precise question is per-record and is asked directly by the preimage check: a
subset whose targets were untouched validates, one whose targets were rewritten is stale and
says which record and which document, and a deleted document fails the same check. Committing
an apply still expires every approval set minted against the previous commit, via
`approval-base-commit-changed`.

A carried stale reason this run did not re-check still stands, as a report's does: clearing a
verdict is at least as thorough as setting it. Two consequences worth stating. Without
`--audit-config-digest` the configuration is never compared, so a live approval set stays
`clean` and a config-stale one stays stale rather than being laundered clean by the weaker
check — supply it in any lane where configuration can move. And the lineage comparison itself
is `report.compare_lineage()`, shared with `validate-report`: an approval set and the report it
came from cannot notice different drift in the same lineage.

**Not an approval set.** Anything else handed in where one is required is
`approval-not-an-approval-set`, and the message says what it actually is: a report ("proof of
what was examined, and deliberately not authority"), a list of digests ("a dispatch list …
which is how an approval set is minted, never a substitute for one"), a string (a branch name
or run id), or an object that does not declare `artifact: approval-set`. A cache entry is a
report payload, so it is refused as one.

**Never repository state.** `write_approval_set(approval, path)` refuses any path git would
keep: `approval-set-tracked-path` for a tracked file, and `approval-set-would-be-tracked` for
one inside the work tree that is not ignored — a `git add -A` in the run it authorizes would
otherwise commit it. Outside the repository, or in a git-ignored path, is where it goes. What
travels in the change is the digest and the rendered summary: `render_approval_set()` for a PR
body (same code-span escaping as `render_report()`, since a record's code and path are content
a model wrote), and `approval_trailers()` for a commit message:

```
Doc-Lifecycle-Approval: <approval digest>
Doc-Lifecycle-Report: <report digest>
Doc-Lifecycle-Approval-State: clean
Doc-Lifecycle-Records: 1 approved, 1 skipped
```

`Doc-Lifecycle-Approval-State` carries the verdict, and names any `unchecked` checks, because
the trailers are the only part of an approval set that lands in the repository: without it a
block copied from a stale set reads exactly like a live one, and the artifact it points at is
untracked and gone.

### Commands

```bash
python3 -m doclifecycle mint-approval --report report.json --repo . \
  --record <record digest> --minter avery@example.com [--minter-kind policy] \
  [--out /tmp/approval.json]
python3 -m doclifecycle validate-approval --approval approval.json --repo . \
  [--report report.json] [--audit-config-digest <sha256>] \
  [--expected-digest <approval digest from the change's trailer>]
python3 -m doclifecycle render-approval --approval approval.json [--trailers]
```

`--record` is repeatable and required; naming none is a usage error (exit 2). Exit codes are
the shared ones: 0 clean, 1 invalid, 2 usage, 3 stale. `render-approval` prints nothing when
the approval set is invalid, exactly as `render-report` does.

```python
from doclifecycle.approval import Minter, mint_approval_set, validate_approval_set
from doclifecycle.reconcile import reconcile

groups = reconcile(report)                      # → Reconciliation or Invalid
approval = mint_approval_set(                   # → ApprovalSet or Invalid
    report, [record_digest], repo_root=".",
    minter=Minter(kind="human", id="avery@example.com"),
)
validate_approval_set(approval.to_dict(), report=report, repo_root=".")
```

## The auto-apply policy

Issue #73, `doclifecycle/policy.py`. The other minter: a standing,
consumer-configured declaration that a narrow class of *mechanical* remedies may have approval
sets minted without waiting for a person, so a scheduled lane keeps producing autonomous fix
PRs. The policy is named as the minter in lineage, and PR review is the designated semantic
review for what it mints — change approval, a person merging the real pull request, still lands
everything.

```json
{
  "artifact": "auto-apply-policy",
  "schema_version": 1,
  "id": "nightly-doc-sync",
  "classes": ["drift-stale-mechanical", "narrative-anchor-refresh"]
}
```

It lives at `.doc-lifecycle/auto-apply-policy.json` beside the registry, because both are
standing declarations a reviewer reads as repository state. `id` is what lineage records, so an
unnamed policy is `policy-missing-field`. `classes` is optional and defaults to every class
there is; an empty list is `policy-invalid-classes` rather than "the defaults", since a policy
that would mint nothing said the confusing way is one nobody can read.

**An absent file is a refusal, not a default.** No policy is `policy-not-configured`, and
`load_auto_apply_policy` returns it as `Invalid`. The permissive reading is the failure the
component exists to avoid: it would make every repository that never considered autonomous
minting into one that performs it.

**The vocabulary is closed, and the closure is the restriction.** The two class names are
`drift-stale-mechanical` (a living document's `STALE` verdict) and `narrative-anchor-refresh` (a
narrative document's `ANCHOR-STALE`). A name outside them is `policy-unknown-class` — refused,
never ignored, so a typo cannot silently narrow a policy and an invented name cannot widen one.
There is no class name for a bloat verdict, a create, or a retire, so no configuration reaches
them; and the bloat codes are refused a second time by name (`policy-never-eligible`), so a
future class that tried to reach one is a contradiction two definitions apart rather than a
permission. `UNVERIFIABLE` is deliberately absent from the drift class: "nobody could check
this" is a question, and a policy answering it would invent the fact nobody could find. So are
the anchor codes that need an anchor *authored* or that name something nobody can resolve.

Per record, in this order — the refusals that hold regardless of configuration first, so a
repository that enabled everything still cannot reach them:

| Refusal | What it means |
|---|---|
| `policy-never-eligible` | a bloat verdict: a passage or document should stop existing or move |
| `policy-record-waived` | a human already disputed this finding, in the waivers file |
| `policy-record-has-destination` | the remedy writes a second document |
| `policy-code-not-mechanical` | no class admits this code at all |
| `policy-class-not-enabled` | a class admits it; this consumer did not enable that class |
| `policy-missing-preimage` | no `units`, or no `assertion` — nothing pinned to replace |
| `policy-missing-evidence` | no `evidence.source` — a PR reviewer has nothing to follow |
| `policy-external-evidence` | `evidence.command` — a real pointer, but outside the closed world, so nobody re-deriving the change from the commit can settle it |
| `policy-fix-names-other-document` | the `fix` names a file the claim it replaces did not — the remedy speaks for a document this record pins nothing from |

The last one is the narrowest and the newest (#123). A preimage pins what a run *read*; a
`fix` is the half a model *wrote*. When the replacement names a file the claim never named, it
asserts something about that file — that it exists, that it carries a section, that it is now
the live one — and the record holds nothing read from it. A citation does not close the gap:
`evidence.source` says one line was consulted, and what a document contains is the thing being
asserted. The document the finding lives in is excluded, since rewriting a passage that names
its own file speaks for nothing else. The shape this refuses is DRIFT-023 of the second
shadow-parity cycle: a superseded pointer repointed at its successor, asserting the successor
"carries criteria and verdict" while that file's verdict section still read "Not yet run"
(`docs/plans/2026-07-27-shadow-parity-gate-rerun-addendum.md`). Recognizing a file reference is
`paths.path_references`, which reads a dotted symbol and a slash-joined prose list as prose,
and is generous everywhere else: a token it over-reads costs a person one more record, and one
it misses costs the refusal.

Deciding is `policy_eligibility(policy, report)`, which is always an `Eligibility` and never
`Invalid`: a report of bloat findings is not a failed run but one whose answer is "a person
decides all of these". It carries a decision *per record* — the class that admitted it, or the
typed reason it did not — because an unattended lane that reported "nothing to do" without
saying what it declined is one nobody can tell from a lane that never ran.

**No bypass.** `mint_policy_approval_set` derives its selection from those decisions and hands
it to `approval.mint_approval_set` — the same call a human dispatch makes, through the same
reconciliation, path-authorization, and preimage refusals. There is no parameter through which
a caller names a record, and no second producer of approval sets. A policy-minted artifact and a
human-minted one over the same selection differ in `minter` and nothing else
(`tests/engine/acceptance/scenario_policy_test.py`), and it reaches the applier by the same
route: the applier is handed an approval set and never asks who minted it. The
operation half of the restriction is `RECORD_REMEDIES`, and the coupling is checked in both
directions: no code any class admits maps to `create-document`, `retire-document`, or
`move-with-provenance`, and every code any class admits has a non-empty entry there — a class
whose code the table did not carry would mint authority the lane then refuses itself, which is
fail-shut but is not a working default.

### Commands

```bash
python3 -m doclifecycle policy-eligibility --report report.json --repo . \
  [--policy .doc-lifecycle/auto-apply-policy.json] [--audit-config-digest <sha256>]
python3 -m doclifecycle policy-mint --report report.json --repo . \
  [--policy <path>] [--out /tmp/approval.json]
```

`policy-eligibility` is read-only and exits 0 even when nothing is eligible. `policy-mint`
refuses `policy-nothing-eligible` (exit 1) in that case, listing every record's own reason on
the run surface, and `--out` refuses any path git would keep exactly as `mint-approval`'s does.
Neither takes a `--record` flag: one that named a record would be a human dispatch wearing a
policy's name.

```python
from doclifecycle.policy import (
    load_auto_apply_policy, mint_policy_approval_set, policy_eligibility,
)

policy = load_auto_apply_policy(".")            # → AutoApplyPolicy or Invalid
policy_eligibility(policy, report)              # → Eligibility (never Invalid)
mint_policy_approval_set(report, policy, repo_root=".")   # → ApprovalSet or Invalid
```

## The applier

The one component that writes, `doclifecycle/applier.py`. An **edit plan** is a separate
versioned artifact (`artifact: edit-plan`, digest required, like an approval set's) binding to
exactly one approval set by digest, with operations from a closed vocabulary — `replace`,
`delete`, `insert`, `create-document`, `retire-document`, `move-with-provenance` — each
declaring the approved record it comes from and the target class it is allowed to write
(`documentation` is the only declarable one, exactly as in `paths.py`).

```bash
python3 -m doclifecycle apply-plan --repo . --plan plan.json --approval approval.json \
  --report report.json --audit-config-digest <sha256>
```

The order of refusals is the contract:

1. **Authority.** The approval set is validated with the repository *and* the report it names,
   through `validate_approval_set`. Both are required: `--report` is a required flag, and a
   verdict that skipped a check refuses as `approval-unchecked-<check>` — in practice
   `approval-unchecked-report`, the applier always supplying the repository — before anything
   else is
   read. Without the report every remaining check is a function of public repository state, so
   a selection nobody minted would validate. `invalid` problems surface as-is; a lineage field
   that moved is a `stale` refusal (exit 3) naming every field, with no working-tree change —
   the message says to re-run the audit and mint afresh.
2. **The plan.** Structural validation is exhaustive: unknown fields, the schema version, the
   digest (`plan-digest-mismatch` on any tamper), the approval binding
   (`plan-approval-mismatch`), each operation's exact field set and spelling
   (`plan-invalid-operation`, via `paths.write_target_problem` — the same owner the approval
   set's paths go through), the target class (`plan-forbidden-target-class`), the record
   binding (`plan-record-not-approved`, `plan-target-not-record-target` — an operation writes
   only its own record's targets), duplicates (`plan-duplicate-operation`), overlapping or
   ambiguous spans (`plan-overlapping-spans`, `plan-conflicting-operations`), and the declared
   postimages (`plan-invalid-postimages`, `plan-postimages-not-derived`).
3. **The remedy is the record's, not the plan's.** `RECORD_REMEDIES` maps each finding code to
   the operations its approved remedy is made of — `STALE`/`UNVERIFIABLE`, `ANCHOR-STALE`, and
   `CONDENSE` to the
   span edits, `CUT` to `delete`, `EXTRACT-AND-MOVE` to `move-with-provenance`, `MERGE-DOC` to
   move and retire, `RETIRE-DOC` to `retire-document`, `DISTILL` to the residue-authoring set
   including `create-document`. Closed and fail-shut: a code nobody listed authorizes nothing
   (`plan-operation-not-record-remedy`). Without it the plan picks the operation, and the
   auto-apply policy's whole restriction — mechanical drift fixes yes, retirements and
   creations never — is unenforceable, because a policy-minted `STALE` record could be executed
   as a `retire-document`. A positioned operation on the record's own document must also lie
   within the hull of that record's approved units — their first line through their last, so
   the blank lines between two approved units stay editable —
   or it is `plan-span-outside-approved-units`. The hull is measured against HEAD, and checked
   *before* the idempotency step below: measured against the working tree it would be
   unavailable on exactly the re-run an attacker arranges, by pre-placing the result of an
   out-of-passage edit on disk. A record's units locate nothing in the document it names as a
   destination, so there is no hull to measure there — which is why a positioned operation may
   name only the record's own document (`plan-target-not-record-target`). A destination is
   written by the whole-document operations and by a move's append, both of which the approval
   covers entire.
4. **Idempotency.** `postimages` maps every written path to the sha256 of its bytes after the
   plan (`null` for a retired document). The no-op verdict is *derived*, never declared: this
   plan is applied to each written path **as HEAD has it** (`repository.head_bytes()`), and the
   run is a no-op — `clean`, `already_applied: true`, nothing written — only when the result is
   byte-for-byte what the working tree holds, the declared postimages agree, and nothing
   outside the plan's own written paths differs from HEAD. A plan is attacker-controlled by
   assumption, so a check that only asked "are the bytes the plan *names* on disk?" would let
   it name the unchanged document (an approved fix reported as landed without landing) or bytes
   somebody else put there (an unapproved diff certified as the approved one). HEAD is the
   sound baseline because a moved base commit is already a stale refusal. The approval's own
   preimage staleness is judged *after* this check, because the applier's writes are the one
   legitimate way those preimages move; preimage staleness that is not "already applied"
   refuses as `stale` like any other moved field.
5. **Exact preimages.** A span operation carries 1-based line numbers and the exact text of
   those lines; `retire-document` carries the whole document. A file, span, or document that
   is not the preimage is `apply-preimage-mismatch` / `apply-preimage-missing`; a create whose
   target exists is `apply-create-exists`. Every post-content is computed in memory and checked
   against the declared postimage (`apply-postimage-mismatch`) before any byte lands.
6. **Whole-diff confinement.** Before writing, the complete working-tree diff — index, work
   tree, and untracked files, read by `repository.worktree_changes()` — must be inside the
   approval set's allowed mutation scope (`apply-working-tree-not-confined`) *and* empty
   (`apply-working-tree-not-clean`): the applier applies onto the committed baseline and
   nothing else, because a scope check is path-granular and would otherwise let a change to
   another passage of an approved document — one no record covers, so one no unit-level
   preimage check sees — ride into the diff this run certifies. Commit or discard first; this
   is also why sequential partial applies from one report commit between subsets. After
   writing, the diff is read again, and an unaccounted change rolls this run's writes back and
   fails the run (`apply-unconfined-change`). Nothing is ever staged or committed here: change
   approval — a person merging or committing — is the only thing that lands anything.

Application order is deterministic: per document, span edits apply bottom-up so the plan's line
numbers stay true, and moved text is appended to its destination (in source-path, span order)
after the destination's own edits, followed by a newline. Provenance travels as data: each
applied `move-with-provenance` entry in the result names its record, source, and destination,
and the approval trailers name the authority.

Model-generated content reaches the applier only as data inside the plan and report payloads.
The module runs no shell and executes nothing it reads — behaviorally, hostile replacement text
lands as bytes and runs nothing (`tests/engine/applier_test.py`), and statically, the module
grants no shell, git, exec, or network capability
(`tests/scripts/engine-capability_test.py`); its only git uses are the read-only status behind
the confinement check and the read-only HEAD blob behind the idempotency check, both through
`repository.py`.

```python
from doclifecycle.applier import apply_edit_plan, load_approval_payload, load_edit_plan

plan = load_edit_plan("plan.json")                    # payload dict or Invalid
approval = load_approval_payload("approval.json")     # payload dict or Invalid
apply_edit_plan(".", plan, approval, report=report)   # ApplyResult or Invalid
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
`load_verdicts()`, `draft_registry()`, `dry_run_migration()`, `repository.lineage()`,
`repository.resolve_commit()`, `repository.changed_paths()`, `repository.last_change()`,
`repository.tracking()`, `repository.tracked_files()`, `reconcile()`, `mint_approval_set()`,
`validate_approval_set()`, `load_approval_set()`, `write_approval_set()`,
`render_approval_set()`, `approval_trailers()`, `load_auto_apply_policy()`,
`policy_eligibility()`, `mint_policy_approval_set()`,
`apply_edit_plan()`, `load_edit_plan()`,
`load_approval_payload()`, `repository.worktree_changes()`), and the commands as subprocesses whose payload
must equal the library result. Path authorization, the git reads, the cache, finding identity,
and verdict recording have no command of their own — they are substrate the other components
(and, for the cache, the bloat lane) call. `tests/engine/support.py` holds what every suite
needs — the engine on `sys.path`,
`RepoTestCase.repo()`, and `run_command()` for the subprocess seam; report fixtures live in
`report_test.py`, which `report_cli_test.py`, `cache_test.py`, and `bloat_test.py` all import
(`GitRepoTestCase`, for a real repository to check freshness against). The report, cache,
bloat-cache, and drift suites build real git repositories, because staleness is a comparison
against a repository — and a diff-scoped scope is a question about a commit range — so a mocked
one would prove nothing. `drift_cli_test.py` imports `drift_test.py`'s repository fixture rather
than rebuilding it. `repository_test.py` holds the git reads to their read-only contract
directly, probing every argument with the spellings git would read as options.
`migrate_test.py` builds a real pre-registry consumer on disk — the `.github/doc-sync/` config
and state a scheduled install carries, plus the documents it managed — and `migrate_cli_test.py`
imports that fixture rather than rebuilding it; both compare the whole tree byte for byte
before and after, because a door that mutates during a dry run is the failure that matters.

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
after every run, refusal paths included. `scenario_approval_test.py` is the approval set's
(issue #68), one class per acceptance criterion: a strict subset of the findings the drift
audit really produced, an apply performed by hand between two subsets so the untouched one
still validates and the applied one is refused by its own preimage, a rival remedy for the
same passage that neither leg can be approved from, and the fixture repository refusing to
hold the artifact anywhere git would keep it. `scenario_policy_test.py` is the auto-apply
policy's (issue #73), one class per acceptance criterion: the policy minting for the STALE
finding the drift audit really produced and that approval set going through the *same*
`apply_edit_plan` to write real bytes into a real work tree; a bloat verdict and a document
retirement refused by name with nothing written; the waiver the fixture's own install carries
stopping the policy dead; and the policy file removed and committed, so an unconfigured
repository mints nothing while a human still can. It imports `scenario_approval_test.py`'s
fixture, so the findings it decides about are the ones those suites already hold the audit to.

`approval_test.py` and `approval_cli_test.py` build real git repositories for the same reason
the report suite does — an approval set's freshness, its allowed scope, and the refusal to
write it into tracked state are all comparisons against a real index and a real work tree.
`approval_cli_test.py` imports `approval_test.py`'s fixture rather than rebuilding it, and
`scenario_approval_test.py` imports `scenario_drift_test.py`'s, so the findings it approves are
the ones that suite already holds the audit to. `applier_test.py` builds on `approval_test.py`'s
fixture the same way — every apply is against a real work tree, refusals compare the whole tree
byte for byte before and after, and the mutation-facing cases (traversal targets, borrowed
paths, forged approval scopes, span-overlap tricks) all run through the public
`apply_edit_plan` seam; `applier_cli_test.py` holds `apply-plan` to the same payloads and exit
codes.
