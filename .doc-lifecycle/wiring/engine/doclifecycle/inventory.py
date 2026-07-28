"""The document inventory: what documentation exists, and what kind it is."""

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from . import registry as registry_mod
from .digest import sha256_canonical, sha256_file
from .results import STATUS_OK, Invalid, Problem

DEFAULT_REGISTRY_PATH = ".doc-lifecycle/registry.json"


@dataclass(frozen=True)
class Document:
    path: str
    kind: str
    doc_set: Optional[str]
    rule: str
    digest: str


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class Inventory:
    status: str
    registry_path: str
    registry_digest: str
    documents: Tuple[Document, ...]
    findings: Tuple[Finding, ...]
    digest: str
    # The parsed registry this inventory was classified by. Not identity — the
    # digest above is — and not part of the wire form; it is here so a caller
    # that must classify a path the inventory does *not* hold reads the same
    # rules that produced it, rather than parsing the file a second time and
    # risking a different answer.
    registry: Optional[registry_mod.Registry] = field(
        default=None, compare=False, repr=False
    )

    def to_dict(self):
        """The wire form. Both the library and the CLI hand back exactly this."""
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "registry": {"path": self.registry_path, "digest": self.registry_digest},
            "digest": self.digest,
            "documents": _document_payload(self.documents),
            "findings": [
                {"code": f.code, "path": f.path, "message": f.message}
                for f in self.findings
            ],
        }


def _document_payload(documents):
    return [
        {
            "path": d.path,
            "kind": d.kind,
            "set": d.doc_set,
            "rule": d.rule,
            "digest": d.digest,
        }
        for d in documents
    ]


def walk_root(repo_root, root, registry):
    """Yield (repo-relative path, is_symlink) under `root`, in sorted order.

    A root may be a single file (`CLAUDE.md`) or a subtree (`docs`). Only files
    with a registry-declared extension are documents; other files under a root
    are not documentation, and so are not subject to the closed-world rule.

    Excluded paths are pruned, not filtered, so an excluded subtree is never
    walked. Symlinks are yielded but never followed: a symlinked directory is
    reported and pruned rather than descended, so an innocuous-looking
    documentation path cannot pull in a subtree from outside its root.

    Public because the migration door walks a corpus before any rule exists to
    classify it (`registry.unclassified`), and a draft built from a second,
    subtly different enumeration would propose rules for documents the
    inventory will not hold.
    """
    absolute = os.path.join(repo_root, root)
    if os.path.islink(absolute):
        yield root, True
        return
    if os.path.isfile(absolute):
        if registry.is_document(root):
            yield root, False
        return
    for dirpath, dirnames, filenames in os.walk(absolute):
        kept = []
        for name in sorted(dirnames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, repo_root)
            if name == ".git" or registry.excludes(rel):
                continue
            if os.path.islink(path):
                yield rel, True
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, repo_root)
            if not registry.is_document(rel) or registry.excludes(rel):
                continue
            yield rel, os.path.islink(path)


def load_registry(repo_root, registry_path=DEFAULT_REGISTRY_PATH):
    """Read and parse the registry at `repo_root`. Returns a `Registry`/`Invalid`.

    Public because the registry answers one question no other module can:
    which subtrees are declared documentation. Path authorization needs that
    list, and an approval set's allowed mutation scope is authorized against
    it — so both read the registry through here rather than each learning where
    the file lives and what an unparseable one means.
    """
    try:
        with open(os.path.join(repo_root, registry_path), encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return Invalid((Problem(
            code="registry-missing",
            message=(
                f"cannot read the registry at {registry_path}: {exc.strerror} — "
                f"classification is closed-world, so there is nothing to audit "
                f"without it"
            ),
            location=registry_path,
        ),))
    reg, problems = registry_mod.parse(text, location=registry_path)
    if problems:
        return Invalid(tuple(problems))
    return reg


def build_inventory(repo_root, registry_path=DEFAULT_REGISTRY_PATH):
    """Inventory every document under the registry's declared roots.

    Returns an `Inventory` (status "ok"), or `Invalid` when the registry cannot
    be trusted — the whole run fails, rather than degrading to a partial
    inventory a reader could mistake for the corpus.
    """
    reg = load_registry(repo_root, registry_path)
    if isinstance(reg, Invalid):
        return reg

    missing_roots = [
        root for root in reg.roots
        if not os.path.exists(os.path.join(repo_root, root))
    ]
    if missing_roots:
        return Invalid(tuple(Problem(
            code="registry-missing-root",
            message=(
                f"declared root '{root}' does not exist in the repository — "
                f"fix the registry rather than auditing a corpus that silently "
                f"omits it"
            ),
            location=registry_path,
        ) for root in missing_roots))

    documents, findings = [], []
    for root in reg.roots:
        for rel, is_symlink in walk_root(repo_root, root, reg):
            if is_symlink:
                findings.append(Finding(
                    code="symlinked-path",
                    path=rel,
                    message=(
                        f"{rel} is a symlink — documentation paths must be real "
                        f"files inside their root, so it is neither inventoried "
                        f"nor followed"
                    ),
                ))
                continue
            rule = reg.classify(rel)
            if rule is None:
                # Closed world: a document under a declared root that no rule
                # claims is a finding, never a silent skip.
                findings.append(Finding(
                    code="unregistered-document",
                    path=rel,
                    message=(
                        f"{rel} is under declared root '{root}' but matches no "
                        f"registry rule — classify it or exclude it"
                    ),
                ))
                continue
            documents.append(Document(
                path=rel,
                kind=rule.kind,
                doc_set=rule.doc_set,
                rule=rule.glob,
                digest=sha256_file(os.path.join(repo_root, rel)),
            ))

    documents = tuple(sorted(documents, key=lambda d: d.path))
    findings = tuple(sorted(findings, key=lambda f: (f.path, f.code)))
    return Inventory(
        status=STATUS_OK,
        registry_path=registry_path,
        registry_digest=reg.digest,
        documents=documents,
        findings=findings,
        # The inventory's identity is what it says about the corpus: which
        # documents, classified how, with what contents — plus the registry that
        # decided it. Finding *messages* are prose, so they are not identity.
        digest=sha256_canonical({
            "registry_digest": reg.digest,
            "documents": _document_payload(documents),
            "findings": [{"code": f.code, "path": f.path} for f in findings],
        }),
        registry=reg,
    )
