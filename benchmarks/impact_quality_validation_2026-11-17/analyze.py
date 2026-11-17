#!/usr/bin/env python3
"""Facts (majority of three judges) and tokens per task for Graphtyn main (PR #68), c213b37 and a41fcb6.

Reads judge_grades.json, written by benchmarks/judge_grades.py with --variant codex/main
--variant codex/tokens --variant codex/final over <run-root>/codex/<variant>/<task>/runs/<run_id>/.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("main", "tokens", "final")


def _facts(run: dict) -> int:
    return sum(bool(value) for value in run["majority"].values())


def main() -> None:
    runs = json.loads((HERE / "judge_grades.json").read_text(encoding="utf-8"))["runs"]
    cells: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for run in runs:
        cells[run["task"]][run["variant"].split("/")[1]].append(run)
    print("| Task | " + " | ".join(f"{arm}: facts · median tokens" for arm in ARMS) + " |")
    print("|---|" + "---|" * len(ARMS))
    for task in sorted(cells):
        row = []
        for arm in ARMS:
            group = cells[task][arm]
            row.append(f"{sum(map(_facts, group))}/{sum(len(run['majority']) for run in group)} · "
                       f"{statistics.median(run['tokens'] for run in group) / 1000:.0f}k")
        print(f"| {task} | " + " | ".join(row) + " |")
    print()
    for arm in ARMS:
        group = [run for task in cells for run in cells[task][arm]]
        tokens = [run["tokens"] for run in group]
        print(f"{arm}: {sum(map(_facts, group))}/{sum(len(run['majority']) for run in group)} facts, "
              f"{len(group)} runs, median {statistics.median(tokens):.0f}, mean {statistics.mean(tokens):.0f} tokens")
    print()
    for left, right in (("final", "main"), ("final", "tokens"), ("tokens", "main")):
        better = worse = cheaper = 0
        changes = []
        for task in cells:
            pairs = {run["repetition"]: run for run in cells[task][right]}
            for run in cells[task][left]:
                other = pairs.get(run["repetition"])
                if other is None:
                    continue
                better += _facts(run) > _facts(other)
                worse += _facts(run) < _facts(other)
                cheaper += run["tokens"] < other["tokens"]
                changes.append(run["tokens"] / other["tokens"] - 1)
        print(f"{left} vs {right}: {len(changes)} pairs, cheaper in {cheaper}, median change "
              f"{statistics.median(changes) * 100:+.1f} %, sessions better/worse {better}/{worse}")
    print()
    for task in sorted(cells):
        for arm in ARMS:
            missed = defaultdict(int)
            for run in cells[task][arm]:
                for fact, value in run["majority"].items():
                    missed[fact] += not value
            lost = {fact: count for fact, count in missed.items() if count}
            if lost:
                print(f"{task} {arm} missed: {lost}")


if __name__ == "__main__":
    main()
