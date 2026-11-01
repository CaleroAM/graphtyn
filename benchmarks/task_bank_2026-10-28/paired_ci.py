#!/usr/bin/env python3
"""Paired per-task differences between variants, with 95 % bootstrap intervals.

usage: python paired_ci.py <analyze_variants.py --json output> [--pairs A:B,...]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

METRICS = {"coste USD": lambda row: row["cost_usd"], "calidad literal": lambda row: row["passed"] / row["total"],
           "calidad juzgada": lambda row: row["judged"], "tokens totales": lambda row: row["tokens"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--pairs", default="BCD:none,BCD:current,current:none")
    args = parser.parse_args()
    runs = json.loads(args.results.read_text())["runs"]
    cells: dict[tuple, list[dict]] = {}
    for row in runs:
        if row["session_status"] == "complete":
            cells.setdefault((row["client"], row["task_id"], row["variant"]), []).append(row)
    random.seed(7)
    for client in sorted({key[0] for key in cells}):
        for pair in args.pairs.split(","):
            first, second = pair.split(":")
            tasks = sorted(task for (c, task, v) in cells if c == client and v == first
                           and (client, task, second) in cells)
            if not tasks:
                continue
            parts = []
            for name, metric in METRICS.items():
                values = [(statistics.fmean(v for v in map(metric, cells[(client, task, first)]) if v is not None),
                           statistics.fmean(v for v in map(metric, cells[(client, task, second)]) if v is not None))
                          for task in tasks]
                diffs = [a - b for a, b in values]
                base = statistics.fmean(b for _a, b in values)
                boots = sorted(statistics.fmean(random.choices(diffs, k=len(diffs))) for _ in range(4000))
                low, high, mean = boots[100], boots[3899], statistics.fmean(diffs)
                if name.startswith("calidad"):
                    parts.append(f"{name} {mean * 100:+.1f} pt [{low * 100:+.1f}; {high * 100:+.1f}]")
                else:
                    parts.append(f"{name} {mean / base * 100:+.1f} % [{low / base * 100:+.1f}; {high / base * 100:+.1f}]")
            print(f"{client} {first} vs {second} ({len(tasks)} tareas): " + " | ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
