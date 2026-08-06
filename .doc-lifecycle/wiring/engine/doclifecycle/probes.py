"""Closed, read-only deterministic probes used by incremental sync."""

import ast
import json
import keyword
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from .digest import sha256_file
from .paths import repository_read_problem, repository_relative_problem
from .results import Problem

PROBE_KINDS = (
    "path_exists", "content_match", "json_value", "symbol_defined",
    "tool_probe",
)
DEFAULT_EVIDENCE_TOOLS_PATH = ".doc-lifecycle/evidence-tools.json"
_TOOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHELL_SYNTAX = ";&|<>()$`"
_GLOB_META = "*?["
_MAX_PATTERN_LENGTH = 4096
_MAX_FILE_BYTES = 4 * 1024 * 1024
_MAX_MATCH_EVIDENCE = 1000
_TOOL_FLAGS = ("--help", "--version")
_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class ProbeOutcome:
    passed: bool
    observed: dict
    problem: Problem = None


def _problem(code, message, location="probe"):
    return ProbeOutcome(False, {}, Problem(code, message, location))


def _one_line(value):
    return (
        isinstance(value, str) and bool(value.strip())
        and not any(char in value for char in "\r\n\x00")
    )


def _reject_constant(value):
    raise ValueError(f"{value} is not JSON")


def _path_shape(value, *, glob=False):
    problem = repository_relative_problem(value)
    if problem is not None:
        return Problem("probe-unsafe-path", problem[1], "probe.args")
    if any(char in value for char in _SHELL_SYNTAX):
        return Problem(
            "probe-command-shaped-path",
            "probe paths are data and may not contain shell syntax",
            "probe.args",
        )
    if glob and not any(char in value for char in _GLOB_META):
        return Problem(
            "probe-malformed-args", "a probe glob must be a glob", "probe.args"
        )
    if not glob and any(char in value for char in _GLOB_META):
        return Problem(
            "probe-malformed-args", "a literal probe path may not be a glob",
            "probe.args",
        )
    return None


def _pattern(value):
    if not (_one_line(value) and len(value) <= _MAX_PATTERN_LENGTH):
        return None
    try:
        return re.compile(value)
    except re.error:
        return None


def _compile_path_glob(pattern):
    """Compile the probe's POSIX glob without letting ``*`` cross ``/``."""
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        elif pattern[index] == "[":
            end = pattern.find("]", index + 1)
            if end < 0:
                raise re.error("unterminated character class")
            characters = pattern[index + 1:end]
            if "/" in characters:
                raise re.error("a character class may not contain '/'")
            negated = characters.startswith("!")
            if negated:
                characters = characters[1:]
            characters = characters.replace("\\", r"\\").replace("]", r"\]")
            prefix = "^/" if negated else ""
            out.append("[" + prefix + characters + "]")
            index = end + 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def _validate(probe):
    """Return compiled/runtime metadata or a typed pre-execution refusal."""
    if not isinstance(probe, dict) or set(probe) != {"kind", "args", "expect"}:
        return None, Problem(
            "probe-malformed-args",
            "probe must carry exactly 'kind', 'args', and 'expect'", "probe",
        )
    kind, args, expect = probe["kind"], probe["args"], probe["expect"]
    if kind not in PROBE_KINDS:
        return None, Problem(
            "probe-unknown-kind",
            f"probe kind {kind!r} is not in the closed vocabulary", "probe.kind",
        )
    if not isinstance(args, dict) or not isinstance(expect, dict):
        return None, Problem(
            "probe-malformed-args", "probe args and expect must be objects", "probe",
        )

    compiled = None
    if kind == "path_exists":
        literal = set(args) == {"path", "kind"}
        glob = set(args) == {"glob", "kind"}
        if (not (literal or glob) or expect != {}
                or args.get("kind") not in ("file", "dir", "any")):
            return None, Problem(
                "probe-malformed-args", "invalid path_exists arguments", "probe"
            )
        fault = _path_shape(args["path" if literal else "glob"], glob=glob)
        if glob and fault is None:
            try:
                compiled = _compile_path_glob(args["glob"])
            except re.error:
                return None, Problem(
                    "probe-malformed-args", "invalid path_exists glob",
                    "probe.args.glob",
                )
    elif kind == "content_match":
        if set(args) != {"path", "pattern"} or not (
                set(expect) == {"presence"} or set(expect) == {"presence", "count"}):
            return None, Problem(
                "probe-malformed-args", "invalid content_match arguments", "probe"
            )
        fault = _path_shape(args["path"])
        compiled = _pattern(args["pattern"])
        if compiled is None or expect.get("presence") not in ("present", "absent") or (
                "count" in expect and not (
                    isinstance(expect["count"], int) and not isinstance(expect["count"], bool)
                    and expect["count"] >= 0)):
            return None, Problem(
                "probe-malformed-args", "invalid content_match expectation", "probe"
            )
    elif kind == "json_value":
        if set(args) != {"path", "pointer"} or set(expect) != {"equals"}:
            return None, Problem(
                "probe-malformed-args", "invalid json_value arguments", "probe"
            )
        fault = _path_shape(args["path"])
        pointer = args["pointer"]
        if (not isinstance(pointer, str)
                or (pointer and not pointer.startswith("/"))
                or re.search(r"~(?![01])", pointer)):
            return None, Problem(
                "probe-malformed-args", "invalid RFC 6901 pointer",
                "probe.args.pointer",
            )
    elif kind == "symbol_defined":
        if set(args) != {"path", "language", "name"} or expect != {}:
            return None, Problem(
                "probe-malformed-args", "invalid symbol_defined arguments", "probe"
            )
        fault = _path_shape(args["path"])
        name = args["name"]
        if args["language"] != "python" or not (_one_line(name) and all(
                part.isidentifier() and not keyword.iskeyword(part)
                for part in name.split("."))):
            return None, Problem(
                "probe-malformed-args", "invalid Python symbol name",
                "probe.args.name",
            )
    else:
        if set(args) != {"tool", "flag", "pattern"} or expect != {}:
            return None, Problem(
                "probe-malformed-args", "invalid tool_probe arguments", "probe"
            )
        fault = None
        compiled = _pattern(args["pattern"])
        if (not (_one_line(args["tool"]) and _TOOL.fullmatch(args["tool"]))
                or args["flag"] not in _TOOL_FLAGS or compiled is None):
            return None, Problem(
                "probe-malformed-args", "invalid tool_probe arguments", "probe"
            )
    return compiled, fault


def _declared_tools(repo_root, config_path):
    absolute = os.path.join(repo_root, config_path)
    try:
        with open(absolute, encoding="utf-8") as fh:
            raw = json.load(fh, parse_constant=_reject_constant)
    except FileNotFoundError:
        return (), None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, Problem(
            "probe-evidence-tools-unreadable",
            f"cannot read {config_path}: {exc}", config_path,
        )
    tools = raw.get("tools") if isinstance(raw, dict) else None
    if not isinstance(tools, list) or any(
            not isinstance(tool, str) or not _TOOL.fullmatch(tool)
            for tool in tools):
        return None, Problem(
            "probe-evidence-tools-invalid",
            f"{config_path} must declare a list of bare tool names", config_path,
        )
    return tuple(tools), None


def _safe_dependencies(repo_root, deps):
    if not isinstance(deps, (list, tuple)) or not deps:
        return None, Problem(
            "probe-malformed-deps", "a probe requires non-empty dependencies",
            "deps",
        )
    paths = []
    for index, dep in enumerate(deps):
        if not isinstance(dep, dict) or set(dep) != {"path", "digest"} or not (
                isinstance(dep.get("path"), str)
                and isinstance(dep.get("digest"), str)
                and _DIGEST.fullmatch(dep["digest"])):
            return None, Problem(
                "probe-malformed-deps", "invalid dependency", f"deps[{index}]"
            )
        path = dep["path"]
        fault = _path_shape(path)
        if fault is not None:
            return None, fault
        fault = repository_read_problem(path, repo_root=repo_root)
        if fault is not None:
            return None, Problem(
                ("probe-symlink-escape" if fault.code == "symlinked-path"
                 else "probe-unsafe-path"),
                fault.message, fault.location,
            )
        paths.append(path)
    return tuple(paths), None


def _file_bytes(path):
    with open(path, "rb") as fh:
        data = fh.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise ValueError(f"file exceeds {_MAX_FILE_BYTES} byte probe bound")
    return data


def _dependency_evidence(repo_root, paths):
    evidence = []
    for path in paths:
        absolute = os.path.join(repo_root, path)
        digest = sha256_file(absolute) if os.path.isfile(absolute) else None
        evidence.append({"path": path, "digest": digest})
    return evidence


def _pointer(document, pointer):
    value = document
    for raw in pointer.split("/")[1:] if pointer else ():
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif (isinstance(value, list)
              and re.fullmatch(r"0|[1-9][0-9]*", token)
              and int(token) < len(value)):
            value = value[int(token)]
        else:
            raise KeyError(token)
    return value


def _symbol_exists(tree, dotted):
    parts = dotted.split(".")
    bodies = [tree.body]
    for part in parts:
        next_bodies = []
        found = False
        for body in bodies:
            for node in body:
                names = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names = [node.name]
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names = [target.id for target in targets if isinstance(target, ast.Name)]
                if part in names:
                    found = True
                    if hasattr(node, "body"):
                        next_bodies.append(node.body)
        if not found:
            return False
        bodies = next_bodies
    return True


def _tool_env():
    # A tool receives no ambient repository, account, credential, editor, or
    # pager configuration.  The executable has already been resolved by the
    # parent process, so even PATH is unnecessary to the direct exec.
    return {"LC_ALL": "C", "LANG": "C", "NO_COLOR": "1", "TERM": "dumb"}


def _run_tool(binary, flag):
    result = subprocess.run(
        [binary, flag], capture_output=True, text=True, stdin=subprocess.DEVNULL,
        timeout=_TIMEOUT_SECONDS, env=_tool_env(), shell=False,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise OSError(f"tool exited {result.returncode}")
    if len(output.encode("utf-8")) > _MAX_FILE_BYTES:
        raise OSError(f"tool output exceeds {_MAX_FILE_BYTES} byte probe bound")
    return output


def execute_probe(repo_root, probe, deps,
                  evidence_tools_path=DEFAULT_EVIDENCE_TOOLS_PATH):
    """Validate, authorize, then execute one probe without shell or writes."""
    compiled, fault = _validate(probe)
    if fault is not None:
        return ProbeOutcome(False, {}, fault)
    dep_paths, fault = _safe_dependencies(repo_root, deps)
    if fault is not None:
        return ProbeOutcome(False, {}, fault)
    kind, args, expect = probe["kind"], probe["args"], probe["expect"]

    target = args.get("path")
    if target is not None and target not in dep_paths:
        return _problem(
            "probe-path-outside-boundary",
            f"{target!r} is not one of this probe's declared dependencies",
            "probe.args.path",
        )
    if "glob" in args:
        matches = tuple(path for path in dep_paths if compiled.match(path))
    else:
        matches = ()

    try:
        dep_evidence = _dependency_evidence(repo_root, dep_paths)
        observed = {"dependencies": dep_evidence}
        if kind == "path_exists":
            paths = matches if "glob" in args else (args["path"],)
            resolved = []
            for path in paths:
                absolute = os.path.join(repo_root, path)
                actual = (
                    "file" if os.path.isfile(absolute)
                    else "dir" if os.path.isdir(absolute) else None
                )
                if actual is not None:
                    resolved.append({"path": path, "kind": actual})
            required = args["kind"]
            passed = bool(resolved) and all(
                required == "any" or item["kind"] == required
                for item in resolved
            )
            observed["resolved_paths"] = resolved
        elif kind == "content_match":
            text = _file_bytes(
                os.path.join(repo_root, args["path"])
            ).decode("utf-8")
            found = [match.group(0) for match in compiled.finditer(text)]
            if len(found) > _MAX_MATCH_EVIDENCE:
                return _problem(
                    "probe-evidence-over-bound",
                    "too many regex matches to record",
                )
            count = len(found)
            passed = ((expect["presence"] == "present" and count > 0)
                      or (expect["presence"] == "absent" and count == 0))
            if "count" in expect:
                passed = passed and count == expect["count"]
            observed.update({
                "path": args["path"], "matched_text": found, "count": count,
            })
        elif kind == "json_value":
            document = json.loads(
                _file_bytes(os.path.join(repo_root, args["path"])).decode("utf-8"),
                parse_constant=_reject_constant,
            )
            try:
                value = _pointer(document, args["pointer"])
                resolved = True
            except KeyError:
                value, resolved = None, False
            passed = resolved and value == expect["equals"]
            observed.update({
                "path": args["path"], "pointer": args["pointer"],
                "resolved": resolved, "value": value,
            })
        elif kind == "symbol_defined":
            text = _file_bytes(
                os.path.join(repo_root, args["path"])
            ).decode("utf-8")
            defined = _symbol_exists(
                ast.parse(text, filename=args["path"]), args["name"]
            )
            passed = defined
            observed.update({
                "path": args["path"], "language": "python",
                "name": args["name"], "defined": defined,
            })
        else:
            if evidence_tools_path not in dep_paths:
                return _problem(
                    "probe-path-outside-boundary",
                    (f"{evidence_tools_path!r} is not one of this probe's "
                     "declared dependencies"),
                    evidence_tools_path,
                )
            tools, fault = _declared_tools(repo_root, evidence_tools_path)
            if fault is not None:
                return ProbeOutcome(False, {}, fault)
            if args["tool"] not in tools:
                return _problem(
                    "probe-tool-not-declared",
                    f"tool {args['tool']!r} is not declared", "probe.args.tool",
                )
            binary = shutil.which(args["tool"])
            if binary is None:
                return _problem(
                    "probe-tool-unavailable",
                    f"tool {args['tool']!r} is not installed", "probe.args.tool",
                )
            output = _run_tool(binary, args["flag"])
            version_output = (
                output if args["flag"] == "--version"
                else _run_tool(binary, "--version")
            )
            version_line = next(
                (line for line in version_output.splitlines() if line.strip()), ""
            )
            match = compiled.search(output)
            passed = match is not None
            observed.update({
                "tool": args["tool"], "flag": args["flag"],
                "version": version_line,
                "matched_text": match.group(0) if match is not None else None,
            })
        return ProbeOutcome(passed, observed)
    except (OSError, UnicodeDecodeError, ValueError, SyntaxError,
            json.JSONDecodeError, RecursionError,
            subprocess.TimeoutExpired) as exc:
        return _problem(
            "probe-execution-unavailable",
            f"probe could not read its evidence: {exc}",
        )
