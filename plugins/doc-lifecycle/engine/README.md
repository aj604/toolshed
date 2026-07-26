# doc-lifecycle engine

Stdlib-only Python package (`doclifecycle`) behind the plugin's skills and workflows. No
third-party dependencies. Library functions are the implementation; the commands wrap them and
add nothing, so an import and a command cannot disagree.

Current surface: the registry parser and the document inventory. Report contract, segmenter,
cache, path authorization, approval sets, and the applier land in later slices of the
re-architecture (issue #57).

## Modules

| Module | Owns |
|---|---|
| `doclifecycle/registry.py` | registry parsing, validation, classification, glob matching, registry digest |
| `doclifecycle/inventory.py` | `build_inventory()`, the closed-world walk, document/inventory digests |
| `doclifecycle/results.py` | `Problem`, `Invalid`, the `ok`/`invalid` status strings |
| `doclifecycle/digest.py` | `sha256_file`, `sha256_canonical`, the canonical JSON form digests are taken over |
| `doclifecycle/cli.py`, `__main__.py`, `doc-lifecycle.py` | argv parsing and exit codes only |

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
Symlinks under a root are reported as `symlinked-path` and never followed; the general path
authorization module (issue #67) becomes the single owner of path rules when it lands.

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

## Digests

`digest.sha256_canonical` hashes the canonical JSON form (sorted keys, compact separators),
so reformatting a registry is not a new registry while changing a rule is. Rule order is part
of the registry digest because it decides precedence; root, exclude, set, and extension order
is normalized away. A document's digest is the sha256 of its bytes. The inventory digest covers
the registry digest, every document entry, and each finding's code and path — not finding
messages, which are prose.

## Tests

`tests/engine/*_test.py` (stdlib `unittest`), run by ordinary discovery, which is also how
CI runs them (`.github/workflows/release.yml`, "Engine tests"):

```bash
python3 -m unittest discover -s tests/engine -p '*_test.py'
```

Seams under test: `build_inventory()` as a library call, and the commands as subprocesses
whose payload must equal `build_inventory(...).to_dict()`. Shared fixtures live in
`tests/engine/support.py`.
