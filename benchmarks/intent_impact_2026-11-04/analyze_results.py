#!/usr/bin/env python3
"""Grade the before/after intent run against the rubrics frozen before implementing.

Layout: <run-root>/{before,after}/<task>/runs/<run_id>/{summary.json,events.jsonl,answer.txt}.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARIANTS = ("before", "after")


def _steps(events: list[dict]) -> list[dict]:
    steps = {}
    for event in events:
        step = event.get("step_update") if event.get("event") == "step_update" else None
        if isinstance(step, dict):
            steps[step.get("step_index")] = step
    return list(steps.values())


def load_runs(root: Path) -> list[dict]:
    specs = {task["id"]: task for corpus in ("redis", "fmt", "rails")
             for task in json.loads((HERE / f"{corpus}_tasks.json").read_text(encoding="utf-8"))["tasks"]}
    rows = []
    for variant in VARIANTS:
        for path in sorted((root / variant).glob("*/runs/*/summary.json")):
            summary = json.loads(path.read_text(encoding="utf-8"))
            answer = (path.parent / "answer.txt").read_text(encoding="utf-8", errors="replace").casefold()
            events = [json.loads(line) for line in (path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()
                      if line.strip()]
            steps = _steps(events)
            task = specs[summary["task_id"]]
            facts = {fact["id"]: any(term.casefold() in answer for term in fact["any"]) for fact in task["rubric"]}
            rows.append({"variant": variant, "task": summary["task_id"], "repetition": summary["repetition"],
                         "session_status": summary["session_status"], "tokens": summary["usage"].get("total_tokens"),
                         "cached_input_tokens": summary["usage"].get("cached_input_tokens") or 0,
                         "seconds": summary["wall_seconds"], "passed": sum(facts.values()), "total": len(facts),
                         "facts": facts, "tool_calls": sum(step.get("step_type") == "tool" for step in steps),
                         "mcp_calls": sum(step.get("tool_name") == "call_mcp_tool" for step in steps)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    rows = load_runs(parser.parse_args().run_root)
    (HERE / "grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {}
    for task in sorted({row["task"] for row in rows}):
        summary[task] = {}
        for variant in VARIANTS:
            group = [row for row in rows if row["task"] == task and row["variant"] == variant]
            summary[task][variant] = {
                "statuses": [row["session_status"] for row in group], "tokens": [row["tokens"] for row in group],
                "cached_input_tokens": [row["cached_input_tokens"] for row in group],
                "rubric": [row["passed"] for row in group], "rubric_total": group[0]["total"],
                "tool_calls": [row["tool_calls"] for row in group], "mcp_calls": [row["mcp_calls"] for row in group],
                "seconds": round(statistics.fmean(row["seconds"] for row in group), 1)}
    (HERE / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
