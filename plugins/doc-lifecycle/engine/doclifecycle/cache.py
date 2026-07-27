"""Lineage-keyed cache with payload revalidation (issue #64).

A cached semantic result is a derived artifact: it cannot outlive the inputs
that could have changed the judgment it records. `cache_key()` folds every one
of them into a single lookup key — document bytes, the source evidence a claim
was checked against, the document inventory, the consumer's audit
configuration, the registry that classified the corpus, the audit ruleset, the
artifact schema, the plugin, and the repository/commit the evidence was read
at. Two keys differing in exactly one field address different cache slots, so
changing any one of them is a cache miss, never a stale hit.

A key match is not enough to earn a hit. On read, the stored payload is
revalidated exactly as a report is: it is wrapped in the same shape and run
through `report.validate_report` — the landed validator (#62), never a
parallel one — so a parseable-but-invalid record, a lineage that has since
drifted (a different repository, a moved commit, a re-run audit
configuration, a changed registry or inventory, a bumped ruleset or plugin),
or a result that admits it did not finish are each `Invalid`/`stale`/`partial`
under that validator and therefore a miss here too. On top of that, because a
cache entry is about *one* document checked against *one* piece of source
evidence — neither of which the report contract's lineage carries — the
entry's declared identity is compared against what was asked for, so a payload
that validates cleanly but describes a different document/source pair (a
mismatched chunk sitting at the right path) is also a miss rather than a false
hit.

Fails closed throughout: any lookup this module cannot positively confirm is
still valid comes back as a miss, never a warning and never the stale payload.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

from . import ARTIFACT_SCHEMA_VERSION
from .digest import sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH
from .report import validate_report
from .results import STATE_FINDINGS, STATE_PARTIAL, STATE_STALE, Invalid

# Why a lookup missed, named rather than left to be inferred from a bare
# `False` — a test (or a caller logging a miss) can tell "nothing was ever
# cached here" from "something was, and revalidation refused it."
MISS_NOT_FOUND = "cache-miss-not-found"
MISS_CORRUPT = "cache-miss-corrupt"
MISS_INVALID = "cache-miss-invalid-payload"
MISS_STALE = "cache-miss-stale-lineage"
MISS_INCOMPLETE = "cache-miss-incomplete-result"
MISS_IDENTITY = "cache-miss-identity-mismatch"
MISS_SHAPE = "cache-miss-malformed-entry"

# Everything that can change a semantic judgment about one document checked
# against one piece of source evidence. The tuple's order is for readability
# only — the digest is over the canonical JSON form, so field order never
# matters to identity.
KEY_FIELDS = (
    "document_digest",
    "source_digest",
    "inventory_digest",
    "audit_config_digest",
    "registry_digest",
    "ruleset_version",
    "schema_version",
    "plugin_version",
    "repository",
    "base_commit",
)


@dataclass(frozen=True)
class CacheKey:
    """Every input the issue names, folded into one lookup key.

    Two keys differing in exactly one field never collide: `digest` is a
    sha256 over the canonical JSON of every field above, so a changed
    ruleset version, a re-run audit configuration, or a moved `HEAD` each
    address a distinct cache slot rather than silently reusing another one's.
    """

    document_digest: str
    source_digest: str
    inventory_digest: str
    audit_config_digest: str
    registry_digest: str
    ruleset_version: int
    schema_version: int
    plugin_version: str
    repository: str
    base_commit: str

    def to_dict(self):
        return {field: getattr(self, field) for field in KEY_FIELDS}

    @property
    def digest(self):
        return sha256_canonical(self.to_dict())


def _lineage_mapping(lineage):
    """Accept either a plain mapping (what `report.current_lineage()` returns)
    or an object carrying the same fields as attributes (a `report.Lineage`,
    or a validated `Report`'s `.lineage`) — both are legitimate sources of
    "the current lineage" and callers should not have to convert one to the
    other just to build a key."""
    if hasattr(lineage, "to_dict"):
        return lineage.to_dict()
    return lineage


def cache_key(document_digest, source_digest, lineage,
             schema_version=ARTIFACT_SCHEMA_VERSION):
    """Build a `CacheKey` from a document/source pair and a report lineage.

    Reuses the report contract's own lineage fields rather than re-deriving
    them: `lineage` is whatever `report.current_lineage()` (called with the
    consumer's current `audit_config_digest` — that field is only present when
    the caller supplies one) produced, or a validated `Report`'s `.lineage`,
    so a cache key and a report's own freshness check are always computed from
    the same values.
    """
    fields = _lineage_mapping(lineage)
    return CacheKey(
        document_digest=document_digest,
        source_digest=source_digest,
        inventory_digest=fields["inventory_digest"],
        audit_config_digest=fields["audit_config_digest"],
        registry_digest=fields["registry_digest"],
        ruleset_version=fields["ruleset_version"],
        schema_version=schema_version,
        plugin_version=fields["plugin_version"],
        repository=fields["repository"],
        base_commit=fields["base_commit"],
    )


@dataclass(frozen=True)
class CacheResult:
    """The outcome of a cache lookup.

    `hit` is `True` only when an entry was found at the key *and* survived
    full revalidation; every other case is a miss with `reason` naming which
    check closed it, never a partial or "probably fine" outcome in between.
    """

    hit: bool
    record: Optional[dict] = None
    reason: Optional[str] = None


def entry_path(cache_dir, key):
    """The file one cache entry lives at. `put()`/`get()` are the supported
    interface; this is exposed for tooling (and tests) that need to inspect
    or deliberately corrupt an entry on disk."""
    return os.path.join(cache_dir, key.digest + ".json")


def put(cache_dir, key, record, evidence_sources=("cached-semantic-result",)):
    """Store one semantic result under `key`.

    Written as a single-record report payload — the same shape
    `report.validate_report` reads — so a later `get()` revalidates it through
    that validator rather than a cache-specific one. `record` must already
    carry the `id` and `digest` the report contract requires; its
    `document_digest`/`source_digest` fields are set from `key` when absent,
    since the report contract's lineage has no notion of "one document" and
    this is how a read tells one cache entry's subject from another's.

    The write is atomic (write-then-rename), so a reader never observes a
    half-written entry.
    """
    os.makedirs(cache_dir, exist_ok=True)
    record = dict(record)
    record.setdefault("document_digest", key.document_digest)
    record.setdefault("source_digest", key.source_digest)
    payload = {
        "status": STATE_FINDINGS,
        "schema_version": key.schema_version,
        "lineage": {
            "repository": key.repository,
            "base_commit": key.base_commit,
            "audit_mode": "chunk",
            "inventory_digest": key.inventory_digest,
            "audit_config_digest": key.audit_config_digest,
            "registry_digest": key.registry_digest,
            "ruleset_version": key.ruleset_version,
            "plugin_version": key.plugin_version,
            "evidence_boundary": {
                "sources": list(evidence_sources), "excluded": [],
            },
        },
        "records": [record],
        "incomplete": [],
    }
    path = entry_path(cache_dir, key)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp_path, path)
    return path


def get(cache_dir, key, repo_root, registry_path=DEFAULT_REGISTRY_PATH):
    """Look up `key`, revalidate the payload, and return a `CacheResult`.

    Fails closed at every step: a missing file, unparseable JSON, a
    structurally invalid record, a lineage the repository has since outgrown
    (including one naming a different repository or commit entirely, or an
    audit configuration/registry/inventory/ruleset/plugin that no longer
    matches), a result admitting it did not finish, or a payload describing a
    different document/source pair than `key` names are each a miss — never a
    warning, and never the stale payload.
    """
    path = entry_path(cache_dir, key)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return CacheResult(False, reason=MISS_NOT_FOUND)

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return CacheResult(False, reason=MISS_CORRUPT)

    # Revalidate through the landed validator — the same one a report reads
    # through — rather than a parallel check of our own. This is what catches
    # a parseable-but-invalid record, a drifted or foreign lineage, and an
    # incomplete result: validate_report's own staleness comparison already
    # covers repository, base_commit, inventory_digest, registry_digest,
    # ruleset_version, and plugin_version, and its content/state consistency
    # check already covers "partial".
    result = validate_report(
        payload, repo_root=repo_root, registry_path=registry_path,
        audit_config_digest=key.audit_config_digest,
    )
    if isinstance(result, Invalid):
        return CacheResult(False, reason=MISS_INVALID)
    if result.status == STATE_STALE:
        return CacheResult(False, reason=MISS_STALE)
    if result.status == STATE_PARTIAL:
        return CacheResult(False, reason=MISS_INCOMPLETE)
    if len(result.records) != 1:
        # A cache entry is one semantic result about one document/source
        # pair; anything else is not a shape this module ever wrote itself.
        return CacheResult(False, reason=MISS_SHAPE)

    record = result.records[0]
    if (
        record.extra.get("document_digest") != key.document_digest
        or record.extra.get("source_digest") != key.source_digest
    ):
        # The lineage fields all matched, but the payload is about a
        # different document or a different piece of source evidence than
        # the one being asked about — a mismatched chunk sitting at the
        # right path is not a hit for this key.
        return CacheResult(False, reason=MISS_IDENTITY)

    return CacheResult(True, record=record.to_dict())
