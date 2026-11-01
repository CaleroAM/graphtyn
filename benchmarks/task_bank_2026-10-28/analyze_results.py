#!/usr/bin/env python3
"""Grade the agent sessions run on the second test split.

Layout: <run-root>/<corpus>/<task id lowercased>/<client>/runs/<run_id>/.
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
CORPORA = ("redis", "fmt", "rails", "flask")


def load_runs(root: Path) -> list[dict]:
    specs = {task["id"]: (corpus, task) for corpus in CORPORA
             for task in json.loads((HERE / "test2" / f"{corpus}_tasks.json").read_text())["tasks"]}
    rows = []
    for summary_path in sorted(root.glob("*/*/*/runs/*/summary.json")):
        summary = json.loads(summary_path.read_text())
        corpus, task = specs[summary["task_id"]]
        run_dir = summary_path.parent
        answer_path = run_dir / "answer.txt"
        answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        facts = {fact["id"]: any(term.casefold() in answer.casefold() for term in fact["any"]) for fact in task["rubric"]}
        tools = grader._tools(summary["client"], events)
        rows.append({"repository": corpus, "task_id": summary["task_id"], "client": summary["client"],
                     "arm": summary["arm"], "run_id": run_dir.name, "session_status": summary["session_status"],
                     "tokens": summary["usage"].get("total_tokens"), "seconds": summary["wall_seconds"],
                     "quality": {"facts": facts, "passed": sum(facts.values()), "total": len(facts)},
                     "tool_calls": len(tools), "raw_directory": str(run_dir)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    rows = load_runs(args.run_root)
    (HERE / "agent_grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    complete = [row for row in rows if row["session_status"] == "complete"]
    arms: dict[str, list[dict]] = {}
    for row in complete:
        arms.setdefault(f"{row['client']}/{row['arm']}", []).append(row)
    summary = {key: {"n": len(group),
                     "mean_tokens": round(statistics.fmean(r["tokens"] for r in group)),
                     "mean_quality": round(statistics.fmean(r["quality"]["passed"] / r["quality"]["total"]
                                                            for r in group), 4),
                     "mean_tool_calls": round(statistics.fmean(r["tool_calls"] for r in group), 1)}
               for key, group in sorted(arms.items())}
    result = {"schema_version": "1.0", "sessions": len(rows), "complete_sessions": len(complete),
              "incomplete": [r["run_id"] for r in rows if r["session_status"] != "complete"], "arms": summary}
    (HERE / "agent_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for row in sorted(complete, key=lambda r: (r["task_id"], r["client"], r["arm"])):
        print(f"{row['task_id']:30} {row['client']:7} {row['arm']:14} tokens={row['tokens']:>8} "
              f"q={row['quality']['passed']}/{row['quality']['total']} tools={row['tool_calls']}")
    for key, value in summary.items():
        print(key, value)
    print("sessions", result["sessions"], "complete", result["complete_sessions"], result["incomplete"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
