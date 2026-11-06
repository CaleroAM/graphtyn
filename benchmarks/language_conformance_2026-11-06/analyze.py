#!/usr/bin/env python3
"""Compare Graphtyn main with the language-conformance fix on the frozen validation tasks.

Layout: <run-root>/codex-<version>/<task>/runs/<run_id>/{summary.json,events.jsonl,answer.txt}.
Judged facts come from judge_grades.json, written by benchmarks/judge_grades.py with
--tasks-root pointing at this folder and --variant codex-main --variant codex-fix.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = ("codex-main", "codex-fix")


def _tools(events: Path) -> int:
    count = 0
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") in {"mcp_tool_call", "command_execution"}:
            count += 1
    return count


def load(root: Path) -> list[dict]:
    grades = json.loads((HERE / "judge_grades.json").read_text(encoding="utf-8"))["runs"]
    judged = {(row["variant"], row["task"], row["repetition"]): row for row in grades}
    rows = []
    for version in VERSIONS:
        for path in sorted((root / version).glob("*/runs/*/summary.json")):
            summary = json.loads(path.read_text(encoding="utf-8"))
            verdict = judged.get((version, summary["task_id"], summary["repetition"]))
            rows.append({"version": version.removeprefix("codex-"), "task": summary["task_id"],
                         "repetition": summary["repetition"], "status": summary["session_status"],
                         "tokens": int((summary.get("usage") or {}).get("total_tokens") or 0),
                         "tools": _tools(path.parent / "events.jsonl"),
                         "facts": sum(verdict["consensus"].values()) if verdict else None,
                         "facts_total": len(verdict["consensus"]) if verdict else None})
    return rows


def summarize(rows: list[dict]) -> dict:
    result: dict = {"versions": {}, "tasks": {}}
    for version in ("main", "fix"):
        group = [row for row in rows if row["version"] == version and row["status"] == "complete"]
        result["versions"][version] = {
            "sessions": len([row for row in rows if row["version"] == version]), "complete": len(group),
            "facts": sum(row["facts"] or 0 for row in group), "facts_total": sum(row["facts_total"] or 0 for row in group),
            "mean_tokens": round(statistics.fmean(row["tokens"] for row in group)) if group else None,
            "median_tokens": round(statistics.median(row["tokens"] for row in group)) if group else None,
            "mean_tools": round(statistics.fmean(row["tools"] for row in group), 1) if group else None}
    by_task = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["status"] == "complete":
            by_task[row["task"]][row["version"]].append(row)
    for task, versions in by_task.items():
        result["tasks"][task] = {version: {"facts": sum(row["facts"] or 0 for row in group),
                                           "facts_total": sum(row["facts_total"] or 0 for row in group),
                                           "mean_tokens": round(statistics.fmean(row["tokens"] for row in group))}
                                 for version, group in versions.items()}
    pairs = defaultdict(dict)
    for row in rows:
        if row["status"] == "complete":
            pairs[(row["task"], row["repetition"])][row["version"]] = row
    matched = [pair for pair in pairs.values() if {"main", "fix"} <= set(pair)]
    ratios = [pair["fix"]["tokens"] / pair["main"]["tokens"] - 1 for pair in matched if pair["main"]["tokens"]]
    result["pairs"] = {"pairs": len(matched),
                       "fix_more_facts": sum((pair["fix"]["facts"] or 0) > (pair["main"]["facts"] or 0) for pair in matched),
                       "fix_fewer_facts": sum((pair["fix"]["facts"] or 0) < (pair["main"]["facts"] or 0) for pair in matched),
                       "fix_fewer_tokens": sum(pair["fix"]["tokens"] < pair["main"]["tokens"] for pair in matched),
                       "median_token_change": round(statistics.median(ratios), 3) if ratios else None}
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
