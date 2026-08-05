#!/usr/bin/env python3
"""The apply lanes' byte verification at the two git boundaries (#191).

The applier certifies a **postimage manifest**: every path one apply run wrote,
with the sha256 of the bytes it read back off disk — `null` for a document it
retired (`doclifecycle/applier.py`, "Final-byte certification"). That
certification ends at the working tree, and two trust boundaries lie beyond it
that the engine cannot see, because git owns both:

  * **the index.** `git add` does not have to store the bytes it was pointed
    at. A `clean` filter or an end-of-line attribute rewrites content on the
    way in, and anything that mutates an approved path between the apply and
    the staging lands in the index unread — path confinement
    (`render-apply-summary.py verify-staged`) sees the same path list either
    way, because the path *is* one the plan writes. Only the bytes betray it.
  * **the commit tree.** A `pre-commit` hook may rewrite a target and re-stage
    it after the index was verified, so the tree that would be pushed is not
    the index anybody checked.

So each boundary is re-read from git's own object store and compared with the
manifest, and the commit this script certifies is the one the lane pushes: it
writes the verified commit id out, and the push names that id rather than
`HEAD`, which anything running in between could have moved.

Path confinement and byte binding stay separate checks here, exactly as they
are in the applier, and both must hold: `--result`'s `changed_paths` must be
covered by the manifest, the commit's whole diff against its parent must lie
inside it, and every manifest entry must match byte for byte — or be absent,
which is what a retired document's `null` certifies and what a deletion has to
mean at an index and a tree alike.

Both apply lanes run this script, with the same arguments, at the same two
points: `doc-apply.yml` (a human selected the records) and
`doc-policy-apply.yml` (a standing policy did). Selection and trigger are the
only intended differences between them, and
`tests/scripts/apply-lane-parity_test.py` is what holds that true.

Usage:
    verify-apply-bytes.py index  --result FILE [--repo DIR]
    verify-apply-bytes.py commit --result FILE [--repo DIR] --out FILE

Exit status: 0 the boundary holds; 1 a typed refusal, rendered to
$GITHUB_STEP_SUMMARY (stdout when unset); 2 a usage error, caught by argparse
before any subcommand body runs. A refusal never writes `--out`: a commit id no
check certified is one a later step would push.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from hashlib import sha256

SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A git object id, sha-1 or sha-256 — what a listing hands back and what
# `cat-file --batch` is fed. Nothing else becomes a name this script reads.
OBJECT_ID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
DRIVE_LETTER = re.compile(r"^[A-Za-z]:")

# The modes a document may be stored under. A `120000` entry is a symlink,
# whose blob content is the path it points at — bytes that would digest as some
# other document's — and `160000` is a submodule. Neither is something the
# applier writes, so neither is something this lane certifies.
REGULAR_MODES = ("100644", "100755")

# git, invoked exactly as `doclifecycle/repository.py` invokes it: the
# repository named on the command line and no other, and no environment
# variable left that could redirect it at another tree.
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

# A local object-store read is milliseconds. Anything near this is a hung git,
# and hanging a credentialed job is a worse answer than a typed refusal.
TIMEOUT_SECONDS = 30

STAGE_INDEX = "staging"
STAGE_COMMIT = "commit"


# -- the run surface ---------------------------------------------------------

def write_surface(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def quoted(value):
    """One JSON string, for a value this script did not shape-check.

    Everything else it prints — a repository-relative path, a sha256, a git
    mode — is refused before it is rendered, so a plain code span around one
    cannot be escaped from. git's own stderr is the exception: it is a line
    from another program, and `json.dumps` escapes every control character in
    it rather than letting one restructure the page a reviewer reads.
    """
    return json.dumps(value if isinstance(value, str) else str(value))


def refuse(stage, code, message, details=()):
    """Render one typed refusal and return the lane's exit status.

    Worded for where this runs: by the staging boundary a local branch exists,
    so the honest claim is not "no branch" but that nothing left this runner.
    """
    lines = [
        f"## Doc apply: REFUSED at {stage}",
        "",
        f"- `{code}`: {message}",
    ]
    lines += [f"  - {d}" for d in details]
    lines += [
        "",
        "**Nothing was pushed and no pull request was created.** This run "
        "could not certify that what git holds is what the applier verified, "
        "so it will not publish it as approved. Inspect the checkout, then "
        "re-run the audit and mint afresh.",
        "",
    ]
    write_surface("\n".join(lines))
    return 1


# -- git ---------------------------------------------------------------------

def git(repo, *args, stdin=None):
    """Read-only git in `repo`. Returns (stdout bytes, None) or (None, detail).

    Bytes throughout, never text: a stored blob is compared byte for byte, and
    decoding it — or letting git translate its line endings — would make the
    comparison answer about a rendering rather than about the object. No shell,
    a fixed argv, and a timeout, for the reasons `repository.py` gives.
    """
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTING_VARS}
    try:
        result = subprocess.run(
            ["git", "-C", repo, *args],
            input=stdin, capture_output=True, env=env, timeout=TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return None, f"git is not available ({exc.strerror})"
    except subprocess.TimeoutExpired:
        return None, f"git {args[0]} did not finish in {TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        return None, (detail[0] if detail else f"git {args[0]} failed")
    return result.stdout, None


def _nul_fields(out):
    """A `-z` listing's entries, the trailing empty one dropped."""
    return [entry for entry in out.split(b"\0") if entry]


def _listing(stage, repo, args, what):
    """({path: (mode, object id)}, None) for one git listing, or (None, status).

    `ls-files --stage` writes `mode oid stage`, `ls-tree -r` writes
    `mode type oid`, and both put the path after a tab — so the mode is the
    first field and the object id is the one field shaped like one. Read that
    way, neither format needs its own parser and neither can be read as the
    other's.

    A path git cannot hand back as valid UTF-8 is not one the applier wrote,
    and is refused rather than replaced: a lossy decode would compare a
    different name than the one git holds. A path listed twice is an unmerged
    index, whose entries are several competing versions of one document — not
    something a lane that commits one reviewed change may pick between.
    """
    out, detail = git(repo, *args)
    if detail is not None:
        return None, refuse(
            stage, "apply-git-listing-unavailable",
            f"git could not list the {what}, so what it holds cannot be "
            f"compared with what the applier certified",
            [quoted(detail)])
    entries = {}
    for entry in _nul_fields(out):
        info, tab, name = entry.partition(b"\t")
        if not tab:
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing carries an entry with no path in it",
                [quoted(entry.decode("utf-8", "replace"))])
        try:
            path = name.decode("utf-8")
        except UnicodeDecodeError:
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing names a path that is not valid UTF-8, "
                f"so it cannot be compared with a certified one",
                [quoted(name.decode("utf-8", "replace"))])
        if path in entries:
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing carries `{path}` more than once, so "
                f"which bytes it holds there is not a question with one answer")
        fields = [field.decode("ascii", "replace") for field in info.split()]
        oids = [field for field in fields if OBJECT_ID.match(field)]
        entries[path] = (fields[0] if fields else "",
                         oids[0] if oids else "")
    return entries, None


def _blobs(stage, repo, oids, what):
    """({object id: bytes}, None) for every id in `oids`, or (None, status).

    Object ids, never `:path` or `<commit>:path`: the ids come from the listing
    already read, so nothing this script hands git has to be parsed as a
    revision. They travel on stdin rather than in argv for the same reason —
    there is no position there an id could be read from as an option.
    """
    wanted = sorted(set(oids))
    if not wanted:
        return {}, None
    for oid in wanted:
        if not OBJECT_ID.match(oid):
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing names {quoted(oid)} where an object id "
                f"belongs")
    out, detail = git(repo, "cat-file", "--batch",
                      stdin="".join(f"{oid}\n" for oid in wanted).encode())
    if detail is not None:
        return None, refuse(
            stage, "apply-git-listing-unavailable",
            f"git could not read the {what}'s stored content, so it cannot be "
            f"compared with what the applier certified",
            [quoted(detail)])

    blobs, cursor = {}, 0
    for oid in wanted:
        end = out.find(b"\n", cursor)
        if end < 0:
            return None, refuse(
                stage, "apply-git-object-unreadable",
                f"git's batch read of the {what} ended mid-header")
        header = out[cursor:end].decode("utf-8", "replace").split()
        cursor = end + 1
        if len(header) != 3 or header[1] != "blob":
            return None, refuse(
                stage, "apply-git-object-unreadable",
                f"git reports {quoted(header[0] if header else '')} as "
                f"{quoted(' '.join(header[1:]))} — a document is stored as a "
                f"blob, and nothing else is content this lane may certify")
        size = int(header[2]) if header[2].isdigit() else -1
        if size < 0 or cursor + size > len(out):
            return None, refuse(
                stage, "apply-git-object-unreadable",
                f"git's batch read of the {what} declares a length its output "
                f"does not carry")
        blobs[oid] = out[cursor:cursor + size]
        cursor += size + 1
    return blobs, None


# -- the certified manifest --------------------------------------------------

def read_json(path):
    """(payload, None) or (None, reason)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc.strerror}"
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"{path} is not readable JSON: {exc}"


def _unsafe_path_reason(path):
    """Why `path` must not be compared as a repository document, or None.

    A third reading of a string `paths.authorize_path` and
    `render-apply-summary.py`'s `_unsafe_path_reason` have each already read,
    at the boundary where it stops being data and starts naming a git object.
    Deliberately not the full authorization check — that has one owner — only
    the shapes that are dangerous *here*: a path that is not canonically and
    printably spelled cannot be matched against a listing git wrote, and a
    mismatch that silently reads as "absent" would certify a deletion nobody
    approved.
    """
    if not isinstance(path, str) or not path:
        return "not a path"
    for ch in path:
        category = unicodedata.category(ch)
        if category in ("Cc", "Cf", "Cs", "Co", "Cn"):
            return "holds a control character"
        if category in ("Zl", "Zp"):
            return "holds a line or paragraph separator"
    if path.startswith("-"):
        return "starts with a dash, which git reads as an option"
    if path.startswith("/") or path.startswith("~") or DRIVE_LETTER.match(path):
        return "is not repository-relative"
    if "\\" in path:
        return "uses a backslash separator"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "is not canonically spelled"
    return None


def manifest(stage, result_path):
    """(the applier's verified postimage manifest, None), or (None, status).

    The manifest is the *engine's* certification and the only authority this
    script compares against: `{path: sha256 of the bytes read back}`, `None`
    for a document the run retired. A result that carries none certifies
    nothing, so there is nothing here to check bytes against — which is a
    refusal, never a boundary quietly skipped.
    """
    res, reason = read_json(result_path)
    if res is None:
        return None, refuse(stage, "apply-result-unreadable", reason)
    if res.get("status") != "clean":
        return None, refuse(
            stage, "apply-result-not-clean",
            f"the applier returned `{res.get('status')}` — only a clean apply "
            f"certifies postimages, and only certified bytes may be committed")

    postimages = res.get("postimages")
    if not isinstance(postimages, dict) or not postimages:
        return None, refuse(
            stage, "apply-postimages-absent",
            "the apply result carries no verified postimage manifest — the "
            "applier certifies one for every clean run, so this result came "
            "from an engine that cannot certify what it wrote, and this lane "
            "will not publish bytes nothing verified")

    bad = []
    for path, digest in sorted(postimages.items()):
        why = _unsafe_path_reason(path)
        if why is not None:
            bad.append(f"`{path if isinstance(path, str) else quoted(path)}` {why}")
        elif not (digest is None or (isinstance(digest, str)
                                     and SHA256.match(digest))):
            bad.append(f"`{path}` carries {quoted(digest)} where a sha256 or "
                       f"null belongs")
    if bad:
        return None, refuse(
            stage, "apply-postimages-malformed",
            "the verified postimage manifest is not a map of repository "
            "documents to the sha256 of their bytes", bad)

    # Path confinement, the half that is not about bytes: everything the run
    # reported changing must be something it also certified. A path in the
    # staged set with no manifest entry has no certified bytes to be compared
    # against, so it would ride into the commit unchecked. A `changed_paths`
    # that is not a list is not a path set at all, and reading one out of it
    # would answer this question about something else.
    changed = res.get("changed_paths") or []
    if not isinstance(changed, list) or any(
            not isinstance(p, str) for p in changed):
        return None, refuse(
            stage, "apply-result-unreadable",
            "the apply result does not name the paths it changed as a list of "
            "documents, so what it wrote cannot be compared with what it "
            "certified")
    uncertified = sorted(set(changed) - set(postimages))
    if uncertified:
        return None, refuse(
            stage, "apply-changed-path-uncertified",
            "the apply result reports changing path(s) its postimage manifest "
            "does not certify, so their bytes rest on nothing",
            [f"`{p}`" for p in uncertified])
    return postimages, None


# -- the comparison ----------------------------------------------------------

def compare(stage, repo, entries, postimages, what):
    """Every manifest entry against one git listing. Returns an exit status.

    Exhaustively, as the engine reports its own problems: a reader fixing one
    path at a time learns nothing about the second. Present-and-different,
    present-when-it-should-be-absent, and absent-when-it-should-be-present are
    three distinct answers and each gets its own line.
    """
    absent, present = [], {}
    for path, digest in sorted(postimages.items()):
        entry = entries.get(path)
        if digest is None:
            # A retired document. Its certified final state is its absence,
            # and an index or a tree that still carries it would commit the
            # document the approval retired.
            if entry is not None:
                absent.append(
                    f"`{path}` was retired by this apply and the {what} still "
                    f"carries it")
            continue
        if entry is None:
            absent.append(
                f"`{path}` was written by this apply and the {what} does not "
                f"carry it")
            continue
        mode, oid = entry
        if mode not in REGULAR_MODES:
            absent.append(
                f"`{path}` is stored with mode `{mode}` — a document is a "
                f"regular file, and a symlink or submodule entry is not "
                f"content the applier wrote")
            continue
        present[path] = (oid, digest)

    blobs, bad = _blobs(stage, repo, [oid for oid, _ in present.values()], what)
    if bad is not None:
        return bad

    mismatched = []
    for path, (oid, digest) in sorted(present.items()):
        stored = blobs.get(oid)
        if stored is None or sha256(stored).hexdigest() != digest:
            mismatched.append(
                f"`{path}`: the applier certified `{digest}`, and the {what} "
                f"holds `"
                + (sha256(stored).hexdigest() if stored is not None else "?")
                + "`")

    if absent or mismatched:
        return refuse(
            stage, "apply-bytes-not-certified",
            f"the {what} is not what the applier certified — git holds "
            f"different bytes than the apply result verified on disk, so "
            f"something rewrote an approved document (a `clean`/`smudge` "
            f"filter, an end-of-line attribute, a hook, or another writer) "
            f"after the engine read it back",
            absent + mismatched)
    return 0


# -- subcommands -------------------------------------------------------------

def verify_index(args):
    """The staged index, against the certified manifest.

    Run after `render-apply-summary.py verify-staged` has settled which *paths*
    got staged, and before the commit. Every manifest entry is checked, not
    only the staged ones: a path the plan wrote to the bytes it already had
    produces no diff and so is never staged, and the index must still carry the
    certified content for the commit to be the approved change.
    """
    postimages, bad = manifest(STAGE_INDEX, args.result)
    if bad is not None:
        return bad
    entries, bad = _listing(
        STAGE_INDEX, args.repo, ("ls-files", "--stage", "-z"), "index")
    if bad is not None:
        return bad
    return compare(STAGE_INDEX, args.repo, entries, postimages, "index")


def verify_commit(args):
    """The commit tree, against the certified manifest — then name that commit.

    The last check before anything leaves the runner, and the reason it exists
    is that the index it re-reads is not the one `index` verified: `git commit`
    runs hooks, and a `pre-commit` that rewrote and re-staged a target would
    have moved the tree in between. What this writes to `--out` is the commit
    id it verified, and the push names that id — so the commit that lands is
    provably the tree that passed, not whatever `HEAD` points at by then.
    """
    postimages, bad = manifest(STAGE_COMMIT, args.result)
    if bad is not None:
        return bad

    out, detail = git(args.repo, "rev-parse", "--verify", "--end-of-options",
                      "HEAD^{commit}")
    if detail is not None:
        return refuse(
            STAGE_COMMIT, "apply-commit-unreadable",
            "the commit this run just made cannot be resolved, so there is no "
            "tree to verify and nothing safe to push", [quoted(detail)])
    commit = out.decode("ascii", "replace").strip()
    if not OBJECT_ID.match(commit):
        return refuse(
            STAGE_COMMIT, "apply-commit-unreadable",
            f"git resolved HEAD to {quoted(commit)}, which is not a commit id")

    # `commit` reaches the reads below where an option would, so it is the
    # `OBJECT_ID` gate above — not a `--` separator, which only says where
    # pathspecs start — that makes it a revision rather than a flag. The same
    # reasoning `repository.changed_paths` states about a diff baseline.
    lineage, detail = git(args.repo, "rev-list", "--parents", "-n", "1", commit)
    if detail is not None:
        return refuse(
            STAGE_COMMIT, "apply-commit-unreadable",
            "the commit's parentage cannot be read, so what it changed cannot "
            "be established", [quoted(detail)])
    parents = lineage.decode("ascii", "replace").split()[1:]
    if len(parents) != 1:
        # The diff below is against the one parent this lane's commit has.
        # A merge (or a root commit) is a different shape of change, and this
        # lane never makes one.
        return refuse(
            STAGE_COMMIT, "apply-commit-not-linear",
            f"the commit has {len(parents)} parent(s) — this lane commits one "
            f"reviewed change onto the base it checked out, and anything else "
            f"is a change nobody approved the shape of")

    # Path confinement at the commit boundary, the counterpart to
    # `verify-staged` at the index: the *whole* diff this commit carries must
    # lie inside what the applier certified. Byte binding below cannot answer
    # this — a path outside the manifest has no certified bytes at all.
    diff, detail = git(args.repo, "diff-tree", "-r", "--no-commit-id",
                       "--name-only", "-z", "--no-renames", commit, "--")
    if detail is not None:
        return refuse(
            STAGE_COMMIT, "apply-commit-unreadable",
            "the commit's own diff cannot be read, so whether it is confined "
            "to the approved paths is unanswerable", [quoted(detail)])
    changed = sorted(
        entry.decode("utf-8", "replace") for entry in _nul_fields(diff))
    outside = [p for p in changed if p not in postimages]
    if outside:
        return refuse(
            STAGE_COMMIT, "apply-commit-not-confined",
            "the commit changes path(s) the applier never certified — the "
            "tree that would be pushed is not the change this run verified",
            [f"`{p}`" for p in outside])

    entries, bad = _listing(
        STAGE_COMMIT, args.repo,
        ("ls-tree", "-r", "-z", "--full-tree", commit, "--"),
        "commit tree")
    if bad is not None:
        return bad
    status = compare(
        STAGE_COMMIT, args.repo, entries, postimages, "commit tree")
    if status != 0:
        return status

    # Written only now: a commit id this file carries is one the push names,
    # so it must never exist for a tree no check certified.
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"{commit}\n")
    write_surface(
        f"\n**Commit tree verified:** `{commit}` holds exactly the "
        f"{len(postimages)} certified postimage(s); it is the commit this run "
        f"pushes.\n")
    return 0


# -- argv --------------------------------------------------------------------

def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    index = sub.add_parser("index")
    index.add_argument("--result", required=True)
    index.add_argument("--repo", default=".")
    index.set_defaults(run=verify_index)

    commit = sub.add_parser("commit")
    commit.add_argument("--result", required=True)
    commit.add_argument("--repo", default=".")
    commit.add_argument("--out", required=True)
    commit.set_defaults(run=verify_commit)

    return parser


def main():
    args = _parser().parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
