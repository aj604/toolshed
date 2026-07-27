"""The repository-wide context index (issue #66).

A bloat audit reaches verdicts about *value*, and value is never a local
property. Whether a passage is redundant depends on what the rest of the corpus
says; where content belongs depends on which document owns the subject; whether
two merges collide depends on what every other chunk is proposing. A worker
handed a bounded slice cannot see any of that, so a worker that decided it
locally would be guessing — and guessing about deletion is the one thing this
engine must not do.

So the index is built first, over the *whole* repository, before any slicing:
every inventoried document, segmented into the assertion units `segment.py`
already defines, with a reverse map from each unit's content digest to every
place it occurs. Chunk workers still receive bounded slices for cost, but any
question about duplication, ownership, or a destination is answered here, from
global data, identically no matter which slice asked.

Read-only and deterministic throughout: it opens documents the inventory
already claims, runs the model-free segmenter over them, and derives everything
else. The same repository state always produces the same index and the same
digest, and the index is a pure function of the inventory — which is why it
needs no lineage field of its own.

Two design points worth naming.

**Occurrences are positions, not identities.** A unit's digest is its content
(`segment.unit_digest`), so the same sentence written five times is one unit
with five occurrences. That is exactly what a duplication audit needs, and it is
also why a finding cannot say *which* copy it means from its unit group alone —
the group is deduplicated. `occurrences_of()` is the record data that closes
that gap.

**Ownership is deterministic, not judged.** When one unit occurs in several
documents, `owner_of()` names the document a duplicate's content belongs in by a
fixed rule — document kind first, then path. No model, no heuristics over prose:
a destination a reviewer cannot re-derive is a destination nobody can check.
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .digest import sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .results import STATUS_OK, Invalid
from .segment import segment_text

# Which document kind is a claim's home, most durable first. A living document
# must be currently true, so it is where a durable claim belongs; a narrative
# document is honestly dated rather than line-verified; a planning document is
# temporary and ends in distillation or retirement, so content is never moved
# *into* one. Ordering ownership by this is what makes "the legitimate
# destination" a fact about the document model rather than a preference.
KIND_PRECEDENCE = ("living", "narrative", "planning")


@dataclass(frozen=True)
class Occurrence:
    """One place a unit's content actually appears.

    The pointer a duplication finding needs and its unit group cannot carry:
    the group is a deduplicated set of content digests, so five identical
    sentences are one member of it. `path` and `line` are how a reviewer finds
    the copy under discussion.
    """

    path: str
    ordinal: int
    line: int
    end_line: int

    def to_dict(self):
        return {
            "path": self.path,
            "ordinal": self.ordinal,
            "line": self.line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True)
class IndexedUnit:
    """One distinct piece of content in the corpus, wherever it appears."""

    digest: str
    kind: str
    text: str
    assertion_capable: bool

    def to_dict(self):
        return {
            "digest": self.digest,
            "kind": self.kind,
            "text": self.text,
            "assertion_capable": self.assertion_capable,
        }


@dataclass(frozen=True)
class IndexedDocument:
    """One inventoried document, as the index sees it."""

    path: str
    kind: str
    doc_set: Optional[str]
    document_digest: str
    segmentation_digest: str
    units: Tuple[str, ...]

    def to_dict(self):
        return {
            "path": self.path,
            "kind": self.kind,
            "set": self.doc_set,
            "document_digest": self.document_digest,
            "segmentation_digest": self.segmentation_digest,
            "units": list(self.units),
        }


@dataclass(frozen=True)
class Unexamined:
    """One part of the corpus the index could not read.

    Named rather than skipped: the audit built on this index declares the same
    gap as an `incomplete` scope, so the absence of a finding about a document
    the index never opened never reads as a clean verdict about it.
    """

    scope: str
    code: str
    reason: str

    def to_dict(self):
        return {"scope": self.scope, "code": self.code, "reason": self.reason}


@dataclass(frozen=True)
class ContextIndex:
    """Every document, every distinct unit, and every place each unit occurs."""

    status: str
    registry_digest: str
    inventory_digest: str
    documents: Tuple[IndexedDocument, ...]
    units: Tuple[IndexedUnit, ...]
    unexamined: Tuple[Unexamined, ...]
    digest: str
    _occurrences: Dict[str, Tuple[Occurrence, ...]]
    _kinds: Dict[str, str]

    def occurrences_of(self, unit_digest):
        """Every place this content appears, in (path, position) order.

        Global by construction: the answer does not depend on which chunk is
        asking, and includes occurrences in documents no worker was given.
        """
        return self._occurrences.get(unit_digest, ())

    def duplicated_units(self):
        """Unit digests occurring more than once anywhere in the corpus."""
        return tuple(sorted(
            digest for digest, places in self._occurrences.items()
            if len(places) > 1
        ))

    def owner_of(self, unit_digest):
        """The document this content belongs in, or `None` if it occurs nowhere.

        Deterministic: the most durable document kind wins
        (`KIND_PRECEDENCE`), and equal kinds are broken by path. A copy in a
        planning document therefore never outranks the living document that
        states the same thing, whichever chunk happens to be looking.
        """
        places = self._occurrences.get(unit_digest, ())
        if not places:
            return None
        return min(
            {place.path for place in places},
            key=lambda path: (self.rank_of(path), path),
        )

    def rank_of(self, path):
        """A document's ownership rank; unknown documents rank last."""
        kind = self._kinds.get(path)
        if kind not in KIND_PRECEDENCE:
            return len(KIND_PRECEDENCE)
        return KIND_PRECEDENCE.index(kind)

    def document(self, path):
        return next((d for d in self.documents if d.path == path), None)

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "registry_digest": self.registry_digest,
            "inventory_digest": self.inventory_digest,
            "digest": self.digest,
            "documents": [d.to_dict() for d in self.documents],
            "units": [u.to_dict() for u in self.units],
            "occurrences": {
                digest: [o.to_dict() for o in places]
                for digest, places in sorted(self._occurrences.items())
            },
            "unexamined": [u.to_dict() for u in self.unexamined],
        }


def _index_digest(inventory_digest, documents, unexamined):
    """The index's identity.

    Covers the inventory it was built from, each document's ordered units, and
    the scopes it could not read — everything a downstream verdict could depend
    on. Reasons are prose and stay out, as they do in the inventory digest.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "inventory_digest": inventory_digest,
        "documents": [d.to_dict() for d in documents],
        "unexamined": [{"scope": u.scope, "code": u.code} for u in unexamined],
    })


def build_context_index(repo_root, registry_path=DEFAULT_REGISTRY_PATH):
    """Index the whole repository's documentation. Read-only and model-free.

    Returns a `ContextIndex`, or `Invalid` when the registry cannot be trusted
    — the same fail-closed rule the inventory follows, for the same reason: an
    index built on a corpus that silently omits documents would make every
    "this appears nowhere else" verdict a lie.
    """
    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        return inventory

    documents, units, occurrences, kinds = [], {}, {}, {}
    unexamined = [
        Unexamined(scope=f.path, code=f.code, reason=f.message)
        for f in inventory.findings
    ]

    for document in inventory.documents:
        try:
            with open(os.path.join(repo_root, document.path), "rb") as fh:
                text = fh.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # A document the inventory claims but the index cannot read is a
            # coverage gap, not a reason to abandon the index: the rest of the
            # corpus is still indexable, and the gap is declared rather than
            # silently narrowing what "occurs nowhere else" means.
            unexamined.append(Unexamined(
                scope=document.path,
                code="document-unreadable",
                reason=(
                    f"cannot index {document.path} ({exc}) — it is inventoried "
                    f"but was not searched, so no verdict may claim its "
                    f"contents are absent from the corpus"
                ),
            ))
            continue

        segmentation = segment_text(text, path=document.path, kind=document.kind)
        kinds[document.path] = document.kind
        documents.append(IndexedDocument(
            path=document.path,
            kind=document.kind,
            doc_set=document.doc_set,
            document_digest=document.digest,
            segmentation_digest=segmentation.digest,
            units=tuple(unit.digest for unit in segmentation.units),
        ))
        for unit in segmentation.units:
            units.setdefault(unit.digest, IndexedUnit(
                digest=unit.digest,
                kind=unit.kind,
                text=unit.text,
                assertion_capable=unit.assertion_capable,
            ))
            occurrences.setdefault(unit.digest, []).append(Occurrence(
                path=document.path,
                ordinal=unit.ordinal,
                line=unit.line,
                end_line=unit.end_line,
            ))

    documents = tuple(documents)
    unexamined = tuple(sorted(unexamined, key=lambda u: (u.scope, u.code)))
    frozen = {
        digest: tuple(sorted(places, key=lambda o: (o.path, o.ordinal)))
        for digest, places in occurrences.items()
    }
    return ContextIndex(
        status=STATUS_OK,
        registry_digest=inventory.registry_digest,
        inventory_digest=inventory.digest,
        documents=documents,
        units=tuple(sorted(units.values(), key=lambda u: u.digest)),
        unexamined=unexamined,
        digest=_index_digest(inventory.digest, documents, unexamined),
        _occurrences=frozen,
        _kinds=kinds,
    )
