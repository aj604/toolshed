#!/usr/bin/env python3
"""Reconstruct enhancement-lane state from a repo's branches and pull requests.

The orchestrator's memory of an unattended run is not evidence. This reads the
remote instead: every branch named `lane/<slug>/r<n>`, the pull request opened
from it, and whether each round is really based on the round below it.

Use it to resume after a compaction, and to check a claim before reporting it.

Usage:
    lanes.py --repo OWNER/REPO
    lanes.py --repo OWNER/REPO --lane cli-ergonomics
    lanes.py --repo OWNER/REPO --json          # machine-readable

Exit codes:
    0  state read successfully (check `problems` in the output)
    1  bad arguments or a `gh` call failed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

BRANCH_RE = re.compile(r"^lane/(?P<slug>[^/]+)/r(?P<round>\d+)$")


def gh(args: list[str]) -> Any:
    """Run a `gh` command and parse its stdout as JSON."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"gh {' '.join(args)}\n  failed: {proc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def default_branch(repo: str) -> str:
    proc = subprocess.run(
        ["gh", "repo", "view", repo, "--json", "defaultBranchRef",
         "--jq", ".defaultBranchRef.name"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"could not read default branch: {proc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout.strip()


def remote_branches(repo: str) -> list[str]:
    """Every lane branch on the remote, including ones with no PR yet.

    `--paginate` with `--jq` emits one result per page, so the output is a
    stream of lines rather than a single JSON document — parse it as lines.
    """
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/branches", "--paginate", "--jq", ".[].name"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"could not list branches: {proc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return [b for b in proc.stdout.split("\n") if BRANCH_RE.match(b.strip())]


def pull_requests(repo: str) -> list[dict]:
    """Open and merged PRs, keyed later by head branch."""
    return gh(["pr", "list", "--repo", repo, "--state", "all", "--limit", "200",
               "--json", ("number,title,headRefName,baseRefName,isDraft,state,"
                          "url,mergedAt,reviewDecision")]) or []


def build(repo: str, only_lane: str | None) -> dict:
    base_default = default_branch(repo)
    prs_by_head: dict[str, dict] = {}
    for pr in pull_requests(repo):
        head = pr["headRefName"]
        # A branch can carry more than one PR over its life; the open one wins,
        # otherwise the most recently numbered.
        prior = prs_by_head.get(head)
        if prior is None or (pr["state"] == "OPEN" and prior["state"] != "OPEN") \
                or (pr["state"] == prior["state"] and pr["number"] > prior["number"]):
            prs_by_head[head] = pr

    branches = set(remote_branches(repo)) | set(prs_by_head)
    lanes: dict[str, list[dict]] = {}
    for branch in branches:
        m = BRANCH_RE.match(branch)
        if not m:
            continue
        slug = m.group("slug")
        if only_lane and slug != only_lane:
            continue
        pr = prs_by_head.get(branch)
        lanes.setdefault(slug, []).append({
            "round": int(m.group("round")),
            "branch": branch,
            "pushed": branch in branches,
            "pr": None if pr is None else {
                "number": pr["number"],
                "url": pr["url"],
                "title": pr["title"],
                "base": pr["baseRefName"],
                "draft": pr["isDraft"],
                "state": pr["state"],
                "merged": bool(pr["mergedAt"]),
                "review": pr["reviewDecision"],
            },
        })

    problems: list[str] = []
    out: dict[str, Any] = {"repo": repo, "default_branch": base_default, "lanes": {}}

    for slug, rounds in sorted(lanes.items()):
        rounds.sort(key=lambda r: r["round"])
        numbers = [r["round"] for r in rounds]
        for r in rounds:
            expected = base_default if r["round"] == 1 else f"lane/{slug}/r{r['round'] - 1}"
            r["expected_base"] = expected
            pr = r["pr"]
            if pr is None:
                r["status"] = "branch pushed, no PR"
                problems.append(
                    f"{slug} r{r['round']}: branch exists but no pull request — "
                    "the implementer pushed and died, or never opened one")
                continue
            if pr["base"] != expected:
                problems.append(
                    f"{slug} r{r['round']}: PR #{pr['number']} is based on "
                    f"{pr['base']}, expected {expected} — the stack is broken and "
                    f"this diff contains earlier rounds")
            if pr["merged"]:
                r["status"] = "merged"
            elif pr["state"] != "OPEN":
                r["status"] = "closed unmerged"
                problems.append(
                    f"{slug} r{r['round']}: PR #{pr['number']} was closed without "
                    "merging — anything stacked on it is orphaned")
            else:
                r["status"] = "draft" if pr["draft"] else "ready for review"

        missing = [n for n in range(1, max(numbers) + 1) if n not in numbers]
        if missing:
            problems.append(
                f"{slug}: round(s) {', '.join(map(str, missing))} missing while "
                f"r{max(numbers)} exists — a round never pushed, or the branch was deleted")

        tip = rounds[-1]
        out["lanes"][slug] = {
            "rounds": rounds,
            "depth": max(numbers),
            "tip_branch": tip["branch"],
            "next_round": max(numbers) + 1,
            "next_base": tip["branch"],
        }

    out["problems"] = problems
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, metavar="OWNER/REPO")
    ap.add_argument("--lane", help="restrict to one lane slug")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    result = build(args.repo, args.lane)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["lanes"]:
        print(f"{args.repo}: no lane/<slug>/r<n> branches found. "
              "Nothing has been dispatched, or the branch convention wasn't followed.")
        return 0

    print(f"{args.repo}  (default branch: {result['default_branch']})\n")
    for slug, lane in result["lanes"].items():
        print(f"LANE {slug}  — depth {lane['depth']}")
        for r in lane["rounds"]:
            pr = r["pr"]
            if pr is None:
                print(f"  r{r['round']}  {r['branch']}  — no PR")
                continue
            flag = "" if pr["base"] == r["expected_base"] else \
                f"  !! base={pr['base']} expected {r['expected_base']}"
            print(f"  r{r['round']}  #{pr['number']:<5} {r['status']:<17} "
                  f"<- {pr['base']}{flag}")
            print(f"        {pr['title']}")
        print(f"  next: dispatch r{lane['next_round']} off {lane['next_base']}\n")

    if result["problems"]:
        print("PROBLEMS")
        for p in result["problems"]:
            print(f"  ! {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
