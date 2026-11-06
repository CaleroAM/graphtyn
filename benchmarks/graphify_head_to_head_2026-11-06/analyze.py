#!/usr/bin/env python3
"""Summarize the head-to-head: tokens, cost, tools and judged facts per client and arm.

Layout: <run-root>/<client>/<task>/runs/<run_id>/{summary.json,events.jsonl,answer.txt}.
Judged facts come from judge_grades.json, written by benchmarks/judge_grades.py with
--tasks-root pointing at this folder and one --variant per client.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("baseline", "graphtyn", "graphify")


def _tools(events: Path) -> int:
    count = 0
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") in {"mcp_tool_call", "command_execution"}:
            count += 1  # Codex
        message = event.get("message") or {}
        if event.get("type") == "assistant" and isinstance(message.get("content"), list):
            count += sum(part.get("type") == "tool_use" for part in message["content"])  # Claude Code
    return count


def load(root: Path) -> list[dict]:
    judged = {}
    grades = HERE / "judge_grades.json"
    if grades.exists():
        for row in json.loads(grades.read_text(encoding="utf-8"))["runs"]:
            judged[(row["variant"], row["arm"], row["task"], row["repetition"])] = row
    rows = []
    for path in sorted(root.glob("*/*/runs/*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        client = path.parents[3].name
        key = (client, summary["arm"], summary["task_id"], summary["repetition"])
        verdict = judged.get(key)
        usage = summary.get("usage") or {}
        rows.append({"client": client, "arm": summary["arm"], "task": summary["task_id"],
                     "repetition": summary["repetition"], "status": summary["session_status"],
                     "tokens": int(usage.get("total_tokens") or 0),
                     "cost": usage.get("provider_cost", usage.get("cost_usd")),
                     "tools": _tools(path.parent / "events.jsonl"),
                     "facts": sum(verdict["consensus"].values()) if verdict else None,
                     "facts_total": len(verdict["consensus"]) if verdict else None,
                     "literal": sum(verdict["literal"].values()) if verdict else None})
    return rows


def summarize(rows: list[dict]) -> dict:
    result: dict = {}
    for client in sorted({row["client"] for row in rows}):
        cell = result.setdefault(client, {})
        for arm in ARMS:
            group = [row for row in rows if row["client"] == client and row["arm"] == arm]
            if not group:
                continue
            complete = [row for row in group if row["status"] == "complete"]
            judged = [row for row in complete if row["facts"] is not None]
            costs = [float(row["cost"]) for row in complete if row["cost"] is not None]
            cell[arm] = {"sessions": len(group), "complete": len(complete),
                         "mean_tokens": round(statistics.fmean(row["tokens"] for row in complete)) if complete else None,
                         "median_tokens": round(statistics.median(row["tokens"] for row in complete)) if complete else None,
                         "mean_cost_usd": round(statistics.fmean(costs), 4) if costs else None,
                         "mean_tools": round(statistics.fmean(row["tools"] for row in complete), 1) if complete else None,
                         "facts": sum(row["facts"] for row in judged), "facts_total": sum(row["facts_total"] for row in judged),
                         "literal": sum(row["literal"] for row in judged)}
        pairs = defaultdict(dict)
        for row in rows:
            if row["client"] == client and row["status"] == "complete":
                pairs[(row["task"], row["repetition"])][row["arm"]] = row
        comparisons = {}
        for left, right in (("graphtyn", "graphify"), ("graphtyn", "baseline"), ("graphify", "baseline")):
            matched = [pair for pair in pairs.values() if left in pair and right in pair]
            ratios = [pair[left]["tokens"] / pair[right]["tokens"] - 1 for pair in matched if pair[right]["tokens"]]
            comparisons[f"{left}_vs_{right}"] = {
                "pairs": len(matched), "fewer_tokens_in": sum(pair[left]["tokens"] < pair[right]["tokens"] for pair in matched),
                "median_token_change": round(statistics.median(ratios), 3) if ratios else None,
                "facts_left": sum(pair[left]["facts"] or 0 for pair in matched),
                "facts_right": sum(pair[right]["facts"] or 0 for pair in matched)}
        cell["comparisons"] = comparisons
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    rows = load(parser.parse_args().run_root)
    (HERE / "runs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = summarize(rows)
    (HERE / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
