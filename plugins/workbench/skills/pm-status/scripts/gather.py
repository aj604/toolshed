#!/usr/bin/env python3
"""Gather everything that moved in the current repo since the last pm-status run.

Prints one JSON document to stdout. Read-only apart from `git fetch`, a
frontier snapshot left in the git dir for --mark to keep, and, with --mark,
writing the last-run timestamp and that snapshot.

Usage:
  gather.py [--since 24h|3d|2026-10-01T09:00] [--repo PATH]
  gather.py --mark            # record "now" as the last run (call after reporting)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIRST_RUN_LOOKBACK = timedelta(hours=48)
BRANCH_NUMBER = re.compile(r"(?:^|[/_-])(\d+)(?=$|[/_-])")
PART_OF = re.compile(r"(?i)\b(?:part of|works? (?:on|toward)|towards?)\s+#(\d+)")
NOW = datetime.now(timezone.utc)


def run(cmd, cwd=None, check=False):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {p.stderr.strip()}")
    return p.stdout.strip() if p.returncode == 0 else None


def gh_json(args, cwd):
    out = run(["gh", *args], cwd=cwd)
    try:
        return json.loads(out) if out else None
    except json.JSONDecodeError:
        return None


def parse_since(value, last_run):
    if not value:
        return (last_run, "since last run") if last_run else (NOW - FIRST_RUN_LOOKBACK, "first run: last 48h")
    m = re.fullmatch(r"(\d+)\s*([hdw])", value.strip().lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"h": timedelta(hours=n), "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
        return NOW - delta, f"last {value}"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc), f"since {value}"


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def age(ts):
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    secs = (NOW - dt).total_seconds()
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"


def slug(path):
    # Claude Code names ~/.claude/projects/<dir> by replacing every non-alphanumeric char with '-'
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def summarize_checks(rollup):
    if not rollup:
        return {"state": "none"}
    failing, pending, passing = [], [], 0
    for c in rollup:
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        status = (c.get("status") or "").upper()
        name = c.get("name") or c.get("context") or "?"
        if concl in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            failing.append(name)
        elif status in ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING") or concl in ("PENDING", "EXPECTED", ""):
            pending.append(name)
        else:
            passing += 1
    state = "failing" if failing else "pending" if pending else "passing"
    return {"state": state, "failing": failing, "pending": pending, "passing": passing}


# ---------------------------------------------------------------- git

def git_section(root, default, since):
    remote_default = f"origin/{default}"
    log = run(["git", "log", remote_default, f"--since={iso(since)}", "--first-parent",
               "--format=%h%x09%cI%x09%an%x09%s"], cwd=root) or ""
    commits = []
    for line in log.splitlines():
        h, when, author, subj = line.split("\t", 3)
        pr = re.search(r"\(#(\d+)\)|Merge pull request #(\d+)", subj)
        commits.append({"sha": h, "at": when, "author": author, "subject": subj,
                        "pr": int(next(g for g in pr.groups() if g)) if pr else None})
    return commits


def changes_on_default(root, default, ref):
    """True when every file ref changed since forking already matches the default branch.

    Commit counts call a squash-merged branch "ahead" forever; comparing content doesn't.
    """
    base = run(["git", "merge-base", f"origin/{default}", ref], cwd=root)
    if not base:
        return None
    files = (run(["git", "diff", "--name-only", base, ref], cwd=root) or "").splitlines()
    if not files:
        return True
    p = subprocess.run(["git", "diff", "--quiet", f"origin/{default}", ref, "--", *files], cwd=root, capture_output=True)
    return {0: True, 1: False}.get(p.returncode)


def worktrees_section(root, default, pr_by_branch):
    porcelain = run(["git", "worktree", "list", "--porcelain"], cwd=root) or ""
    trees, cur = [], {}
    for line in porcelain.splitlines() + [""]:
        if not line:
            if cur:
                trees.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        cur[key] = val or True
    out = []
    for t in trees:
        path = t.get("worktree")
        branch = (t.get("branch") or "").removeprefix("refs/heads/") or None
        exists = path and os.path.isdir(path)
        entry = {"path": path, "branch": branch, "is_main_checkout": os.path.realpath(path) == os.path.realpath(root),
                 "exists": bool(exists), "prunable": "prunable" in t}
        if exists and not t.get("bare"):
            ref = branch or "HEAD"  # a detached worktree can hold at-risk work too
            entry["detached"] = branch is None
            dirty = run(["git", "status", "--porcelain"], cwd=path) or ""
            entry["uncommitted_files"] = len(dirty.splitlines())
            counts = run(["git", "rev-list", "--left-right", "--count", f"origin/{default}...{ref}"], cwd=path)
            if counts:
                behind, ahead = map(int, counts.split())
                entry.update(ahead_of_default=ahead, behind_default=behind)
                if ahead:
                    entry["changes_on_default"] = changes_on_default(path, default, ref)
            upstream = run(["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], cwd=path) if branch else None
            entry["upstream"] = upstream
            # A branch that was never pushed has no upstream; count what no remote branch has.
            unpushed = run(["git", "rev-list", "--count", f"{upstream}..{ref}"] if upstream
                           else ["git", "rev-list", "--count", ref, "--not", "--remotes"], cwd=path)
            entry["unpushed_commits"] = int(unpushed) if unpushed else None
            entry["last_commit"] = run(["git", "log", "-1", "--format=%cI %s", ref], cwd=path)
        pr = pr_by_branch.get(branch)
        if pr:
            entry["pr"] = {"number": pr["number"], "state": pr["state"]}
        out.append(entry)
    return out


def orphan_branches(root, default, pr_by_branch, worktree_branches, since):
    """Local branches with commits not on default, no worktree, no PR — work that can get lost."""
    raw = run(["git", "for-each-ref", "refs/heads", "--format=%(refname:short)\t%(committerdate:iso-strict)"], cwd=root) or ""
    out = []
    for line in raw.splitlines():
        name, when = line.split("\t")
        if name == default or name in worktree_branches or name in pr_by_branch:
            continue
        ahead = run(["git", "rev-list", "--count", f"origin/{default}..{name}"], cwd=root)
        if not ahead or int(ahead) == 0:
            continue
        recent = datetime.fromisoformat(when) >= since - timedelta(days=14)
        if recent:
            out.append({"branch": name, "ahead_of_default": int(ahead), "last_commit_at": when,
                        "pushed": bool(run(["git", "rev-parse", "--verify", "--quiet", f"origin/{name}"], cwd=root)),
                        "changes_on_default": changes_on_default(root, default, name)})
    return sorted(out, key=lambda b: b["last_commit_at"], reverse=True)[:15]


# ---------------------------------------------------------------- github

def github_section(root, since, owner_repo, default):
    s = iso(since)
    pr_fields_done = "number,title,url,state,mergedAt,closedAt,headRefName,baseRefName,author,additions,deletions,closingIssuesReferences"
    pr_fields_open = ("number,title,url,isDraft,headRefName,baseRefName,createdAt,updatedAt,reviewDecision,mergeable,"
                      "statusCheckRollup,closingIssuesReferences,labels,author,body")
    jobs = {
        "merged": ["pr", "list", "--state", "merged", "--search", f"merged:>={s}", "--limit", "100", "--json", pr_fields_done],
        "closed_unmerged": ["pr", "list", "--state", "closed", "--search", f"closed:>={s} is:unmerged", "--limit", "50", "--json", pr_fields_done],
        "open": ["pr", "list", "--state", "open", "--limit", "100", "--json", pr_fields_open],
        "issues_closed": ["issue", "list", "--state", "closed", "--search", f"closed:>={s}", "--limit", "100",
                          "--json", "number,title,url,closedAt,stateReason"],
        "issues_opened": ["issue", "list", "--state", "all", "--search", f"created:>={s}", "--limit", "100",
                          "--json", "number,title,url,state,createdAt,author"],
        "issues_open": ["issue", "list", "--state", "open", "--limit", "100",
                        "--json", "number,title,url,labels,assignees,createdAt,updatedAt,milestone"],
        "all_prs_for_branches": ["pr", "list", "--state", "all", "--limit", "1000", "--json", "number,state,headRefName,baseRefName"],
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        results = dict(zip(jobs, ex.map(lambda a: gh_json(a, root), jobs.values())))

    open_numbers = {i["number"] for i in results.get("issues_open") or []}
    for pr in results.get("open") or []:
        pr["checks"] = summarize_checks(pr.pop("statusCheckRollup", None))
        pr["age"] = age(pr.get("createdAt"))
        pr["idle"] = age(pr.get("updatedAt"))
        pr["closes"] = [i["number"] for i in pr.pop("closingIssuesReferences", None) or []]
        # Stacked sub-PRs say "Part of #N", which GitHub doesn't link; they still take #N off the frontier.
        part_of = [int(n) for n in PART_OF.findall(pr.pop("body", None) or "")]
        # Agents often name the branch after the issue (impl/533-..., implement-ticket-672).
        named = BRANCH_NUMBER.findall(pr.get("headRefName") or "")[-1:]
        named = [int(n) for n in named if int(n) in open_numbers]
        pr["works_on"] = sorted(set(pr["closes"]) | set(part_of) | set(named))
        pr["labels"] = [l["name"] for l in pr.get("labels") or []]
        pr["author"] = (pr.get("author") or {}).get("login")
    for key in ("merged", "closed_unmerged"):
        for pr in results.get(key) or []:
            pr["closes"] = [i["number"] for i in pr.pop("closingIssuesReferences", None) or []]
            pr["author"] = (pr.get("author") or {}).get("login")

    # Issue frontier: which open issues have open blockers (GitHub native dependencies)?
    open_issues = results.get("issues_open") or []
    in_progress = {n for pr in results.get("open") or [] for n in pr["works_on"]}

    def links(issue):
        n = issue["number"]
        deps = gh_json(["api", f"repos/{owner_repo}/issues/{n}/dependencies/blocked_by"], root)
        subs = gh_json(["api", f"repos/{owner_repo}/issues/{n}/sub_issues?per_page=100"], root)
        blockers = None if deps is None else [b["number"] for b in deps if b.get("state") == "open"]
        children = None if subs is None else [
            {"number": c["number"], "title": c["title"], "state": c["state"], "state_reason": c.get("state_reason")}
            for c in subs]
        return blockers, children

    deps_supported = True
    if open_issues and len(open_issues) <= 60:
        with ThreadPoolExecutor(max_workers=8) as ex:
            linked = list(ex.map(links, open_issues))
        deps_supported = any(b is not None for b, _ in linked)
    else:
        linked = [(None, None)] * len(open_issues)
    for issue, (b, children) in zip(open_issues, linked):
        issue["labels"] = [l["name"] for l in issue.get("labels") or []]
        issue["assignees"] = [a["login"] for a in issue.get("assignees") or []]
        issue["milestone"] = (issue.get("milestone") or {}).get("title")
        issue["open_blockers"] = b
        issue["has_open_pr"] = issue["number"] in in_progress
        # A parent is tracked through its children (or waits to be closed), never picked up itself.
        if issue["has_open_pr"] or b or children:
            issue["ready"] = False
        elif b is None and deps_supported:
            issue["ready"] = None  # blockers weren't fetched, so readiness is unknown
        else:
            issue["ready"] = True
        # Parent/sub-issue links, so epics can be drawn as trees. None when not fetched or the call failed.
        issue["sub_issues"] = children
        issue["children_all_closed"] = all(c["state"] == "closed" for c in children) if children else None

    all_prs = results.pop("all_prs_for_branches", None) or []
    pr_by_branch = {}
    for pr in all_prs:
        pr_by_branch.setdefault(pr["headRefName"], pr)  # newest first
    results["dependency_api_available"] = deps_supported
    results["default_ci"] = latest_runs(root, default, 20)
    return results, pr_by_branch, all_prs


def latest_runs(root, branch, limit):
    """The newest Actions run per workflow on a branch."""
    runs = gh_json(["run", "list", "--branch", branch, "-L", str(limit),
                    "--json", "databaseId,workflowName,status,conclusion,createdAt"], root) or []
    seen, out = set(), []
    for r in runs:
        if r["workflowName"] not in seen:
            seen.add(r["workflowName"])
            out.append({"id": r.get("databaseId"), "workflow": r["workflowName"], "status": r["status"],
                        "conclusion": r["conclusion"], "at": r["createdAt"]})
    return out


def merge_conflicts(root, ours, theirs):
    """Files that would conflict merging theirs into ours: [] when clean, None when git can't tell."""
    p = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", ours, theirs],
                       cwd=root, capture_output=True, text=True)
    if p.returncode == 0:
        return []
    return [f for f in p.stdout.splitlines()[1:] if f] if p.returncode == 1 else None


def staged_branches(root, default, merged, all_prs, pr_by_branch):
    """Branches other than the default that PRs merged into: work staged, not shipped.

    Covers bases merged into this window, plus older ones whose work is still stranded off the default.
    """
    bases = {}
    for pr in merged or []:
        if pr["baseRefName"] != default:
            bases.setdefault(pr["baseRefName"], ([], True))[0].append(pr["number"])
    for pr in all_prs:
        base = pr.get("baseRefName")
        if pr["state"] == "MERGED" and base and base != default and (base not in bases or not bases[base][1]):
            bases.setdefault(base, ([], False))[0].append(pr["number"])
    out = []
    for branch, (numbers, in_window) in sorted(bases.items()):
        on_remote = bool(run(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], cwd=root))
        counts = on_remote and run(["git", "rev-list", "--left-right", "--count",
                                    f"origin/{default}...origin/{branch}"], cwd=root)
        behind, ahead = map(int, counts.split()) if counts else (None, None)
        pr = pr_by_branch.get(branch)
        if not in_window and (not ahead or (pr and pr["state"] == "MERGED")):
            continue
        # Once the branch's own PR merged, its work shipped onward; ancestry and conflicts would only mislead.
        live = on_remote and not (pr and pr["state"] == "MERGED")
        conflicts = merge_conflicts(root, f"origin/{default}", f"origin/{branch}") if live else None
        runs = latest_runs(root, branch, 1)
        out.append({"branch": branch, "merged_prs": sorted(numbers), "on_remote": on_remote,
                    "ahead": ahead, "behind": behind, "in_window": in_window,
                    "changes_on_default": changes_on_default(root, default, f"origin/{branch}") if live else None,
                    "conflict_count": None if conflicts is None else len(conflicts),
                    "conflicts_with_default": None if conflicts is None else conflicts[:10],
                    "pr": {"number": pr["number"], "state": pr["state"], "base": pr.get("baseRefName")} if pr else None,
                    "last_ci": runs[0] if runs else None})
    return out


# ---------------------------------------------------------------- frontier diff

def frontier_snapshot(github):
    """Each open issue's frontier state, or None when the open-issue list may be incomplete."""
    issues = github.get("issues_open")
    if github.get("unavailable") or issues is None or len(issues) >= 100:
        return None

    def state(issue):
        if issue["has_open_pr"]:
            return "in_progress"
        if issue["open_blockers"]:
            return "blocked"
        if issue.get("sub_issues"):
            return "parent"
        return "ready" if issue["ready"] else "unknown"

    return {str(i["number"]): {"title": i["title"], "state": state(i)} for i in issues}


def frontier_changes(previous, current):
    """Issues whose frontier state moved between two snapshots; gone from the open list means closed."""
    changes = []
    for n in sorted(set(previous) | set(current), key=int):
        was = (previous.get(n) or {}).get("state")
        now = (current.get(n) or {}).get("state", "closed")
        # "unknown" means blockers weren't fetched, so a move to or from it isn't a real change.
        if was == now or (was and now != "closed" and "unknown" in (was, now)):
            continue
        changes.append({"number": int(n), "title": (current.get(n) or previous[n])["title"], "from": was, "to": now})
    return changes


# ---------------------------------------------------------------- local transcripts (CLI fallback)

def tail(text, limit):
    """The end of text, at most limit chars, starting on a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[-limit:]
    return cut[cut.find(" ") + 1:] if " " in cut else cut


def local_transcripts(root, worktree_paths, since, repo_name):
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return []
    prefixes = {slug(root)} | {slug(p) for p in worktree_paths if p}
    home_wt = slug(Path.home() / ".worktrees" / repo_name)
    out = []
    for d in projects.iterdir():
        if not (any(d.name.startswith(p) for p in prefixes) or d.name.startswith(home_wt + "-")):
            continue
        for f in d.glob("*.jsonl"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
            if mtime < since:
                continue
            first_user, last_assistant, branch, cwd, stamp = None, None, None, None, None
            try:
                for line in f.open():
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    branch = e.get("gitBranch") or branch
                    stamp = e.get("timestamp") or stamp
                    cwd = e.get("cwd") or cwd
                    msg = e.get("message") or {}
                    content = msg.get("content")
                    text = content if isinstance(content, str) else " ".join(
                        c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text")
                    if not text.strip() or e.get("isSidechain"):
                        continue
                    if e.get("type") == "user" and first_user is None and not text.startswith("<"):
                        first_user = text
                    elif e.get("type") == "assistant":
                        last_assistant = text
            except OSError:
                continue
            # mtime only pre-filters: a bulk copy or touch makes every old transcript look fresh.
            try:
                last = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else mtime
            except ValueError:
                last = mtime
            if last < since:
                continue
            out.append({"session_id": f.stem, "session_file": str(f), "cwd": cwd, "branch": branch,
                        "last_activity": iso(last), "first_prompt": (first_user or "")[:300],
                        "last_reply": tail(last_assistant or "", 2000)})
    return sorted(out, key=lambda s: s["last_activity"], reverse=True)[:20]


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--mark", action="store_true", help="record now as the last run and exit")
    args = ap.parse_args()

    root = run(["git", "rev-parse", "--show-toplevel"], cwd=args.repo)
    if not root:
        sys.exit(json.dumps({"error": f"{args.repo} is not inside a git repository"}))
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root)
    # Stored in the shared git dir so every worktree of this repo sees the same "last run", and it never gets committed.
    state_file = Path(common) / "pm-status.json"
    # This run's frontier, kept by --mark only once the user has seen the report built from it.
    pending_file = Path(common) / "pm-status-pending.json"
    # Report against the primary checkout even when invoked from a worktree.
    main_root = str(Path(common).parent) if Path(common).name == ".git" else root

    if args.mark:
        state = {"last_run": iso(NOW)}
        if pending_file.exists():
            try:
                state["frontier"] = json.loads(pending_file.read_text())["frontier"]
            except (ValueError, KeyError):
                pass
            pending_file.unlink()
        state_file.write_text(json.dumps(state))
        print(json.dumps({"marked": iso(NOW), "state_file": str(state_file), "frontier_saved": "frontier" in state}))
        return

    state, last_run = {}, None
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            last_run = datetime.fromisoformat(state["last_run"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError, AttributeError):
            state = {}
    since, window_label = parse_since(args.since, last_run)

    fetched = run(["git", "fetch", "--prune", "--quiet", "origin"], cwd=main_root) is not None
    default = (run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=main_root) or "origin/main").removeprefix("origin/")
    remote_url = run(["git", "remote", "get-url", "origin"], cwd=main_root) or ""
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", remote_url)
    owner_repo = m.group(1) if m else None
    repo_name = Path(main_root).name

    gh_ok = bool(owner_repo) and run(["gh", "auth", "status"]) is not None
    github, pr_by_branch, all_prs = (github_section(main_root, since, owner_repo, default) if gh_ok
                                     else ({"unavailable": True}, {}, []))
    snapshot = frontier_snapshot(github)
    if snapshot is None:
        pending_file.unlink(missing_ok=True)
    else:
        pending_file.write_text(json.dumps({"frontier": snapshot}))
    previous = state.get("frontier")
    changes = ({"since": state["last_run"], "changes": frontier_changes(previous, snapshot)}
               if snapshot is not None and previous is not None else None)
    trees = worktrees_section(main_root, default, pr_by_branch)
    tree_branches = {t["branch"] for t in trees if t["branch"]}

    known_branches = sorted(set(pr_by_branch) | tree_branches |
                            set((run(["git", "for-each-ref", "refs/heads", "--format=%(refname:short)"], cwd=main_root) or "").split()))

    report = {
        "repo": {"name": repo_name, "root": main_root, "github": owner_repo, "default_branch": default, "fetched": fetched},
        "window": {"since": iso(since), "label": window_label, "now": iso(NOW), "last_run": iso(last_run) if last_run else None},
        "landed_on_default": git_section(main_root, default, since),
        "github": github,
        "frontier_changes": changes,
        "staged_branches": staged_branches(main_root, default, github.get("merged"), all_prs, pr_by_branch) if gh_ok else None,
        "worktrees": trees,
        "orphan_branches": orphan_branches(main_root, default, pr_by_branch, tree_branches, since),
        "session_match_hints": {
            "cwd_prefixes": sorted({main_root, str(Path.home() / ".worktrees" / repo_name)} | {t["path"] for t in trees if t["path"]}),
            "known_branches": known_branches,
        },
        "local_transcripts": local_transcripts(main_root, [t["path"] for t in trees], since, repo_name),
    }
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
