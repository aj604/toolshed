#!/usr/bin/env python3
"""Run-surface rendering for the doc-sync pipeline.

This script owns user-facing strings — step summaries and PR/issue bodies — so
a caller's self-explaining exits are unit-testable instead of living as
jq/heredoc templates in YAML. Its callers are doc-sync-upgrade.yml
(`upgrade-summary`, `upgrade-pr-body`, `upgrade-notice`) and the
detecting-doc-bloat skill's in-session triage render (`bloat-triage`).

The legacy doc-sync.yml/doc-bloat.yml write lanes had their own subcommands
here (pre-summary, issue-body, pr-body, the remaining bloat-* variants, and
more); both lanes and every non-triage rendering path were removed in
aj604/toolshed#77 — the new engine's render-audit-summary.py and
render-apply-summary.py own that run surface now.

Usage:
    render-report.py bloat-triage --report FILE
    render-report.py upgrade-summary --status S --current C --latest L [--pr-url URL] [--files F]
    render-report.py upgrade-pr-body --current C --latest L [--files F]
    render-report.py upgrade-notice --current C --latest L --repo OWNER/NAME [--workflow NAME] --title-out FILE --body-out FILE

Exit status: 0 on success; 2 on bad input.
"""

import argparse
import json
import os
import sys


def load_report(path):
    """(records, unswept-or-None) from a report file, either shape."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"], data.get("unswept")
    raise ValueError(
        "report must be a JSON array of records, or an object with a 'records' array"
    )


def render_unswept_banner(unswept):
    """The loud gap: chunks the sweep never produced a valid result for."""
    if not unswept:
        return []
    docs = [p for u in unswept for p in u.get("docs", [])]
    return [
        f"> ⚠️ **{len(unswept)} chunk(s) unswept** — these docs were NOT "
        f"audited this run (their sweep jobs failed twice); the next sweep "
        f"resumes them automatically: {', '.join(f'`{d}`' for d in docs)}",
        "",
    ]


def md_cell(text):
    # Cells escape | and flatten newlines so evidence can't break its row.
    return str(text).replace("|", "\\|").replace("\n", " ")


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)


def render_bloat_rollup(records):
    counts, docs = {}, set()
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        docs.add(r["doc"])
    order = ["CUT", "CONDENSE", "EXTRACT-AND-MOVE", "RETIRE-DOC",
             "MERGE-DOC", "DISTILL", "POLICY"]
    parts = [f"{v.lower().replace('-', ' ')} {counts[v]}" for v in order if v in counts]
    return (f"**Rollup:** {len(records)} record(s) across {len(docs)} doc(s) — "
            + ", ".join(parts))


def render_bloat_triage(records, unswept=None):
    """In-session triage view: rollup, then records grouped by doc, one line
    per record — the human approves by the [id]s shown."""
    by_doc = {}
    for r in records:
        by_doc.setdefault(r["doc"], []).append(r)
    lines = [*render_unswept_banner(unswept), render_bloat_rollup(records), ""]
    for doc in sorted(by_doc):
        lines.append(doc)
        for r in by_doc[doc]:
            verdict = r["verdict"]
            if verdict == "DISTILL":
                verdict = f"DISTILL({r.get('status')})"
            where = r.get("location") or ""
            extra = f" ({len(r.get('files') or [])} files)" if r["verdict"] == "POLICY" else ""
            lines.append(f"  [{r['id']}] {verdict:<14} {where}{extra} — "
                         f"{md_cell(r['evidence'])}")
    return "\n".join(lines)


def _upgrade_apply_instructions(latest):
    # `git apply --index` so a patch that creates and deletes files lands whole;
    # `commit -am` would miss both.
    return ("```\n"
            "git switch -c doc-sync/upgrade\n"
            "git apply --index doc-sync-upgrade.patch\n"
            f"git commit -m 'docs: upgrade doc-sync wiring to plugin v{latest}'\n"
            "git push -u origin doc-sync/upgrade   # then open a PR\n"
            "```\n\n")


def render_upgrade_summary(status, current, latest, pr_url, files=""):
    if status == "blocked-workflows":
        changed = [f for f in files.split(",") if f]
        wf = [f for f in changed if f.startswith(".github/workflows/")]
        wf_list = ", ".join(f"`{f}`" for f in wf) or "workflow files"
        return (
            f"🛑 **Upgrade `{current}` → `{latest}` needs a manual apply.** It regenerated "
            f"{wf_list}, and GitHub forbids the Actions token from pushing changes under "
            "`.github/workflows/` (the `workflows` permission is not grantable to it). The "
            "full diff is attached as the **`doc-sync-upgrade-patch`** run artifact. Apply it "
            "from a local checkout with a credential that has the `workflow` scope:\n\n"
            + _upgrade_apply_instructions(latest) +
            "Routine version-only upgrades don't hit this — they change only "
            "`.doc-lifecycle/installed-version`, which the token can push.")
    if status == "blocked-relocation":
        return (
            f"📦 **Upgrade `{current}` → `{latest}` moves this install, and needs a manual "
            "apply.** doc-lifecycle now keeps everything it owns under `.doc-lifecycle/` — "
            "your judgment files (`registry.json`, `audit-scope.json`, `drift-waivers.json`, "
            "`evidence-tools.json`) at its root, the regenerated machinery under "
            "`.doc-lifecycle/wiring/`, and the sync marker under `.doc-lifecycle/state/`. "
            "`.github/doc-sync/` and `.github/doc-sync-marker` go away; only the workflow "
            "YAML stays in `.github/`.\n\n"
            "This is a one-time move, not a routine version bump, and it needs your hands "
            "for the same reason a template change does: it rewrites files under "
            "`.github/workflows/`, which the Actions token may not push. The complete patch "
            "— every creation, every deletion — is attached as the "
            "**`doc-sync-upgrade-patch`** run artifact. Apply it from a local checkout with "
            "a credential that has the `workflow` scope:\n\n"
            + _upgrade_apply_instructions(latest) +
            "Your configuration is carried across byte-for-byte; nothing in "
            "`.github/doc-sync/` that this upgrade does not own was touched, and the step "
            "log names anything it left behind.")
    if status == "current":
        return (f"✅ **doc-sync wiring is current.** Installed `{current}`, latest "
                f"release `{latest}` — nothing to upgrade.")
    if status == "ahead":
        return (f"✅ **doc-sync wiring is ahead of releases.** Installed `{current}` is "
                f"newer than the latest release `{latest}` (a dev/prerelease pin) — no upgrade.")
    if status == "noop":
        return (f"✅ **No wiring change.** Regenerating at `{latest}` (from `{current}`) "
                f"produced no diff — the shipped wiring already matches.")
    if status == "opened":
        return (f"🔁 **Wiring upgrade ready.** `{current}` → `{latest}` regenerated — "
                f"review {pr_url}. Merging advances `.doc-lifecycle/installed-version` "
                f"and re-pins the workflows; closing it re-checks next run.")
    if status == "pending":
        return (f"⏭️ **Upgrade skipped — a `doc-sync/upgrade` PR is already open.** "
                f"Review {pr_url}; the next check resumes after it merges/closes. "
                f"(Installed `{current}`, latest `{latest}`.)")
    if status == "undeclared-paths":
        left = ", ".join(f"`{f}`" for f in files.split(",") if f) or "paths"
        return (
            f"🛑 **Upgrade `{current}` → `{latest}` refused — the regeneration touched "
            f"{left}, which apply-upgrade.py did not declare it wrote.** The lane stages "
            "the declared set by name and commits nothing else, so an undeclared change "
            "is either a bug in apply-upgrade.py's reporting or something else writing "
            "into the work tree. Nothing was committed or pushed. Reproduce locally with "
            "`apply-upgrade.py --report-written` and compare that list against "
            "`git status`.")
    if status == "available":
        return (f"📣 **A newer doc-lifecycle release exists: `{current}` → `{latest}`.** "
                f"This check detects; it does not upgrade. Nothing was cloned and none of "
                f"the release's code ran — a notice issue tracks it, and the upgrade "
                f"happens when a human dispatches this workflow with `target: {latest}`.")
    if status == "notified":
        return (f"⏭️ **Already flagged — `{current}` → `{latest}`.** An open notice issue "
                f"names this release; no second one was filed. Dispatch this workflow with "
                f"`target: {latest}` when you have reviewed the release.")
    if status == "refused":
        return (f"🛑 **Upgrade refused — the regeneration reached outside the wiring.** "
                f"Regenerating `{current}` → `{latest}` changed a path the upgrade engine "
                f"does not own; the step log names every one. Nothing was staged and no "
                f"pull request was opened. Review the release before retrying.\n\n"
                f"If those paths are under `.doc-lifecycle/`, this is the one-time move of "
                f"the install out of `.github/doc-sync/`: the path authority that refused "
                f"is the copy *you* have installed, and it predates the new layout, so it "
                f"cannot authorize a move it has never heard of — which is the trust split "
                f"working, not failing. Relocate from a local checkout by re-running the "
                f"`scheduling-doc-sync` skill in Upgrade mode; this lane resumes routine "
                f"upgrades once the new layout is in place.")
    raise ValueError(f"unknown upgrade status: {status!r}")


# The notice issue's title is the dedupe key: one open issue per release, so a
# weekly check that keeps finding the same unreviewed release keeps quiet.
UPGRADE_NOTICE_TITLE = "doc-sync: doc-lifecycle {latest} is available"


def render_upgrade_notice_title(latest):
    return UPGRADE_NOTICE_TITLE.format(latest=latest)


def render_upgrade_notice_body(current, latest, repo, workflow):
    """The tracking issue the scheduled detection files — a signal, not a change.

    Deliberately an instruction to a human rather than an automated follow-up:
    dispatching the workflow IS the decision that lets the target release's own
    upgrade logic run here, so the issue's job is to make that decision informed
    and easy, never to make it automatically.
    """
    return "\n".join([
        f"This install's doc-sync wiring is pinned to `{current}` "
        f"(`.doc-lifecycle/installed-version`). doc-lifecycle `{latest}` has shipped.",
        "",
        "**Nothing has run.** The weekly check compares two version numbers and stops "
        "there; it does not clone the release and it does not execute its upgrade logic. "
        "A version number is not a reviewable artifact, so the comparison is a "
        "notification, not an authorization.",
        "",
        "**To upgrade**, review the release first — "
        f"https://github.com/{repo}/releases/tag/v{latest} — then run the "
        f"`{workflow}` workflow from the Actions tab with:",
        "",
        "```",
        f"target: {latest}",
        "```",
        "",
        "That dispatch regenerates the wiring in a job holding no token and no write "
        "scope, and a separate credentialed job — which executes none of the release's "
        "code — stages exactly the wiring paths it produced and opens a pull request. "
        "Merging that pull request is what advances the pin.",
        "",
        "Close this issue to stop being reminded about "
        f"`{latest}`; the next release files a new one.",
    ])


def render_upgrade_notice(current, latest, repo, workflow, title_out, body_out):
    """Render the notice issue. Whether to file it is `upgrade-gate.py notice`.

    Strings only, like every other subcommand here: the gate owns decisions and
    this file owns what a human reads. The title it writes is what the gate
    dedupes on, so the two travel through a file rather than a shared literal.
    """
    title = render_upgrade_notice_title(latest)
    with open(title_out, "w", encoding="utf-8") as f:
        f.write(title + "\n")
    with open(body_out, "w", encoding="utf-8") as f:
        f.write(render_upgrade_notice_body(current, latest, repo, workflow) + "\n")
    return title


def render_upgrade_pr_body(current, latest, files):
    lines = [
        f"Self-upgrade: this repo's doc-sync wiring was pinned to `{current}`; "
        f"doc-lifecycle `{latest}` has shipped. Regenerated the wiring at `{latest}` and "
        "re-pinned every workflow's marketplace checkout to it.",
        "",
        "**Preserved unchanged:** the `.doc-lifecycle/state/sync-marker` (sync state), "
        "`.doc-lifecycle/audit-scope.json` and `drift-waivers.json` (tuned config and "
        "accepted waivers), and every install-time knob (the upgrade and audit crons). "
        "Only the wiring and `.doc-lifecycle/installed-version` change.",
    ]
    if files:
        changed = [f for f in files.split(",") if f]
        if changed:
            lines += ["", "**Regenerated files:**"]
            lines += [f"- `{f}`" for f in changed]
    lines += ["", "Merge to adopt the new version; close to stay on "
              f"`{current}` until the next release."]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    btriage = sub.add_parser("bloat-triage")
    btriage.add_argument("--report", required=True)

    usum = sub.add_parser("upgrade-summary")
    usum.add_argument("--status", required=True)
    usum.add_argument("--current", required=True)
    usum.add_argument("--latest", required=True)
    usum.add_argument("--pr-url", default="")
    usum.add_argument("--files", default="")

    upr = sub.add_parser("upgrade-pr-body")
    upr.add_argument("--current", required=True)
    upr.add_argument("--latest", required=True)
    upr.add_argument("--files", default="")

    unot = sub.add_parser("upgrade-notice")
    unot.add_argument("--current", required=True)
    unot.add_argument("--latest", required=True)
    unot.add_argument("--repo", required=True)
    unot.add_argument("--workflow", default="doc-sync-upgrade")
    unot.add_argument("--title-out", required=True)
    unot.add_argument("--body-out", required=True)

    args = parser.parse_args()

    try:
        if args.mode == "upgrade-summary":
            write_summary(render_upgrade_summary(
                args.status, args.current, args.latest, args.pr_url, args.files))
        elif args.mode == "upgrade-pr-body":
            print(render_upgrade_pr_body(args.current, args.latest, args.files))
        elif args.mode == "upgrade-notice":
            print(render_upgrade_notice(
                args.current, args.latest, args.repo, args.workflow,
                args.title_out, args.body_out))
        elif args.mode == "bloat-triage":
            records, unswept = load_report(args.report)
            print(render_bloat_triage(records, unswept))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
