"""The repository's own identity and position — the half of lineage git owns.

A report claims to describe one repository at one commit. Checking that claim
needs both facts from the repository itself, and needs them to fail loudly:
a run that cannot read the repository state must not certify a report as fresh.
"""

import os
import subprocess

from .results import Problem

SCHEMES = ("https://", "http://", "ssh://", "git://", "git+ssh://")


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
    """Run git in `repo_root`. Returns (stdout, error detail or None)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True, text=True,
        )
    except OSError as exc:
        return None, f"git is not available ({exc.strerror})"
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        return None, detail[0] if detail else f"git {args[0]} failed"
    return result.stdout.strip(), None


def normalize_remote(url):
    """A remote URL reduced to host and path, so spellings of one repository
    agree: scheme, credentials, `.git`, and trailing `/` are not identity."""
    value = url.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    for scheme in SCHEMES:
        if value.lower().startswith(scheme):
            value = value[len(scheme):]
            break
    head = value.split("/", 1)[0]
    if "@" in head:
        value = value.split("@", 1)[1]
        head = value.split("/", 1)[0]
    if ":" in head:
        host, _, rest = value.partition(":")
        value = f"{host}/{rest}"
    return value.lower()


def state(repo_root):
    """(`{repository, base_commit}`, problems) for the repository at `repo_root`.

    Identity prefers the declared origin remote — stable across clones and
    shallow checkouts alike — and falls back to the root commit, which a
    remoteless repository (a fixture, a fresh `git init`) still has. A
    repository that gains a remote therefore changes identity, which is the
    honest answer: reports pinned to the old identity read as stale.
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
