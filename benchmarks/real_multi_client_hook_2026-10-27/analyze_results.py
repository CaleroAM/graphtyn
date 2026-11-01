#!/usr/bin/env python3
"""Grade the multi-client lean-MCP / prompt-hook run against the frozen rubrics.

Layout: <run-root>/<corpus>/<client>/runs/<run_id>/{summary.json,events.jsonl,answer.txt}.
Quality is the literal rubric (as in earlier runs); the blind adjudication in
`blind_adjudication.py` is reported separately and never replaces it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "single_run_grader", HERE.parent / "real_claude_agents_2026-10-25" / "analyze_results.py")
grader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(grader)
_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "benchmark_runner", HERE.parent / "run_three_client_mcp_comparison.py")
runner = importlib.util.module_from_spec(_RUNNER_SPEC)
_RUNNER_SPEC.loader.exec_module(runner)
CORPORA = ("redis", "fmt", "rails")
CLIENTS = ("claude", "codex", "opencode", "antigravity")
ARMS = ("baseline", "graphtyn_full", "graphtyn", "graphtyn_hook")
# Earlier same-task sessions kept as non-contemporaneous references.
REFERENCES = {
    ("claude", "baseline"): (HERE.parent / "real_claude_agents_reps_2026-10-25", "baseline"),
    ("claude", "graphtyn_previous"): (HERE.parent / "real_claude_agents_reps_2026-10-25", "graphtyn"),
    ("claude", "graphtyn_lean_2026-10-26"): (HERE.parent / "real_claude_agents_lean_hook_2026-10-26", "graphtyn_lean"),
    ("claude", "graphtyn_hook_2026-10-26"): (HERE.parent / "real_claude_agents_lean_hook_2026-10-26", "graphtyn_hook"),
}


def _tools(client: str, events: list[dict]) -> list[str]:
    """Tool calls per client event format (MCP calls are prefixed `mcp:`)."""
    if client == "claude":
        names = [block.get("name", "") for event in events if event.get("type") == "assistant"
                 for block in (event.get("message") or {}).get("content") or []
                 if isinstance(block, dict) and block.get("type") == "tool_use"]
        return [f"mcp:{name.split('__')[-1]}" if name.startswith("mcp__") else name for name in names]
    if client == "codex":
        items = [event.get("item") or {} for event in events if event.get("type") == "item.completed"]
        return [f"mcp:{item.get('tool')}" if item.get("type") == "mcp_tool_call" else str(item.get("type"))
                for item in items if item.get("type") not in {"agent_message", "reasoning", "error"}]
    if client == "opencode":
        return [("mcp:" + tool.split("_", 2)[-1]) if tool.startswith("graphtyn_benchmark") else tool
                for event in events if event.get("type") == "tool_use"
                for tool in [str((event.get("part") or {}).get("tool") or "")]]
    steps = {}
    for event in events:
        step = event.get("step_update") if event.get("event") == "step_update" else None
        if isinstance(step, dict):
            steps[step.get("step_index")] = step
    return [str(step.get("tool_name") or "") for step in steps.values() if step.get("step_type") == "tool"]


def _model_calls(client: str, events: list[dict]) -> int | None:
    if client == "claude":
        return len(runner._claude_model_calls(events))
    if client == "opencode":
        return sum(event.get("type") == "step_finish" for event in events)
    if client == "antigravity":
        steps = {(event.get("step_update") or {}).get("step_index"): event.get("step_update")
                 for event in events if event.get("event") == "step_update"}
        return sum((step or {}).get("step_type") == "agent_response" for step in steps.values())
    return None  # Codex reports one aggregate usage per turn.


def load_runs(root: Path, repositories: dict[str, Path]) -> list[dict]:
    specs = {json.loads((HERE / f"{name}_tasks.json").read_text())["tasks"][0]["id"]:
             json.loads((HERE / f"{name}_tasks.json").read_text())["tasks"][0] for name in CORPORA}
    rows = []
    for summary_path in sorted(root.glob("*/*/runs/*/summary.json")):
        if summary_path.parents[3].name not in CORPORA:
            continue  # pilot/ and failed_attempts/ are reported separately
        run_dir = summary_path.parent
        summary = json.loads(summary_path.read_text())
        corpus = grader.CORPORA[summary["task_id"]]
        answer = (run_dir / "answer.txt").read_text(encoding="utf-8", errors="replace")
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        normalized = answer.casefold()
        facts = {fact["id"]: any(term.casefold() in normalized for term in fact["any"])
                 for fact in specs[summary["task_id"]]["rubric"]}
        tools = _tools(summary["client"], events)
        rows.append({
            "repository": corpus, "client": summary["client"], "model": summary["model"],
            "arm": summary["arm"], "repetition": summary.get("repetition", 1), "run_id": run_dir.name,
            "session_status": summary["session_status"], "tokens": summary["usage"].get("total_tokens"),
            "usage": summary["usage"], "seconds": summary["wall_seconds"],
            "quality": {"facts": facts, "passed": sum(facts.values()), "total": len(facts),
                        "citations": grader._citations(answer, repositories[corpus])},
            "tools": {name: tools.count(name) for name in sorted(set(tools))},
            "tool_calls": len(tools), "model_calls": _model_calls(summary["client"], events),
            "prompt_hook": summary.get("prompt_hook"),
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(), "raw_directory": str(run_dir),
        })
    return rows


def _summary(values: list) -> dict:
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.fmean(values), 1),
            "median": round(statistics.median(values), 1),
            "stdev": round(statistics.stdev(values), 1) if len(values) > 1 else None,
            "min": min(values), "max": max(values)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--redis-repo", type=Path, required=True)
    parser.add_argument("--fmt-repo", type=Path, required=True)
    parser.add_argument("--rails-repo", type=Path, required=True)
    args = parser.parse_args()
    rows = load_runs(args.run_root, {"redis": args.redis_repo, "fmt": args.fmt_repo, "rails": args.rails_repo})
    (HERE / "grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    cells = {}
    for corpus in CORPORA:
        for client in CLIENTS:
            for arm in ARMS:
                group = [row for row in rows if (row["repository"], row["client"], row["arm"]) == (corpus, client, arm)
                         and row["session_status"] == "complete"]
                if not group:
                    continue
                cells[f"{corpus}/{client}/{arm}"] = {
                    "model": group[0]["model"], "tokens": _summary([row["tokens"] for row in group]),
                    "tokens_by_repetition": [row["tokens"] for row in sorted(group, key=lambda r: r["repetition"])],
                    "quality": [row["quality"]["passed"] for row in sorted(group, key=lambda r: r["repetition"])],
                    "tool_calls": [row["tool_calls"] for row in sorted(group, key=lambda r: r["repetition"])],
                    "model_calls": [row["model_calls"] for row in sorted(group, key=lambda r: r["repetition"])],
                    "seconds": _summary([row["seconds"] for row in group]),
                    "hook_injected": [((row.get("prompt_hook") or {}).get("expected") or {}).get("injected")
                                      for row in group] if arm == "graphtyn_hook" else None,
                }
    references = {}
    for (client, label), (directory, arm) in REFERENCES.items():
        for row in json.loads((directory / "grades_by_run.json").read_text(encoding="utf-8")):
            if row["arm"] == arm and row.get("session_status") == "complete":
                references.setdefault(f"{row['repository']}/{client}/{label}", []).append(
                    {"tokens": row["usage"]["total_tokens"], "quality": row["quality"]["passed"]})
    result = {"schema_version": "1.0", "sessions": len(rows),
              "complete_sessions": sum(row["session_status"] == "complete" for row in rows),
              "incomplete": [row["run_id"] for row in rows if row["session_status"] != "complete"],
              "cells": cells,
              "references": {key: {"tokens": _summary([item["tokens"] for item in items]),
                                   "quality": [item["quality"] for item in items]}
                             for key, items in references.items()},
              "comparison_warning": ("Arms of one client are contemporaneous and counterbalanced. References "
                                     "are earlier sessions with the same task and Claude model."),
              "raw_artifacts_preserved": all(Path(row["raw_directory"]).is_dir() for row in rows)}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for key, cell in cells.items():
        print(f"{key:40} mean={cell['tokens'].get('mean')} q={cell['quality']} tools={cell['tool_calls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
