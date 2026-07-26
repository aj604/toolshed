"""The registry: globs -> document kind and set, within declared roots.

The registry owns classification. Content-coupled facts (as-of, anchors,
lifecycle state) stay in the documents themselves. Validation fails closed and
reports every problem it finds in one pass: a registry that cannot be trusted
invalidates the run rather than classifying part of the corpus.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .digest import sha256_canonical
from .results import Problem

SCHEMA_VERSION = 1
KINDS = ("living", "narrative", "planning")
DEFAULT_EXTENSIONS = (".md",)
FIELDS = ("schema_version", "roots", "exclude", "sets", "extensions", "rules")
REQUIRED_FIELDS = ("schema_version", "roots", "rules")
RULE_FIELDS = ("glob", "kind", "set")


def compile_glob(pattern):
    """Translate a posix doc glob to a regex.

    `*` and `?` stop at `/`; `**/` spans zero or more directories, so
    `docs/**/*.md` matches `docs/a.md` and `docs/deep/a.md` alike.
    """
    out, i, n = [], 0, len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass(frozen=True)
class Rule:
    glob: str
    kind: str
    doc_set: Optional[str] = None
    # Compiled once at parse time: classification asks every rule about every
    # candidate path, and re.compile() results are not cached.
    matcher: re.Pattern = field(default=None, compare=False, repr=False)

    def matches(self, path):
        return bool(self.matcher.match(path))


@dataclass(frozen=True)
class Registry:
    roots: Tuple[str, ...]
    exclude: Tuple[str, ...]
    sets: Tuple[str, ...]
    extensions: Tuple[str, ...]
    rules: Tuple[Rule, ...]
    digest: str
    exclude_matchers: Tuple[re.Pattern, ...] = field(
        default=(), compare=False, repr=False
    )

    def classify(self, path):
        """The rule that classifies `path`, or None if no rule matches.

        Precedence is rule order: the *last* matching rule wins, so a registry
        reads as broad defaults first, narrower overrides after (the .gitignore
        mental model). Glob specificity is deliberately not consulted — order is
        visible in the file, specificity is not.
        """
        winner = None
        for rule in self.rules:
            if rule.matches(path):
                winner = rule
        return winner

    def excludes(self, path):
        """Whether `path`, or any directory above it, is excluded."""
        return any(m.match(path) for m in self.exclude_matchers)

    def is_document(self, path):
        return path.endswith(self.extensions)


def _exclude_matchers(patterns):
    """One matcher per pattern, each also covering everything beneath it.

    So `docs/vendor` excludes `docs/vendor/upstream.md` — naming a directory
    without a trailing `/**` is the obvious spelling, and a no-op there would be
    a silent coverage hole.
    """
    matchers = []
    for pattern in patterns:
        trimmed = pattern.rstrip("/")
        matchers.append(compile_glob(trimmed))
        matchers.append(compile_glob(f"{trimmed}/**"))
    return tuple(matchers)


def _normalize_path(value):
    """Canonical spelling of a declared root: no `./` prefix, no trailing `/`."""
    trimmed = value.strip()
    while trimmed.startswith("./"):
        trimmed = trimmed[2:]
    return trimmed.rstrip("/") or trimmed


def _unsafe_reason(value):
    """Why this path/glob is not a canonical repo-relative path, or None.

    Registry-input hygiene only. The general path-authorization module (#67)
    becomes the single owner of these rules for everything that reads or writes
    on behalf of a record; these checks move behind it when it lands.
    """
    if not isinstance(value, str) or value.strip() == "":
        return "must be a non-empty string"
    if value.startswith("/"):
        return "must be repository-relative, not absolute"
    if "\\" in value:
        return "must use '/' separators"
    if "\n" in value or "\r" in value or "\x00" in value:
        return "must not contain newlines or NUL"
    if ".." in value.split("/"):
        return "must not traverse with '..'"
    if value in (".", "./"):
        return "must name a documentation subtree, not the whole repository"
    return None


def _overlapping(roots):
    """Pairs of declared roots where one contains the other (or repeats it)."""
    overlaps = []
    for i, outer in enumerate(roots):
        for inner in roots[i + 1:]:
            if inner == outer or inner.startswith(f"{outer}/") or outer.startswith(
                f"{inner}/"
            ):
                overlaps.append((outer, inner))
    return overlaps


def _digest(roots, exclude, sets, extensions, rules):
    """Digest the registry's meaning, so reformatting it is not a new registry.

    Rule order is significant (it decides precedence); root, exclude, set, and
    extension order is not, so those are normalized before digesting.
    """
    return sha256_canonical({
        "schema_version": SCHEMA_VERSION,
        "roots": sorted(roots),
        "exclude": sorted(exclude),
        "sets": sorted(sets),
        "extensions": sorted(extensions),
        "rules": [
            {"glob": r.glob, "kind": r.kind, "set": r.doc_set} for r in rules
        ],
    })


def parse(text, location=None):
    """Parse and validate registry JSON. Returns (Registry|None, [Problem])."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [Problem(
            code="registry-unparseable",
            message=f"the registry is not valid JSON: {exc}",
            location=location,
        )]

    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(
            code=code,
            message=message,
            location=location if where is None else f"{location}#{where}",
        ))

    if not isinstance(data, dict):
        bad("registry-invalid-shape", "the registry must be a JSON object")
        return None, problems

    for name in REQUIRED_FIELDS:
        if name not in data:
            bad("registry-missing-field", f"missing required field '{name}'")
    for name in data:
        if name not in FIELDS:
            bad(
                "registry-unknown-field",
                f"unexpected field '{name}' — known fields are {list(FIELDS)}",
            )

    version = data.get("schema_version")
    if "schema_version" in data and version != SCHEMA_VERSION:
        bad(
            "registry-schema-version",
            f"registry schema_version {version!r} is not supported; this engine "
            f"reads version {SCHEMA_VERSION}. Migrate the registry rather than "
            f"guessing at its meaning.",
        )

    roots = data.get("roots")
    if "roots" in data:
        if not isinstance(roots, list):
            bad("registry-invalid-shape", "roots must be a list of paths")
            roots = []
        elif not roots:
            bad(
                "registry-invalid-shape",
                "roots must declare at least one documentation root — "
                "classification is closed-world within the roots",
            )
        for i, root in enumerate(roots):
            reason = _unsafe_reason(root)
            if reason:
                bad("registry-unsafe-root", f"root {root!r} {reason}", f"roots[{i}]")
    else:
        roots = []
    roots = [_normalize_path(r) for r in roots if isinstance(r, str)]
    for outer, inner in _overlapping(roots):
        bad(
            "registry-overlapping-root",
            f"roots {outer!r} and {inner!r} overlap — a document must belong to "
            f"exactly one root, or it would be inventoried twice",
        )

    exclude = data.get("exclude", [])
    if not isinstance(exclude, list):
        bad("registry-invalid-shape", "exclude must be a list of globs")
        exclude = []
    for i, pattern in enumerate(exclude):
        reason = _unsafe_reason(pattern)
        if reason:
            bad(
                "registry-unsafe-exclude",
                f"exclude {pattern!r} {reason}",
                f"exclude[{i}]",
            )

    sets = data.get("sets", [])
    if not isinstance(sets, list) or not all(
        isinstance(s, str) and s.strip() != "" for s in sets
    ):
        bad("registry-invalid-shape", "sets must be a list of non-empty set names")
        sets = []

    extensions = data.get("extensions", list(DEFAULT_EXTENSIONS))
    if (
        not isinstance(extensions, list)
        or not extensions
        or not all(
            isinstance(e, str) and e.startswith(".") and len(e) > 1 for e in extensions
        )
    ):
        bad(
            "registry-invalid-extensions",
            f"extensions must be a non-empty list of dotted suffixes, e.g. "
            f"{list(DEFAULT_EXTENSIONS)} — it declares which files under a root "
            f"are documents, so the closed-world rule can name what it covered",
        )
        extensions = list(DEFAULT_EXTENSIONS)

    rules_data = data.get("rules")
    if "rules" in data and not isinstance(rules_data, list):
        bad("registry-invalid-shape", "rules must be a list of rule objects")
        rules_data = []
    rules = []
    for i, raw in enumerate(rules_data or []):
        where = f"rules[{i}]"
        if not isinstance(raw, dict):
            bad("registry-invalid-rule", f"rule {i} is not an object", where)
            continue
        for name in ("glob", "kind"):
            if name not in raw:
                bad(
                    "registry-invalid-rule",
                    f"rule {i} is missing required field '{name}'",
                    where,
                )
        for name in raw:
            if name not in RULE_FIELDS:
                bad(
                    "registry-invalid-rule",
                    f"rule {i} has unexpected field '{name}' — a rule declares "
                    f"{list(RULE_FIELDS)}",
                    where,
                )
        glob, kind, doc_set = raw.get("glob"), raw.get("kind"), raw.get("set")
        reason = _unsafe_reason(glob) if "glob" in raw else None
        if reason:
            bad("registry-unsafe-glob", f"glob {glob!r} {reason}", where)
        if "kind" in raw and kind not in KINDS:
            bad(
                "registry-unknown-kind",
                f"kind {kind!r} is not a document kind — every document is "
                f"exactly one of {list(KINDS)}",
                where,
            )
        if doc_set is not None:
            if not isinstance(doc_set, str) or doc_set.strip() == "":
                bad("registry-invalid-rule", f"rule {i} set must be a name", where)
            elif doc_set not in sets:
                bad(
                    "registry-unknown-set",
                    f"set {doc_set!r} is not declared in 'sets' — declare the set "
                    f"before assigning documents to it",
                    where,
                )
        if isinstance(glob, str) and kind in KINDS:
            rules.append(Rule(
                glob=glob,
                kind=kind,
                doc_set=doc_set,
                matcher=compile_glob(glob),
            ))

    if problems:
        return None, problems
    return Registry(
        roots=tuple(roots),
        exclude=tuple(exclude),
        sets=tuple(sets),
        extensions=tuple(extensions),
        rules=tuple(rules),
        digest=_digest(roots, exclude, sets, extensions, rules),
        exclude_matchers=_exclude_matchers(exclude),
    ), []
