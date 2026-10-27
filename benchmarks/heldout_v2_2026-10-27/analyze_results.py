#!/usr/bin/env python3
"""Grade the second held-out set and the first set re-run with the targeted stop rule.

Layout: <run-root>/{v2,set1}/<corpus>/<task id lowercased>/<client>/runs/<run_id>/.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "multi_client_grader", HERE.parent / "real_multi_client_hook_2026-10-27" / "analyze_results.py")
grader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(grader)
CORPORA = ("redis", "fmt", "rails")
TASK_FILES = {"v2": HERE, "set1": HERE.parent / "heldout_tasks_2026-10-27"}


def load_runs(root: Path) -> list[dict]:
    rows = []
    for label, directory in TASK_FILES.items():
        specs = {task["id"]: (corpus, task) for corpus in CORPORA
                 for task in json.loads((directory / f"{corpus}_tasks.json").read_text())["tasks"]}
        for summary_path in sorted((root / label).glob("*/*/*/runs/*/summary.json")):
            summary = json.loads(summary_path.read_text())
            corpus, task = specs[summary["task_id"]]
            run_dir = summary_path.parent
            answer = (run_dir / "answer.txt").read_text(encoding="utf-8", errors="replace").casefold()
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
            facts = {fact["id"]: any(term.casefold() in answer for term in fact["any"]) for fact in task["rubric"]}
            tools = grader._tools(summary["client"], events)
            rows.append({"set": label, "repository": corpus, "task_id": summary["task_id"],
                         "client": summary["client"], "arm": summary["arm"], "repetition": summary.get("repetition", 1),
                         "stop_rule": summary.get("stop_rule"), "run_id": run_dir.name,
                         "session_status": summary["session_status"], "tokens": summary["usage"].get("total_tokens"),
                         "seconds": summary["wall_seconds"],
                         "quality": {"facts": facts, "passed": sum(facts.values()), "total": len(facts)},
                         "tool_calls": len(tools), "tools": {name: tools.count(name) for name in sorted(set(tools))},
                         "raw_directory": str(run_dir)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    rows = load_runs(args.run_root)
    (HERE / "grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    cells: dict[str, list[dict]] = {}
    for row in rows:
        if row["session_status"] == "complete":
            cells.setdefault(f"{row['set']}/{row['task_id']}/{row['client']}/{row['arm']}", []).append(row)
    summary = {key: {"mean_tokens": round(statistics.fmean(r["tokens"] for r in group)),
                     "tokens": [r["tokens"] for r in group],
                     "quality": [r["quality"]["passed"] for r in group], "total": group[0]["quality"]["total"],
                     "tool_calls": [r["tool_calls"] for r in group],
                     "missed": sorted({k for r in group for k, v in r["quality"]["facts"].items() if not v})}
               for key, group in sorted(cells.items())}
    result = {"schema_version": "1.0", "sessions": len(rows),
              "complete_sessions": sum(r["session_status"] == "complete" for r in rows),
              "incomplete": [r["run_id"] for r in rows if r["session_status"] != "complete"], "cells": summary}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for key, cell in summary.items():
        print(f"{key:56} tokens={cell['mean_tokens']:>7} q={cell['quality']}/{cell['total']} "
              f"tools={cell['tool_calls']} missed={cell['missed']}")
    print("sessions", result["sessions"], "complete", result["complete_sessions"], result["incomplete"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
