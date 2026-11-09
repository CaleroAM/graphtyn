#!/usr/bin/env python3
"""Paired comparison of two variants over tasks, with bootstrap intervals.

A validation compares two versions on the same tasks. Sessions of one task vary a lot
(30k to 230k tokens), so totals hide how uncertain a difference is. This pairs runs by
task and repetition, averages each task, and resamples tasks (not sessions) to give a
95% interval for the difference in the share of facts and for the token ratio.

Usage: paired_stats.py <judge_grades.json> --base codex-main --new codex-fix [--rule consensus]
Rules: consensus (both judges), either, gemini, gpt, literal.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

RESAMPLES = 10_000


def facts(row: dict, rule: str) -> tuple[int, int]:
    if rule == "either":
        verdict = {key: row["gemini"][key] or row["gpt"][key] for key in row["consensus"]}
    else:
        verdict = row[rule]
    return sum(bool(value) for value in verdict.values()), len(verdict)


def per_task(rows: list[dict], base: str, new: str, rule: str) -> list[dict]:
    """One entry per task that has at least one matched pair, averaged over its pairs."""
    cells: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        cells[(row["task"], row["repetition"])][row["variant"]] = row
    tasks: dict[str, list[tuple[float, float, int, int]]] = defaultdict(list)
    for (task, _repetition), pair in cells.items():
        if base in pair and new in pair:
            (base_hits, total), (new_hits, _total) = facts(pair[base], rule), facts(pair[new], rule)
            tasks[task].append((base_hits / total, new_hits / total,
                                int(pair[base]["tokens"] or 0), int(pair[new]["tokens"] or 0)))
    return [{"task": task, "pairs": len(items),
             "base_share": statistics.fmean(item[0] for item in items),
             "new_share": statistics.fmean(item[1] for item in items),
             "log_token_ratio": statistics.fmean(math.log(item[3] / item[2]) for item in items if item[2] and item[3])}
            for task, items in sorted(tasks.items())]


def _interval(values: list[float], seed: int = 7) -> tuple[float, float]:
    generator = random.Random(seed)
    means = sorted(statistics.fmean(generator.choices(values, k=len(values))) for _ in range(RESAMPLES))
    return means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def summarize(tasks: list[dict]) -> dict:
    if not tasks:
        return {"tasks": 0}
    differences = [task["new_share"] - task["base_share"] for task in tasks]
    ratios = [task["log_token_ratio"] for task in tasks]
    low, high = _interval(differences)
    ratio_low, ratio_high = _interval(ratios)
    return {"tasks": len(tasks), "pairs": sum(task["pairs"] for task in tasks),
            "fact_share_difference": round(statistics.fmean(differences), 4),
            "fact_share_difference_95ci": [round(low, 4), round(high, 4)],
            "token_ratio": round(math.exp(statistics.fmean(ratios)), 3),
            "token_ratio_95ci": [round(math.exp(ratio_low), 3), round(math.exp(ratio_high), 3)],
            "tasks_better": sum(value > 0 for value in differences), "tasks_worse": sum(value < 0 for value in differences)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("grades", type=Path, nargs="+", help="judge_grades.json files; their runs are pooled")
    parser.add_argument("--base", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--rule", default="consensus", choices=["consensus", "either", "gemini", "gpt", "literal"])
    args = parser.parse_args()
    rows = [row for path in args.grades for row in json.loads(path.read_text(encoding="utf-8"))["runs"]]
    tasks = per_task(rows, args.base, args.new, args.rule)
    print(json.dumps({"rule": args.rule, **summarize(tasks), "per_task": tasks}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
