#!/usr/bin/env python3
"""Check a drafted pm-status report against the skill's shape limits.

Usage: check_report.py REPORT.md [--facts GATHER.json]

Counting words by eye is unreliable. This counts them, plus sentences, pictures and
lines, and prints one line per problem. Exit 0 means the draft is within every limit.
With --facts (the gather.py JSON), it also checks that every open PR shows up with a CI
state. Stdlib only.
"""
import argparse
import json
import re
import sys

BUCKETS = ("Landed", "In flight", "Needs you", "Next up")
LABEL = re.compile(r"^\*\*(Landed|Staged|Sessions|In flight|Needs you|Next up|Cleanup)\b")
ITEM = re.compile(r"^(\d+)\.\s")
REF = re.compile(r"#\d+(?!\d)")
CI_WORDS = re.compile(r"\b(CI|checks?|green|red|passing|failing|failed|pending|no runs?)\b", re.I)
STOP = set("""that this with from have been were they them their there what when which while into onto
than then also only just still since because about after before under over does done your it's isn't
nothing every each both either other more most some such these those would could should will""".split())

LIMITS = {"verdict_words": 40, "verdict_sentences": 2, "needs_words": 40, "needs_sentences": 2,
          "next_items": (2, 6), "next_words": 25, "cleanup_words": 50, "pictures": 3, "lines": 70}


def words(text):
    """Words a reader reads: markdown emphasis stripped, lone punctuation like `·` or `→` not counted."""
    return [w for w in text.replace("**", "").split() if re.search(r"\w", w)]


def sentences(text):
    plain = re.sub(r"`[^`]*`", "x", text.replace("**", ""))
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9#`(\[\"])", plain.strip())
    return [p for p in parts if words(p)]


def content(text):
    return {w for w in re.findall(r"#?\w+", text.lower()) if (len(w) >= 4 or w.startswith("#") or w[0].isdigit())
            and w not in STOP}


def parse(text):
    """Split the report into heading, verdict, labelled sections, and fenced pictures."""
    lines = text.splitlines()
    report = {"lines": lines, "heading": None, "verdict": [], "sections": [], "fences": []}
    fence, section = None, None
    for n, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if fence is None:
                fence = {"start": n, "lang": stripped[3:].strip(), "body": [], "section": section}
                report["fences"].append(fence)
            else:
                fence = None
            continue
        if fence is not None:
            fence["body"].append(line)
            continue
        if report["heading"] is None and stripped.startswith("## "):
            report["heading"] = n
            continue
        m = LABEL.match(stripped)
        if m:
            section = {"label": m.group(1), "start": n, "lines": [(n, line)]}
            report["sections"].append(section)
        elif section is None:
            if report["heading"] is not None and stripped:
                report["verdict"].append(stripped)
        else:
            section["lines"].append((n, line))
    return report


def blocks(section_lines, starts):
    """Group a section's source lines into items: a line where starts() holds opens one, indented lines continue it."""
    items, current = [], None
    for n, line in section_lines:
        if not line.strip():
            current = None
            continue
        if starts(line):
            current = {"line": n, "text": [line.strip()]}
            items.append(current)
        elif current is not None and (line.startswith((" ", "\t"))):
            current["text"].append(line.strip())
        else:
            current = None
    return items


def check(text, facts=None):
    r = parse(text)
    problems = []

    def flag(where, what):
        problems.append(f"{where}: {what}")

    if r["heading"] != 1:
        flag("line 1", "the report should open with its `## <repo>: <window> (<since> → now)` heading")
    labels = {s["label"] for s in r["sections"]}
    for b in BUCKETS:
        if b not in labels:
            flag("buckets", f"no **{b}** label (an empty bucket still gets its label, with `nothing` and why)")

    verdict = " ".join(r["verdict"])
    if not verdict:
        flag("verdict", "no verdict between the heading and the first bucket")
    else:
        w, s = len(words(verdict)), len(sentences(verdict))
        if w > LIMITS["verdict_words"] or s > LIMITS["verdict_sentences"]:
            flag("verdict", f"{s} sentences / {w} words; limit is 2 sentences and 40 words. Keep the one state "
                 "that matters most and drop the rest to its bucket")

    pictures = r["fences"]
    if len(pictures) > LIMITS["pictures"]:
        flag("pictures", f"{len(pictures)} fenced pictures; limit is 3. Turn the lowest-priority ones into bullets")
    for f in pictures:
        if f["lang"].lower() in ("mermaid", "html", "svg", "dot"):
            flag(f"line {f['start']}", f"`{f['lang']}` fence renders as source in a terminal; draw plain text")

    needs = [s for s in r["sections"] if s["label"] == "Needs you"]
    needs_bullets = []
    for s in needs:
        for item in blocks(s["lines"], lambda l: l.startswith("- ")):
            body = " ".join(item["text"])[2:]
            lead = re.match(r"\*\*(.+?)\*\*\s*", body)
            rest = body[lead.end():] if lead else body
            needs_bullets.append({"line": item["line"], "lead": lead.group(1) if lead else body[:40], "text": body})
            w, sc = len(words(rest)), len(sentences(rest))
            if w > LIMITS["needs_words"] or sc > LIMITS["needs_sentences"]:
                flag(f"line {item['line']} (Needs you)", f"{sc} sentences / {w} words after the lead-in; limit is 2 and "
                     "40. Keep the consequence and the one example that matters; detail the user acts on moves "
                     "to the Next-up step sequence")

    nxt = [s for s in r["sections"] if s["label"] == "Next up"]
    if nxt:
        s = nxt[0]
        end = s["lines"][-1][0]
        fenced = [f for f in pictures if s["start"] < f["start"] <= end and f["body"] and ITEM.match(f["body"][0])]
        items = blocks(s["lines"], lambda l: bool(ITEM.match(l)))
        numbers = [int(ITEM.match(f["body"][0]).group(1)) for f in fenced] + [int(ITEM.match(i["text"][0]).group(1)) for i in items]
        lo, hi = LIMITS["next_items"]
        if not lo <= len(numbers) <= hi:
            flag("Next up", f"{len(numbers)} numbered items; give 2–6")
        for f in fenced:
            if int(ITEM.match(f["body"][0]).group(1)) != 1:
                flag(f"line {f['start']} (Next up)", "only item 1 may be drawn as a step sequence")
        for item in items:
            where = f"line {item['line']} (Next up)"
            line = item["text"][0]
            if len(item["text"]) > 1:
                flag(where, "item spans more than one source line or has nested bullets; make it one line")
            if not re.match(r"^\d+\.\s+\*\*.+?:\*\*\s+\S", line):
                flag(where, "shape is `N. **<action naming the PR, issue, or branch>:** <reason>`")
            elif not re.search(r"#\d|`|\[", line.split(":**", 1)[0]):
                flag(where, "the action names no PR, issue, branch, path or session; name the thing the user acts on")
            w = len(words(" ".join(item["text"])))
            if w > LIMITS["next_words"]:
                flag(where, f"{w} words; limit is 25. Cut the background, keep the action and why it ranks here")
            reason = line.split(":**", 1)[1] if ":**" in line else line
            mine = content(reason)
            for b in needs_bullets:
                if set(REF.findall(line)) & set(REF.findall(b["text"])) and len(mine) >= 4:
                    overlap = len(mine & content(b["text"])) / len(mine)
                    if overlap >= 0.5:
                        flag(where, f"reason repeats Needs-you bullet \"{b['lead']}\" ({overlap:.0%} shared words). "
                             "Point back to it and say what doing this unlocks")
                        break

    cleanup = [s for s in r["sections"] if s["label"] == "Cleanup"]
    for s in cleanup:
        first = s["lines"][0][1].strip()
        w = len(words(first[len("**Cleanup:**"):] if first.startswith("**Cleanup:**") else first))
        if w > LIMITS["cleanup_words"]:
            flag(f"line {s['start']} (Cleanup)", f"{w} words; limit is 50. Count per kind, and name items only "
                 "when a kind has three or fewer")
        if any(l.strip() for _, l in s["lines"][1:]):
            flag(f"line {s['start']} (Cleanup)", "Cleanup is one line with nothing under it")

    if len(r["lines"]) > LIMITS["lines"]:
        flag("length", f"{len(r['lines'])} lines; aim for 70 or fewer")

    if facts:
        for pr in (facts.get("github") or {}).get("open") or []:
            tag = f"#{pr['number']}"
            hits = [l for l in r["lines"] if re.search(re.escape(tag) + r"(?!\d)", l)]
            if not hits:
                flag(f"PR {tag}", "open PR missing; every open PR goes under In flight, Needs you, or Cleanup")
            elif not any(CI_WORDS.search(l) for l in hits):
                flag(f"PR {tag}", "open PR shown without its CI state (passing, failing, none), even on the Cleanup line")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--facts", help="gather.py JSON, to check open-PR coverage")
    args = ap.parse_args()
    text = sys.stdin.read() if args.report == "-" else open(args.report, encoding="utf-8").read()
    facts = None
    if args.facts:
        with open(args.facts, encoding="utf-8") as fh:
            facts = json.load(fh)
    problems = check(text, facts)
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)" if problems else "ok: within every limit")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
