#!/usr/bin/env python3
"""Grade the lean-MCP and prompt-hook arms and compare them with earlier arms."""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "single_run_grader", HERE.parent / "real_claude_agents_2026-10-25" / "analyze_results.py")
grader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(grader)
grader.HERE = HERE  # same frozen tasks, copied into this directory
PRIOR = {
    # arm label in this report -> (directory with grades_by_run.json, arm name there)
    "baseline": (HERE.parent / "real_claude_agents_reps_2026-10-25", "baseline"),
    "graphtyn_previous": (HERE.parent / "real_claude_agents_reps_2026-10-25", "graphtyn"),
    "graphify": (HERE.parent / "real_claude_agents_graphify_2026-10-26", "graphify"),
}
ARMS = ("baseline", "graphify", "graphtyn_previous", "graphtyn_lean", "graphtyn_hook")


def _summary(values: list[float]) -> dict:
    values = [value for value in values if value is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.fmean(values), 2),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else None,
            "min": round(min(values), 2), "max": round(max(values), 2)}


def _model_calls(row: dict) -> int | None:
    events_path = Path(row["audit"]["raw_directory"]) / "events.jsonl"
    if not events_path.is_file():
        return None
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    return len(grader._claude_model_calls(events)) if hasattr(grader, "_claude_model_calls") else len(
        {(event.get("message") or {}).get("id") for event in events
         if event.get("type") == "assistant" and (event.get("message") or {}).get("id")})


def _side(row: dict) -> dict:
    return {"status": row["session_status"], "tokens": row["usage"]["total_tokens"],
            "usage": row["usage"], "seconds": row["wall_seconds"],
            "quality": row["quality"]["passed"], "missed": [k for k, v in row["quality"]["facts"].items() if not v],
            "citations": row["quality"]["citations"]["valid"], "cost_usd": row["usage"].get("provider_cost"),
            "tool_counts": row["audit"]["tool_counts"], "forbidden_tools": row["audit"]["forbidden_tools"],
            "mcp": row.get("claude_mcp"), "prompt_hook": row.get("prompt_hook"),
            "model_calls": _model_calls(row), "retrieval": row.get("retrieval")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--redis-repo", type=Path, required=True)
    parser.add_argument("--fmt-repo", type=Path, required=True)
    parser.add_argument("--rails-repo", type=Path, required=True)
    args = parser.parse_args()
    new_rows = grader._load_runs(args.run_root, {"redis": args.redis_repo, "fmt": args.fmt_repo,
                                                 "rails": args.rails_repo})
    for row in new_rows:
        row["arm"] = {"graphtyn": "graphtyn_lean"}.get(row["arm"], row["arm"])
    rows = list(new_rows)
    for label, (directory, arm) in PRIOR.items():
        for row in json.loads((directory / "grades_by_run.json").read_text(encoding="utf-8")):
            if row["arm"] == arm:
                rows.append({**row, "arm": label})
    cells = []
    for repository in ("redis", "fmt", "rails"):
        for repetition in (1, 2, 3):
            arms = {row["arm"]: _side(row) for row in rows
                    if row["repository"] == repository and row.get("repetition", 1) == repetition}
            if {"graphtyn_lean", "graphtyn_hook"} <= set(arms):
                cells.append({"repository": repository, "repetition": repetition, "arms": arms})
    corpora = {}
    for repository in ("redis", "fmt", "rails"):
        items = [cell for cell in cells if cell["repository"] == repository]
        present = [arm for arm in ARMS if all(arm in cell["arms"] for cell in items)]
        corpora[repository] = {
            "repetitions": len(items),
            "tokens": {arm: _summary([cell["arms"][arm]["tokens"] for cell in items]) for arm in present},
            "quality": {arm: [cell["arms"][arm]["quality"] for cell in items] for arm in present},
            "cost_usd": {arm: _summary([cell["arms"][arm]["cost_usd"] for cell in items]) for arm in present},
            "seconds": {arm: _summary([cell["arms"][arm]["seconds"] for cell in items]) for arm in present},
            "model_calls": {arm: [cell["arms"][arm]["model_calls"] for cell in items] for arm in present},
            "hook_vs_lean_tokens_percent": _summary([
                grader._delta(cell["arms"]["graphtyn_hook"]["tokens"], cell["arms"]["graphtyn_lean"]["tokens"])
                for cell in items]),
            "lean_vs_previous_tokens_percent": _summary([
                grader._delta(cell["arms"]["graphtyn_lean"]["tokens"], cell["arms"]["graphtyn_previous"]["tokens"])
                for cell in items if "graphtyn_previous" in cell["arms"]]),
            "hook_vs_baseline_tokens_percent": _summary([
                grader._delta(cell["arms"]["graphtyn_hook"]["tokens"], cell["arms"]["baseline"]["tokens"])
                for cell in items if "baseline" in cell["arms"]]),
            "hook_vs_graphify_tokens_percent": _summary([
                grader._delta(cell["arms"]["graphtyn_hook"]["tokens"], cell["arms"]["graphify"]["tokens"])
                for cell in items if "graphify" in cell["arms"]]),
        }
    (HERE / "grades_by_run.json").write_text(json.dumps(new_rows, ensure_ascii=False, indent=2) + "\n")
    result = {"schema_version": "1.0", "new_runs": len(new_rows),
              "complete_new_runs": sum(row["session_status"] == "complete" for row in new_rows),
              "cells": cells, "corpora": corpora,
              "comparison_warning": ("graphtyn_lean and graphtyn_hook ran together (counterbalanced); baseline, "
                                     "graphtyn_previous and graphify come from earlier runs on the same commits, "
                                     "tasks, model and client. Token totals are the primary metric."),
              "raw_artifacts_preserved": all(Path(row["audit"]["raw_directory"]).is_dir() for row in new_rows)}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(corpora, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
