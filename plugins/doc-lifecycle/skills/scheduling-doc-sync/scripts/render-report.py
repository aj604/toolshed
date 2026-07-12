#!/usr/bin/env python3
"""Run-surface rendering for the doc-sync nightly pipeline.

The workflow (doc-sync.yml) gathers facts and performs side effects; sync-gate.py
owns the decisions; this script owns every user-facing string — step summaries,
::notice:: annotations, and issue/PR bodies — so the pipeline's self-explaining
exits are unit-testable instead of living as jq/heredoc templates in YAML.

Usage:
    render-report.py pre-summary --decision D --marker M --head H --commits N --open-prs N --open-issues N
    render-report.py no-drift-summary --commits N --head H [--push-rejected] [--report FILE] [--waivers FILE]
    render-report.py issue-body --report FILE --cap N --marker M --head H
    render-report.py blast-summary --report FILE --cap N --issue-url URL
    render-report.py pr-body --report FILE --marker M --head H [--waivers FILE] [--prev-stales FILE]
    render-report.py pr-title --report FILE --date YYYY-MM-DD [--waivers FILE]
    render-report.py growth-backlog --scope-file docs/doc-scope.md
    render-report.py pr-summary --report FILE --pr-url URL
    render-report.py bloat-pre-summary --decision {detect|skip-pending}
    render-report.py bloat-pr-body --report FILE
    render-report.py bloat-pr-title --report FILE --lane L --date YYYY-MM-DD
    render-report.py bloat-pr-summary --report FILE --lane L --pr-url URL
    render-report.py bloat-skip-summary --lane L --reason {skip-empty|skip-pending|skip-noop}
    render-report.py bloat-triage --report FILE

Body subcommands (issue-body, pr-body) print markdown on stdout for --body-file.
Summary subcommands append to the file named by $GITHUB_STEP_SUMMARY (stdout when
unset) and print ::notice:: annotations on stdout where the old workflow did.

Exit status: 0 on success; 2 on bad input.
"""

import argparse
import json
import os
import sys


def load_records(path):
    return load_report(path)[0]


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


def by_verdict(records, verdict):
    return [r for r in records if isinstance(r, dict) and r.get("verdict") == verdict]


def load_waivers(path):
    """Set of (file, claim) pairs from a drift-waivers file.

    None or a missing file is an empty set — installs seed the file, but its
    absence must not kill the run surface mid-pipeline. A malformed file is an
    error: a typo'd waiver silently un-waiving everything would defeat the
    disposition mechanism.
    """
    if not path:
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return set()
    if not (isinstance(data, dict) and isinstance(data.get("waivers"), list)):
        raise ValueError("waivers file must be an object with a 'waivers' array")
    pairs = set()
    for w in data["waivers"]:
        if not (isinstance(w, dict) and "file" in w and "claim" in w):
            raise ValueError("each waiver needs 'file' and 'claim' fields")
        pairs.add((w["file"], w["claim"]))
    return pairs


RECUR_WINDOW = 3  # lines a claim may drift between runs and still be "the same spot"


def load_prev_stales(path):
    """Prior run's stale-state entries; None or a missing file is empty (first
    proceed run, or an install predating recurrence tracking)."""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    if not (isinstance(data, dict) and isinstance(data.get("stales"), list)):
        raise ValueError("stale-state file must carry a 'stales' array")
    return [s for s in data["stales"] if isinstance(s, dict)]


def is_recurrence(record, prev_stales):
    """Same file, same kind, within RECUR_WINDOW lines of a prior-run STALE.

    Line-window matching, not claim text: the previous fix rewrote the line,
    so a re-stale carries new text at nearly the same location.
    """
    loc = str(record.get("location", ""))
    file, _, line = loc.rpartition(":")
    try:
        line_no = int(line)
    except ValueError:
        return False
    for s in prev_stales:
        try:
            prev_line = int(s.get("line"))
        except (TypeError, ValueError):
            continue
        if (s.get("file") == file and s.get("kind") == record.get("kind")
                and abs(prev_line - line_no) <= RECUR_WINDOW):
            return True
    return False


def split_waived(records, waivers):
    """(unwaived, waived) UNVERIFIABLE records under a (file, claim) waiver set.

    Identity is exact claim text — a reworded claim resurfaces by design; new
    authorship is a new disposition decision.
    """
    unwaived, waived = [], []
    for r in by_verdict(records, "UNVERIFIABLE"):
        key = (str(r["location"]).rsplit(":", 1)[0], r["claim"])
        (waived if key in waivers else unwaived).append(r)
    return unwaived, waived


def load_merge(path):
    """plan-distill.py --merge summary: {'applied': [ids], 'unapplied': [...]}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not (isinstance(data, dict) and isinstance(data.get("applied"), list)
            and isinstance(data.get("unapplied"), list)):
        raise ValueError(
            "merge summary must carry 'applied' and 'unapplied' arrays")
    return data


def render_unapplied_banner(unapplied):
    """The loud gap: lane records the distill merge could not land."""
    if not unapplied:
        return []
    items = ", ".join(f"`{u['id']}` ({md_cell(u['reason'])})"
                      for u in unapplied)
    return [
        f"> ⚠️ **{len(unapplied)} record(s) not landed this run** — proposed "
        f"by the sweep but not applied; the next sweep re-proposes them: "
        f"{items}",
        "",
    ]


def render_distill_merge_summary(merge):
    n, u = len(merge["applied"]), len(merge["unapplied"])
    if u == 0:
        return f"🧬 **Distill merge:** all {n} record(s) landed."
    return (f"🧬 **Distill merge:** {n} record(s) landed, {u} not landed — "
            f"reasons in the PR body; the next sweep re-proposes them.")


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)


def notice(text):
    print(f"::notice::{text}")


def render_pre_summary(args):
    if args.decision == "skip-empty":
        notice("doc-sync skipped: nothing new since the marker")
        write_summary(
            f"⏭️ **Skipped — nothing to sync.** No commits (beyond marker bookkeeping) "
            f"since marker `{args.marker}`. No model calls were made."
        )
    elif args.decision == "skip-pending":
        notice("doc-sync skipped: a doc-sync PR/issue awaits a human")
        write_summary(
            f"⏭️ **Skipped — pending human review.** Open doc-sync PRs: {args.open_prs}, "
            f"open `doc-sync` issues: {args.open_issues}. The nightly resumes after they "
            f"are merged/closed. No model calls were made."
        )
    elif args.decision == "detect":
        write_summary(
            f"▶️ **Checking {args.commits} commit(s)** for doc drift over "
            f"`{args.marker}..{args.head}`."
        )
    else:
        raise ValueError(f"unknown pre-gate decision: {args.decision!r}")


def render_no_drift_summary(args):
    if args.push_rejected:
        notice(
            "marker push rejected (branch protection?) — marker will advance with the "
            "next doc-sync PR"
        )
        write_summary(
            f"✅ **No drift** ({args.commits} commit(s) checked) — but the marker push "
            f"was rejected (branch protection?); it will advance with the next doc-sync PR."
        )
    else:
        write_summary(
            f"✅ **No drift.** {args.commits} commit(s) checked, all doc claims still "
            f"hold; marker advanced to `{args.head}`."
        )
    # The quiet-night surface: UNVERIFIABLE records ride no PR on a no-drift
    # run, so this summary is the only place a human ever sees them.
    report = getattr(args, "report", None)
    if report:
        records = load_records(report)
        waivers_path = getattr(args, "waivers", None)
        unwaived, _ = split_waived(records, load_waivers(waivers_path))
        if unwaived:
            hint = waivers_path or ".github/doc-sync/drift-waivers.json"
            write_summary(
                f"🔎 **{len(unwaived)} unverifiable claim(s) await disposition** — "
                f"reword or cut the doc line, or waive it in `{hint}` to accept "
                f"it permanently."
            )


def render_issue_body(records, cap, marker, head):
    lines = [
        f"Nightly doc-sync found more stale claims than the blast-radius cap ({cap}) "
        f"over `{marker}..{head}`.",
        "Per the doc-lifecycle guardrails this is escalated instead of opened as a giant PR.",
        "The sync marker was NOT advanced; close this issue after handling to let the "
        "nightly resume.",
        "",
        "## Stale claims",
    ]
    for r in by_verdict(records, "STALE"):
        lines.append(f"- `{r['location']}` — {r['claim']}")
        lines.append(f"  - **evidence:** {r['evidence']}")
        lines.append(f"  - **drafted fix:** {r['fix']}")
    return "\n".join(lines)


def render_blast_summary(records, cap, issue_url):
    stale = len(by_verdict(records, "STALE"))
    return (
        f"🛑 **Blast-radius stop.** {stale} stale claims exceed the cap ({cap}) — "
        f"escalated as {issue_url} instead of a giant PR. Marker NOT advanced; the "
        f"nightly resumes when the issue is closed."
    )


def md_cell(text):
    # Cells escape | and flatten newlines so evidence can't break its row.
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_pr_body(records, marker, head, waivers=None, waivers_path=None,
                   prev_stales=None):
    lines = [
        f"Nightly doc sync over `{marker}..{head}` — merge to advance the marker, "
        "close to re-check next run.",
        "",
        "| Fixed (see diff) | Why it was stale |",
        "|---|---|",
    ]
    recurred = 0
    for r in by_verdict(records, "STALE"):
        tag = ""
        if prev_stales and is_recurrence(r, prev_stales):
            tag = " ⟳ **recurred**"
            recurred += 1
        lines.append(f"| `{r['location']}`{tag} | {md_cell(r['evidence'])} |")
    if recurred:
        lines.append("")
        lines.append(
            f"⟳ {recurred} location(s) were STALE in the previous sync too — "
            f"recurring drift at one spot is a shape problem, not a fix problem: "
            f"consider replacing the snapshot with a pointer to the source "
            f"(writing-docs), instead of another re-fix.")
    if waivers is None:
        unverifiable, waived = by_verdict(records, "UNVERIFIABLE"), []
    else:
        unverifiable, waived = split_waived(records, waivers)
    if unverifiable:
        lines.append("")
        lines.append("| Flagged for a human — not edited | Why unverifiable |")
        lines.append("|---|---|")
        for r in unverifiable:
            lines.append(f"| `{r['location']}` | {md_cell(r['evidence'])} |")
    if waivers is not None:
        notes = []
        if unverifiable:
            notes.append(
                f"To accept a flagged line permanently, add its `file` + `claim` "
                f"to `{waivers_path}` — it stops appearing here.")
        if waived:
            notes.append(f"{len(waived)} waived claim(s) suppressed "
                         f"(`{waivers_path}`).")
        if notes:
            lines.append("")
            lines.extend(notes)
    return "\n".join(lines)


def render_pr_title(records, date, waivers=None):
    stale = len(by_verdict(records, "STALE"))
    if waivers is None:
        flagged = len(by_verdict(records, "UNVERIFIABLE"))
    else:
        flagged = len(split_waived(records, waivers)[0])
    title = "docs: nightly sync — 1 fix" if stale == 1 else f"docs: nightly sync — {stale} fixes"
    if flagged > 0:
        title += f", {flagged} flagged"
    return f"{title} ({date})"


def render_pr_summary(records, pr_url):
    stale = len(by_verdict(records, "STALE"))
    return (
        f"📝 **Drift found and fixed.** {stale} stale claim(s) corrected — review "
        f"{pr_url}. Merging it advances the marker; closing it unmerged re-checks the "
        f"range next night."
    )


def parse_deferred(scope_text):
    """[(item, [seen lines])] from doc-scope.md's ## Deferred section.

    Tolerant by design: the file is human-edited; a parse miss must degrade to
    an incomplete list, never a failed run."""
    items = []
    in_deferred = False
    for line in scope_text.splitlines():
        if line.startswith("## "):
            in_deferred = line.strip().lower() == "## deferred"
            continue
        if not in_deferred:
            continue
        stripped = line.strip()
        if line.startswith("- "):
            items.append((line[2:].strip(), []))
        elif stripped.startswith("- seen:") and items:
            items[-1][1].append(stripped[2:].split("<!--")[0].strip())
    return items


def render_growth_backlog(scope_path):
    """The weekly grow-loop surface: deferred docs and their fired tallies."""
    try:
        with open(scope_path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return (f"🌱 Growth backlog: no doc-scope.md at `{scope_path}` — "
                f"bootstrapping-docs/growing-docs write it; nothing recorded yet.")
    items = parse_deferred(text)
    if not items:
        return "🌱 Growth backlog: empty — no deferred docs awaiting a signal."
    lines = [
        f"🌱 **Growth backlog: {len(items)} deferred doc(s)** (`{scope_path}`) — "
        f"deliberate deferrals awaiting their promotion signal:"]
    for item, seens in items:
        lines.append(f"- {item}")
        for s in seens:
            lines.append(f"  - {s} — **next occurrence promotes** (growing-docs)")
    return "\n".join(lines)


def render_bloat_pre_summary(decision):
    if decision == "detect":
        return "▶️ **Weekly doc-bloat sweep** — auditing every doc (incl. `docs/plans/`)."
    if decision == "skip-pending":
        return ("⏭️ **Skipped — both bloat PRs are open.** `doc-bloat/prune` and "
                "`doc-bloat/distill` await review; the sweep resumes after they merge/close.")
    raise ValueError(f"unknown bloat-pre decision: {decision!r}")


def bloat_change_cell(r):
    where = r.get("location") or r.get("doc")
    verdict = r["verdict"]
    if verdict == "DISTILL":
        verdict = f"DISTILL({r.get('status')})"
    cell = f"`{verdict}` @ `{where}`"
    if r["verdict"] == "POLICY":
        cell += f" ({len(r.get('files') or [])} files)"
    return cell


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


def render_bloat_pr_body(records, unswept=None, merge=None):
    unapplied = (merge or {}).get("unapplied") or []
    if unapplied:
        preamble = ("Proposed by the weekly doc-bloat sweep — applied rows "
                    "land in the diff below; the banner lists what could not "
                    "be landed this run. Draft PR: review, drop any commit "
                    "you don't want, merge to accept.")
    else:
        preamble = ("Proposed by the weekly doc-bloat sweep — each row is "
                    "applied in the diff below. Draft PR: review, drop any "
                    "commit you don't want, merge to accept.")
    lines = [
        preamble,
        "",
        *render_unswept_banner(unswept),
        *render_unapplied_banner(unapplied),
        render_bloat_rollup(records),
        "",
        "| Change (see diff) | Why it's bloat |",
        "|---|---|",
    ]
    for r in records:
        lines.append(f"| {bloat_change_cell(r)} | {md_cell(r['evidence'])} |")
    return "\n".join(lines)


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


def render_bloat_pr_title(records, lane, date):
    n = len(records)
    noun = "change" if n == 1 else "changes"
    return f"docs: bloat {lane} — {n} {noun} ({date})"


def render_bloat_pr_summary(records, lane, pr_url):
    n = len(records)
    return (f"🧹 **Bloat sweep — {lane} lane.** {n} proposed change(s) — review {pr_url}. "
            f"Draft PR: merge to accept, close to discard.")


def render_bloat_skip_summary(lane, reason):
    msgs = {
        "skip-empty": f"✅ **{lane} lane: nothing to propose.** The sweep found no {lane} findings.",
        "skip-pending": f"⏭️ **{lane} lane skipped.** An open `doc-bloat/{lane}` PR awaits review.",
        "skip-noop": (f"✅ **{lane} lane: no diff to propose.** The approved {lane} records "
                      f"produced no change — already applied, or every claim failed re-verification."),
    }
    if reason not in msgs:
        raise ValueError(f"unknown skip reason: {reason!r}")
    return msgs[reason]


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
            "```\n"
            "git switch -c doc-sync/upgrade\n"
            "git apply doc-sync-upgrade.patch\n"
            f"git commit -am 'docs: upgrade doc-sync wiring to plugin v{latest}'\n"
            "git push -u origin doc-sync/upgrade   # then open a PR\n"
            "```\n\n"
            "Routine version-only upgrades don't hit this — they change only "
            "`.github/doc-sync/installed-version`, which the token can push.")
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
                f"review {pr_url}. Merging advances `.github/doc-sync/installed-version` "
                f"and re-pins the workflows; closing it re-checks next run.")
    if status == "pending":
        return (f"⏭️ **Upgrade skipped — a `doc-sync/upgrade` PR is already open.** "
                f"Review {pr_url}; the next check resumes after it merges/closes. "
                f"(Installed `{current}`, latest `{latest}`.)")
    raise ValueError(f"unknown upgrade status: {status!r}")


def render_upgrade_pr_body(current, latest, files):
    lines = [
        f"Self-upgrade: this repo's doc-sync wiring was pinned to `{current}`; "
        f"doc-lifecycle `{latest}` has shipped. Regenerated the wiring at `{latest}` and "
        "re-pinned every workflow's marketplace checkout to it.",
        "",
        "**Preserved unchanged:** the `.github/doc-sync-marker` (sync state), "
        "`.github/doc-sync/audit-scope.json` (tuned config), and every install-time knob "
        "(cron / blast-radius cap / bloat & upgrade crons). Only the wiring and "
        "`.github/doc-sync/installed-version` change.",
    ]
    if files:
        changed = [f for f in files.split(",") if f]
        if changed:
            lines += ["", "**Regenerated files:**"]
            lines += [f"- `{f}`" for f in changed]
    lines += ["", "Merge to adopt the new version; close to stay on "
              f"`{current}` until the next release."]
    return "\n".join(lines)


def nonneg(value):
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    pre = sub.add_parser("pre-summary")
    pre.add_argument("--decision", required=True)
    pre.add_argument("--marker", required=True)
    pre.add_argument("--head", required=True)
    pre.add_argument("--commits", type=nonneg, required=True)
    pre.add_argument("--open-prs", type=nonneg, required=True)
    pre.add_argument("--open-issues", type=nonneg, required=True)

    nodrift = sub.add_parser("no-drift-summary")
    nodrift.add_argument("--commits", type=nonneg, required=True)
    nodrift.add_argument("--head", required=True)
    nodrift.add_argument("--push-rejected", action="store_true")
    nodrift.add_argument("--report", help="drift report; surfaces unwaived UNVERIFIABLE counts")
    nodrift.add_argument("--waivers", help="drift-waivers.json path")

    issue = sub.add_parser("issue-body")
    issue.add_argument("--report", required=True)
    issue.add_argument("--cap", type=nonneg, required=True)
    issue.add_argument("--marker", required=True)
    issue.add_argument("--head", required=True)

    blast = sub.add_parser("blast-summary")
    blast.add_argument("--report", required=True)
    blast.add_argument("--cap", type=nonneg, required=True)
    blast.add_argument("--issue-url", required=True)

    prbody = sub.add_parser("pr-body")
    prbody.add_argument("--report", required=True)
    prbody.add_argument("--marker", required=True)
    prbody.add_argument("--head", required=True)
    prbody.add_argument("--waivers", help="drift-waivers.json path")
    prbody.add_argument("--prev-stales", help="previous run's stale-state file")

    prtitle = sub.add_parser("pr-title")
    prtitle.add_argument("--report", required=True)
    prtitle.add_argument("--date", required=True)
    prtitle.add_argument("--waivers", help="drift-waivers.json path")

    prsum = sub.add_parser("pr-summary")
    prsum.add_argument("--report", required=True)
    prsum.add_argument("--pr-url", required=True)

    bpre = sub.add_parser("bloat-pre-summary")
    bpre.add_argument("--decision", required=True)

    bbody = sub.add_parser("bloat-pr-body")
    bbody.add_argument("--report", required=True)
    bbody.add_argument("--merge", help="plan-distill.py --merge summary JSON")

    dmerge = sub.add_parser("distill-merge-summary")
    dmerge.add_argument("--merge", required=True)

    btitle = sub.add_parser("bloat-pr-title")
    btitle.add_argument("--report", required=True)
    btitle.add_argument("--lane", required=True)
    btitle.add_argument("--date", required=True)

    bsum = sub.add_parser("bloat-pr-summary")
    bsum.add_argument("--report", required=True)
    bsum.add_argument("--lane", required=True)
    bsum.add_argument("--pr-url", required=True)

    bskip = sub.add_parser("bloat-skip-summary")
    bskip.add_argument("--lane", required=True)
    bskip.add_argument("--reason", required=True)

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

    bgaps = sub.add_parser("bloat-unswept-summary")
    bgaps.add_argument("--report", required=True)

    growth = sub.add_parser("growth-backlog")
    growth.add_argument("--scope-file", required=True)

    args = parser.parse_args()

    try:
        if args.mode == "pre-summary":
            render_pre_summary(args)
        elif args.mode == "no-drift-summary":
            render_no_drift_summary(args)
        elif args.mode == "bloat-pre-summary":
            write_summary(render_bloat_pre_summary(args.decision))
        elif args.mode == "bloat-skip-summary":
            write_summary(render_bloat_skip_summary(args.lane, args.reason))
        elif args.mode == "upgrade-summary":
            write_summary(render_upgrade_summary(
                args.status, args.current, args.latest, args.pr_url, args.files))
        elif args.mode == "upgrade-pr-body":
            print(render_upgrade_pr_body(args.current, args.latest, args.files))
        elif args.mode == "distill-merge-summary":
            write_summary(render_distill_merge_summary(load_merge(args.merge)))
        elif args.mode == "growth-backlog":
            write_summary(render_growth_backlog(args.scope_file))
        else:
            records, unswept = load_report(args.report)
            if args.mode == "issue-body":
                print(render_issue_body(records, args.cap, args.marker, args.head))
            elif args.mode == "blast-summary":
                write_summary(render_blast_summary(records, args.cap, args.issue_url))
            elif args.mode == "pr-body":
                waivers = load_waivers(args.waivers) if args.waivers else None
                print(render_pr_body(records, args.marker, args.head,
                                     waivers, args.waivers,
                                     load_prev_stales(args.prev_stales)))
            elif args.mode == "pr-title":
                waivers = load_waivers(args.waivers) if args.waivers else None
                print(render_pr_title(records, args.date, waivers))
            elif args.mode == "pr-summary":
                write_summary(render_pr_summary(records, args.pr_url))
            elif args.mode == "bloat-pr-body":
                merge = load_merge(args.merge) if args.merge else None
                print(render_bloat_pr_body(records, unswept, merge))
            elif args.mode == "bloat-pr-title":
                print(render_bloat_pr_title(records, args.lane, args.date))
            elif args.mode == "bloat-pr-summary":
                write_summary(render_bloat_pr_summary(records, args.lane, args.pr_url))
            elif args.mode == "bloat-triage":
                print(render_bloat_triage(records, unswept))
            elif args.mode == "bloat-unswept-summary":
                if unswept:
                    write_summary("\n".join(render_unswept_banner(unswept)).rstrip())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
