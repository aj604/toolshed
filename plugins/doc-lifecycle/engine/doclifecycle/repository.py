"""The repository's own identity and position — the half of lineage git owns.

A report claims to describe one repository at one commit. Checking that claim
needs both facts from the repository itself, and needs them to fail loudly:
a run that cannot read the repository state must not certify a report as fresh.
"""

import os
import subprocess

from .results import Problem

SCHEMES = ("https://", "http://", "ssh://", "git://", "git+ssh://", "file://")

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


def _git(repo_root, *args):
    """Run git in `repo_root`. Returns (stdout, error detail or None).

    The repository is the one named here and nowhere else: the environment is
    scrubbed of every variable that could point git at another tree, so the
    `--show-toplevel` guard below cannot be walked around.
    """
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTING_VARS}
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True, text=True, env=env, timeout=TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return None, f"git is not available ({exc.strerror})"
    except subprocess.TimeoutExpired:
        return None, f"git {args[0]} did not finish in {TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        return None, detail[0] if detail else f"git {args[0]} failed"
    return result.stdout.strip(), None


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
    resolved, detail = _git(
        repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}"
    )
    if detail is not None:
        return None, _problem(repo_root, f"{revision} is not a commit in it")
    return resolved, None


def changed_paths(repo_root, since):
    """(paths changed between `since` and HEAD, None), or (None, problem).

    Repository-relative, sorted, including deleted paths — a document citing a
    file that a commit removed is exactly the case a diff-scoped audit must
    still reach.
    """
    out, detail = _git(repo_root, "diff", "--name-only", "--no-renames",
                       f"{since}..HEAD")
    if detail is not None:
        return None, _problem(repo_root, detail)
    return tuple(sorted(line for line in out.splitlines() if line.strip())), None


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
