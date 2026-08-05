#!/usr/bin/env python3
"""The audit lanes' repository-integrity gate (aj604/toolshed#185).

Both read-only audit lanes assemble their report *from the checkout* — the
drift lane's verdicts cite repository paths, the bloat lane's chunks quote
documents — so every one of those citations is only worth what the checkout
was worth when it was read. Models in these lanes hold no repository
credential and no write-capable permission, but "cannot" is a capability
claim about an action implementation, not a fact this run observed. This gate
observes it: before a lane assembles anything, the checkout must still be the
declared base commit, with no staged change, no tracked modification, and no
untracked file beyond the artifacts the lane itself declared.

The bloat lane carried this as inline shell first (#144); the drift lane needs
exactly the same contract, and a second copy of a security gate is a second
thing to keep true. One script owns it for both lanes, invoked from the
release-pinned marketplace clone under RUNNER_TEMP rather than from the
checkout it is judging — the same reason bloat-cadence.py runs from there.

Never repairs. A `git reset`/`restore`/`clean` here would erase the very
evidence the refusal rests on and let a mutated run continue as if it had been
clean; a refusal is terminal, and the lane publishes no report at all.

Usage:
    check-repo-integrity.py --repo PATH --expected-head SHA
                            [--allow REPO_RELATIVE_PATH ...] --out FILE

`--allow` names an artifact the lane *declared* it would write into the work
tree — the drift lane's `verdicts.json`, which the model is told by name to
write there (detecting-doc-drift/SKILL.md documents that carve-out). It
exempts that path only as an untracked *addition*: an allowed name that turns
up as a tracked modification or a staged change is repository mutation
whatever it is called, and is still refused. A lane that declares nothing
passes no --allow and every added file fails the gate.

The verdict is written to --out as
`{"status": "verified"|"refused", "expected_head", "head", "allowed",
"problems": [{"code", "message", "location"}]}` — exhaustively, naming every
surface that moved rather than the first. render-audit-summary.py renders that
file, so the refusal states itself on the run surface instead of surfacing as
a bare red step.

Exit status:
    0  verified — the checkout is still the declared base commit, untouched
    1  unverifiable — the check itself could not run (no git, no repository);
       a lane that cannot confirm its evidence must not publish a report
    2  refused — at least one integrity problem, each named in --out
"""

import argparse
import json
import subprocess
import sys


HEAD_MOVED = "evidence-integrity-head-moved"
TRACKED_MODIFIED = "evidence-integrity-tracked-modified"
STAGED_CHANGE = "evidence-integrity-staged-change"
UNTRACKED_ADDED = "evidence-integrity-untracked-added"
UNVERIFIABLE = "evidence-integrity-unverifiable"


class Unverifiable(Exception):
    """The gate itself could not run. Exit 1."""


def _git(repo, *args):
    """One read-only git plumbing call. Never mutates, never repairs."""
    try:
        result = subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True)
    except OSError as e:
        raise Unverifiable(f"could not run git in {repo!r}: {e}")
    if result.returncode != 0:
        raise Unverifiable(
            f"`git {' '.join(args)}` exited {result.returncode} in {repo!r}: "
            f"{result.stderr.strip()}")
    return result.stdout


def _paths(output):
    """NUL-separated plumbing output as a list of repository-relative paths."""
    return [entry for entry in output.split("\0") if entry]


def check(repo, expected_head, allowed):
    """Every integrity problem this checkout has, in a stable order."""
    problems = []
    head = _git(repo, "rev-parse", "HEAD").strip()
    if head != expected_head:
        problems.append({
            "code": HEAD_MOVED,
            "message": (
                f"the checkout is no longer the declared base commit — the "
                f"lane planned against {expected_head}, and evidence read "
                f"after this point describes a different tree"),
            "location": head,
        })

    # Tracked content, in the work tree and in the index. An allowed artifact
    # name buys no exemption here: the lane declared it would *add* a file,
    # never that it would edit repository content that already exists.
    for path in _paths(_git(repo, "diff", "--name-only", "-z", "--")):
        problems.append({
            "code": TRACKED_MODIFIED,
            "message": (
                "a tracked file changed during the run — evidence read from "
                "it cannot be attributed to the declared base commit"),
            "location": path,
        })
    for path in _paths(
            _git(repo, "diff", "--cached", "--name-only", "-z", "HEAD", "--")):
        problems.append({
            "code": STAGED_CHANGE,
            "message": (
                "a staged change appeared during the run — a read-only lane "
                "stages nothing"),
            "location": path,
        })

    # `--others` without `--exclude-standard`, deliberately: a mutation hidden
    # behind a .gitignore rule is still a mutation of this checkout.
    for path in _paths(_git(repo, "ls-files", "--others", "-z")):
        if path in allowed:
            continue
        problems.append({
            "code": UNTRACKED_ADDED,
            "message": (
                "a file appeared in the work tree that this lane never "
                f"declared — the declared artifacts are {sorted(allowed)}"),
            "location": path,
        })
    return head, problems


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--allow", action="append", default=[],
        help="repository-relative path this lane declared it would write")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    allowed = set(args.allow)
    try:
        head, problems = check(args.repo, args.expected_head, allowed)
    except Unverifiable as e:
        head, problems = None, [{
            "code": UNVERIFIABLE,
            "message": f"the repository-integrity gate could not run: {e}",
            "location": args.repo,
        }]
        status = 1
    else:
        status = 2 if problems else 0

    verdict = {
        "status": "verified" if not problems else "refused",
        "expected_head": args.expected_head,
        "head": head,
        "allowed": sorted(allowed),
        "problems": problems,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(verdict, f, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as e:
        # The verdict still has to reach the log even when it cannot reach a
        # file; the exit status below is unchanged either way.
        print(f"::error::could not write {args.out}: {e}", file=sys.stderr)

    for problem in problems:
        print(f"::error::{problem['code']}: {problem['message']} "
              f"({problem['location']})")
    if not problems:
        print(f"repository integrity verified at {head}")
    return status


if __name__ == "__main__":
    sys.exit(main())
