#!/usr/bin/env python3
"""Grade the Antigravity hook run against the frozen literal rubrics.

Layout: <run-root>/<task>/runs/<run_id>/{summary.json,events.jsonl,answer.txt}.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEN = HERE.parent / "real_multi_client_hook_2026-10-27"
HELD_OUT = HERE.parent / "heldout_v2_2026-10-27"
TASK_SETS = {"seen": SEEN, "heldout_v2": HELD_OUT}


def rubrics() -> dict[str, tuple[str, dict]]:
    tasks = {}
    for label, folder in TASK_SETS.items():
        for corpus in ("redis", "fmt", "rails"):
            for task in json.loads((folder / f"{corpus}_tasks.json").read_text(encoding="utf-8"))["tasks"]:
                tasks[task["id"]] = (label, task)
    return tasks


def _tools(events: list[dict]) -> list[str]:
    steps = {}
    for event in events:
        step = event.get("step_update") if event.get("event") == "step_update" else None
        if isinstance(step, dict):
            steps[step.get("step_index")] = step
    return [str(step.get("tool_name") or "") for step in steps.values() if step.get("step_type") == "tool"]


def load_runs(root: Path) -> list[dict]:
    specs = rubrics()
    rows = []
    for summary_path in sorted(root.glob("*/runs/*/summary.json")):
        if summary_path.parents[2].name == "pilot":
            continue
        run_dir = summary_path.parent
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        label, task = specs[summary["task_id"]]
        answer = (run_dir / "answer.txt").read_text(encoding="utf-8", errors="replace").casefold()
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        facts = {fact["id"]: any(term.casefold() in answer for term in fact["any"]) for fact in task["rubric"]}
        tools = _tools(events)
        hook = summary.get("prompt_hook") or {}
        rows.append({
            "set": label, "task": summary["task_id"], "arm": summary["arm"], "repetition": summary["repetition"],
            "model": summary["model"], "session_status": summary["session_status"],
            "tokens": summary["usage"].get("total_tokens"),
            "cached_input_tokens": summary["usage"].get("cached_input_tokens") or 0, "seconds": summary["wall_seconds"],
            "passed": sum(facts.values()), "total": len(facts), "facts": facts,
            "tool_calls": len(tools), "mcp_calls": tools.count("call_mcp_tool"),
            "hook_injected": hook.get("context_injected"),
            "hook_characters": hook.get("injected_characters"),
        })
    return rows


def cells(rows: list[dict]) -> dict:
    result = {}
    for row in rows:
        result.setdefault(row["task"], {"set": row["set"]}).setdefault(row["arm"], []).append(row)
    summary = {}
    for task, cell in result.items():
        summary[task] = {"set": cell["set"]}
        for arm in ("graphtyn", "graphtyn_hook"):
            group = [row for row in cell.get(arm, []) if row["session_status"] == "complete"]
            summary[task][arm] = {
                "n": len(group), "incomplete": len(cell.get(arm, [])) - len(group),
                "tokens": [row["tokens"] for row in group],
                "mean_tokens": round(statistics.fmean(row["tokens"] for row in group)) if group else None,
                "rubric": [row["passed"] for row in group], "rubric_total": group[0]["total"] if group else None,
                "tool_calls": [row["tool_calls"] for row in group],
                "mcp_calls": [row["mcp_calls"] for row in group],
                "cached_input_tokens": [row["cached_input_tokens"] for row in group],
                "seconds": round(statistics.fmean(row["seconds"] for row in group), 1) if group else None,
                "hook_injected": [row["hook_injected"] for row in group] if arm == "graphtyn_hook" else None,
            }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    rows = load_runs(args.run_root)
    (HERE / "grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = cells(rows)
    (HERE / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for label in TASK_SETS:
        lean, hook = [], []
        print(f"\n[{label}]")
        for task, cell in summary.items():
            if cell["set"] != label:
                continue
            a, b = cell["graphtyn"], cell["graphtyn_hook"]
            delta = (f"{(b['mean_tokens'] / a['mean_tokens'] - 1) * 100:+.1f}%"
                     if a["mean_tokens"] and b["mean_tokens"] else "n/d")
            print(task, "| lean", a["mean_tokens"], a["rubric"], "tools", a["tool_calls"],
                  "| hook", b["mean_tokens"], b["rubric"], "tools", b["tool_calls"], "injected", b["hook_injected"],
                  "| /", a["rubric_total"] or b["rubric_total"], delta)
            if a["mean_tokens"] and b["mean_tokens"]:
                lean.append(a)
                hook.append(b)
        if lean:
            mean = lambda group: statistics.fmean(token for cell in group for token in cell["tokens"])
            rate = lambda group: (sum(sum(cell["rubric"]) for cell in group)
                                  / sum(cell["n"] * cell["rubric_total"] for cell in group))
            print(f"mean tokens lean {mean(lean):.0f} hook {mean(hook):.0f} "
                  f"({(mean(hook) / mean(lean) - 1) * 100:+.1f}%) rubric lean {rate(lean):.1%} hook {rate(hook):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
