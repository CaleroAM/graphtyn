#!/usr/bin/env python3
"""Facts (majority of three judges) and tokens per task for baseline, Graphtyn fix (7ae4c27) and tokens (c213b37).

Reads judge_grades.json, written by benchmarks/judge_grades.py with --variant codex/fix
--variant codex/tokens over <run-root>/codex/{fix,tokens}/<task>/runs/<run_id>/.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("baseline", "fix", "tokens")


def main() -> None:
    runs = json.loads((HERE / "judge_grades.json").read_text(encoding="utf-8"))["runs"]
    cells: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for run in runs:
        arm = "baseline" if run["arm"] == "baseline" else run["variant"].split("/")[1]
        cells[run["task"]][arm].append(run)
    print("| Task | " + " | ".join(f"{arm}: facts · median tokens" for arm in ARMS) + " |")
    print("|---|" + "---|" * len(ARMS))
    for task in sorted(cells):
        row = []
        for arm in ARMS:
            group = cells[task][arm]
            facts = sum(sum(bool(value) for value in run["majority"].values()) for run in group)
            total = sum(len(run["majority"]) for run in group)
            row.append(f"{facts}/{total} · {statistics.median(run['tokens'] for run in group) / 1000:.0f}k")
        print(f"| {task} | " + " | ".join(row) + " |")
    print()
    for arm in ARMS:
        group = [run for task in cells for run in cells[task][arm]]
        facts = sum(sum(bool(value) for value in run["majority"].values()) for run in group)
        total = sum(len(run["majority"]) for run in group)
        tokens = [run["tokens"] for run in group]
        print(f"{arm}: {facts}/{total} facts, median {statistics.median(tokens):.0f}, mean {statistics.mean(tokens):.0f} tokens")


if __name__ == "__main__":
    main()
