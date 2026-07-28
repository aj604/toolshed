#!/usr/bin/env python3
"""Path authority for the doc-sync upgrade lane's trust split.

An upgrade regenerates a consumer's wiring by running the *target release's* own
`apply-upgrade.py`. That code has been reviewed by nobody in the consumer
repository at the moment it runs, so the lane never runs it in a credentialed
job. Instead:

  regenerate  holds `contents: read`, no token, no persisted checkout
              credential. It copies the install's wiring roots into a scratch
              tree, runs the clone's `apply-upgrade.py` against that copy, and
              calls `manifest` below to say exactly which paths changed.
  land        holds `contents: write` and executes nothing from the clone. It
              calls `apply` below, which re-derives the same authority from the
              manifest, transfers exactly those paths, and prints the staging
              list.

This script is the authority both jobs answer to. It is run from the *installed*
checkout in both jobs — never from the target clone and never from the scratch
tree — so the code enforcing the boundary is code a human already reviewed.

Two duties:

1. Say what the regeneration wrote, and refuse anything outside the wiring:
       stage-upgrade.py manifest --scratch DIR --repo DIR --target X.Y.Z
                        --bundle DIR
   Compares the scratch tree against the install under the wiring roots
   (`.github/`, `.doc-lifecycle/`), classifies every difference, and writes
   `<bundle>/manifest.json` plus `<bundle>/files/<path>` for each added or
   modified file. A difference at a path `apply-upgrade.py` does not own — the
   marker, `audit-scope.json`, the registry, a file outside the roots entirely —
   fails the job. Nothing is staged, no pull request exists, and the run surface
   names every offending path.

2. Transfer exactly that path set into the credentialed job's checkout:
       stage-upgrade.py apply --bundle DIR --repo DIR --out FILE
   Re-derives the authority from the manifest (never trusting that `manifest`
   already checked it — the two run in different trust domains, with an artifact
   in between), verifies every bundled file against its recorded digest, then
   copies added/modified files and deletes removed ones. `--out` receives the
   NUL-separated path list for `git add --pathspec-from-file= --pathspec-file-nul`.
   A third duty closes the loop after staging:
       stage-upgrade.py verify --paths FILE --staged FILE --unstaged FILE
   which fails if git staged anything the manifest did not authorize, or if the
   work tree still holds a change nobody asked for.

What `apply-upgrade.py` owns, and therefore all this authorizes:

    .github/doc-sync/installed-version              the version lockfile
    .github/doc-sync/drift-waivers.json             seeded when absent
    .github/doc-sync/evidence-tools.json            seeded when absent
    .github/doc-sync/<name>.py                      the vendored scripts
    .github/doc-sync/engine/**                      the engine, vendored whole
    .github/workflows/doc-<name>.yml                the installed lanes

Deliberately outside it: `.github/doc-sync-marker`, `.github/doc-sync/audit-scope.json`,
and `.doc-lifecycle/registry.json` are consumer state an upgrade preserves, so a
regeneration that changed one is a regeneration to refuse, not to land. The
script and workflow names are matched by pattern rather than by a fixed list
because a release may add a lane; the confinement that matters is the directory
and the extension, and every byte still reaches a human as a pull request.

Exit status: 0 authorized; 1 a difference outside the authority, a bundle that
does not match its manifest, or a digest mismatch; 2 bad input.
"""

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import sys

# The only trees an upgrade may touch. Everything under them is compared; a
# scratch-tree path outside them is a write that escaped the wiring.
WIRING_ROOTS = (".github", ".doc-lifecycle")

# Repo-relative paths `apply-upgrade.py` owns. Anchored, single-segment where
# the directory is flat, so `.github/doc-sync/../../evil` cannot match even
# before normalization rejects it.
OWNED_PATTERNS = (
    re.compile(r"^\.github/doc-sync/installed-version$"),
    re.compile(r"^\.github/doc-sync/(?:drift-waivers|evidence-tools)\.json$"),
    re.compile(r"^\.github/doc-sync/[A-Za-z0-9_-]+\.py$"),
    re.compile(r"^\.github/doc-sync/engine/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+$"),
    re.compile(r"^\.github/workflows/doc-[a-z0-9-]+\.yml$"),
)

# Never compared, never transferred: a bytecode cache is a build artifact of
# whichever interpreter last imported the tree, not wiring.
SKIP_DIRS = ("__pycache__", ".git")

MANIFEST = "manifest.json"
FILES = "files"
ARTIFACT = "upgrade-bundle"
SCHEMA_VERSION = 1


def die(msg):
    """Self-explaining bad-input exit (code 2)."""
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def refuse(errors):
    """Every offending path, then a summary — never the first one only."""
    for e in errors:
        print(e, file=sys.stderr)
    print(f"\nFAILED: {len(errors)} path(s) outside what an upgrade may write — "
          f"nothing staged, no pull request", file=sys.stderr)
    return 1


def safety_error(path):
    """Why this path may never name a file in the install — or None."""
    if not isinstance(path, str) or not path.strip():
        return "empty path"
    if path != path.strip():
        return "leading or trailing whitespace"
    if "\\" in path or "\n" in path or "\t" in path or "\0" in path:
        return "backslash or control character in path"
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "absolute path"
    if posixpath.normpath(path) != path:
        return (f"not a normalized repo-relative path "
                f"(normalizes to {posixpath.normpath(path)!r})")
    if path == ".." or path.startswith("../"):
        return "escapes the repository"
    return None


def authority_error(path):
    """Why an upgrade may not write this path — or None."""
    err = safety_error(path)
    if err:
        return err
    if not any(p.match(path) for p in OWNED_PATTERNS):
        return ("not a file the upgrade engine owns (the wiring is "
                ".github/doc-sync/ and .github/workflows/doc-*.yml; the marker, "
                "audit-scope.json and the registry are consumer state)")
    return None


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(root):
    """{repo-relative path: absolute path} for every regular file under root.

    Symlinks are reported rather than followed: a bundle entry that is a link is
    a path the transfer would resolve somewhere this script never checked.
    """
    found, links = {}, []
    for base in WIRING_ROOTS:
        top = os.path.join(root, base)
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if os.path.islink(full):
                    links.append(rel)
                elif os.path.isfile(full):
                    found[rel] = full
    return found, links


def stray_paths(scratch):
    """Scratch-tree entries outside the wiring roots — writes that escaped."""
    stray = []
    for name in sorted(os.listdir(scratch)):
        if name in WIRING_ROOTS or name in SKIP_DIRS:
            continue
        stray.append(name)
    return stray


def run_manifest(args):
    if not os.path.isdir(args.scratch):
        die(f"--scratch {args.scratch} is not a directory")
    if not os.path.isdir(args.repo):
        die(f"--repo {args.repo} is not a directory")

    errors = []
    for name in stray_paths(args.scratch):
        errors.append(f"{name}: the regeneration wrote outside the wiring roots "
                      f"({', '.join(WIRING_ROOTS)})")

    after, after_links = walk(args.scratch)
    before, _ = walk(args.repo)
    for rel in after_links:
        errors.append(f"{rel}: the regeneration wrote a symlink")

    entries = []
    for rel in sorted(set(after) | set(before)):
        if rel in after and rel in before:
            new = digest(after[rel])
            if new == digest(before[rel]):
                continue
            status, sha = "M", new
        elif rel in after:
            status, sha = "A", digest(after[rel])
        else:
            status, sha = "D", None
        err = authority_error(rel)
        if err:
            errors.append(f"{rel}: {err}")
            continue
        entries.append({"status": status, "path": rel, "sha256": sha})

    if errors:
        return refuse(errors)

    os.makedirs(os.path.join(args.bundle, FILES), exist_ok=True)
    for entry in entries:
        if entry["status"] == "D":
            continue
        dest = os.path.join(args.bundle, FILES, entry["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(after[entry["path"]], dest)

    manifest = {"artifact": ARTIFACT, "schema_version": SCHEMA_VERSION,
                "target": args.target, "entries": entries}
    with open(os.path.join(args.bundle, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    changed = sum(1 for e in entries if e["status"] != "D")
    removed = len(entries) - changed
    print(f"v{args.target}: {changed} file(s) to write, {removed} to remove — "
          f"all within the upgrade engine's own wiring", file=sys.stderr)
    return 0


def load_manifest(bundle):
    path = os.path.join(bundle, MANIFEST)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"cannot read {path}: {e}")
    if not (isinstance(data, dict) and data.get("artifact") == ARTIFACT
            and data.get("schema_version") == SCHEMA_VERSION
            and isinstance(data.get("entries"), list)):
        die(f"{path} is not a stage-upgrade.py {ARTIFACT} manifest")
    return data


def run_apply(args):
    data = load_manifest(args.bundle)
    if args.target is not None and data.get("target") != args.target:
        die(f"the bundle regenerates v{data.get('target')!r}, but this job was "
            f"dispatched for v{args.target!r}")

    files_root = os.path.realpath(os.path.join(args.bundle, FILES))
    errors, plan = [], []
    for entry in data["entries"]:
        if not isinstance(entry, dict):
            errors.append(f"{entry!r}: not a manifest entry")
            continue
        path, status = entry.get("path"), entry.get("status")
        err = authority_error(path)
        if err:
            errors.append(f"{path!r}: {err}")
            continue
        if status not in ("A", "M", "D"):
            errors.append(f"{path}: unknown status {status!r}")
            continue
        if status == "D":
            plan.append((status, path, None))
            continue
        src = os.path.join(args.bundle, FILES, path)
        if os.path.islink(src) or not os.path.isfile(src):
            errors.append(f"{path}: the manifest names it, but the bundle "
                          f"carries no regular file for it")
            continue
        if os.path.realpath(src) != os.path.join(files_root, path):
            errors.append(f"{path}: the bundle entry resolves outside the "
                          f"bundle")
            continue
        if digest(src) != entry.get("sha256"):
            errors.append(f"{path}: the bundled file does not match the digest "
                          f"the manifest recorded for it")
            continue
        plan.append((status, path, src))

    # A bundle carrying a file no manifest entry names is a bundle that was not
    # produced by the run this job is landing. Refuse it whole rather than
    # transferring the subset that happens to check out.
    named = {p for _, p, _ in plan}
    if os.path.isdir(files_root):
        carried, links = walk_bundle(files_root)
        for rel in sorted(set(carried) | set(links)):
            if rel not in named:
                errors.append(f"{rel}: the bundle carries a file the manifest "
                              f"does not name")

    if errors:
        return refuse(sorted(dict.fromkeys(errors)))

    for status, path, src in plan:
        dest = os.path.join(args.repo, path)
        if status == "D":
            if os.path.isfile(dest):
                os.remove(dest)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)

    with open(args.out, "wb") as f:
        for _, path, _ in plan:
            f.write(path.encode("utf-8") + b"\0")

    print(f"{len(plan)} path(s) authorized and transferred", file=sys.stderr)
    for _, path, _ in plan:
        print(path)
    return 0


def read_nul(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        die(f"cannot read {path}: {e}")
    return [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]


def run_verify(args):
    """What git actually staged is inside what the manifest authorized."""
    authorized = set(read_nul(args.paths))
    staged = read_nul(args.staged)
    unstaged = read_nul(args.unstaged)

    errors = [f"{p}: staged, but no manifest entry authorized it"
              for p in sorted(set(staged) - authorized)]
    errors += [f"{p}: left unstaged or untracked in the work tree"
               for p in sorted(set(unstaged))]
    if errors:
        return refuse(errors)

    # A shorter staged list is legitimate — the base can have moved between the
    # regeneration and this checkout, leaving an entry that is already applied —
    # so it is reported, not refused. The direction that matters is the other one.
    print(f"{len(set(staged))} of {len(authorized)} authorized path(s) staged; "
          f"nothing else touched", file=sys.stderr)
    return 0


def walk_bundle(root):
    """Every path the bundle actually carries, and every symlink among them."""
    found, links = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            (links if os.path.islink(full) else found).append(rel)
    return found, links


def main():
    ap = argparse.ArgumentParser(
        description="Confine a doc-sync upgrade to the wiring it may write.")
    sub = ap.add_subparsers(dest="mode", required=True)

    man = sub.add_parser("manifest", help="say what the regeneration wrote")
    man.add_argument("--scratch", required=True,
                     help="the tree the target release's apply-upgrade.py wrote")
    man.add_argument("--repo", required=True, help="the install being upgraded")
    man.add_argument("--target", required=True, help="the version regenerated to")
    man.add_argument("--bundle", required=True, help="bundle directory to write")

    app = sub.add_parser("apply", help="transfer exactly that path set")
    app.add_argument("--bundle", required=True)
    app.add_argument("--repo", required=True)
    app.add_argument("--target", help="refuse a bundle for a different version")
    app.add_argument("--out", required=True,
                     help="NUL-separated staging list for git add")

    ver = sub.add_parser("verify", help="check what git staged against it")
    ver.add_argument("--paths", required=True, help="the `apply` --out list")
    ver.add_argument("--staged", required=True,
                     help="git diff --cached --name-only -z")
    ver.add_argument("--unstaged", required=True,
                     help="git diff --name-only -z, plus untracked, -z")

    args = ap.parse_args()
    return {"manifest": run_manifest,
            "apply": run_apply,
            "verify": run_verify}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
