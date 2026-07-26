"""Content-addressed identity for engine artifacts.

Digests are what later lineage rests on: a report pins the registry and
inventory digests, and a cache entry is only reusable while they still match.
So they are computed over *meaning* — a canonical JSON form — not over the
bytes a human happened to type. Reformatting the registry must not invalidate a
report; changing a rule must.
"""

import hashlib
import json


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


def canonical(value):
    """The canonical JSON encoding a digest is taken over."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_canonical(value):
    return sha256_bytes(canonical(value).encode("utf-8"))
