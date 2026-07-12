#!/usr/bin/env python3
"""Render the docs A/B matrix and the three hypothesis comparisons.

Reads facts.json (and grade.json overrides, when a grader agent has written
one) from each run dir. Success source of truth: grade.json's `success` if
present, else facts.json's mechanical `success`.

H1 (hydration): plugin-shaped vs none        — success and cost
H2 (density):   plugin-shaped vs bloated     — same facts, different densities
H3 (drift):     stale vs none                — misleading vs absent
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_ROOT = HERE.parent.parent / "skill-workspaces" / "docs-ab" / "runs"
VARIANTS = ["none", "plugin-shaped", "bloated", "stale"]


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def load_runs():
    runs = []
    for run_dir in sorted(p for p in RESULTS_ROOT.iterdir() if p.is_dir()):
        facts = read_json(run_dir / "facts.json")
        if not facts:
            continue
        grade = read_json(run_dir / "grade.json")
        if grade and "success" in grade:
            facts["success"] = grade["success"]
            facts["graded"] = True
        runs.append(facts)
    return runs


def med(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def fmt(value, spec):
    return format(value, spec) if value is not None else "-"


def cell_stats(runs):
    n = len(runs)
    succ = sum(1 for r in runs if r.get("success"))
    metrics = [r.get("metrics", {}) for r in runs]
    return {
        "n": n,
        "success_rate": succ / n if n else None,
        "med_cost": med([m.get("total_cost_usd") for m in metrics]),
        "med_turns": med([m.get("num_turns") for m in metrics]),
        "med_out_tokens": med([m.get("output_tokens") for m in metrics]),
    }


def main():
    runs = load_runs()
    if not runs:
        sys.exit(f"no facts.json under {RESULTS_ROOT} — run collect-facts.py first")

    by_cell = defaultdict(list)
    by_variant = defaultdict(list)
    tasks = []
    for r in runs:
        by_cell[(r["variant"], r["task"])].append(r)
        by_variant[r["variant"]].append(r)
        if r["task"] not in tasks:
            tasks.append(r["task"])
    variants = [v for v in VARIANTS if v in by_variant]

    print("## Matrix — success rate (n) | median cost | median turns\n")
    header = "| task | " + " | ".join(variants) + " |"
    print(header)
    print("|" + "---|" * (len(variants) + 1))
    for task in tasks:
        row = [task]
        for v in variants:
            cell = by_cell.get((v, task))
            if not cell:
                row.append("—")
                continue
            s = cell_stats(cell)
            row.append(f"{s['success_rate']:.0%} ({s['n']}) | "
                       f"${fmt(s['med_cost'], '.2f')} | {fmt(s['med_turns'], '.0f')}t"
                       .replace(" | ", " · "))
        print("| " + " | ".join(row) + " |")

    print("\n## Per-variant aggregate\n")
    agg = {}
    for v in variants:
        agg[v] = cell_stats(by_variant[v])
        s = agg[v]
        print(f"- **{v}**: success {s['success_rate']:.0%} (n={s['n']}), "
              f"median cost ${fmt(s['med_cost'], '.2f')}, "
              f"median turns {fmt(s['med_turns'], '.0f')}, "
              f"median output tokens {fmt(s['med_out_tokens'], '.0f')}")

    def compare(label, a, b, expectation):
        if a not in agg or b not in agg:
            print(f"- **{label}**: insufficient data ({a} vs {b})")
            return
        sa, sb = agg[a], agg[b]
        d_succ = sa["success_rate"] - sb["success_rate"]
        d_cost = (sa["med_cost"] - sb["med_cost"]
                  if sa["med_cost"] is not None and sb["med_cost"] is not None else None)
        print(f"- **{label}** ({a} vs {b}; expect {expectation}): "
              f"success {sa['success_rate']:.0%} vs {sb['success_rate']:.0%} "
              f"(Δ {d_succ:+.0%}), median cost "
              f"${fmt(sa['med_cost'], '.2f')} vs ${fmt(sb['med_cost'], '.2f')}"
              + (f" (Δ {d_cost:+.2f})" if d_cost is not None else ""))

    print("\n## Hypotheses\n")
    compare("H1 hydration", "plugin-shaped", "none", "higher success / lower cost")
    compare("H2 density", "plugin-shaped", "bloated", "lower cost at equal-or-better success")
    compare("H3 drift", "stale", "none", "LOWER success than no docs at all")

    graded = sum(1 for r in runs if r.get("graded"))
    print(f"\n{len(runs)} runs analyzed; {graded} with grader overrides; "
          f"{sum(1 for r in runs if r.get('timed_out'))} timed out.")


if __name__ == "__main__":
    main()
