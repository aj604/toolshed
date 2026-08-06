"""Path authorization: the single owner of path safety.

Everything that reads or writes on behalf of a record asks this module first.
A candidate path is authorized only when it is spelled canonically, resolves to
a real non-symlinked location inside a declared documentation root, and belongs
to the target class the caller declared. Anything else is refused with a typed
problem — never silently normalized into something acceptable.

Refusal, not repair, is the rule. Rewriting `docs//a.md` to `docs/a.md` would
make two spellings name one authorization, and a record's identity is its
spelling; so the module names the one canonical form and refuses the rest.

Owning path safety means owning path *shape*, so the recognizer lives here
too: `path_references` reads a piece of prose and says which of its tokens name
a file or directory in a repository. It authorizes nothing and opens nothing —
it answers "what did this sentence put in front of a reader as a file", which
is a question about spelling, and this module is where spelling is decided.
"""

import errno
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, replace
from typing import Optional

from .results import Problem

DOCUMENTATION = "documentation"

# The classes a path can be sorted into. The six after `documentation` are the
# ones an edit set must never reach: they execute, they configure execution, or
# they authenticate. `other` is everything unrecognized — refused too, because
# eligibility is a positive list, not the absence of a known danger.
WORKFLOW = "workflow"
SOURCE = "source"
CONFIGURATION = "configuration"
CREDENTIAL = "credential"
HOOK = "hook"
EXECUTABLE = "executable"
OTHER = "other"

# A caller declares which class it intends to touch. Only documentation may be
# declared: the dangerous classes are not a default that a record, a plan, or a
# consumer config could switch off. Widening this tuple is a deliberate change
# to the engine, reviewed as one.
DECLARABLE_TARGET_CLASSES = (DOCUMENTATION,)

_WORKFLOW_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    # The plugin's own directory in a wired repository, taken whole: the
    # regenerated wiring under `wiring/`, the credentialed jobs' state under
    # `state/`, and the consumer's judgment files at its root — the registry
    # included, which otherwise would be protected only incidentally by not
    # wearing a documentation suffix.
    ".doc-lifecycle/",
    # The pre-relocation spelling of the same tree. Kept beside the current one
    # rather than replaced: an install that has not yet run the relocating
    # upgrade still holds wiring there, and leftovers survive the relocation by
    # design, so removing this would hand that wiring back as source.
    ".github/doc-sync/",
    ".circleci/",
    ".buildkite/",
    ".gitlab/",
)
_WORKFLOW_NAMES = (
    ".gitlab-ci.yml",
    ".travis.yml",
    "azure-pipelines.yml",
    "appveyor.yml",
    "Jenkinsfile",
)
_HOOK_PREFIXES = (".git/hooks/", ".husky/", ".hooks/", ".claude/hooks/")
_HOOK_NAMES = (".pre-commit-config.yaml", ".pre-commit-config.yml")
_GIT_INTERNALS_PREFIX = ".git/"
_CREDENTIAL_NAMES = (
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".htpasswd",
    ".git-credentials",
    "credentials",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
)
_CREDENTIAL_SUFFIXES = (
    ".pem",
    ".key",
    ".crt",
    ".cer",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".kdbx",
    ".ppk",
    ".asc",
    ".gpg",
)
_EXECUTABLE_SUFFIXES = (
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".dll",
    ".dylib",
    ".so",
    ".bin",
    ".jar",
    ".class",
    ".pyc",
    ".wasm",
)
_SOURCE_SUFFIXES = (
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".svelte",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".java",
    ".kt",
    ".swift",
    ".scala",
    ".cs",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".m",
    ".mm",
    ".pl",
    ".lua",
    ".ex",
    ".exs",
    ".erl",
    ".hs",
    ".sql",
)
_CONFIGURATION_NAMES = (
    "Makefile",
    "GNUmakefile",
    "Dockerfile",
    "Containerfile",
    "Procfile",
    "Gemfile",
    "Rakefile",
    "Brewfile",
    "Vagrantfile",
    "justfile",
    "CMakeLists.txt",
    # `.txt` is a documentation suffix, so the well-known configuration files
    # that wear it are named here rather than caught by shape.
    "requirements.txt",
    "constraints.txt",
    "robots.txt",
)
_CONFIGURATION_SUFFIXES = (
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".plist",
    ".lock",
    ".env",
)
_DOCUMENTATION_SUFFIXES = (
    ".md",
    ".mdx",
    ".markdown",
    ".rst",
    ".txt",
    ".adoc",
    ".asciidoc",
    ".org",
)


def _folded(names):
    return tuple(name.casefold() for name in names)


# --------------------------------------------------------------------------
# Recognizing a file reference in prose
# --------------------------------------------------------------------------

# Every suffix this module knows, whatever class it sorts a path into: a
# reference to a file is a reference whether the file is documentation, source,
# configuration, or a key nobody should have named. Reusing the classifier's
# own tuples is the point — a second list would drift from the first, and the
# two answers would disagree about the same filename.
_FILE_SUFFIXES = (
    _DOCUMENTATION_SUFFIXES
    + _SOURCE_SUFFIXES
    + _CONFIGURATION_SUFFIXES
    + _EXECUTABLE_SUFFIXES
    + _CREDENTIAL_SUFFIXES
)
# The well-known files that wear no suffix at all.
_FILE_NAMES = (
    _CONFIGURATION_NAMES + _WORKFLOW_NAMES + _HOOK_NAMES + _CREDENTIAL_NAMES
)

# What a path is spelled with. Everything else — backticks, quotes, brackets,
# parentheses, whitespace, prose punctuation — separates one candidate from the
# next, so a path inside code fencing or a markdown link comes out whole.
_TOKEN_BOUNDARY = re.compile(r"[^A-Za-z0-9._\-/~+]+")


def _reference(token):
    """The file or directory `token` names, canonically spelled, or `None`.

    Two shapes count, and the pair is chosen to separate a file reference from
    the two things that look like one in ordinary prose:

    - a token with a separator, whose last component is either empty (a
      directory, `docs/plans/`) or carries a dot (a file, `docs/a.md`). The dot
      is what keeps `cron/cap/upgrade-cron` and `aj604/toolshed` — slash-joined
      prose, not paths — from reading as files.
    - a bare name with a known suffix, or a well-known suffixless filename.
      Requiring the suffix be one this module knows is what keeps
      `approval.Record.targets` and `e.g.` from reading as files.
    """
    token = token.strip().rstrip(".,")
    while token.startswith("./"):
        token = token[2:]
    if token in ("", ".", "..", "/"):
        return None

    if "/" in token:
        name = token.rpartition("/")[2]
        return token if (name == "" or "." in name) else None

    folded = token.casefold()
    if folded in _folded(_FILE_NAMES):
        return token
    suffix = next(
        (s for s in _folded(_FILE_SUFFIXES) if folded.endswith(s)), None
    )
    return token if suffix is not None and len(folded) > len(suffix) else None


def path_references(text):
    """Every file or directory `text` names, deduplicated and sorted.

    Pure, and generous where it is unsure: a caller asking this question is
    asking whether a sentence speaks about some file, and reading one token too
    many costs a second look, while reading one too few costs the answer.
    """
    if not isinstance(text, str):
        return ()
    found = {
        reference
        for token in _TOKEN_BOUNDARY.split(text)
        for reference in (_reference(token),)
        if reference is not None
    }
    return tuple(sorted(found))


def classify_target(path):
    """The target class a canonical repository-relative path belongs to.

    Pure, and ordered most-dangerous-first: a `.py` under `.doc-lifecycle/`
    is wiring before it is source, and `.env.production` is a credential before
    it is configuration. The last resort is `other`, never `documentation` —
    an unrecognized shape is not evidence of safety.

    Matching is case-folded throughout. The filesystems this runs on are
    case-insensitive, so `.GIT/hooks/pre-commit` is the hooks directory; a
    case-sensitive classifier would hand a capitalized spelling of the wiring
    back as documentation.
    """
    name = path.rpartition("/")[2].casefold()
    probe = f"/{path}".casefold()

    def under(prefixes):
        # Anchored at a component boundary and matched anywhere in the path, so
        # burying the wiring under `docs/` does not reclassify it.
        return any(f"/{prefix}" in probe for prefix in _folded(prefixes))

    if under(_WORKFLOW_PREFIXES) or name in _folded(_WORKFLOW_NAMES):
        return WORKFLOW
    if under(_HOOK_PREFIXES) or name in _folded(_HOOK_NAMES):
        return HOOK
    if under((_GIT_INTERNALS_PREFIX,)):
        return CONFIGURATION
    if (
        name in _folded(_CREDENTIAL_NAMES)
        or name == ".env"
        or name.startswith(".env.")
        or name.endswith(_folded(_CREDENTIAL_SUFFIXES))
    ):
        return CREDENTIAL
    if name.endswith(_folded(_EXECUTABLE_SUFFIXES)):
        return EXECUTABLE
    if name.endswith(_folded(_SOURCE_SUFFIXES)):
        return SOURCE
    if name in _folded(_CONFIGURATION_NAMES) or name.endswith(
        _folded(_CONFIGURATION_SUFFIXES)
    ):
        return CONFIGURATION
    if name.startswith("."):
        # A dotfile is configuration by convention; naming every one of them
        # would be a losing race.
        return CONFIGURATION
    if name.endswith(_folded(_DOCUMENTATION_SUFFIXES)):
        return DOCUMENTATION
    return OTHER


@dataclass(frozen=True)
class Authorization:
    """The verdict on one candidate path.

    Authorized carries the canonical path, the declared root that contains it,
    and its target class. Refused carries a `Problem` and no path — there is no
    partially trustworthy verdict a caller could use by mistake. The one field
    a refusal may still carry is `target_class`, and only for
    `path-forbidden-class`, where the class detected instead is the diagnosis.
    """

    path: Optional[str]
    root: Optional[str]
    target_class: Optional[str]
    problem: Optional[Problem]

    @property
    def authorized(self):
        return self.problem is None


def _refuse(candidate, code, message, location=None):
    if location is None:
        location = candidate if isinstance(candidate, str) else repr(candidate)
    return Authorization(
        path=None,
        root=None,
        target_class=None,
        problem=Problem(code=code, message=message, location=location),
    )


def _is_control(char):
    """Control and format characters, including the invisible reordering ones.

    U+202E and friends are category Cf: they render a filename as something
    other than what it is, which is the whole trick.
    """
    return unicodedata.category(char) in ("Cc", "Cf", "Cs", "Co", "Cn")


def _spelling_problem(path):
    """Why this spelling is not the one canonical form, as (code, message).

    Order is deliberate: the most specific diagnosis wins, so a tab is reported
    as a control character rather than as whitespace, and `..` as traversal
    rather than as a non-canonical component.
    """
    if not isinstance(path, str) or path.strip() == "":
        return (
            "path-empty",
            "a path is required — an empty or blank path names nothing to "
            "authorize",
        )
    bad = next((c for c in path if _is_control(c)), None)
    if bad is not None:
        return (
            "path-control-character",
            f"contains the control character U+{ord(bad):04X} — a path is plain "
            f"printable text, so it reads the same to a shell, to git, and to a "
            f"person",
        )
    if path.startswith("/") or path.startswith("~"):
        return (
            "path-absolute",
            "is absolute — name the document repository-relative, so the same "
            "record means the same file in every checkout",
        )
    if len(path) >= 2 and path[1] == ":" and path[0].isascii() and path[0].isalpha():
        return (
            "path-absolute",
            "carries a drive letter — name the document repository-relative, so "
            "the same record means the same file in every checkout",
        )
    if "\\" in path:
        return (
            "path-separator",
            "uses '\\' as a separator — repository paths use '/', and a "
            "backslash is a literal filename character on posix",
        )
    bad = next((c for c in path if c.isspace() or unicodedata.category(c) == "Zs"), None)
    if bad is not None:
        return (
            "path-whitespace",
            f"contains whitespace (U+{ord(bad):04X}) — whitespace makes a path "
            f"ambiguous to quote and impossible to distinguish by eye; rename "
            f"the file without it",
        )
    if unicodedata.normalize("NFC", path) != path:
        return (
            "path-unicode-non-canonical",
            "is not in Unicode NFC form — two spellings that normalize together "
            "would name one file under two identities; use the composed form",
        )
    components = path.split("/")
    if ".." in components:
        return (
            "path-traversal",
            "traverses with '..' — a repository-relative path names a location "
            "inside the repository and never walks out of one",
        )
    if any(c in ("", ".") for c in components):
        return (
            "path-non-canonical",
            "is not canonical — drop './', '//', and any trailing '/' so one "
            "file has exactly one spelling",
        )
    bad = next((c for c in components if c.startswith("-")), None)
    if bad is not None:
        return (
            "path-leading-dash",
            f"has a component starting with '-' ({bad!r}) — such a path is read "
            f"as an option by the tools that would act on it",
        )
    return None


def repository_relative_problem(path):
    """Why `path` is not a canonical repository-relative spelling, or None.

    Returns `(code, reason)`, where the reason completes the sentence
    "`<path>` ...", so a caller renders one message in its own vocabulary.

    Public because path safety has one owner. `authorize_path` answers the
    question an *applier* asks — may I write here — which is inseparable from
    the declared roots, the target class, and the state of the filesystem. A
    read-only audit asks the smaller question: is this string a path inside the
    repository at all? Both rest on this, so `..`, a leading `/`, a drive
    letter, a backslash separator, a control character, whitespace, a
    non-canonical `//`, and a leading-dash component mean the same thing to a
    record's evidence pointer as they do to an edit target — and cannot mean
    two things, because there is only this one list.

    Existence is deliberately not part of it: a pointer at a file a commit
    deleted is exactly what a STALE finding reports, and refusing it would
    refuse the finding.
    """
    return _spelling_problem(path)


def repository_read_problem(path, *, repo_root):
    """Why a repository-relative evidence path may not be read, or ``None``.

    Read authorization is intentionally owned beside write authorization.  A
    probe may inspect source, configuration, or documentation, so it does not
    apply the applier's target-class/root policy; it does apply the same path
    spelling, filesystem identity, and alias rules.  Missing leaves are safe
    to *ask about* (``path_exists`` needs that answer), while every existing
    component must be the canonically named, non-symlinked repository entry.
    """
    opened = open_repository_read(path, repo_root=repo_root)
    if isinstance(opened, Problem):
        return opened
    opened.close()
    return None


@dataclass
class RepositoryReadHandle:
    """One no-follow repository object held open across evidence reads."""

    path: str
    kind: str
    fd: Optional[int]

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read_bytes(self, limit=None):
        if self.kind != "file" or self.fd is None:
            raise OSError(f"{self.path!r} is not an open regular file")
        os.lseek(self.fd, 0, os.SEEK_SET)
        chunks, size = [], 0
        while True:
            chunk = os.read(self.fd, 64 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            size += len(chunk)
            if limit is not None and size > limit:
                raise ValueError(f"file exceeds {limit} byte probe bound")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _read_refusal(code, message, location):
    return Problem(code=code, message=message, location=location)


def open_repository_read(path, *, repo_root):
    """Open a canonical repository object without following any alias.

    Authorization and use are one operation: every component is opened
    relative to the already-authorized parent directory with ``O_NOFOLLOW``.
    The returned descriptor pins the inode that was authorized, so replacing
    the pathname afterward cannot redirect a probe or separate its digest from
    the bytes it examined. Missing paths return a ``kind='missing'`` handle,
    which lets ``path_exists`` answer safely without inventing an open target.
    """
    fault = _spelling_problem(path)
    if fault:
        code, reason = fault
        return _read_refusal(code, f"{path!r} {reason}", path)

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if not nofollow or not directory:
        return _read_refusal(
            "path-no-follow-unavailable",
            "this platform cannot open repository evidence without following aliases",
            path,
        )
    try:
        current_fd = os.open(
            repo_root, os.O_RDONLY | directory | nofollow | cloexec
        )
    except OSError as exc:
        code = "symlinked-path" if exc.errno == errno.ELOOP else "repo-root-missing"
        return _read_refusal(
            code, f"cannot open repository root {repo_root!r}: {exc}", repo_root,
        )

    components = path.split("/")
    try:
        for index, name in enumerate(components):
            so_far = "/".join(components[: index + 1])
            try:
                entries = os.listdir(current_fd)
            except OSError as exc:
                return _read_refusal(
                    "path-unreadable",
                    f"cannot list the directory holding {so_far!r}: {exc}",
                    so_far,
                )
            if name not in entries:
                folded = next(
                    (entry for entry in entries
                     if entry.casefold() == name.casefold()
                     or unicodedata.normalize("NFC", entry)
                     == unicodedata.normalize("NFC", name)),
                    None,
                )
                if folded is not None:
                    code = (
                        "path-case-mismatch"
                        if folded.casefold() == name.casefold()
                        else "path-unicode-collision"
                    )
                    return _read_refusal(
                        code,
                        f"{so_far!r} differs from existing entry {folded!r}",
                        so_far,
                    )
                return RepositoryReadHandle(path, "missing", None)

            is_leaf = index == len(components) - 1
            try:
                before = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
            except OSError as exc:
                return _read_refusal(
                    "path-unreadable", f"cannot inspect {so_far!r}: {exc}",
                    so_far,
                )
            if stat.S_ISLNK(before.st_mode):
                return _read_refusal(
                    "symlinked-path",
                    f"{so_far!r} is a symlink — evidence reads never follow aliases",
                    so_far,
                )
            if not is_leaf and not stat.S_ISDIR(before.st_mode):
                return _read_refusal(
                    "path-not-a-directory", f"{so_far!r} is not a directory",
                    so_far,
                )
            if is_leaf and not (
                    stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode)):
                return _read_refusal(
                    "path-special-file",
                    f"{path!r} is neither a regular file nor a directory",
                    path,
                )
            flags = os.O_RDONLY | nofollow | cloexec | nonblock
            if not is_leaf:
                flags |= directory
            try:
                next_fd = os.open(name, flags, dir_fd=current_fd)
            except OSError as exc:
                code = (
                    "symlinked-path" if exc.errno == errno.ELOOP
                    else "path-not-a-directory" if exc.errno == errno.ENOTDIR
                    else "path-unreadable"
                )
                return _read_refusal(
                    code, f"cannot open {so_far!r} without following aliases: {exc}",
                    so_far,
                )
            os.close(current_fd)
            current_fd = next_fd

        info = os.fstat(current_fd)
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink > 1:
                return _read_refusal(
                    "path-hardlinked",
                    f"{path!r} has {info.st_nlink} hard links",
                    path,
                )
            kind = "file"
        elif stat.S_ISDIR(info.st_mode):
            kind = "dir"
        else:
            return _read_refusal(
                "path-special-file",
                f"{path!r} is neither a regular file nor a directory",
                path,
            )
        handle = RepositoryReadHandle(path, kind, current_fd)
        current_fd = None
        return handle
    finally:
        if current_fd is not None:
            os.close(current_fd)


def write_target_problem(path):
    """Why `path` may not be named as a write target, or None.

    The spelling rules above, plus one location: a git directory is inside the
    repository and is spelled canonically, so nothing above refuses it — and a
    single write to `.git/hooks/post-commit` or `.git/config` is arbitrary
    code execution on the next commit. No document lives there, at any depth
    (a nested repository's is the same hazard), under any casing (a
    case-insensitive filesystem makes `.GIT` the same directory). One owner,
    shared by the approval set's record and scope paths and the edit plan's
    operation targets, so a spelling cannot mean one thing to the artifact
    that authorizes a write and another to the component that performs it.
    """
    problem = repository_relative_problem(path)
    if problem is not None:
        return problem[1]
    if any(c.casefold() == ".git" for c in path.split("/")):
        return (
            "is inside a git directory — the repository's own state is not "
            "documentation, and a write there executes on the next commit"
        )
    return None


def _roots_problem(roots):
    """Why the roots cannot decide containment, as (code, message, location)."""
    if not roots:
        return (
            "roots-undeclared",
            "no documentation roots are declared — with nothing declared "
            "eligible, no path can be authorized",
            None,
        )
    for root in roots:
        problem = _spelling_problem(root)
        if problem:
            return ("roots-invalid", f"declared root {root!r} {problem[1]}", root)
    return None


def _folded_entry(parent, name):
    """An entry in `parent` that the filesystem may confuse with `name`.

    Returns (code, the real entry name), or None. A path that names an existing
    file only up to case folding or Unicode normalization is refused rather than
    corrected: on a case-insensitive or normalization-insensitive volume it
    silently *is* that file, so accepting it would let one document hold two
    identities — and let a write aimed at a new file land on an existing one.
    """
    try:
        entries = os.listdir(parent)
    except (FileNotFoundError, NotADirectoryError):
        # Nothing there to collide with (yet): a create-document target under a
        # directory that does not exist is still authorizable.
        return None
    except OSError:
        # Anything else — a directory that cannot be listed — leaves the
        # question unanswered, and an unanswered safety question is a refusal.
        return ("path-unreadable", None)
    if name in entries:
        return None
    for entry in entries:
        if entry.casefold() == name.casefold():
            return ("path-case-mismatch", entry)
        if unicodedata.normalize("NFC", entry) == unicodedata.normalize("NFC", name):
            return ("path-unicode-collision", entry)
    return None


def _filesystem_problem(path, repo_root):
    """Why the path on disk is not what it says it is, as (code, msg, location).

    Walks the path one component at a time from the repository root. No
    component may be a symlink, so an alias cannot carry a documentation-looking
    path out of its root, and the walk stops at the first alias rather than
    resolving through it. Components that do not exist are fine — a
    create-document target is authorized before anything is written there.
    """
    components = path.split("/")
    current = repo_root
    for index, name in enumerate(components):
        parent, current = current, os.path.join(current, name)
        so_far = "/".join(components[: index + 1])

        folded = _folded_entry(parent, name)
        if folded:
            code, entry = folded
            if code == "path-unreadable":
                return (
                    code,
                    f"the directory holding {so_far!r} cannot be listed, so "
                    f"whether an existing entry collides with it is unknown — "
                    f"an unanswered safety question is a refusal",
                    so_far,
                )
            return (
                code,
                f"{so_far!r} differs from the existing entry {entry!r} only by "
                f"case or Unicode normalization — name the file as it is spelled "
                f"on disk, so one document has one identity",
                so_far,
            )
        if os.path.islink(current):
            return (
                "symlinked-path",
                f"{so_far!r} is a symlink — an authorized path names a real "
                f"location inside its root, and following the alias is exactly "
                f"how a documentation path escapes one",
                so_far,
            )
        is_leaf = index == len(components) - 1
        if not is_leaf and os.path.lexists(current) and not os.path.isdir(current):
            return (
                "path-not-a-file",
                f"{so_far!r} is a file, so nothing can live beneath it",
                so_far,
            )

    if not os.path.lexists(current):
        return None
    info = os.stat(current)
    if not stat.S_ISREG(info.st_mode):
        # A directory, a fifo, a device: authorization names one document, and
        # the applier's read-modify-write is only meaningful for a real file.
        return (
            "path-not-a-file",
            f"{path!r} is not a regular file — authorization names one document, "
            f"not a subtree or a special file",
            path,
        )
    if info.st_nlink > 1:
        # The alias a symlink check misses. Two names for one inode means a
        # write through the documentation-looking name lands in both places.
        return (
            "path-hardlinked",
            f"{path!r} has {info.st_nlink} hard links — it is one name for a "
            f"file that answers to another, so writing it writes somewhere this "
            f"authorization never examined",
            path,
        )
    if info.st_mode & 0o111:
        return (
            "path-executable-mode",
            f"{path!r} is marked executable — a document that runs is not a "
            f"document, whatever its suffix says",
            path,
        )
    return None


def _containing_root(path, roots):
    """The declared root holding `path` — the file itself, or a subtree."""
    for root in roots:
        if path == root or path.startswith(f"{root}/"):
            return root
    return None


def authorize_path(path, *, repo_root, roots, target_class=DOCUMENTATION):
    """Authorize one candidate path against the declared documentation roots.

    `roots` are repository-relative, each a subtree or a single file. The
    verdict is a deterministic function of the path, the roots, the target
    class, and the state of `repo_root` on disk.
    """
    fault = _spelling_problem(path)
    if fault:
        code, reason = fault
        return _refuse(path, code, f"{path!r} {reason}")

    fault = _roots_problem(roots)
    if fault:
        code, message, location = fault
        return _refuse(path, code, message, location)

    if target_class not in DECLARABLE_TARGET_CLASSES:
        return _refuse(
            path,
            "target-class-undeclarable",
            f"target class {target_class!r} cannot be declared — this engine "
            f"writes {list(DECLARABLE_TARGET_CLASSES)} and nothing else, so the "
            f"dangerous classes are not a default a caller can switch off",
        )

    if not os.path.isdir(repo_root):
        return _refuse(
            path,
            "repo-root-missing",
            f"the repository root {repo_root!r} is not a directory — without it "
            f"every path would look like an unwritten create-document target",
        )

    root = _containing_root(path, roots)
    if root is None:
        return _refuse(
            path,
            "path-outside-root",
            f"{path!r} is under none of the declared documentation roots "
            f"{list(roots)} — only documentation inside a declared root is "
            f"eligible",
        )

    if not os.path.lexists(os.path.join(repo_root, root)):
        # Containment is a claim about the repository, not about strings. With
        # the root absent, `CLAUDE.md/evil.md` reads as a create-document target
        # under a root that is really a file.
        return _refuse(
            path,
            "root-missing",
            f"declared root {root!r} is not in the repository — fix the roots "
            f"rather than authorizing paths under one that is not there",
            root,
        )

    # What the path *is* comes before what class its spelling suggests: for a
    # directory or an alias, "it is a directory" is the answer a caller can act
    # on, and "it classifies as other" is not.
    fault = _filesystem_problem(path, repo_root)
    if fault:
        code, message, location = fault
        return _refuse(path, code, message, location)

    actual_class = classify_target(path)
    if actual_class != target_class:
        refusal = _refuse(
            path,
            "path-forbidden-class",
            f"{path!r} is a {actual_class} path, not {target_class} — living "
            f"under documentation root {root!r} does not make it eligible",
        )
        # The detected class travels with the refusal: a caller reporting the
        # problem should not have to re-derive what it was refused as.
        return replace(refusal, target_class=actual_class)

    return Authorization(
        path=path, root=root, target_class=actual_class, problem=None
    )
