#!/usr/bin/env python3
"""Remove agent worktrees whose lane is finished and that hold nothing GitHub lacks.

Only touches worktrees Claude Code created for subagents (`<repo>/.claude/worktrees/agent-*`).
One is removed when all of these hold:

  - it has no modified, staged, or untracked files. Leftover comment notes at its
    top level (`review-*.md`, `fix-*.md`, `rebase-*.md`, ...) don't count: each
    is a copy of a comment already posted to its PR. Ignored files (build caches)
    go with the worktree;
  - its HEAD is on the default branch, or in a PR that merged, or in PRs none of
    which is open. Commits are matched to PRs by ancestry within each PR's own
    range (against its base, so a staging branch's PR doesn't claim every lane),
    by branch name, and by patch-id, which survives a force-push. Anything not
    on the default branch must also be on GitHub;
  - no process has its working directory inside it, and it isn't locked;
  - a worktree whose HEAD is only on the default branch has also had no
    checkout or commit for --idle minutes, because a freshly dispatched agent
    looks exactly like that.

Its local branch is deleted with it when nothing else has that branch checked out.

Dry run unless --apply. Usage:
  prune_worktrees.py                  # report what would go
  prune_worktrees.py --apply          # remove it
  prune_worktrees.py --apply --pr 138 # only worktrees whose HEAD is in PR #138
  prune_worktrees.py --json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

NOTE = re.compile(r"^(review|fix|rebase|integrate|merge|pr|pr-body|split|ci)-[\w.-]*\.md$")
REF_NS = "refs/workbench-prune/pr/"


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def ok(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True).returncode == 0


def worktrees(root):
    trees, cur = [], {}
    for line in (run(["git", "worktree", "list", "--porcelain"], cwd=root) or "").splitlines() + [""]:
        if not line:
            if cur:
                trees.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        cur[key] = val or True
    return trees


def busy_dirs():
    """Working directories of running processes; empty when lsof isn't available."""
    out = run(["lsof", "-a", "-d", "cwd", "-Fn"]) or ""
    return [line[1:] for line in out.splitlines() if line.startswith("n/")]


def dirt(path):
    """(blocking status lines, disposable note files) for a worktree."""
    # Not run(): stripping would eat the leading space of a " M path" line.
    p = subprocess.run(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=normal"],
                       cwd=path, capture_output=True, text=True)
    if p.returncode != 0:
        return ["   git status failed"], []
    status = p.stdout.rstrip("\n")
    blocking, notes = [], []
    for line in status.splitlines():
        name = line[3:]
        if line.startswith("?? ") and "/" not in name and NOTE.match(name):
            notes.append(name)
        else:
            blocking.append(line)
    return blocking, notes


def patch_ids(root, revs):
    """Stable patch-ids of the non-merge commits in revs; they survive a rebase or force-push."""
    log = subprocess.run(["git", "log", "--no-merges", "-p", *revs], cwd=root, capture_output=True)
    out = subprocess.run(["git", "patch-id", "--stable"], cwd=root, input=log.stdout, capture_output=True)
    return {line.split()[0] for line in out.stdout.decode(errors="replace").splitlines() if line.strip()}


def idle_minutes(path):
    gitdir = run(["git", "rev-parse", "--absolute-git-dir"], cwd=path)
    stamps = [p.stat().st_mtime for p in (Path(gitdir or path) / "HEAD", Path(gitdir or path) / "logs" / "HEAD") if p.exists()]
    return (time.time() - max(stamps)) / 60 if stamps else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="remove; without it, only report")
    ap.add_argument("--pr", type=int, action="append", default=[], help="only worktrees whose HEAD is in this PR (repeatable)")
    ap.add_argument("--idle", type=int, default=60, help="minutes a default-branch-only worktree must sit untouched (default 60)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repo", default=".", help="any checkout of the repo (default: cwd)")
    args = ap.parse_args()

    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=args.repo)
    if not common:
        sys.exit("not inside a git repository")
    root = str(Path(common).parent)
    agent_dir = os.path.realpath(os.path.join(root, ".claude", "worktrees")) + os.sep
    default = (run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=root) or "origin/main")

    # PR heads under a private namespace: GitHub creates some of them itself (`gh pr update-branch`),
    # so they may not be local, and its commit->PR lookup forgets squash-merged branches.
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=root, capture_output=True)
    subprocess.run(["git", "fetch", "-q", "--no-tags", "origin", f"+refs/pull/*/head:{REF_NS}*"], cwd=root, capture_output=True)
    try:
        listed = run(["gh", "pr", "list", "--state", "all", "--limit", "2000", "--json", "number,state,headRefName,baseRefName"], cwd=root)
        opened = run(["gh", "pr", "list", "--state", "open", "--limit", "1000", "--json", "number", "--jq", ".[].number"], cwd=root)
        nwo = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=root)
        if listed is None or opened is None:
            sys.exit("gh pr list failed; can't tell finished lanes from open ones")
        open_prs = {int(n) for n in opened.split()}
        by_head, base_of, merged = {}, {}, set()
        for pr in json.loads(listed):
            base_of[pr["number"]] = "origin/" + pr["baseRefName"]
            if pr["state"] == "MERGED":
                merged.add(pr["number"])
            by_head.setdefault(pr["headRefName"], set()).add(pr["number"])
            if pr["state"] == "OPEN":
                open_prs.add(pr["number"])
        pr_ids = {}

        def ids_by_pr():
            # Lanes that were force-pushed or rebased no longer contain the commits an old
            # worktree holds; the same change under a new sha still has the same patch-id.
            if not pr_ids:
                for ref in (run(["git", "for-each-ref", "--format=%(refname)", REF_NS], cwd=root) or "").split():
                    n = int(ref.removeprefix(REF_NS))
                    pr_ids[n] = patch_ids(root, [ref, "--not", base(n)])
            return pr_ids

        def base(n):
            # A PR's own commits are those not on its base. Measured against the default
            # branch instead, a PR into a staging branch would claim every lane merged there.
            b = base_of.get(n, default)
            return b if run(["git", "rev-parse", "--verify", "-q", b], cwd=root) else default

        def owns(n, sha):
            return not ok(["git", "merge-base", "--is-ancestor", sha, base(n)], cwd=root)

        busy = busy_dirs()
        trees = worktrees(root)
        checked_out = {}
        for t in trees:
            if t.get("branch"):
                checked_out.setdefault(t["branch"], []).append(t["worktree"])

        results = []
        for t in trees:
            path = t["worktree"]
            if not (os.path.realpath(path) + os.sep).startswith(agent_dir) or not os.path.basename(path).startswith("agent-"):
                continue
            branch = (t.get("branch") or "").removeprefix("refs/heads/") or None
            r = {"path": path, "branch": branch, "head": t.get("HEAD"), "prs": [], "notes": []}
            results.append(r)

            def keep(reason):
                r.update(action="keep", reason=reason)

            if not os.path.isdir(path):
                r.update(action="prune", reason="directory already gone")
                continue
            if t.get("locked"):
                keep("locked")
                continue
            sha = t.get("HEAD")
            on_default = ok(["git", "merge-base", "--is-ancestor", sha, default], cwd=root)
            pushed = on_default
            if not on_default:
                refs = run(["git", "for-each-ref", "--contains", sha, "--format=%(refname)", REF_NS], cwd=root) or ""
                prs = {int(x.removeprefix(REF_NS)) for x in refs.split()}
                pushed = bool(prs)
                prs = {n for n in prs if owns(n, sha)}
                upstream = run(["git", "config", f"branch.{branch}.merge"], cwd=root) if branch else None
                for name in (branch, (upstream or "").removeprefix("refs/heads/")):
                    prs |= by_head.get(name, set())
                if not prs:
                    mine = patch_ids(root, [sha, "--not", default])
                    matched = {n for n, theirs in ids_by_pr().items() if mine & theirs}
                    prs |= matched
                    if not pushed and mine and mine <= set().union(*(pr_ids[n] for n in matched)):
                        pushed = True
                if not pushed and nwo:
                    pushed = ok(["gh", "api", "--silent", f"repos/{nwo}/commits/{sha}"], cwd=root)
                r["prs"] = sorted(prs)
            if args.pr and not set(args.pr) & set(r["prs"]):
                keep("not in --pr")
                continue
            blocking, r["notes"] = dirt(path)
            if blocking:
                keep(f"{len(blocking)} uncommitted: " + ", ".join(b[3:] for b in blocking[:3]))
                continue
            if not on_default:
                if not pushed:
                    keep("commits that never reached GitHub")
                    continue
                if not r["prs"]:
                    keep("pushed, but in no PR")
                    continue
                # Work merged anywhere has landed, even if a staging branch holding it has an open PR.
                still_open = [n for n in r["prs"] if n in open_prs]
                if still_open and not merged & set(r["prs"]):
                    keep("PR still open: " + ", ".join(f"#{n}" for n in still_open))
                    continue
            else:
                idle = idle_minutes(path)
                if idle is None or idle < args.idle:
                    keep(f"only on {default}, touched {int(idle or 0)} min ago (an agent may be starting)")
                    continue
            pids = [d for d in busy if (d + os.sep).startswith(os.path.realpath(path) + os.sep)]
            if pids:
                keep("a process is running inside it")
                continue
            r.update(action="remove", reason=("on " + default) if on_default else
                     "PR " + ", ".join(f"#{n}" for n in r["prs"] if n not in open_prs) + " merged or closed")

        if args.apply:
            for r in results:
                if r["action"] != "remove":
                    continue
                if not ok(["git", "worktree", "remove", "--force", r["path"]], cwd=root):
                    r.update(action="keep", reason="git worktree remove failed")
                    continue
                r["action"] = "removed"
                b = r["branch"]
                if b and b != default.split("/", 1)[-1] \
                        and checked_out.get(f"refs/heads/{b}") == [r["path"]] \
                        and run(["git", "rev-parse", f"refs/heads/{b}"], cwd=root) == r["head"]:
                    r["branch_deleted"] = ok(["git", "branch", "-D", b], cwd=root)
            subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True)
    finally:
        refs = run(["git", "for-each-ref", "--format=delete %(refname)", REF_NS], cwd=root) or ""
        if refs:
            subprocess.run(["git", "update-ref", "--stdin"], cwd=root, input=refs + "\n", text=True, capture_output=True)

    if args.json:
        print(json.dumps(results, indent=2))
        return
    verb = "removed" if args.apply else "remove"
    gone = [r for r in results if r["action"] in ("remove", "removed", "prune")]
    kept = [r for r in results if r["action"] == "keep" and r["reason"] != "not in --pr"]
    for r in gone:
        extra = f"  (+{len(r['notes'])} note{'s' * (len(r['notes']) != 1)})" if r["notes"] else ""
        print(f"{verb:7} {os.path.basename(r['path'])}  {r['branch'] or 'detached'}  {r['reason']}{extra}")
    for r in kept:
        print(f"keep    {os.path.basename(r['path'])}  {r['branch'] or 'detached'}  {r['reason']}")
    print(f"\n{len(gone)} {'removed' if args.apply else 'to remove'}, {len(kept)} kept"
          + ("" if args.apply or not gone else "; rerun with --apply to remove them"))


if __name__ == "__main__":
    main()
