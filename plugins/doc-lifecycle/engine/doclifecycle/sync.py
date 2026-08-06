"""Incremental-sync planning: compare the accepted ledger to the repository.

This module owns the durable assertion-ledger contract and the first complete
path through phase 1: assertion identities are compared document-by-document,
safe reuse is explained, and only units needing judgment enter the bounded
work order.  The accepted ledger is only ever read.  Probe execution remains a
later extension of this seam; ledger comparison never invokes a model.
"""

import datetime
import json
import keyword
import os
import re
from dataclasses import dataclass
from typing import Tuple

from . import ARTIFACT_SCHEMA_VERSION, RULESET_VERSION
from .digest import sha256_bytes, sha256_canonical, sha256_file
from .drift import OBLIGATION_ANCHOR, _audit_anchor, plan_drift_audit
from .finding import FACTUAL, NORMATIVE, RATIONALE
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .paths import repository_relative_problem
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    Invalid,
    Problem,
)
from .segment import segment_document

LEDGER_SCHEMA_VERSION = 1
WORK_ORDER_SCHEMA_VERSION = 1

DEFAULT_LEDGER_PATH = ".doc-lifecycle/assertion-ledger.jsonl"
DEFAULT_CONFIG_PATH = ".doc-lifecycle/config.json"

MODE_SYNC = "sync"
MODE_BOOTSTRAP = "bootstrap"
MODE_RECONCILE = "reconcile"
SYNC_MODES = (MODE_SYNC, MODE_BOOTSTRAP, MODE_RECONCILE)

DEFAULT_MAX_WORK_ORDER_UNITS = 40
DEFAULT_MAX_MODEL_CALLS = 1
DEFAULT_MAX_TURNS = 40
DEFAULT_SYNC_MODEL = "sonnet"

STRATEGY_PROBE = "probe"
STRATEGY_DEPS = "deps"
STRATEGY_ON_CHANGE = "on-change"
STRATEGY_RECONCILE_ONLY = "reconcile-only"
STRATEGIES = (
    STRATEGY_PROBE,
    STRATEGY_DEPS,
    STRATEGY_ON_CHANGE,
    STRATEGY_RECONCILE_ONLY,
)

PROVENANCES = ("judged", "heuristic", "seeded")
PROBE_KINDS = (
    "path_exists",
    "content_match",
    "json_value",
    "symbol_defined",
    "tool_probe",
)
STATUSES = ("active", "tombstone")

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_SHELL_SYNTAX = ";&|<>()$`"
_GLOB_META = "*?["
_MAX_PATTERN_LENGTH = 4096
_HEADER_FIELDS = {
    "record", "schema", "ruleset", "registry_digest", "plugin_version",
    "established", "covered", "uncovered",
}
_ENTRY_BASE_FIELDS = {
    "record", "doc", "unit", "class", "obligation", "strategy",
    "provenance", "lineage", "status",
}
_LINEAGE_FIELDS = {
    "report_digest", "commit", "plugin_version", "model", "date",
}
_ESTABLISHED_FIELDS = {"report_digest", "commit", "date"}
_REMOVED_FIELDS = {"commit", "date"}
_OBLIGATIONS = {
    FACTUAL: ("evidence",),
    NORMATIVE: ("governing-source", "owner-judgment"),
    RATIONALE: ("coherence",),
}


def _one_line(value):
    return (
        isinstance(value, str) and bool(value.strip())
        and not any(char in value for char in "\r\n\x00")
    )


def _date(value):
    if not (isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _whole_positive(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _reject_constant(name):
    raise ValueError(f"{name} is not JSON")


@dataclass(frozen=True)
class SyncBudget:
    max_work_order_units: int = DEFAULT_MAX_WORK_ORDER_UNITS
    max_model_calls: int = DEFAULT_MAX_MODEL_CALLS
    max_turns: int = DEFAULT_MAX_TURNS
    sync_model: str = DEFAULT_SYNC_MODEL

    def to_dict(self):
        return {
            "max_work_order_units": self.max_work_order_units,
            "max_model_calls": self.max_model_calls,
            "max_turns": self.max_turns,
            "sync_model": self.sync_model,
        }

    @property
    def digest(self):
        return sha256_canonical(self.to_dict())


@dataclass(frozen=True)
class LedgerHeader:
    ruleset: int
    registry_digest: str
    plugin_version: str
    established: dict
    covered: Tuple[str, ...]
    uncovered: Tuple[str, ...]


@dataclass(frozen=True)
class LedgerEntry:
    doc: str
    unit: str
    assertion_class: str
    obligation: str
    strategy: str
    provenance: str
    lineage: dict
    status: str
    raw: dict


@dataclass(frozen=True)
class AssertionLedger:
    path: str
    digest: str
    header: LedgerHeader
    entries: Tuple[LedgerEntry, ...]


@dataclass(frozen=True)
class JudgmentWorkOrder:
    mode: str
    session_id: str
    chunk_id: str
    total_chunk_count: int
    ledger_digest: str
    inventory_digest: str
    unit_set_digest: str
    budget: SyncBudget
    units: Tuple[dict, ...] = ()

    def to_dict(self):
        return {
            "schema_version": WORK_ORDER_SCHEMA_VERSION,
            "mode": self.mode,
            "session_id": self.session_id,
            "chunk_id": self.chunk_id,
            "total_chunk_count": self.total_chunk_count,
            "bindings": {
                "ledger_digest": self.ledger_digest,
                "inventory_digest": self.inventory_digest,
                "unit_set_digest": self.unit_set_digest,
                "budget_digest": self.budget.digest,
            },
            "budget": self.budget.to_dict(),
            "units": [dict(unit) for unit in self.units],
        }


@dataclass(frozen=True)
class SyncPlan:
    status: str
    mode: str
    as_of: str
    deterministic_results: dict
    work_order: JudgmentWorkOrder

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "mode": self.mode,
            "as_of": self.as_of,
            "deterministic_results": dict(self.deterministic_results),
            "work_order": self.work_order.to_dict(),
        }


def load_sync_budget(repo_root, config_path=DEFAULT_CONFIG_PATH):
    """Load the consumer's ``sync`` config, or the conservative defaults.

    The top-level file is shared with later phases, so sibling sections are
    accepted without interpretation.  The sync section itself is closed:
    silently ignoring a misspelled budget field would defeat the tripwire.
    """
    absolute = os.path.join(repo_root, config_path)
    if not os.path.exists(absolute):
        return SyncBudget()
    try:
        with open(absolute, encoding="utf-8") as fh:
            payload = json.load(fh, parse_constant=_reject_constant)
    except OSError as exc:
        return Invalid((Problem(
            code="sync-config-unreadable",
            message=f"cannot read the sync configuration at {config_path}: {exc}",
            location=config_path,
        ),))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        return Invalid((Problem(
            code="sync-config-unparseable",
            message=(f"the sync configuration at {config_path} is not strict "
                     f"JSON: {exc}"),
            location=config_path,
        ),))

    if not isinstance(payload, dict):
        return Invalid((Problem(
            code="sync-config-invalid",
            message="the consumer configuration must be an object of named sections",
            location=config_path,
        ),))
    raw = payload.get("sync", {})
    allowed = {
        "max_work_order_units", "max_model_calls", "max_turns", "sync_model",
    }
    if not isinstance(raw, dict) or not set(raw).issubset(allowed):
        return Invalid((Problem(
            code="sync-config-invalid",
            message=("config.sync must be an object containing only "
                     f"{sorted(allowed)}"),
            location=f"{config_path}:sync",
        ),))

    defaults = SyncBudget().to_dict()
    values = {**defaults, **raw}
    problems = []
    for name in ("max_work_order_units", "max_model_calls", "max_turns"):
        if not _whole_positive(values[name]):
            problems.append(Problem(
                code="sync-config-invalid-budget",
                message=f"config.sync.{name} must be a positive integer",
                location=f"{config_path}:sync.{name}",
            ))
    if not (_one_line(values["sync_model"]) and _MODEL.fullmatch(values["sync_model"])):
        problems.append(Problem(
            code="sync-config-invalid-model",
            message=("config.sync.sync_model must be a non-empty model-tier alias "
                     "containing only letters, digits, '.', '_', or '-'"),
            location=f"{config_path}:sync.sync_model",
        ))
    if problems:
        return Invalid(tuple(problems))
    return SyncBudget(**values)


def _record_problem(problems, code, message, location):
    problems.append(Problem(code=code, message=message, location=location))


def _validate_lineage(raw, provenance, problems, where):
    if not isinstance(raw, dict) or set(raw) != _LINEAGE_FIELDS:
        _record_problem(
            problems, "ledger-invalid-lineage",
            f"entry lineage must carry exactly {sorted(_LINEAGE_FIELDS)}", where,
        )
        return False
    ok = True
    if not (isinstance(raw["report_digest"], str)
            and _DIGEST.fullmatch(raw["report_digest"])):
        _record_problem(problems, "ledger-invalid-lineage",
                        "lineage.report_digest must be a sha256 digest",
                        f"{where}.report_digest")
        ok = False
    for name in ("commit", "plugin_version"):
        if not _one_line(raw[name]):
            _record_problem(problems, "ledger-invalid-lineage",
                            f"lineage.{name} must be a non-empty single-line string",
                            f"{where}.{name}")
            ok = False
    if not _date(raw["date"]):
        _record_problem(problems, "ledger-invalid-lineage",
                        "lineage.date must be a real YYYY-MM-DD date",
                        f"{where}.date")
        ok = False
    model = raw["model"]
    if model is not None and not (_one_line(model) and _MODEL.fullmatch(model)):
        _record_problem(problems, "ledger-invalid-lineage",
                        "lineage.model must be null or a model-tier alias",
                        f"{where}.model")
        ok = False
    if provenance == "judged" and model is None:
        _record_problem(problems, "ledger-invalid-lineage",
                        "a judged entry must name the model that judged it",
                        f"{where}.model")
        ok = False
    return ok


def _validate_deps(raw, problems, where):
    if not isinstance(raw, list) or not raw:
        _record_problem(problems, "ledger-invalid-deps",
                        "deps must be a non-empty list", where)
        return False
    ok, prior = True, None
    for index, dep in enumerate(raw):
        place = f"{where}[{index}]"
        if not isinstance(dep, dict) or set(dep) != {"path", "digest"}:
            _record_problem(problems, "ledger-invalid-deps",
                            "each dependency must carry exactly 'path' and 'digest'",
                            place)
            ok = False
            continue
        path = dep["path"]
        before_path = len(problems)
        _validate_probe_path(path, problems, f"{place}.path")
        if len(problems) != before_path:
            ok = False
        if not (isinstance(dep["digest"], str)
                and _DIGEST.fullmatch(dep["digest"])):
            _record_problem(problems, "ledger-invalid-deps",
                            "dependency digest must be a sha256 digest",
                            f"{place}.digest")
            ok = False
        if prior is not None and isinstance(path, str) and path <= prior:
            _record_problem(problems, "ledger-nondeterministic-order",
                            "dependencies must be unique and ordered by path",
                            place)
            ok = False
        if isinstance(path, str):
            prior = path
    return ok


def _validate_probe_path(value, problems, where, *, glob=False):
    """Validate one stored probe path without resolving or opening it.

    Existence and boundary authorization belong to probe execution (#199), but
    shape is part of the persisted ledger contract: a path cannot be a command
    string, and a literal path cannot smuggle glob semantics.
    """
    problem = repository_relative_problem(value)
    if problem is not None:
        _record_problem(problems, "ledger-invalid-probe-field",
                        f"probe path {value!r} {problem[1]}", where)
        return False
    if any(char in value for char in _SHELL_SYNTAX):
        _record_problem(problems, "ledger-invalid-probe-field",
                        "probe paths are data and may not contain shell syntax", where)
        return False
    if not glob and any(char in value for char in _GLOB_META):
        _record_problem(problems, "ledger-invalid-probe-field",
                        "a literal probe path may not contain glob metacharacters",
                        where)
        return False
    if glob and not any(char in value for char in _GLOB_META):
        _record_problem(problems, "ledger-invalid-probe-field",
                        "a probe glob must contain a glob metacharacter", where)
        return False
    return True


def _validate_pattern(value, problems, where):
    if not (_one_line(value) and len(value) <= _MAX_PATTERN_LENGTH):
        _record_problem(problems, "ledger-invalid-probe-field",
                        f"probe pattern must be 1–{_MAX_PATTERN_LENGTH} characters",
                        where)
        return False
    try:
        re.compile(value)
    except re.error as exc:
        _record_problem(problems, "ledger-invalid-probe-field",
                        f"probe pattern is not a valid regular expression: {exc}",
                        where)
        return False
    return True


def _validate_probe(probe, problems, where):
    """Validate the exact v1 schema of one stored deterministic probe."""
    if not isinstance(probe, dict) or set(probe) != {"kind", "args", "expect"}:
        _record_problem(problems, "ledger-invalid-probe-shape",
                        "probe must carry exactly 'kind', 'args', and 'expect'",
                        where)
        return False
    kind, args, expect = probe["kind"], probe["args"], probe["expect"]
    if not isinstance(kind, str) or kind not in PROBE_KINDS:
        _record_problem(problems, "ledger-forbidden-probe-kind",
                        f"probe kind {kind!r} is not in the closed vocabulary "
                        f"{list(PROBE_KINDS)}", f"{where}.kind")
        return False
    if not isinstance(args, dict) or not isinstance(expect, dict):
        _record_problem(problems, "ledger-invalid-probe-shape",
                        "probe args and expect must be objects", where)
        return False

    if kind == "path_exists":
        literal = set(args) == {"path", "kind"}
        patterned = set(args) == {"glob", "kind"}
        if not (literal or patterned) or expect != {}:
            _record_problem(problems, "ledger-invalid-probe-shape",
                            "path_exists args must carry exactly ('path' or "
                            "'glob') and 'kind'; expect must be empty", where)
            return False
        if args["kind"] not in ("file", "dir", "any"):
            _record_problem(problems, "ledger-invalid-probe-field",
                            "path_exists kind must be 'file', 'dir', or 'any'",
                            f"{where}.args.kind")
            return False
        name = "path" if literal else "glob"
        return _validate_probe_path(
            args[name], problems, f"{where}.args.{name}", glob=patterned
        )

    if kind == "content_match":
        if set(args) != {"path", "pattern"} or not (
            set(expect) == {"presence"}
            or set(expect) == {"presence", "count"}
        ):
            _record_problem(problems, "ledger-invalid-probe-shape",
                            "content_match args must carry exactly 'path' and "
                            "'pattern'; expect must carry 'presence' and optional "
                            "'count'", where)
            return False
        valid = _validate_probe_path(
            args["path"], problems, f"{where}.args.path"
        )
        valid = _validate_pattern(
            args["pattern"], problems, f"{where}.args.pattern"
        ) and valid
        if expect["presence"] not in ("present", "absent"):
            _record_problem(problems, "ledger-invalid-probe-field",
                            "content_match presence must be 'present' or 'absent'",
                            f"{where}.expect.presence")
            valid = False
        if "count" in expect and not (
            isinstance(expect["count"], int)
            and not isinstance(expect["count"], bool)
            and expect["count"] >= 0
        ):
            _record_problem(problems, "ledger-invalid-probe-field",
                            "content_match count must be a non-negative integer",
                            f"{where}.expect.count")
            valid = False
        return valid

    if kind == "json_value":
        if set(args) != {"path", "pointer"} or set(expect) != {"equals"}:
            _record_problem(problems, "ledger-invalid-probe-shape",
                            "json_value args must carry exactly 'path' and "
                            "'pointer'; expect must carry exactly 'equals'", where)
            return False
        valid = _validate_probe_path(
            args["path"], problems, f"{where}.args.path"
        )
        pointer = args["pointer"]
        if not isinstance(pointer, str) or (
            pointer != "" and not pointer.startswith("/")
        ) or re.search(r"~(?![01])", pointer):
            _record_problem(problems, "ledger-invalid-probe-field",
                            "json_value pointer must be an RFC 6901 pointer",
                            f"{where}.args.pointer")
            valid = False
        return valid

    if kind == "symbol_defined":
        if set(args) != {"path", "language", "name"} or expect != {}:
            _record_problem(problems, "ledger-invalid-probe-shape",
                            "symbol_defined args must carry exactly 'path', "
                            "'language', and 'name'; expect must be empty", where)
            return False
        valid = _validate_probe_path(
            args["path"], problems, f"{where}.args.path"
        )
        if args["language"] != "python":
            _record_problem(problems, "ledger-invalid-probe-field",
                            "symbol_defined language must be 'python'",
                            f"{where}.args.language")
            valid = False
        name = args["name"]
        if not (_one_line(name) and all(
            part.isidentifier() and not keyword.iskeyword(part)
            for part in name.split(".")
        )):
            _record_problem(problems, "ledger-invalid-probe-field",
                            "symbol_defined name must be a dotted Python name",
                            f"{where}.args.name")
            valid = False
        return valid

    # tool_probe: its tool declaration and environment are checked at
    # execution; the persisted contract permits only one bare tool, one safe
    # introspection flag, and one bounded regular expression.
    if set(args) != {"tool", "flag", "pattern"} or expect != {}:
        _record_problem(problems, "ledger-invalid-probe-shape",
                        "tool_probe args must carry exactly 'tool', 'flag', and "
                        "'pattern'; expect must be empty", where)
        return False
    valid = True
    if not (_one_line(args["tool"]) and _TOOL.fullmatch(args["tool"])):
        _record_problem(problems, "ledger-invalid-probe-field",
                        "tool_probe tool must be one bare executable name",
                        f"{where}.args.tool")
        valid = False
    if args["flag"] not in ("--help", "--version"):
        _record_problem(problems, "ledger-invalid-probe-field",
                        "tool_probe flag must be '--help' or '--version'",
                        f"{where}.args.flag")
        valid = False
    return _validate_pattern(
        args["pattern"], problems, f"{where}.args.pattern"
    ) and valid


def _parse_header(raw, expected_registry_digest, problems, where):
    if not isinstance(raw, dict) or set(raw) != _HEADER_FIELDS:
        _record_problem(problems, "ledger-invalid-header",
                        f"the header must carry exactly {sorted(_HEADER_FIELDS)}",
                        where)
        return None
    if raw["record"] != "ledger-header":
        _record_problem(problems, "ledger-invalid-header",
                        "line 1 must be the ledger-header record", where)
    schema = raw["schema"]
    if not (isinstance(schema, int) and not isinstance(schema, bool)
            and schema == LEDGER_SCHEMA_VERSION):
        _record_problem(problems, "ledger-unknown-schema",
                        f"ledger schema {schema!r} is not supported; expected 1",
                        f"{where}.schema")
    if raw["ruleset"] != RULESET_VERSION:
        _record_problem(problems, "ledger-ruleset-incompatible",
                        f"ledger ruleset {raw['ruleset']!r} is incompatible with "
                        f"engine ruleset {RULESET_VERSION}", f"{where}.ruleset")
    registry_digest = raw["registry_digest"]
    if registry_digest != expected_registry_digest:
        _record_problem(problems, "ledger-registry-mismatch",
                        "the ledger was established under a different registry",
                        f"{where}.registry_digest")
    if not _one_line(raw["plugin_version"]):
        _record_problem(problems, "ledger-invalid-header",
                        "plugin_version must be a non-empty single-line string",
                        f"{where}.plugin_version")

    established = raw["established"]
    if not isinstance(established, dict) or set(established) != _ESTABLISHED_FIELDS:
        _record_problem(problems, "ledger-invalid-header",
                        f"established must carry exactly {sorted(_ESTABLISHED_FIELDS)}",
                        f"{where}.established")
    else:
        if not (isinstance(established["report_digest"], str)
                and _DIGEST.fullmatch(established["report_digest"])):
            _record_problem(problems, "ledger-invalid-header",
                            "established.report_digest must be a sha256 digest",
                            f"{where}.established.report_digest")
        if not _one_line(established["commit"]):
            _record_problem(problems, "ledger-invalid-header",
                            "established.commit must be a non-empty string",
                            f"{where}.established.commit")
        if not _date(established["date"]):
            _record_problem(problems, "ledger-invalid-header",
                            "established.date must be a real YYYY-MM-DD date",
                            f"{where}.established.date")

    lists = {}
    for name in ("covered", "uncovered"):
        value = raw[name]
        valid = isinstance(value, list) and all(
            _one_line(path) and repository_relative_problem(path) is None
            for path in value
        )
        if not valid or value != sorted(set(value)):
            _record_problem(problems, "ledger-invalid-coverage",
                            f"{name} must be unique canonical paths in sorted order",
                            f"{where}.{name}")
            lists[name] = ()
        else:
            lists[name] = tuple(value)
    if set(lists["covered"]) & set(lists["uncovered"]):
        _record_problem(problems, "ledger-invalid-coverage",
                        "a document cannot be both covered and uncovered", where)

    if problems:
        return None
    return LedgerHeader(
        ruleset=raw["ruleset"], registry_digest=registry_digest,
        plugin_version=raw["plugin_version"], established=dict(established),
        covered=lists["covered"], uncovered=lists["uncovered"],
    )


def _parse_entry(raw, problems, where):
    problem_count = len(problems)
    if not isinstance(raw, dict):
        _record_problem(problems, "ledger-invalid-entry",
                        "an assertion record must be an object", where)
        return None
    strategy = raw.get("strategy")
    status = raw.get("status")
    expected = set(_ENTRY_BASE_FIELDS)
    if strategy == STRATEGY_PROBE:
        expected.update(("probe", "deps"))
    elif strategy == STRATEGY_DEPS:
        expected.add("deps")
    if status == "tombstone":
        expected.add("removed")
    if set(raw) != expected:
        _record_problem(problems, "ledger-invalid-entry-shape",
                        f"the entry must carry exactly {sorted(expected)}", where)
        return None
    if raw["record"] != "assertion":
        _record_problem(problems, "ledger-invalid-entry",
                        "entry record must be 'assertion'", f"{where}.record")
    doc = raw["doc"]
    path_problem = repository_relative_problem(doc)
    if path_problem is not None:
        _record_problem(problems, "ledger-invalid-entry",
                        f"entry document {doc!r} {path_problem[1]}", f"{where}.doc")
    unit = raw["unit"]
    if not (isinstance(unit, str) and _DIGEST.fullmatch(unit)):
        _record_problem(problems, "ledger-invalid-entry",
                        "entry unit must be a sha256 assertion-unit digest",
                        f"{where}.unit")
    assertion_class = raw["class"]
    if not isinstance(assertion_class, str) or assertion_class not in _OBLIGATIONS:
        _record_problem(problems, "ledger-invalid-entry",
                        f"entry class must be one of {list(_OBLIGATIONS)}",
                        f"{where}.class")
    elif raw["obligation"] not in _OBLIGATIONS[assertion_class]:
        _record_problem(problems, "ledger-invalid-obligation",
                        f"{assertion_class!r} cannot carry obligation "
                        f"{raw['obligation']!r}", f"{where}.obligation")
    if strategy not in STRATEGIES:
        _record_problem(problems, "ledger-invalid-strategy",
                        f"entry strategy must be one of {list(STRATEGIES)}",
                        f"{where}.strategy")
    if raw["provenance"] not in PROVENANCES:
        _record_problem(problems, "ledger-invalid-provenance",
                        f"entry provenance must be one of {list(PROVENANCES)}",
                        f"{where}.provenance")
    if status not in STATUSES:
        _record_problem(problems, "ledger-invalid-status",
                        f"entry status must be one of {list(STATUSES)}",
                        f"{where}.status")

    if strategy == STRATEGY_PROBE:
        _validate_probe(raw["probe"], problems, f"{where}.probe")
        if assertion_class in (NORMATIVE, RATIONALE):
            _record_problem(problems, "ledger-forbidden-probe-class",
                            "normative and rationale entries may not use probes",
                            f"{where}.strategy")
        _validate_deps(raw["deps"], problems, f"{where}.deps")
    elif strategy == STRATEGY_DEPS:
        _validate_deps(raw["deps"], problems, f"{where}.deps")

    _validate_lineage(raw["lineage"], raw["provenance"], problems,
                      f"{where}.lineage")
    if status == "tombstone":
        removed = raw["removed"]
        if not isinstance(removed, dict) or set(removed) != _REMOVED_FIELDS:
            _record_problem(problems, "ledger-invalid-tombstone",
                            f"removed must carry exactly {sorted(_REMOVED_FIELDS)}",
                            f"{where}.removed")
        else:
            if not _one_line(removed["commit"]):
                _record_problem(problems, "ledger-invalid-tombstone",
                                "removed.commit must be a non-empty string",
                                f"{where}.removed.commit")
            if not _date(removed["date"]):
                _record_problem(problems, "ledger-invalid-tombstone",
                                "removed.date must be a real YYYY-MM-DD date",
                                f"{where}.removed.date")

    # Parsing is exhaustive, but invalid data never becomes a partially valid
    # object.  In particular, no unhashable identity can reach duplicate
    # detection and no malformed lineage can reach dict() coercion.
    if len(problems) != problem_count:
        return None

    return LedgerEntry(
        doc=doc, unit=unit, assertion_class=assertion_class,
        obligation=raw["obligation"], strategy=strategy,
        provenance=raw["provenance"], lineage=dict(raw["lineage"]),
        status=status, raw=dict(raw),
    )


def load_assertion_ledger(repo_root, expected_registry_digest=None,
                          ledger_path=DEFAULT_LEDGER_PATH):
    """Read and validate the accepted JSONL ledger, without ever writing it."""
    if expected_registry_digest is None:
        inventory = build_inventory(repo_root)
        if isinstance(inventory, Invalid):
            return inventory
        expected_registry_digest = inventory.registry_digest
    absolute = os.path.join(repo_root, ledger_path)
    try:
        with open(absolute, "rb") as fh:
            data = fh.read()
        text = data.decode("utf-8")
    except FileNotFoundError:
        return Invalid((Problem(
            code="ledger-missing",
            message=(f"the accepted assertion ledger is missing at {ledger_path}; "
                     "sync mode never silently widens into bootstrap"),
            location=ledger_path,
        ),))
    except (OSError, UnicodeDecodeError) as exc:
        return Invalid((Problem(
            code="ledger-unreadable",
            message=f"cannot read the assertion ledger at {ledger_path}: {exc}",
            location=ledger_path,
        ),))

    lines = text.splitlines()
    if not lines:
        return Invalid((Problem(
            code="ledger-missing-header",
            message="the assertion ledger is empty; line 1 must be its header",
            location=ledger_path,
        ),))

    decoded, problems = [], []
    for number, line in enumerate(lines, start=1):
        where = f"{ledger_path}:{number}"
        try:
            decoded.append(json.loads(line, parse_constant=_reject_constant))
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            _record_problem(problems, "ledger-unparseable-line",
                            f"line {number} is not one strict JSON value: {exc}", where)
            decoded.append(None)
    if problems:
        return Invalid(tuple(problems))

    header_problems = []
    header = _parse_header(decoded[0], expected_registry_digest,
                           header_problems, f"{ledger_path}:1")
    entries = []
    entry_problems = []
    for index, raw in enumerate(decoded[1:], start=2):
        entry = _parse_entry(raw, entry_problems, f"{ledger_path}:{index}")
        if entry is not None:
            entries.append(entry)

    seen, prior_doc = {}, None
    for index, entry in enumerate(entries, start=2):
        where = f"{ledger_path}:{index}"
        identity = (entry.doc, entry.unit)
        if identity in seen:
            _record_problem(entry_problems, "ledger-duplicate-identity",
                            f"entry identity {entry.doc!r} + {entry.unit} already "
                            f"appeared on line {seen[identity]}", where)
        else:
            seen[identity] = index
        if prior_doc is not None and entry.doc < prior_doc:
            _record_problem(entry_problems, "ledger-nondeterministic-order",
                            "assertion records must be ordered by document path", where)
        prior_doc = entry.doc

    all_problems = tuple(header_problems + entry_problems)
    if all_problems:
        return Invalid(all_problems)
    return AssertionLedger(
        path=ledger_path, digest=sha256_bytes(data), header=header,
        entries=tuple(entries),
    )


def _current_units(repo_root, drift_plan, registry_path):
    documents, details, problems = [], {}, []
    for document in drift_plan.documents:
        if document.obligation == OBLIGATION_ANCHOR:
            continue
        segmented = segment_document(repo_root, document.path, registry_path)
        if isinstance(segmented, Invalid):
            problems.extend(segmented.problems)
            continue
        capable = [unit for unit in segmented.units if unit.assertion_capable]
        documents.append({
            "doc": document.path,
            "units": [unit.digest for unit in capable],
        })
        details[document.path] = tuple(capable)
    if problems:
        return None, None, Invalid(tuple(problems))
    return documents, details, None


def _entry_ref(entry):
    return {"doc": entry.doc, "unit": entry.unit}


def _unit_ref(doc, unit):
    return {
        "doc": doc,
        "unit": unit.digest,
        "kind": unit.kind,
        "text": unit.text,
        "ordinal": unit.ordinal,
        "line": unit.line,
        "end_line": unit.end_line,
    }


def _dependency_changes(repo_root, entry):
    """Return deterministic observations for deps that moved or disappeared.

    Dependency paths are already canonical repository-relative strings by the
    ledger validator.  Comparison still refuses to follow a symlink: a path
    that no longer names a regular repository file is an unavailable dep and
    therefore escalates only its owning entry.
    """
    changes = []
    for dependency in entry.raw["deps"]:
        path = dependency["path"]
        absolute = os.path.join(repo_root, path)
        observed = None
        current, aliased = repo_root, False
        for component in path.split("/"):
            current = os.path.join(current, component)
            if os.path.islink(current):
                aliased = True
                break
        if not aliased and os.path.isfile(absolute):
            try:
                observed = sha256_file(absolute)
            except OSError:
                observed = None
        if observed == dependency["digest"]:
            continue
        changes.append({
            "path": path,
            "expected_digest": dependency["digest"],
            "observed_digest": observed,
            "change": "disappeared" if observed is None else "changed",
        })
    return changes


def _carried_result(entry):
    reasons = {
        STRATEGY_DEPS: (
            "unit identity and every declared dependency digest are unchanged"
        ),
        STRATEGY_ON_CHANGE: "unit identity and normalized content are unchanged",
        STRATEGY_RECONCILE_ONLY: (
            "unit identity is unchanged and its strategy defers review to explicit "
            "reconciliation"
        ),
        STRATEGY_PROBE: (
            "unit identity and its deterministic probe assignment are unchanged"
        ),
    }
    return {
        **_entry_ref(entry),
        "classification": "unchanged",
        "strategy": entry.strategy,
        "coverage_source": "carried",
        "reason": reasons[entry.strategy],
        "originating_lineage": dict(entry.lineage),
    }


def _compare_units(repo_root, ledger, current, details):
    """Classify current and accepted identities without mutating either input."""
    covered = set(ledger.header.covered)
    active_by_doc = {doc: [] for doc in ledger.header.covered}
    for entry in ledger.entries:
        if entry.status != "active":
            continue
        if entry.doc not in active_by_doc:
            return [], [], [], [], Problem(
                code="sync-ledger-active-entry-outside-coverage",
                message=(f"active entry {entry.doc!r} + {entry.unit} is not in "
                         "the header's covered documents"),
                location=ledger.path,
            )
        active_by_doc[entry.doc].append(entry)

    current_by_doc = {item["doc"]: item["units"] for item in current}
    carried, work, tombstones, uncovered = [], [], [], []
    for doc in sorted(current_by_doc):
        if doc not in covered:
            uncovered.append({
                "doc": doc,
                "classification": "declared-uncovered",
                "units": [unit.digest for unit in details[doc]],
            })
            continue
        accepted = {entry.unit: entry for entry in active_by_doc[doc]}
        for unit in details[doc]:
            entry = accepted.get(unit.digest)
            if entry is None:
                work.append({
                    **_unit_ref(doc, unit),
                    "classification": "new",
                    "reason": (
                        "no active ledger entry has this document-scoped identity"
                    ),
                })
                continue
            if entry.strategy == STRATEGY_DEPS:
                changes = _dependency_changes(repo_root, entry)
                if changes:
                    work.append({
                        **_unit_ref(doc, unit),
                        "classification": "unchanged",
                        "strategy": entry.strategy,
                        "reason": "declared-dependency-changed",
                        "dependency_changes": changes,
                        "originating_lineage": dict(entry.lineage),
                    })
                    continue
            carried.append(_carried_result(entry))

    for doc in sorted(active_by_doc):
        present = set(current_by_doc.get(doc, ()))
        for entry in active_by_doc[doc]:
            if entry.unit not in present:
                tombstones.append({
                    **_entry_ref(entry),
                    "classification": "removed",
                    "disposition": "tombstone-candidate",
                    "reason": "the active identity is absent from its covered document",
                    "originating_lineage": dict(entry.lineage),
                })

    work.sort(key=lambda item: (item["doc"], item["ordinal"], item["unit"]))
    return carried, work, tombstones, uncovered, None


def _over_budget(work, budget, config_path):
    if len(work) <= budget.max_work_order_units:
        return None
    names = ", ".join(f"{item['doc']} + {item['unit']}" for item in work)
    return Invalid((Problem(
        code="sync-work-order-over-budget",
        message=(f"{len(work)} units require judgment, exceeding "
                 f"max_work_order_units={budget.max_work_order_units}; affected "
                 f"units: {names}"),
        location=f"{config_path}:sync.max_work_order_units",
    ),))


def _anchor_results(repo_root, drift_plan, registry_path):
    checks, gaps = [], []
    for document in drift_plan.documents:
        if document.obligation != OBLIGATION_ANCHOR:
            continue
        findings, coverage, gap = _audit_anchor(
            repo_root, document.path, registry_path
        )
        checks.append({
            "path": document.path,
            "coverage": coverage,
            "findings": [
                {"code": finding.code, "path": finding.path,
                 "units": list(finding.units), **finding.extra}
                for finding in findings
            ],
        })
        if gap is not None:
            gaps.append(gap.to_dict())
    return checks, gaps


def plan_sync(repo_root, as_of, mode=MODE_SYNC,
              registry_path=DEFAULT_REGISTRY_PATH,
              ledger_path=DEFAULT_LEDGER_PATH,
              config_path=DEFAULT_CONFIG_PATH,
              session_id=None, chunk_id=None, total_chunk_count=1):
    """Plan one incremental sync, returning ``SyncPlan`` or typed ``Invalid``.

    No callback or model adapter is accepted by phase 1.  Judgment can happen
    only after a caller receives a non-empty work order, which makes every
    refusal here mechanically incapable of doing model work.
    """
    if mode not in SYNC_MODES:
        return Invalid((Problem(
            code="sync-unknown-mode",
            message=f"sync mode must be one of {list(SYNC_MODES)}, not {mode!r}",
            location="mode",
        ),))
    if mode != MODE_SYNC:
        return Invalid((Problem(
            code=f"sync-{mode}-not-implemented",
            message=(f"{mode} is a recognized sync mode but is not implemented "
                     "in Phase A's tracer-bullet slice"),
            location="mode",
        ),))
    if not _date(as_of):
        return Invalid((Problem(
            code="sync-invalid-as-of",
            message="as_of must be supplied explicitly as a real YYYY-MM-DD date",
            location="as_of",
        ),))
    if not _whole_positive(total_chunk_count):
        return Invalid((Problem(
            code="sync-invalid-chunk-count",
            message="total_chunk_count must be a positive integer",
            location="total_chunk_count",
        ),))
    for name, value in (("session_id", session_id), ("chunk_id", chunk_id)):
        if value is not None and not _one_line(value):
            return Invalid((Problem(
                code="sync-invalid-binding",
                message=f"{name} must be a non-empty single-line string",
                location=name,
            ),))

    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        return inventory
    budget = load_sync_budget(repo_root, config_path)
    if isinstance(budget, Invalid):
        return budget
    ledger = load_assertion_ledger(
        repo_root, inventory.registry_digest, ledger_path
    )
    if isinstance(ledger, Invalid):
        return ledger

    drift_plan = plan_drift_audit(repo_root, registry_path=registry_path)
    if isinstance(drift_plan, Invalid):
        return drift_plan
    current, details, problem = _current_units(
        repo_root, drift_plan, registry_path
    )
    if problem is not None:
        return problem
    carried, work, tombstones, uncovered, comparison_problem = _compare_units(
        repo_root, ledger, current, details
    )
    if comparison_problem is not None:
        return Invalid((comparison_problem,))
    over_budget = _over_budget(work, budget, config_path)
    if over_budget is not None:
        return over_budget

    unit_set_digest = sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "documents": current,
    })
    core_binding = {
        "mode": mode, "as_of": as_of, "ledger_digest": ledger.digest,
        "inventory_digest": inventory.digest,
        "unit_set_digest": unit_set_digest, "budget_digest": budget.digest,
    }
    if session_id is None:
        session_id = "s-" + sha256_canonical(core_binding)[:24]
    if chunk_id is None:
        chunk_id = "c-" + sha256_canonical({
            "mode": mode, "unit_set_digest": unit_set_digest, "units": work,
        })[:24]

    anchor_checks, gaps = _anchor_results(repo_root, drift_plan, registry_path)
    inventory_findings = [
        {"code": finding.code, "path": finding.path, "message": finding.message}
        for finding in inventory.findings
    ]
    anchor_findings = [
        finding for check in anchor_checks for finding in check["findings"]
    ]
    result_payload = {
        "unchanged": carried,
        "tombstone_candidates": tombstones,
        "declared_uncovered": sorted(
            set(ledger.header.uncovered) | {item["doc"] for item in uncovered}
        ),
        "declared_uncovered_units": uncovered,
        "narrative_checks": anchor_checks,
        "excluded": [entry.to_dict() for entry in drift_plan.excluded],
        "inventory_findings": inventory_findings,
        "incomplete": gaps,
    }
    deterministic_results = {
        "digest": sha256_canonical(result_payload), **result_payload,
    }
    status = (
        STATE_PARTIAL if gaps or work
        else STATE_FINDINGS if inventory_findings or anchor_findings
        else STATE_CLEAN
    )
    work_order = JudgmentWorkOrder(
        mode=mode, session_id=session_id, chunk_id=chunk_id,
        total_chunk_count=total_chunk_count, ledger_digest=ledger.digest,
        inventory_digest=inventory.digest, unit_set_digest=unit_set_digest,
        budget=budget, units=tuple(work),
    )
    return SyncPlan(
        status=status, mode=mode, as_of=as_of,
        deterministic_results=deterministic_results, work_order=work_order,
    )
