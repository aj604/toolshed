#!/usr/bin/env python3
"""Validate a detecting-doc-drift verdicts artifact before the engine reads it.

The contract lives in ../SKILL.md ("The output contract") and is the engine's:
`doclifecycle/drift.py` reads this artifact through `drift-audit --verdicts`.
Division of labor: this validator catches shape violations before dispatch —
enums, the judged-unit field set, one answer per unit, evidence citation rules,
the STALE-only `fix` — so a malformed answer fails in a second instead of after
a full audit run.
`drift-audit` is the authority. It holds what this script cannot see: the
segmentation (whether an ordinal names a real unit, whether a multi-line `fix`
owns its span), the plan (whether a document was in scope), and the run's
evidence boundary. A payload this script accepts can still be refused there,
and the engine's refusal is the one that decides.

Usage:
    validate-drift-output.py [FILE]        # reads FILE, or stdin if omitted

Input: the verdicts artifact —
    {"schema_version": 1, "documents": [{"path": ..., "status": "ok",
     "verdicts": [{"unit": <ordinal>, "assertion_class": ..., ...}]}]}
`schema_version` is optional and must be 1 when present.

Exit status: 0 if valid, 1 if any entry or verdict violates the contract,
2 on bad input (unreadable, unparseable, or wrong top-level shape).
On success, prints a summary recomputed from the verdicts, so callers never
rely on a hand-counted one.
"""

import json
import re
import sys
import unicodedata

ASSERTION_CLASSES = ("factual", "normative", "rationale", "non-assertive")
# Every assertion owes a judgment; only non-assertive prose may not carry one.
VERDICT_REQUIRED_CLASSES = ("factual", "normative", "rationale")
VERDICT_FORBIDDEN_CLASSES = ("non-assertive",)

OBLIGATIONS_BY_CLASS = {
    "factual": ("evidence",),
    "normative": ("governing-source", "owner-judgment"),
    "rationale": ("coherence",),
}

VERDICTS = ("VERIFIED", "STALE", "UNVERIFIABLE")
# The verdicts that assert someone read the code; both must cite where.
POINTED_VERDICTS = ("VERIFIED", "STALE")
KINDS = ("command", "path", "symbol", "behavior", "structure", "value")
TIERS = (1, 2, 3)

VERDICT_FIELDS = ("unit", "assertion_class", "verdict", "kind", "tier",
                  "evidence", "obligation", "fix")
REQUIRED_VERDICT_FIELDS = ("unit", "assertion_class")
# Owed together by a judged unit, and refused together for an unjudged one.
VERDICT_ONLY_FIELDS = ("verdict", "kind", "tier", "evidence", "obligation")

EVIDENCE_FIELDS = ("source", "line", "observed", "command")
EVIDENCE_CITATIONS = ("source", "command")
# Chaining, redirection, substitution, escaping: what would make a cited
# command a shell program rather than one line a reader can re-run.
SHELL_SYNTAX = ";&|<>()$`\\"

ENTRY_FIELDS = ("path", "status", "verdicts", "reason", "chunk")
ENTRY_OK = "ok"
ENTRY_FAILED = "failed"
ENTRY_STATUSES = (ENTRY_OK, ENTRY_FAILED)

TOPLEVEL_FIELDS = ("schema_version", "documents")
SCHEMA_VERSION = 1

DIGEST = re.compile(r"[0-9a-f]{64}")


def real_int(v):
    # `bool` is an `int` subclass and `1.0 == 1`, so a bare equality or
    # membership check would wave through `true` / `1.0`.
    return isinstance(v, int) and not isinstance(v, bool)


def valid_unit(v):
    """Whether `v` names a unit the way the contract spells one.

    `fullmatch`, never `match` against a `$`-anchored pattern: `$` also
    matches just before a trailing newline, so `"<64 hex>\\n"` would read as a
    digest here and then reach the engine as a digest no unit has —
    `classification-unknown-unit`, the whole document refused after the audit
    has already been paid for. Transcription damage to a 64-character string
    is the exact failure this seam exists to catch, so the match is exact.
    """
    return ((real_int(v) and v >= 0)
            or (isinstance(v, str) and DIGEST.fullmatch(v) is not None))


def one_line(v):
    """A non-empty single-line string — what a contract field may carry."""
    return (
        isinstance(v, str)
        and v.strip() != ""
        and not any(c in v for c in "\n\r\x00")
    )


def is_control(char):
    """Control and format characters, including the invisible reordering ones.

    U+202E and friends are category Cf: they render a filename as something
    other than what it is, which is the whole trick.
    """
    return unicodedata.category(char) in ("Cc", "Cf", "Cs", "Co", "Cn")


def source_spelling_problem(path):
    """Why `path` is not a canonical repository-relative spelling, or None.

    A faithful port of the engine's `paths.repository_relative_problem`
    (`doclifecycle/paths.py`), which `drift.py` applies to every
    `evidence.source`. Ported rather than imported so this script stays
    standalone and dependency-free — `paths.py` is the rule's owner, and this
    copy exists only to reach the same refusal a second earlier. The order is
    the engine's: the most specific diagnosis wins, so a tab reads as a control
    character rather than as whitespace, and `..` as traversal rather than as a
    non-canonical component.

    Existence is deliberately not checked, there as here: a pointer at a file a
    commit deleted is exactly what a STALE finding reports.
    """
    if not isinstance(path, str) or path.strip() == "":
        return "is empty or blank — a path names the file that settled the claim"
    bad = next((c for c in path if is_control(c)), None)
    if bad is not None:
        return (f"contains the control character U+{ord(bad):04X} — a path is "
                f"plain printable text, so it reads the same to a shell, to "
                f"git, and to a person")
    if path.startswith("/") or path.startswith("~"):
        return ("is absolute — name the file repository-relative, so the same "
                "verdict means the same file in every checkout")
    if len(path) >= 2 and path[1] == ":" and path[0].isascii() and path[0].isalpha():
        return ("carries a drive letter — name the file repository-relative, so "
                "the same verdict means the same file in every checkout")
    if "\\" in path:
        return ("uses '\\' as a separator — repository paths use '/', and a "
                "backslash is a literal filename character on posix")
    bad = next((c for c in path if c.isspace() or unicodedata.category(c) == "Zs"),
               None)
    if bad is not None:
        return (f"contains whitespace (U+{ord(bad):04X}) — whitespace makes a "
                f"path ambiguous to quote and impossible to distinguish by eye")
    if unicodedata.normalize("NFC", path) != path:
        return ("is not in Unicode NFC form — two spellings that normalize "
                "together would name one file under two identities; use the "
                "composed form")
    components = path.split("/")
    if ".." in components:
        return ("traverses with '..' — a repository-relative path names a "
                "location inside the repository and never walks out of one")
    if any(c in ("", ".") for c in components):
        return ("is not canonical — drop './', '//', and any trailing '/' so "
                "one file has exactly one spelling")
    bad = next((c for c in components if c.startswith("-")), None)
    if bad is not None:
        return (f"has a component starting with '-' ({bad!r}) — such a path is "
                f"read as an option by the tools that would act on it")
    return None


def load(src):
    raw = sys.stdin.read() if src is None else open(src, encoding="utf-8").read()
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) - set(TOPLEVEL_FIELDS) or (
        "documents" not in data
    ) or not isinstance(data["documents"], list):
        raise ValueError(
            "input must be the verdicts artifact — an object shaped "
            "{'documents': [...]} (optionally with 'schema_version'), one "
            "entry per document the plan declared"
        )
    version = data.get("schema_version", SCHEMA_VERSION)
    if not real_int(version) or version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version {version!r} is not supported; this contract is "
            f"integer version {SCHEMA_VERSION}"
        )
    return data["documents"]


def validate_evidence(raw, verdict, where, errs):
    if not isinstance(raw, dict):
        errs.append(
            f"{where}: evidence must be an object naming the fact observed and "
            f"where — {list(EVIDENCE_FIELDS)}, 'observed' required"
        )
        return
    for key in raw:
        if key not in EVIDENCE_FIELDS:
            errs.append(f"{where}: unexpected evidence field '{key}'")
    if not one_line(raw.get("observed")):
        errs.append(
            f"{where}: evidence.observed is mandatory for every verdict, "
            f"VERIFIED included, and is one line — the fact that was read"
        )

    cited = [name for name in EVIDENCE_CITATIONS if raw.get(name) is not None]
    if len(cited) > 1:
        # Which citation the rest of the checks are about is exactly what is in
        # doubt, so every one of them would be a guess.
        errs.append(
            f"{where}: evidence cites both {list(EVIDENCE_CITATIONS)} — a "
            f"verdict rests on one place a reader goes"
        )
        return
    if not cited and verdict in POINTED_VERDICTS:
        errs.append(
            f"{where}: a {verdict} verdict asserts that something was actually "
            f"checked, so evidence must cite where: a repository-relative path "
            f"in evidence.source, or the command that settled it in "
            f"evidence.command"
        )

    line = raw.get("line")
    command = raw.get("command")
    if command is not None:
        if not one_line(command):
            errs.append(
                f"{where}: evidence.command must be the single command line "
                f"that settled the claim"
            )
        elif any(c in SHELL_SYNTAX for c in command):
            errs.append(
                f"{where}: evidence.command {command!r} carries shell syntax "
                f"({SHELL_SYNTAX!r}) — chaining, redirection, substitution, or "
                f"escaping makes it a shell program, not one read-only command "
                f"a reader re-runs"
            )
        if line is not None:
            errs.append(
                f"{where}: evidence.line points into a file, and a tool's "
                f"output is not one — a command citation carries 'observed' "
                f"and nothing else"
            )
        return

    if raw.get("source") is not None:
        # The engine runs this same predicate on every source and drops the
        # whole document when it fails, so a spelling it refuses must not pass
        # here — that gap is what this pre-flight exists to close.
        fault = source_spelling_problem(raw["source"])
        if fault:
            errs.append(
                f"{where}: evidence.source must be a repository-relative path "
                f"to the file that settled the claim, and {raw['source']!r} "
                f"{fault}"
            )
    if line is not None and (not real_int(line) or line < 1):
        errs.append(f"{where}: evidence.line must be a line number counted from 1")


def validate_fix(entry, verdict, where, errs):
    fix = entry.get("fix")
    if verdict != "STALE":
        if fix is not None:
            errs.append(
                f"{where}: only a STALE verdict carries a fix; {verdict!r} "
                f"proposes no edit"
            )
        return
    # Shape only. Whether an embedded LF is permitted depends on the unit's
    # span, which the segmentation owns — `drift-audit` decides that.
    if not isinstance(fix, str) or any(c in fix for c in "\r\x00") or (
        any(line.strip() == "" for line in fix.split("\n"))
    ):
        errs.append(
            f"{where}: a STALE verdict must carry 'fix': the complete "
            f"replacement text for the unit, never an instruction describing "
            f"one — non-empty physical lines separated by LF, no CR or NUL"
        )


def validate_verdict(entry, where, errs):
    """Validate one verdict. Returns its verdict string, or None."""
    if not isinstance(entry, dict):
        errs.append(f"{where}: a verdict is a JSON object, not "
                    f"{type(entry).__name__}")
        return None

    shaped = True
    for field in entry:
        if field not in VERDICT_FIELDS:
            errs.append(f"{where}: unexpected field '{field}'")
            shaped = False
    for field in REQUIRED_VERDICT_FIELDS:
        if field not in entry:
            errs.append(f"{where}: missing required field '{field}'")
            shaped = False
    if not shaped:
        return None

    unit = entry["unit"]
    if not valid_unit(unit):
        errs.append(
            f"{where}: unit {unit!r} must be the ordinal `segment` printed "
            f"alongside the unit — a non-negative integer (a 64-character "
            f"unit digest is also accepted)"
        )

    assertion_class = entry["assertion_class"]
    if assertion_class not in ASSERTION_CLASSES:
        errs.append(
            f"{where}: assertion_class {assertion_class!r} not in "
            f"{list(ASSERTION_CLASSES)}"
        )
        return None

    judged = sorted(set(VERDICT_ONLY_FIELDS) & set(entry))
    if assertion_class in VERDICT_FORBIDDEN_CLASSES:
        if judged:
            errs.append(
                f"{where}: a {assertion_class!r} unit asserts nothing the code "
                f"could contradict, so it takes no verdict — {judged} would "
                f"record a claim nobody made"
            )
        return None
    if not judged:
        if assertion_class in VERDICT_REQUIRED_CLASSES:
            errs.append(
                f"{where}: a {assertion_class!r} unit carries a review "
                f"obligation, so it must be judged: {list(VERDICT_ONLY_FIELDS)} "
                f"are owed for it"
            )
        return None
    missing = [f for f in VERDICT_ONLY_FIELDS if f not in entry]
    if missing:
        errs.append(
            f"{where}: a judged unit carries all of "
            f"{list(VERDICT_ONLY_FIELDS)}; this one is missing {missing}"
        )
        return None

    obligation = entry["obligation"]
    allowed_obligations = OBLIGATIONS_BY_CLASS[assertion_class]
    if obligation not in allowed_obligations:
        errs.append(
            f"{where}: obligation {obligation!r} does not discharge a "
            f"{assertion_class!r} assertion — expected one of "
            f"{list(allowed_obligations)}"
        )

    verdict = entry["verdict"]
    if verdict not in VERDICTS:
        errs.append(f"{where}: verdict {verdict!r} not in {list(VERDICTS)}")
    if entry["kind"] not in KINDS:
        errs.append(f"{where}: kind {entry['kind']!r} not in {list(KINDS)} — "
                    f"downstream tooling switches on it")
    tier = entry["tier"]
    if not (real_int(tier) and tier in TIERS):
        errs.append(f"{where}: tier {tier!r} not in {list(TIERS)}")

    validate_evidence(entry["evidence"], verdict, where, errs)
    validate_fix(entry, verdict, where, errs)
    return verdict if verdict in VERDICTS else None


def check_unique_units(verdicts, path, errs):
    """Refuse a unit answered twice within one document.

    The engine refuses the same thing in `finding.record_classifications` —
    `classification-duplicate`, "a unit has one class, and two answers is no
    answer" — and fails the document closed, so a duplicate costs the run every
    finding it reached, not just the repeated one. Purely shape-detectable, so
    it belongs here too.

    Units are compared exactly as written. An ordinal and a digest are two ways
    to name a unit, and only the segmentation says whether they name the same
    one; this script has no segmentation, so `1` and its digest read as two
    units here and it is `drift-audit` that collides them. A unit the contract
    does not recognize is skipped: its own violation is already reported, and
    it names nothing to be a duplicate of.
    """
    first = {}
    for i, entry in enumerate(verdicts):
        if not isinstance(entry, dict) or not valid_unit(entry.get("unit")):
            continue
        unit = entry["unit"]
        if unit in first:
            errs.append(
                f"{path}:verdicts[{i}]: unit {unit!r} is answered more than "
                f"once (first at verdicts[{first[unit]}]) — a unit takes one "
                f"class and one verdict, and two answers is no answer"
            )
        else:
            first[unit] = i


def validate_entry(i, entry, seen, errs):
    """Validate one document entry. Returns the verdict strings it reached."""
    where = f"documents[{i}]"
    if not isinstance(entry, dict):
        errs.append(f"{where}: a document entry is a JSON object, not "
                    f"{type(entry).__name__}")
        return []

    shaped = True
    for field in entry:
        if field not in ENTRY_FIELDS:
            errs.append(f"{where}: unexpected field '{field}'")
            shaped = False
    if not one_line(entry.get("path")):
        errs.append(f"{where}: each entry names the document it reports on in "
                    f"'path'")
        shaped = False
    status = entry.get("status")
    if status not in ENTRY_STATUSES:
        errs.append(f"{where}: status {status!r} not in {list(ENTRY_STATUSES)}")
        shaped = False
    if not shaped:
        return []

    path = entry["path"]
    where = path
    if path in seen:
        errs.append(f"{where}: two entries report on {path} — which one "
                    f"describes the run is not knowable from here")
        return []
    seen.add(path)

    if "chunk" in entry and not one_line(entry["chunk"]):
        errs.append(f"{where}: 'chunk' names the unit of work that produced "
                    f"the entry")

    if status == ENTRY_FAILED:
        if "verdicts" in entry:
            errs.append(f"{where}: a {ENTRY_FAILED!r} entry reached no "
                        f"verdicts, so it carries none")
        if not one_line(entry.get("reason")):
            errs.append(
                f"{where}: a {ENTRY_FAILED!r} entry must say why in 'reason' — "
                f"a gap with no reason is indistinguishable from a document "
                f"nobody thought about"
            )
        return []

    if "reason" in entry:
        errs.append(f"{where}: an {ENTRY_OK!r} entry carries the verdicts it "
                    f"reached, and no reason for not reaching them")
    if not isinstance(entry.get("verdicts"), list):
        errs.append(f"{where}: an {ENTRY_OK!r} entry carries a 'verdicts' list "
                    f"— one answer per assertion unit `segment` printed")
        return []

    reached = []
    for j, verdict in enumerate(entry["verdicts"]):
        reached.append(validate_verdict(verdict, f"{path}:verdicts[{j}]", errs))
    check_unique_units(entry["verdicts"], path, errs)
    return reached


def main():
    if len(sys.argv) > 2:
        print("usage: validate-drift-output.py [FILE]", file=sys.stderr)
        return 2
    src = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        documents = load(src)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    errs, seen, reached = [], set(), []
    for i, entry in enumerate(documents):
        reached.extend(validate_entry(i, entry, seen, errs))

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"\nFAILED: {len(errs)} contract violation(s)", file=sys.stderr)
        return 1

    counts = {"verified": 0, "stale": 0, "unverifiable": 0}
    for verdict in reached:
        if verdict in VERDICTS:
            counts[verdict.lower()] += 1
    print(f"OK: {len(reached)} verdict(s) across {len(documents)} document(s)")
    print(f"summary: {json.dumps(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
