"""Content-addressed identity for engine artifacts.

Digests are what later lineage rests on: a report pins the registry and
inventory digests, and a cache entry is only reusable while they still match.
So they are computed over *meaning* — a canonical JSON form — not over the
bytes a human happened to type. Reformatting the registry must not invalidate a
report; changing a rule must.

`load_strict_json` reads what those digests are taken over: a report, an
approval set, and an edit plan are each read off disk, parsed strictly, and
digested the same way, so this is also where the one strict-JSON reader
lives — one open/decode/parse sequence three call sites used to each carry a
slightly different copy of.
"""

import hashlib
import json

from .results import Problem


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


def _reject_constant(name):
    raise ValueError(
        f"{name} is not JSON — a digested artifact must survive a strict "
        f"parser and its own digest, which are taken over the same encoding"
    )


def load_strict_json(path, *, unreadable_code, unparseable_code, nesting_code,
                      max_nesting=64):
    """Read and strictly parse a JSON file at `path`.

    Returns `(payload, None)` on success, `(None, Problem)` otherwise. The
    caller supplies the codes, since each artifact answers with its own
    vocabulary (`report-unparseable`, `plan-nesting-too-deep`, and so on) —
    this function owns only the mechanics every one of them shared:

    - an unreadable file (`OSError`) and one that is not UTF-8
      (`UnicodeDecodeError`, a `ValueError` and so not caught by `OSError`)
      both answer `unreadable_code`, since neither ever reaches a parser;
    - `NaN`/`Infinity`/`-Infinity` are rejected — JSON defines none of them,
      Python's decoder accepts them by default, and a value that survived
      would make the artifact's own digest untrustworthy against a strict
      re-parse — alongside any other `json.JSONDecodeError`, both answering
      `unparseable_code`;
    - a `RecursionError` — the decoder recurses, and a few kilobytes of
      nested brackets must reach a verdict, not a traceback — answers
      `nesting_code`, whose message cites `max_nesting`. Only `report.py`
      pairs this with a structural bound (`_scan`, an iterative,
      `MAX_NESTING`-deep post-parse walk of every record); `applier.py` and
      `approval.py` have no such guard, so for a plan or an approval set
      this catch is defense in depth, not an enforced bound — a decoded
      payload can nest deeper than the decoder itself happened to survive.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return None, Problem(
            code=unreadable_code,
            message=f"cannot read the file at {path}: {exc.strerror}",
            location=path,
        )
    except UnicodeDecodeError as exc:
        return None, Problem(
            code=unreadable_code,
            message=(
                f"the file at {path} is not valid UTF-8 ({exc.reason} at "
                f"byte {exc.start}) — re-encode it; JSON is a text format"
            ),
            location=path,
        )
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, Problem(
            code=unparseable_code,
            message=f"the file at {path} is not valid JSON: {exc}",
            location=path,
        )
    except RecursionError:
        return None, Problem(
            code=nesting_code,
            message=(
                f"the file at {path} nests too deeply to parse — this engine "
                f"reads at most {max_nesting} levels"
            ),
            location=path,
        )
    return payload, None
