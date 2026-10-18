#!/usr/bin/env python3
"""Query a GitHub issue dependency graph and report which issues are ready to dispatch.

Reads the graph through GitHub's *native* issue dependencies
(`issue_dependencies_summary.blocked_by` and the `dependencies/blocked_by`
endpoint), so what this prints matches what a human sees in the GitHub UI.
The summary count is cross-checked against the live edge states (the summary
lags after a blocker closes; the edges win, with a warning), and issues
carrying a human-gate label (default `needs-human`, see --human-label) are
reported as 'ready -- human' rather than dispatchable.

Usage:
    frontier.py --repo OWNER/REPO --parent 42
    frontier.py --repo OWNER/REPO --label 'epic:billing'
    frontier.py --repo OWNER/REPO --issues 10,11,12,13
    frontier.py --repo OWNER/REPO --parent 42 --json      # machine-readable

Exit codes:
    0  graph read successfully (check `blocked_reason` / `cycles` in the output)
    1  bad arguments or a `gh` call failed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any


def gh(args: list[str]) -> Any:
    """Run a `gh` command and parse its stdout as JSON."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        print(
            f"gh {' '.join(args)}\n  failed: {proc.stderr.strip()}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def is_issue(item: dict) -> bool:
    """GitHub's issues API returns PRs too; they carry a `pull_request` key."""
    return "pull_request" not in item


def collect_scope(repo: str, args: argparse.Namespace) -> list[dict]:
    """Resolve the set of issues the run is responsible for."""
    if args.parent:
        items = gh(
            ["api", f"repos/{repo}/issues/{args.parent}/sub_issues", "--paginate"]
        ) or []
    elif args.label:
        items = gh(
            [
                "api",
                "--paginate",
                f"repos/{repo}/issues?state=all&per_page=100&labels={args.label}",
            ]
        ) or []
    elif args.milestone:
        items = gh(
            [
                "api",
                "--paginate",
                f"repos/{repo}/issues?state=all&per_page=100&milestone={args.milestone}",
            ]
        ) or []
    else:
        numbers = [n.strip() for n in args.issues.split(",") if n.strip()]
        items = [gh(["api", f"repos/{repo}/issues/{n}"]) for n in numbers]
    return expand_splits(repo, [i for i in items if i and is_issue(i)])


def has_children(issue: dict) -> bool:
    return bool((issue.get("sub_issues_summary") or {}).get("total"))


def expand_splits(repo: str, items: list[dict]) -> list[dict]:
    """Pull every in-scope issue's own sub-issues into scope, recursively.

    An oversized issue gets split into sub-issues mid-run. Its children are the
    real work, and without this they would never appear in the frontier, while
    the parent would keep showing as a dispatchable leaf.
    """
    seen = {i["number"] for i in items}
    queue = [i for i in items if has_children(i)]
    while queue:
        parent = queue.pop()
        kids = gh(["api", f"repos/{repo}/issues/{parent['number']}/sub_issues", "--paginate"]) or []
        for kid in kids:
            if is_issue(kid) and kid["number"] not in seen:
                seen.add(kid["number"])
                items.append(kid)
                if has_children(kid):
                    queue.append(kid)
    return items


def blockers_of(repo: str, number: int) -> list[dict]:
    """Native blocked-by edges for one issue. Empty list when the API 404s.

    A 404 here means dependencies are unavailable on this repo (older GHES,
    or the feature is off) rather than "no blockers" -- the caller distinguishes
    the two via the summary counts, which are absent in that case.
    """
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{number}/dependencies/blocked_by"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    out = proc.stdout.strip()
    return json.loads(out) if out else []


PROSE_BLOCKER = re.compile(r"blocked\s+by[:\s]+((?:[,\s]*#\d+)+)", re.IGNORECASE)


def prose_blockers(body: str | None) -> list[int]:
    """`Blocked by: #3, #4` written in the body -- the pre-native-deps fallback.

    Reported but never acted on: the run consumes native edges only, so a prose
    blocker with no matching native edge is a graph defect worth surfacing.
    """
    if not body:
        return []
    match = PROSE_BLOCKER.search(body)
    if not match:
        return []
    return [int(n) for n in re.findall(r"#(\d+)", match.group(1))]


def find_cycles(edges: dict[int, list[int]]) -> list[list[int]]:
    """Every dependency cycle among in-scope issues, as node lists."""
    cycles: list[list[int]] = []
    seen: set[int] = set()
    stack: list[int] = []
    on_stack: set[int] = set()

    def walk(node: int) -> None:
        seen.add(node)
        stack.append(node)
        on_stack.add(node)
        for nxt in edges.get(node, []):
            if nxt in on_stack:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in seen:
                walk(nxt)
        stack.pop()
        on_stack.discard(node)

    for node in edges:
        if node not in seen:
            walk(node)
    return cycles


def linked_prs(repo: str) -> dict[int, list[dict]]:
    """Map issue number -> PRs that reference it via a closing keyword.

    One `gh pr list` call rather than a search per issue; graphs this size never
    justify the extra round trips.
    """
    prs = gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,title,body,state,isDraft,headRefName,baseRefName,mergedAt,url",
        ]
    ) or []
    closes = re.compile(
        r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE
    )
    mapping: dict[int, list[dict]] = {}
    for pr in prs:
        for num in {int(n) for n in closes.findall(pr.get("body") or "")}:
            mapping.setdefault(num, []).append(pr)
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--parent", type=int, help="parent issue; scope = its sub-issues")
    source.add_argument("--label", help="scope = issues carrying this label")
    source.add_argument("--milestone", help="scope = issues in this milestone (number)")
    source.add_argument("--issues", help="scope = this comma-separated list")
    parser.add_argument("--json", action="store_true", help="emit JSON, not a report")
    parser.add_argument(
        "--human-label",
        dest="human_labels",
        action="append",
        help="label marking an issue as human-gated: never dispatchable, reported "
        "as 'ready -- human' instead (repeatable; default: needs-human)",
    )
    args = parser.parse_args()
    if not args.human_labels:
        args.human_labels = ["needs-human"]

    scope = collect_scope(args.repo, args)
    if not scope:
        print("No issues in scope. Check --repo and the scope selector.", file=sys.stderr)
        return 1

    in_scope = {i["number"] for i in scope}
    prs = linked_prs(args.repo)

    nodes: list[dict] = []
    edges: dict[int, list[int]] = {}
    deps_supported = False

    for issue in scope:
        num = issue["number"]
        summary = issue.get("issue_dependencies_summary") or {}
        if summary:
            deps_supported = True
        summary_open = summary.get("blocked_by", 0)

        blockers = blockers_of(args.repo, num) if summary.get("total_blocked_by") else []
        edges[num] = [b["number"] for b in blockers]

        # The summary's open-blocker count lags the live edge states -- long
        # enough, sometimes, to stall a run right after a blocker closes. When
        # we have the edges themselves, they are authoritative; the summary is
        # only trusted when the edge fetch came back empty-handed.
        live_open = [b for b in blockers if b["state"] == "open"]
        if blockers:
            open_blockers = len(live_open)
            summary_stale = summary_open != open_blockers
        else:
            open_blockers = summary_open
            summary_stale = False

        declared = prose_blockers(issue.get("body"))
        unlinked = sorted(set(declared) - set(edges[num]))

        assignees = [a["login"] for a in issue.get("assignees") or []]
        labels = [l["name"] for l in issue.get("labels") or []]
        human_gated = any(l in args.human_labels for l in labels)
        issue_prs = prs.get(num, [])
        open_pr = next((p for p in issue_prs if p["state"] == "OPEN"), None)
        merged_pr = next((p for p in issue_prs if p.get("mergedAt")), None)

        children = issue.get("sub_issues_summary") or {}
        if issue["state"] == "closed":
            status = "done"
        elif children.get("total"):
            # A split parent is a container, not a lane: its children carry the
            # work. Once they are all closed, the parent needs closing by hand,
            # because that closure is what opens its downstream edges.
            if children.get("completed", 0) >= children["total"]:
                status = "split_complete"
            else:
                status = "split"
        elif open_blockers > 0:
            status = "blocked"
        elif human_gated:
            status = "needs_human"
        elif assignees or open_pr:
            status = "in_flight"
        else:
            status = "ready"

        nodes.append(
            {
                "number": num,
                "title": issue["title"],
                "state": issue["state"],
                "status": status,
                "labels": labels,
                "assignees": assignees,
                "open_blockers": open_blockers,
                "summary_stale": summary_stale,
                "summary_open_blockers": summary_open,
                "blocked_by": [
                    {
                        "number": b["number"],
                        "state": b["state"],
                        "title": b["title"],
                        "in_scope": b["number"] in in_scope,
                    }
                    for b in blockers
                ],
                "unlinked_prose_blockers": unlinked,
                "open_pr": open_pr,
                "merged_pr": merged_pr,
                "url": issue["html_url"],
            }
        )

    nodes.sort(key=lambda n: n["number"])
    by_status = {
        s: [n for n in nodes if n["status"] == s]
        for s in ("ready", "in_flight", "blocked", "needs_human", "split", "split_complete", "done")
    }
    cycles = find_cycles({k: [v for v in vs if v in in_scope] for k, vs in edges.items()})

    warnings: list[str] = []
    if not deps_supported:
        warnings.append(
            "No issue_dependencies_summary on any issue -- native dependencies look "
            "unavailable on this repo. The graph below treats every issue as unblocked, "
            "which is almost certainly wrong. Stop and confirm before dispatching."
        )
    for cycle in cycles:
        warnings.append(
            "Dependency cycle: " + " -> ".join(f"#{n}" for n in cycle) + " (nothing in it can ever unblock)"
        )
    for node in nodes:
        if node["summary_stale"]:
            live = node["open_blockers"]
            warnings.append(
                f"#{node['number']}: dependency summary says "
                f"{node['summary_open_blockers']} open blocker(s) but the live "
                f"edges show {live} -- GitHub's summary is lagging; this report "
                "trusts the live edges."
            )
        if node["unlinked_prose_blockers"]:
            warnings.append(
                f"#{node['number']} says 'Blocked by "
                + ", ".join(f"#{n}" for n in node["unlinked_prose_blockers"])
                + "' in its body but has no matching native dependency edge -- "
                "that blocker will NOT gate dispatch."
            )
        for blocker in node["blocked_by"]:
            if not blocker["in_scope"] and blocker["state"] == "open":
                warnings.append(
                    f"#{node['number']} is blocked by #{blocker['number']}, which is "
                    "outside this run's scope -- the run cannot unblock it."
                )

    open_count = sum(1 for n in nodes if n["state"] == "open")
    # Nodes waiting on a human are not a deadlock: the graph can still advance,
    # just not through anything this run may dispatch.
    deadlocked = (
        not by_status["ready"]
        and not by_status["in_flight"]
        and not by_status["needs_human"]
        and not by_status["split_complete"]
        and open_count > 0
    )

    result = {
        "repo": args.repo,
        "total": len(nodes),
        "counts": {k: len(v) for k, v in by_status.items()},
        "ready": by_status["ready"],
        "in_flight": by_status["in_flight"],
        "blocked": by_status["blocked"],
        "needs_human": by_status["needs_human"],
        "split": by_status["split"],
        "split_complete": by_status["split_complete"],
        "done": by_status["done"],
        "cycles": cycles,
        "warnings": warnings,
        "deadlocked": deadlocked,
        "complete": open_count == 0,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    c = result["counts"]
    human = f" / {c['needs_human']} ready-for-human" if c["needs_human"] else ""
    print(f"{args.repo}: {c['done']} done / {c['in_flight']} in flight / "
          f"{c['ready']} ready / {c['blocked']} blocked{human}  (of {result['total']})")

    if warnings:
        print("\nWARNINGS")
        for w in warnings:
            print(f"  ! {w}")

    if result["complete"]:
        print("\nEvery issue in scope is closed. The graph is finished.")
        return 0
    if deadlocked:
        print("\nDEADLOCK: open issues remain, none are ready, none are in flight.")
    elif not by_status["ready"] and not by_status["in_flight"] and by_status["needs_human"]:
        print("\nWAITING ON A HUMAN: nothing is dispatchable; the open frontier "
              "is entirely human-gated.")

    for label, key in (
        ("READY TO DISPATCH", "ready"),
        ("IN FLIGHT", "in_flight"),
        ("READY -- HUMAN (do not dispatch)", "needs_human"),
        ("SPLIT -- ALL CHILDREN CLOSED (close this parent to open its edges)", "split_complete"),
        ("SPLIT -- children in progress (container, do not dispatch)", "split"),
    ):
        if by_status[key]:
            print(f"\n{label}")
            for n in by_status[key]:
                extra = ""
                if n["assignees"]:
                    extra += f"  assignee={','.join(n['assignees'])}"
                if n["open_pr"]:
                    draft = " draft" if n["open_pr"]["isDraft"] else ""
                    extra += (f"  PR #{n['open_pr']['number']}{draft}"
                              f" ({n['open_pr']['headRefName']} -> {n['open_pr']['baseRefName']})")
                print(f"  #{n['number']:<5} {n['title']}{extra}")

    if by_status["blocked"]:
        print("\nBLOCKED")
        for n in by_status["blocked"]:
            waiting = ", ".join(
                f"#{b['number']}" for b in n["blocked_by"] if b["state"] == "open"
            )
            print(f"  #{n['number']:<5} {n['title']}  <- waiting on {waiting}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
