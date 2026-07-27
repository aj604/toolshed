"""The repository's own identity and position — the half of lineage git owns.

A report claims to describe one repository at one commit. Checking that claim
needs both facts from the repository itself, and needs them to fail loudly:
a run that cannot read the repository state must not certify a report as fresh.
"""

import os
import re
import subprocess

from .results import Problem

SCHEMES = ("https://", "http://", "ssh://", "git://", "git+ssh://", "file://")

# A fully resolved git object id — what `resolve_commit` returns, sha-1 or
# sha-256. Anything a caller has not put through that gate is not one.
OBJECT_ID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")

# Environment variables that redirect git at a different repository than the one
# named on the command line. Scrubbed, not trusted: a composite action or an
# earlier workflow step that exports `GIT_DIR` would otherwise make the
# freshness check answer about someone else's tree, silently, and in the
# direction of certifying rather than failing.
REDIRECTING_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_NAMESPACE",
)

# A local repository read is milliseconds. Anything near this is a hung git —
# a pager, a credential prompt, a network remote — and hanging a CI job is a
# worse answer than a typed problem.
TIMEOUT_SECONDS = 30


def _problem(repo_root, detail):
    return Problem(
        code="repository-state-unavailable",
        message=(
            f"cannot read the current state of {repo_root}: {detail} — a report's "
            f"freshness is a comparison against the repository, so it cannot be "
            f"established here"
        ),
        location=repo_root,
    )


def _run(repo_root, *args, raw=False):
    """Run git in `repo_root`. Returns (exit code, stdout, detail).

    The exit code is `None` exactly when git could not be run at all, which is
    a different answer from git running and saying no — `tracking` below has to
    tell those apart, because "this is not a repository" is a fact it may act
    on and "git is missing" is a question it must refuse to answer.

    The repository is the one named here and nowhere else: the environment is
    scrubbed of every variable that could point git at another tree, so the
    `--show-toplevel` guard below cannot be walked around.

    Output is trimmed, because a one-value read wants the value and not the
    newline git ends it with. `raw` is for a *listing*, where the whole listing
    arrives as one string and trimming it would eat leading whitespace from the
    first path in it — a path git is perfectly willing to track.
    """
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTING_VARS}
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True, text=True, env=env, timeout=TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return None, "", f"git is not available ({exc.strerror})"
    except subprocess.TimeoutExpired:
        return None, "", f"git {args[0]} did not finish in {TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        return result.returncode, "", detail[0] if detail else f"git {args[0]} failed"
    return 0, (result.stdout if raw else result.stdout.strip()), None


def _git(repo_root, *args, raw=False):
    """Run git in `repo_root`. Returns (stdout, error detail or None)."""
    code, out, detail = _run(repo_root, *args, raw=raw)
    return (out, None) if code == 0 else (None, detail)


def normalize_remote(url):
    """A remote URL reduced to host and path, so spellings of one repository
    agree: scheme, credentials, port, `.git`, and trailing `/` are not identity.

    Only the host is case-folded. Hosts are case-insensitive; repository paths
    are not on every forge, so lowercasing the whole URL would merge
    `Team/Repo` with `team/repo` into one identity.
    """
    value = url.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]

    scheme = ""
    for candidate in SCHEMES:
        if value.lower().startswith(candidate):
            scheme, value = candidate, value[len(candidate):]
            break

    if scheme:
        authority, _, path = value.partition("/")
    else:
        # scp-like `git@host:path/to/repo`, where the colon is the separator.
        authority, separator, path = value.partition(":")
        if not separator:
            authority, _, path = value.partition("/")

    if "@" in authority:
        authority = authority.split("@", 1)[1]
    if scheme:
        # `host:port` — a route to the repository, not the repository. Only
        # stripped under a scheme, where a colon cannot be a path separator.
        host, colon, port = authority.rpartition(":")
        if colon and port.isdigit():
            authority = host

    path = path.strip("/")
    return f"{authority.lower()}/{path}" if path else authority.lower()


def lineage(repo_root):
    """(`{repository, base_commit}`, problems) for the repository at `repo_root`.

    The half of a report's lineage git owns. Named for what it produces, not
    "state", which the result model already owns.

    Identity prefers the declared origin remote — stable across clones and
    shallow checkouts alike — and falls back to the root commit, which a
    remoteless repository (a fixture, a fresh `git init`) still has. A
    repository that gains a remote therefore changes identity, which is the
    honest answer: reports pinned to the old identity read as stale.

    The fallback is only stable where history is: a `--depth 1` clone reports
    its shallow boundary as the root commit, so a remoteless repository checked
    out shallowly reads as a different repository and can never validate a
    report as fresh. The fail direction is safe (stale, not certified), but a
    repository audited in CI wants either a remote or full history.
    """
    top, detail = _git(repo_root, "rev-parse", "--show-toplevel")
    if detail is not None:
        return {}, (_problem(repo_root, detail),)
    if os.path.realpath(top) != os.path.realpath(repo_root):
        # An enclosing repository is a different repository. Reading its HEAD
        # would silently answer about the wrong tree.
        return {}, (_problem(
            repo_root, f"it is not the root of a git repository (that is {top})"
        ),)

    head, detail = _git(repo_root, "rev-parse", "HEAD")
    if detail is not None:
        return {}, (_problem(repo_root, detail),)

    origin, _ = _git(repo_root, "config", "--get", "remote.origin.url")
    if origin:
        identity = f"origin:{normalize_remote(origin)}"
    else:
        roots, detail = _git(repo_root, "rev-list", "--max-parents=0", "HEAD")
        if detail is not None:
            return {}, (_problem(repo_root, detail),)
        identity = f"root-commit:{','.join(sorted(roots.split()))}"

    return {"repository": identity, "base_commit": head}, ()


def resolve_commit(repo_root, revision):
    """(full commit id, None) for `revision`, or (None, problem).

    A baseline a diff-scoped audit was handed must exist in *this* repository
    before the audit declares a scope derived from it — a scope derived from a
    revision nobody has is not a scope.
    """
    if not isinstance(revision, str):
        return None, _problem(repo_root, f"{revision!r} is not a revision")
    resolved, detail = _git(
        repo_root, "rev-parse", "--verify", "--end-of-options",
        f"{revision}^{{commit}}"
    )
    if detail is not None:
        return None, _problem(repo_root, f"{revision} is not a commit in it")
    return resolved, None


def changed_paths(repo_root, since):
    """(paths changed between `since` and HEAD, None), or (None, problem).

    Repository-relative, sorted, including deleted paths — a document citing a
    file that a commit removed is exactly the case a diff-scoped audit must
    still reach.

    `since` must already be a resolved object id, because it reaches git in
    flag position: an unresolved revision spelled `--output=PWNED` is read by
    `git diff` as an option, and this read-only module would write a file. The
    gate is the check, not the separators — a trailing `--` only says where the
    pathspecs start, and by then the option has already been parsed. Put a
    revision through `resolve_commit` first; that is what makes it one.
    """
    if not (isinstance(since, str) and OBJECT_ID.match(since)):
        return None, _problem(
            repo_root,
            f"{since!r} is not a resolved commit id — a diff baseline reaches "
            f"git where an option would, so it must come from resolve_commit "
            f"rather than from whatever a caller was handed",
        )
    out, detail = _git(repo_root, "diff", "--name-only", "--no-renames",
                       "--end-of-options", f"{since}..HEAD", "--")
    if detail is not None:
        return None, _problem(repo_root, detail)
    return tuple(sorted(line for line in out.splitlines() if line.strip())), None


# What git would do with a file written at a given path. Closed, because the
# caller acts on the answer: `trackable` is the dangerous one — nothing keeps
# the file yet, and the next `git add -A` would.
TRACKING_OUTSIDE = "outside-repository"
TRACKING_TRACKED = "tracked"
TRACKING_IGNORED = "ignored"
TRACKING_TRACKABLE = "trackable"


def tracking(path):
    """Whether git would keep a file written at `path`. Returns (state, problem).

    The question an untracked artifact has to ask before it is written down.
    Answered from the repository that would actually hold the file — found from
    the path itself, not from a root a caller supplied — because an artifact
    written two directories up is in whatever repository is there.

    Fails closed: if git cannot be run, or cannot answer, the state is `None`
    and a problem says why. An unanswered question about whether something
    would be committed is not a licence to write it.
    """
    target = os.path.realpath(os.path.abspath(path))
    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        return None, Problem(
            code="path-unwritable",
            message=(
                f"the directory that would hold {path} does not exist, so "
                f"whether git would track a file written there is unknown"
            ),
            location=path,
        )

    code, top, detail = _run(parent, "rev-parse", "--show-toplevel")
    if code is None:
        return None, _problem(parent, detail)
    if code != 0:
        # git ran and said this is not a repository: nothing here can track it.
        return TRACKING_OUTSIDE, None

    top = os.path.realpath(top)
    relative = os.path.relpath(target, top)
    for args, state in (
        (("ls-files", "--error-unmatch", "--", relative), TRACKING_TRACKED),
        (("check-ignore", "-q", "--", relative), TRACKING_IGNORED),
    ):
        code, _, detail = _run(top, *args)
        if code is None:
            return None, _problem(top, detail)
        if code == 0:
            return state, None
        if code > 1:
            # 1 is the honest "no" both commands give; anything above it is git
            # failing to answer, and a refusal is the only safe reading.
            return None, _problem(top, detail)
    return TRACKING_TRACKABLE, None


def tracked_files(repo_root):
    """(every path the repository tracks under `repo_root`, None), or (None, problem).

    Sorted and repository-relative, the same spelling every other path in an
    artifact carries. `-z` and a raw read, because git renders an unusual path
    in a quoted, escaped form by default and trimming the listing would eat a
    leading space off the first path in it — either way a caller comparing the
    result against a real path concludes the file is not tracked.

    Tracked, not present: a generated or ignored markdown file is not something
    the repository claims, so counting it would overstate what any lane covered.

    Failing is a distinct answer from an empty listing, and callers must keep it
    that way — reading "nothing is tracked" off a directory that is not a
    repository reports a corpus as fully covered exactly when it could not be
    checked. `repo_root` inside a larger repository lists what that repository
    tracks beneath it, which is the same question asked of a smaller tree.
    """
    out, detail = _git(repo_root, "ls-files", "-z", "--", raw=True)
    if detail is not None:
        return None, Problem(
            code="repository-listing-unavailable",
            message=(
                f"cannot list the files tracked in {repo_root}: {detail} — what "
                f"a repository holds cannot be established here"
            ),
            location=repo_root,
        )
    return tuple(sorted(p for p in out.split("\0") if p)), None


def worktree_changes(repo_root):
    """(every path the working tree or index differs from HEAD at, None).

    Or (None, problem) when the state cannot be read — and a caller comparing
    a diff against an allowed scope must fail closed on that, because "the
    diff could not be read" and "the diff is empty" certify opposite things.

    Untracked files are included, one path each (`--untracked-files=all`):
    a stray file nothing accounts for is exactly the change a whole-diff
    confinement check exists to catch. Ignored files are not changes — an
    artifact written to a git-ignored path is deliberately invisible to the
    change it authorizes. `--no-renames`, so every entry is one path and the
    parse cannot mistake a rename's second name for a status. `-z` and a raw
    read, for the same unusual-path reasons as `tracked_files`.
    """
    out, detail = _git(
        repo_root, "status", "--porcelain=v1", "-z",
        "--untracked-files=all", "--no-renames", raw=True,
    )
    if detail is not None:
        return None, _problem(repo_root, detail)
    return tuple(sorted({e[3:] for e in out.split("\0") if len(e) > 3})), None


def last_change(repo_root, path):
    """((committer date `YYYY-MM-DD`, commit id), None) for `path`'s last commit.

    `(None, None)` when the path has no history at all — untracked, or never
    committed — which is a different answer from a failure to look, and the
    caller must be able to tell those apart. Dates are committer dates, whole
    days, because an as-of anchor is written to the day.
    """
    out, detail = _git(repo_root, "log", "-1", "--format=%cs %H", "--", path)
    if detail is not None:
        return None, _problem(repo_root, detail)
    if not out:
        return None, None
    date, _, commit = out.partition(" ")
    return (date, commit), None
