"""The two-phase incremental-sync protocol and read-only ledger contract.

This module owns the durable assertion-ledger contract and the first complete
path through phase 1: assertion identities are compared document-by-document,
safe reuse is explained, and only units needing judgment enter the bounded
work order. Phase 2 revalidates that order and untrusted model judgments before
emitting a schema-v2 report and proposed next ledger. The accepted ledger is
only ever read. Unchanged probe entries and model-proposed probes are executed
with fresh deterministic evidence; neither phase invokes a model itself.
"""

import datetime
import json
import keyword
import os
import re
from dataclasses import dataclass
from typing import Tuple

from . import ARTIFACT_SCHEMA_VERSION, PLUGIN_VERSION, RULESET_VERSION
from .digest import (
    canonical,
    load_strict_json,
    sha256_bytes,
    sha256_canonical,
    sha256_file,
)
from .drift import (
    DEFAULT_EVIDENCE,
    OBLIGATION_ANCHOR,
    VERDICT_REQUIRED_CLASSES,
    VERDICT_STALE,
    _audit_anchor,
    _validated_verdicts,
    audit_config_digest,
    plan_drift_audit,
)
from .finding import FACTUAL, NON_ASSERTIVE, NORMATIVE, RATIONALE, build_finding
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .paths import repository_relative_problem
from .probes import PROBE_KINDS, execute_probe
from .report import (
    COVERAGE_INCREMENTAL,
    REPORT_SCHEMA_VERSION,
    SCOPE_DECLARED_ONLY,
    EvidenceBoundary,
    Lineage,
    current_lineage,
    state_from_content,
    validate_report,
)
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    Invalid,
    Problem,
)
from .segment import Segmentation, segment_document

LEDGER_SCHEMA_VERSION = 1
WORK_ORDER_SCHEMA_VERSION = 1
JUDGMENT_SCHEMA_VERSION = 1
PROPOSED_LEDGER_SCHEMA_VERSION = 1

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


def _whole_nonnegative(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


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
    probe_problems: Tuple[Problem, ...] = ()


@dataclass(frozen=True)
class AssertionLedger:
    path: str
    digest: str
    header: LedgerHeader
    entries: Tuple[LedgerEntry, ...]


@dataclass(frozen=True)
class JudgmentWorkOrder:
    mode: str
    as_of: str
    session_id: str
    chunk_id: str
    total_chunk_count: int
    ledger_digest: str
    inventory_digest: str
    unit_set_digest: str
    budget: SyncBudget
    deterministic_results_digest: str
    units: Tuple[dict, ...] = ()

    def to_dict(self):
        return {
            "schema_version": WORK_ORDER_SCHEMA_VERSION,
            "mode": self.mode,
            "as_of": self.as_of,
            "session_id": self.session_id,
            "chunk_id": self.chunk_id,
            "total_chunk_count": self.total_chunk_count,
            "bindings": {
                "ledger_digest": self.ledger_digest,
                "inventory_digest": self.inventory_digest,
                "unit_set_digest": self.unit_set_digest,
                "budget_digest": self.budget.digest,
                "deterministic_results_digest": self.deterministic_results_digest,
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


@dataclass(frozen=True)
class ProposedLedger:
    """A content-addressed candidate for human review, never an accepted write."""

    as_of: str
    records: Tuple[dict, ...]
    additions: Tuple[dict, ...]
    supersedes: Tuple[dict, ...]
    tombstones: Tuple[dict, ...]
    digest: str

    def to_dict(self):
        return {
            "schema_version": PROPOSED_LEDGER_SCHEMA_VERSION,
            "as_of": self.as_of,
            "records": [dict(record) for record in self.records],
            "changes": {
                "additions": [dict(item) for item in self.additions],
                "supersedes": [dict(item) for item in self.supersedes],
                "tombstones": [dict(item) for item in self.tombstones],
            },
            "digest": self.digest,
        }

    @property
    def jsonl(self):
        """The exact accepted-ledger bytes this proposal represents."""
        return "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in self.records
        )


@dataclass(frozen=True)
class SyncAcceptance:
    """CLI wire envelope for the library's report/proposal pair."""

    report: object
    proposed_ledger: ProposedLedger

    @property
    def status(self):
        return self.report.status

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "report": self.report.to_dict(),
            "proposed_ledger": self.proposed_ledger.to_dict(),
        }


class FakeJudgmentAdapter:
    """Zero-model adapter used to exercise the one external judgment seam.

    ``response`` may be any payload, including malformed or denied output.
    Empty work orders deliberately make no request and return an empty valid
    envelope, which lets tests prove the zero-cost path without a sideline.
    """

    def __init__(self, response=None):
        self.response = response
        self.request_count = 0

    @staticmethod
    def _ok(work, judgments):
        return {
            "schema_version": JUDGMENT_SCHEMA_VERSION,
            "session_id": work["session_id"], "chunk_id": work["chunk_id"],
            "model": work["budget"]["sync_model"], "status": "ok",
            "judgments": list(judgments),
        }

    @classmethod
    def valid(cls, judgments):
        return cls(lambda work: cls._ok(work, judgments))

    @classmethod
    def partial(cls, judgments=()):
        return cls(lambda work: cls._ok(work, judgments))

    @classmethod
    def unasked_unit(cls, judgment):
        return cls(lambda work: cls._ok(work, (judgment,)))

    @classmethod
    def malformed(cls, value=None):
        return cls({"malformed": True} if value is None else value)

    @classmethod
    def denied(cls, reason="model service denied the request"):
        return cls(lambda work: {
            "schema_version": JUDGMENT_SCHEMA_VERSION,
            "session_id": work["session_id"], "chunk_id": work["chunk_id"],
            "model": work["budget"]["sync_model"], "status": "denied",
            "reason": reason,
        })

    def request(self, work_order):
        raw = (work_order.to_dict() if isinstance(work_order, JudgmentWorkOrder)
               else work_order)
        if not raw.get("units"):
            return self._ok(raw, ())
        self.request_count += 1
        return self.response(raw) if callable(self.response) else self.response


def load_sync_input(path, kind):
    """Strict JSON reader for the two untrusted phase-2 CLI inputs."""
    payload, problem = load_strict_json(
        path,
        unreadable_code=f"sync-{kind}-unreadable",
        unparseable_code=f"sync-{kind}-unparseable",
        nesting_code=f"sync-{kind}-nesting-too-deep",
    )
    return Invalid((problem,)) if problem is not None else payload


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

    probe_problems = []
    if strategy == STRATEGY_PROBE:
        # A structurally usable assertion remains usable even when its nested
        # probe control data is unsafe. Execution revalidates that data and
        # turns the typed refusal into work for this entry alone; invalidating
        # the whole accepted ledger here would make that escalation unreachable.
        _validate_probe(raw["probe"], probe_problems, f"{where}.probe")
        if assertion_class in (NORMATIVE, RATIONALE):
            _record_problem(problems, "ledger-forbidden-probe-class",
                            "normative and rationale entries may not use probes",
                            f"{where}.strategy")
        _validate_deps(raw["deps"], probe_problems, f"{where}.deps")
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
        status=status, raw=dict(raw), probe_problems=tuple(probe_problems),
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
        "evidence_boundary": {
            "sources": list(DEFAULT_EVIDENCE),
            "excluded": [],
            "commands": [],
        },
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


def _carried_result(entry, probe_outcome=None):
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
    result = {
        **_entry_ref(entry),
        "classification": "unchanged",
        "strategy": entry.strategy,
        "coverage_source": "probe" if probe_outcome is not None else "carried",
        "reason": reasons[entry.strategy],
        "originating_lineage": dict(entry.lineage),
    }
    if probe_outcome is not None:
        result.pop("originating_lineage")
        result["reason"] = "deterministic probe passed with fresh observed evidence"
        result["probe"] = {
            "kind": entry.raw["probe"]["kind"],
            "observed": dict(probe_outcome.observed),
        }
    return result


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
            if entry.strategy == STRATEGY_PROBE:
                outcome = execute_probe(
                    repo_root, entry.raw["probe"], entry.raw["deps"]
                )
                if outcome.problem is not None:
                    work.append({
                        **_unit_ref(doc, unit),
                        "classification": "unchanged",
                        "strategy": entry.strategy,
                        "reason": "deterministic-probe-refused",
                        "probe_problem": {
                            "code": outcome.problem.code,
                            "message": outcome.problem.message,
                            "location": outcome.problem.location,
                        },
                        "originating_lineage": dict(entry.lineage),
                    })
                    continue
                if not outcome.passed:
                    work.append({
                        **_unit_ref(doc, unit),
                        "classification": "unchanged",
                        "strategy": entry.strategy,
                        "reason": "deterministic-probe-failed",
                        "probe": {
                            "kind": entry.raw["probe"]["kind"],
                            "observed": dict(outcome.observed),
                        },
                        "originating_lineage": dict(entry.lineage),
                    })
                    continue
                carried.append(_carried_result(entry, outcome))
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
        mode=mode, as_of=as_of, session_id=session_id, chunk_id=chunk_id,
        total_chunk_count=total_chunk_count, ledger_digest=ledger.digest,
        inventory_digest=inventory.digest, unit_set_digest=unit_set_digest,
        budget=budget,
        deterministic_results_digest=deterministic_results["digest"],
        units=tuple(work),
    )
    return SyncPlan(
        status=status, mode=mode, as_of=as_of,
        deterministic_results=deterministic_results, work_order=work_order,
    )


_WORK_ORDER_FIELDS = {
    "schema_version", "mode", "as_of", "session_id", "chunk_id",
    "total_chunk_count", "bindings", "budget", "units",
}
_BINDING_FIELDS = {
    "ledger_digest", "inventory_digest", "unit_set_digest", "budget_digest",
    "deterministic_results_digest",
}
_JUDGMENT_ENVELOPE_FIELDS = {
    "schema_version", "session_id", "chunk_id", "model", "status",
    "judgments",
}
_DENIED_ENVELOPE_FIELDS = {
    "schema_version", "session_id", "chunk_id", "model", "status", "reason",
}
_VERDICT_FIELDS = {
    "unit", "assertion_class", "verdict", "kind", "tier", "evidence",
    "obligation", "fix",
}


def _invalid(code, message, location=None):
    return Invalid((Problem(code=code, message=message, location=location),))


def _work_order_payload(value):
    return value.to_dict() if isinstance(value, JudgmentWorkOrder) else value


def _validate_work_order_shape(raw):
    """Parse no control data: establish only that phase 1's wire shape exists."""
    if not isinstance(raw, dict) or set(raw) != _WORK_ORDER_FIELDS:
        return _invalid(
            "sync-work-order-invalid-shape",
            f"a work order must carry exactly {sorted(_WORK_ORDER_FIELDS)}",
            "work_order",
        )
    if raw.get("schema_version") != WORK_ORDER_SCHEMA_VERSION:
        return _invalid(
            "sync-work-order-invalid-schema",
            f"work-order schema {raw.get('schema_version')!r} is not supported",
            "work_order.schema_version",
        )
    if not _date(raw.get("as_of")):
        return _invalid(
            "sync-work-order-invalid-as-of",
            "work-order as_of must be a real YYYY-MM-DD date",
            "work_order.as_of",
        )
    if not isinstance(raw.get("bindings"), dict) or (
        set(raw["bindings"]) != _BINDING_FIELDS
    ):
        return _invalid(
            "sync-work-order-invalid-shape",
            f"work-order bindings must carry exactly {sorted(_BINDING_FIELDS)}",
            "work_order.bindings",
        )
    if not isinstance(raw.get("units"), list):
        return _invalid(
            "sync-work-order-invalid-shape", "work-order units must be a list",
            "work_order.units",
        )
    if not _whole_positive(raw.get("total_chunk_count")):
        return _invalid(
            "sync-work-order-invalid-chunk-count",
            "work-order total_chunk_count must be a positive non-boolean integer",
            "work_order.total_chunk_count",
        )
    for index, unit in enumerate(raw["units"]):
        if not isinstance(unit, dict):
            return _invalid(
                "sync-work-order-invalid-unit-metadata",
                "each work-order unit must be an object",
                f"work_order.units[{index}]",
            )
        numeric_fields = (
            ("ordinal", _whole_nonnegative, "non-negative"),
            ("line", _whole_positive, "positive"),
            ("end_line", _whole_positive, "positive"),
        )
        for name, validator, bound in numeric_fields:
            if not validator(unit.get(name)):
                return _invalid(
                    "sync-work-order-invalid-unit-metadata",
                    f"work-order unit {name} must be a {bound} non-boolean integer",
                    f"work_order.units[{index}].{name}",
                )
    if not (_one_line(raw.get("session_id")) and _one_line(raw.get("chunk_id"))):
        return _invalid(
            "sync-work-order-invalid-shape",
            "work-order session_id and chunk_id must be non-empty single-line strings",
            "work_order",
        )
    budget = raw.get("budget")
    if not isinstance(budget, dict) or set(budget) != set(SyncBudget().to_dict()):
        return _invalid(
            "sync-work-order-invalid-shape", "work-order budget has the wrong shape",
            "work_order.budget",
        )
    if raw["bindings"]["budget_digest"] != sha256_canonical(budget):
        return _invalid(
            "sync-stale-budget-binding",
            "the work-order budget no longer matches its binding digest",
            "work_order.bindings.budget_digest",
        )
    return None


def _expected_orchestration_refusal(raw, expected_session_id, expected_chunk_id,
                                    expected_total_chunk_count):
    """Compare caller-supplied trusted topology before any repository replan."""
    if (
        expected_total_chunk_count is not None
        and not _whole_positive(expected_total_chunk_count)
    ):
        return _invalid(
            "sync-invalid-expected-binding",
            "expected_total_chunk_count must be a positive non-boolean integer",
            "expected_total_chunk_count",
        )
    if expected_session_id is not None and raw["session_id"] != expected_session_id:
        return _invalid(
            "sync-wrong-session",
            f"work order belongs to session {raw['session_id']!r}, not "
            f"{expected_session_id!r}",
            "work_order.session_id",
        )
    if expected_chunk_id is not None and raw["chunk_id"] != expected_chunk_id:
        return _invalid(
            "sync-wrong-chunk",
            f"work order belongs to chunk {raw['chunk_id']!r}, not "
            f"{expected_chunk_id!r}",
            "work_order.chunk_id",
        )
    if (
        expected_total_chunk_count is not None
        and raw["total_chunk_count"] != expected_total_chunk_count
    ):
        return _invalid(
            "sync-wrong-chunk-count",
            f"work order declares {raw['total_chunk_count']} chunks, not the "
            f"trusted expected count {expected_total_chunk_count}",
            "work_order.total_chunk_count",
        )
    return None


def _binding_refusal(raw, fresh, expected_session_id, expected_chunk_id,
                     expected_total_chunk_count):
    expected = fresh.work_order.to_dict()
    for name in sorted(_BINDING_FIELDS):
        if raw["bindings"][name] != expected["bindings"][name]:
            return _invalid(
                "sync-stale-binding",
                f"work-order {name} no longer matches the current repository",
                f"work_order.bindings.{name}",
            )
    # Default identifiers and a single chunk are independently derived. Any
    # caller-assigned orchestration values need all three trusted expectations;
    # otherwise an untrusted order could bless its own session topology.
    orchestration = (
        raw["session_id"], raw["chunk_id"], raw["total_chunk_count"]
    )
    derived = (
        expected["session_id"], expected["chunk_id"],
        expected["total_chunk_count"],
    )
    if orchestration != derived and None in (
        expected_session_id, expected_chunk_id, expected_total_chunk_count,
    ):
        code = (
            "sync-wrong-session"
            if raw["session_id"] != expected["session_id"]
            else "sync-stale-chunk"
        )
        return _invalid(
            code,
            "a caller-assigned session, chunk, or chunk count requires trusted "
            "expected_session_id, expected_chunk_id, and "
            "expected_total_chunk_count values",
            "work_order",
        )
    # The digests bind current state; this exact comparison also refuses a
    # spliced or edited unit list under otherwise current bindings.
    for name in ("mode", "budget", "units"):
        try:
            exact = canonical(raw[name]) == canonical(expected[name])
        except (TypeError, ValueError, RecursionError):
            return _invalid(
                "sync-work-order-invalid-shape",
                f"work-order {name} must be strict, bounded JSON data",
                f"work_order.{name}",
            )
        if not exact:
            return _invalid(
                "sync-stale-chunk",
                f"work-order {name} is not the phase-1 chunk for these bindings",
                f"work_order.{name}",
            )
    return None


def _judgment_envelope(raw, work):
    if not isinstance(raw, dict):
        return None, _invalid(
            "sync-judgments-invalid-shape", "judgments must be an object",
            "judgments",
        )
    status = raw.get("status")
    expected = (_DENIED_ENVELOPE_FIELDS if status == "denied"
                else _JUDGMENT_ENVELOPE_FIELDS)
    if set(raw) != expected or raw.get("schema_version") != JUDGMENT_SCHEMA_VERSION:
        return None, _invalid(
            "sync-judgments-invalid-shape",
            f"a {status!r} judgment envelope must carry exactly {sorted(expected)} "
            f"at integer schema {JUDGMENT_SCHEMA_VERSION}",
            "judgments",
        )
    for name in ("session_id", "chunk_id"):
        if raw.get(name) != work[name]:
            return None, _invalid(
                f"sync-judgments-wrong-{name.replace('_id', '')}",
                f"judgments bind to {name} {raw.get(name)!r}, not {work[name]!r}",
                f"judgments.{name}",
            )
    if raw.get("model") != work["budget"]["sync_model"]:
        return None, _invalid(
            "sync-judgments-wrong-model",
            "judgments do not name the model tier bound into the work order",
            "judgments.model",
        )
    if status == "denied":
        if not _one_line(raw.get("reason")):
            return None, _invalid(
                "sync-judgments-invalid-shape",
                "a denied judgment set must carry a non-empty single-line reason",
                "judgments.reason",
            )
        return (), None
    if status != "ok" or not isinstance(raw.get("judgments"), list):
        return None, _invalid(
            "sync-judgments-invalid-shape",
            "judgment status must be 'ok' with a judgments list, or 'denied'",
            "judgments.status",
        )
    return tuple(raw["judgments"]), None


def _strategy_fields(strategy):
    fields = {"doc", "strategy"} | _VERDICT_FIELDS
    fields.discard("fix")
    if strategy == STRATEGY_PROBE:
        fields.update(("probe", "deps"))
    elif strategy == STRATEGY_DEPS:
        fields.add("deps")
    return fields


def _validate_strategy(repo_root, judgment, model, as_of, report_commit):
    """Return the exact ledger record data, through the ledger/probe owners."""
    strategy = judgment.get("strategy")
    expected = _strategy_fields(strategy)
    if judgment.get("verdict") == VERDICT_STALE:
        expected.add("fix")
    if strategy not in STRATEGIES or set(judgment) != expected:
        return None, _invalid(
            "sync-judgment-invalid-shape",
            f"a {strategy!r} judgment must carry exactly {sorted(expected)}",
            "judgment",
        )
    raw = {
        "record": "assertion", "doc": judgment["doc"],
        "unit": judgment["unit"], "class": judgment["assertion_class"],
        "obligation": judgment["obligation"], "strategy": strategy,
        "provenance": "judged",
        "lineage": {
            "report_digest": "0" * 64, "commit": report_commit,
            "plugin_version": PLUGIN_VERSION,
            "model": model, "date": as_of,
        },
        "status": "active",
    }
    for name in ("probe", "deps"):
        if name in judgment:
            raw[name] = judgment[name]
    problems = []
    _parse_entry(raw, problems, "judgment.strategy")
    if problems:
        return None, Invalid(tuple(problems))
    if strategy == STRATEGY_PROBE:
        outcome = execute_probe(repo_root, raw["probe"], raw["deps"])
        if outcome.problem is not None:
            return None, _invalid(
                "sync-judgment-probe-refused", outcome.problem.message,
                outcome.problem.location,
            )
        if not outcome.passed:
            return None, _invalid(
                "sync-judgment-probe-failed",
                "a proposed probe must establish the judgment when accepted",
                "judgment.probe",
            )
        observed = outcome.observed.get("dependencies", [])
        if observed != raw["deps"]:
            return None, _invalid(
                "sync-judgment-stale-dependencies",
                "proposed probe dependency digests do not match bytes read by the engine",
                "judgment.deps",
            )
    elif strategy == STRATEGY_DEPS:
        # A harmless path-existence probe delegates dependency authorization,
        # symlink confinement and bounded reads to ticket 4's single owner.
        first = raw["deps"][0]["path"] if raw.get("deps") else None
        outcome = execute_probe(repo_root, {
            "kind": "path_exists", "args": {"path": first, "kind": "any"},
            "expect": {},
        }, raw.get("deps"))
        if outcome.problem is not None:
            return None, _invalid(
                "sync-judgment-deps-refused", outcome.problem.message,
                outcome.problem.location,
            )
        if outcome.observed.get("dependencies") != raw["deps"]:
            return None, _invalid(
                "sync-judgment-stale-dependencies",
                "proposed dependency digests do not match bytes read by the engine",
                "judgment.deps",
            )
    return raw, None


def _single_unit_segmentation(segmentation, unit):
    return Segmentation(
        status=segmentation.status, units=(unit,),
        document_digest=segmentation.document_digest,
        digest=sha256_canonical({"source": segmentation.digest, "unit": unit.digest}),
        path=segmentation.path, kind=segmentation.kind,
    )


def _proposal(ledger, report, report_commit, as_of, deterministic,
              judged_records):
    active = {(entry.doc, entry.unit): entry for entry in ledger.entries
              if entry.status == "active"}
    tombstone_keys = {
        (item["doc"], item["unit"])
        for item in deterministic["tombstone_candidates"]
    }
    judged_by_key = {
        (record["doc"], record["unit"]): record for record in judged_records
    }
    covered_keys = {
        (item["doc"], item["unit"])
        for item in deterministic["unchanged"]
    }
    records, additions, tombstones = [], [], []
    header = {
        "record": "ledger-header", "schema": LEDGER_SCHEMA_VERSION,
        "ruleset": RULESET_VERSION,
        "registry_digest": ledger.header.registry_digest,
        "plugin_version": PLUGIN_VERSION,
        "established": {
            "report_digest": report.digest, "commit": report_commit, "date": as_of,
        },
        "covered": list(ledger.header.covered),
        "uncovered": list(ledger.header.uncovered),
    }
    records.append(header)
    for entry in ledger.entries:
        key = (entry.doc, entry.unit)
        if key in judged_by_key:
            continue
        raw = dict(entry.raw)
        if key in tombstone_keys and entry.status == "active":
            raw["status"] = "tombstone"
            raw["removed"] = {"commit": report_commit, "date": as_of}
            tombstones.append({"doc": entry.doc, "unit": entry.unit})
        if key in covered_keys or key in tombstone_keys:
            lineage = dict(raw["lineage"])
            lineage.update({
                "report_digest": report.digest, "commit": report_commit,
                "plugin_version": header["plugin_version"], "date": as_of,
            })
            raw["lineage"] = lineage
        records.append(raw)
    for key in sorted(judged_by_key):
        raw = dict(judged_by_key[key])
        raw["lineage"] = dict(raw["lineage"], report_digest=report.digest)
        records.append(raw)
        if key not in active:
            additions.append({"doc": key[0], "unit": key[1]})
    records = [records[0], *sorted(records[1:], key=lambda r: (
        r["doc"], r["unit"], 0 if r["status"] == "active" else 1
    ))]
    supersedes = []
    for addition in additions:
        for tombstone in tombstones:
            if addition["doc"] == tombstone["doc"]:
                supersedes.append({
                    "doc": addition["doc"], "unit": addition["unit"],
                    "supersedes": tombstone["unit"],
                })
    content = {
        "schema_version": PROPOSED_LEDGER_SCHEMA_VERSION, "as_of": as_of,
        "records": records,
        "changes": {
            "additions": additions, "supersedes": supersedes,
            "tombstones": tombstones,
        },
    }
    return ProposedLedger(
        as_of=as_of, records=tuple(records), additions=tuple(additions),
        supersedes=tuple(supersedes), tombstones=tuple(tombstones),
        digest=sha256_canonical(content),
    )


def accept_sync_judgments(repo_root, work_order, judgments, as_of,
                          registry_path=DEFAULT_REGISTRY_PATH,
                          ledger_path=DEFAULT_LEDGER_PATH,
                          config_path=DEFAULT_CONFIG_PATH,
                          expected_session_id=None, expected_chunk_id=None,
                          expected_total_chunk_count=None):
    """Validate phase-2 model output and return ``(report, proposed ledger)``.

    An invalid or stale input returns ``Invalid`` and no artifact. Partial and
    denied model outcomes are valid reports with explicit unexamined units.
    This function has no callback and can never widen into another model run.
    """
    raw_work = _work_order_payload(work_order)
    problem = _validate_work_order_shape(raw_work)
    if problem is not None:
        return problem
    if as_of != raw_work["as_of"]:
        return _invalid(
            "sync-as-of-mismatch",
            f"phase 2 as_of {as_of!r} does not match the work order's "
            f"caller-supplied date {raw_work['as_of']!r}",
            "as_of",
        )
    problem = _expected_orchestration_refusal(
        raw_work, expected_session_id, expected_chunk_id,
        expected_total_chunk_count,
    )
    if problem is not None:
        return problem
    fresh = plan_sync(
        repo_root, as_of, mode=raw_work["mode"], registry_path=registry_path,
        ledger_path=ledger_path, config_path=config_path,
    )
    if isinstance(fresh, Invalid):
        return fresh
    problem = _binding_refusal(
        raw_work, fresh, expected_session_id, expected_chunk_id,
        expected_total_chunk_count,
    )
    if problem is not None:
        return problem
    entries, problem = _judgment_envelope(judgments, raw_work)
    if problem is not None:
        return problem

    requested = {(item["doc"], item["unit"]): item for item in raw_work["units"]}
    seen, shaped = set(), []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return _invalid(
                "sync-judgment-invalid-shape", "each judgment must be an object",
                f"judgments.judgments[{index}]",
            )
        doc, unit = entry.get("doc"), entry.get("unit")
        path_problem = repository_relative_problem(doc)
        if path_problem is not None or not _one_line(doc):
            return _invalid(
                "sync-judgment-invalid-identity",
                "judgment.doc must be a canonical repository-relative path",
                f"judgments.judgments[{index}].doc",
            )
        if not (isinstance(unit, str) and _DIGEST.fullmatch(unit)):
            return _invalid(
                "sync-judgment-invalid-identity",
                "judgment.unit must be a lowercase sha256 assertion-unit digest",
                f"judgments.judgments[{index}].unit",
            )
        key = (doc, unit)
        if key not in requested:
            return _invalid(
                "sync-judgment-unasked-unit",
                f"judgment names {key!r}, which this work order never requested",
                f"judgments.judgments[{index}]",
            )
        if key in seen:
            return _invalid(
                "sync-judgment-duplicate-unit", "a requested unit was judged twice",
                f"judgments.judgments[{index}]",
            )
        seen.add(key)
        shaped.append(entry)

    boundary = EvidenceBoundary(tuple(DEFAULT_EVIDENCE), (), ())
    state, lineage_problems = current_lineage(
        repo_root, registry_path, audit_config_digest(boundary)
    )
    if lineage_problems:
        return Invalid(tuple(lineage_problems))
    lineage = Lineage(audit_mode="incremental", evidence_boundary=boundary, **state)
    model = raw_work["budget"]["sync_model"]
    drafts, judged_ledger, examined_judgments = [], [], []
    for entry in sorted(shaped, key=lambda item: (item["doc"], item["unit"])):
        planned_boundary = requested[(entry["doc"], entry["unit"])][
            "evidence_boundary"
        ]
        if planned_boundary != boundary.to_dict():
            return _invalid(
                "sync-judgment-evidence-boundary-mismatch",
                "the requested unit's evidence boundary is not the bound phase-2 boundary",
                "work_order.units.evidence_boundary",
            )
        segmentation = segment_document(repo_root, entry["doc"], registry_path)
        if isinstance(segmentation, Invalid):
            return segmentation
        unit = next((unit for unit in segmentation.units
                     if unit.digest == entry["unit"]), None)
        if unit is None:
            return _invalid(
                "sync-stale-unit", "the judged unit is no longer in its document",
                entry["doc"],
            )
        verdict = {name: entry[name] for name in _VERDICT_FIELDS if name in entry}
        found, coverage, verdict_problems = _validated_verdicts(
            _single_unit_segmentation(segmentation, unit), [verdict], boundary,
            entry["doc"],
        )
        if verdict_problems:
            return Invalid(tuple(verdict_problems))
        drafts.extend(found)
        examined_judgments.extend(
            (entry["doc"], item) for item in coverage["verified"]
        )
        if entry["assertion_class"] == NON_ASSERTIVE:
            expected = {"doc", "unit", "assertion_class"}
            if set(entry) != expected:
                return _invalid(
                    "sync-judgment-invalid-shape",
                    "a non-assertive judgment is classification-only and must "
                    f"carry exactly {sorted(expected)}",
                    "judgment",
                )
            examined_judgments.append((entry["doc"], {
                "unit": entry["unit"],
                "assertion_class": NON_ASSERTIVE,
                "classification": "classification-only",
            }))
            continue
        if entry["assertion_class"] in VERDICT_REQUIRED_CLASSES:
            ledger_record, problem = _validate_strategy(
                repo_root, entry, model, as_of, state["base_commit"]
            )
            if problem is not None:
                return problem
            judged_ledger.append(ledger_record)

    deterministic = fresh.deterministic_results
    coverage_entries, examined_by_doc = [], {}
    for item in deterministic["unchanged"]:
        examined_by_doc.setdefault(item["doc"], []).append({"unit": item["unit"]})
        if item["coverage_source"] == "probe":
            coverage_entries.append({
                "path": item["doc"], "unit": item["unit"], "source": "probe",
                "probe": item["probe"],
            })
        else:
            origin = item["originating_lineage"]
            coverage_entries.append({
                "path": item["doc"], "unit": item["unit"], "source": "carried",
                "reason": item["reason"], "lineage": {
                    "report_digest": origin["report_digest"],
                    "commit": origin["commit"],
                },
            })
    for doc, item in examined_judgments:
        examined_by_doc.setdefault(doc, []).append(item)
        coverage_entries.append({
            "path": doc, "unit": item["unit"], "source": "judged",
        })

    records = []
    deterministic_findings = [
        finding
        for check in deterministic["narrative_checks"]
        for finding in check["findings"]
    ]
    record_number = 1
    for spec in deterministic_findings:
        extra = {
            name: value for name, value in spec.items()
            if name not in {"code", "path", "units"}
        }
        finding = build_finding(
            lineage, spec["code"], spec["path"], spec["units"],
            f"SYNC-{record_number:03d}", extra,
        )
        if isinstance(finding, Invalid):
            return finding
        records.append(finding.to_record())
        for unit in spec["units"]:
            coverage_entries.append({
                "path": spec["path"], "unit": unit, "source": "probe",
                "probe": {
                    "kind": "narrative_anchor",
                    "observed": {"finding": spec["code"]},
                },
            })
        record_number += 1
    for draft in drafts:
        finding = build_finding(
            lineage, draft.code, draft.path, draft.units,
            f"SYNC-{record_number:03d}", draft.extra,
        )
        if isinstance(finding, Invalid):
            return finding
        records.append(finding.to_record())
        for unit in draft.units:
            coverage_entries.append({
                "path": draft.path, "unit": unit, "source": "judged",
            })
        record_number += 1

    unexamined = sorted(set(requested) - seen)
    denial_reason = (
        judgments.get("reason") if judgments.get("status") == "denied" else None
    )
    incomplete = [{
        "scope": f"{doc} + {unit}",
        "reason": denial_reason or (
            "the bounded work order received no judgment for this unit"
        ),
    } for doc, unit in unexamined]
    # Deterministic inventory gaps stay gaps; they never become a model request.
    incomplete.extend(deterministic["incomplete"])
    incomplete.extend({
        "scope": finding["path"],
        "reason": (
            f"the inventory reported {finding['code']}, so this document's "
            "assertion obligation could not be established"
        ),
    } for finding in deterministic["inventory_findings"])
    examined = [{
        "scope": doc,
        "verified": sorted(items, key=lambda item: item["unit"]),
    } for doc, items in sorted(examined_by_doc.items())]
    scope_docs = sorted(
        {item["doc"] for item in deterministic["unchanged"]}
        | {doc for doc, _ in requested}
        | {check["path"] for check in deterministic["narrative_checks"]}
        | {finding["path"] for finding in deterministic["inventory_findings"]}
    )
    report = validate_report({
        "status": state_from_content(records, incomplete),
        "schema_version": REPORT_SCHEMA_VERSION,
        "lineage": lineage.to_dict(),
        "records": records,
        "examined": examined,
        "incomplete": incomplete,
        "scope": {
            "basis": "the digest-bound incremental sync work order",
            "coverage": SCOPE_DECLARED_ONLY,
            "documents": scope_docs,
            "excluded": [],
        },
        "coverage": {
            "mode": COVERAGE_INCREMENTAL,
            "units": sorted(coverage_entries, key=lambda item: (
                item["path"], item["unit"]
            )),
        },
    }, registry_path=registry_path)
    if isinstance(report, Invalid):
        return report
    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        return inventory
    ledger = load_assertion_ledger(
        repo_root, inventory.registry_digest, ledger_path
    )
    if isinstance(ledger, Invalid):
        return ledger
    proposed = _proposal(
        ledger, report, state["base_commit"], as_of, deterministic,
        judged_ledger,
    )
    return report, proposed
