#!/usr/bin/env python3
"""Grade agent sessions that compare Graphtyn flow-budget variants on one split.

Layout: <run-root>/<variant>/<corpus>/<task id lowercased>/<client>/runs/<run_id>/,
where variant `none` holds the sessions without Graphtyn. Sessions under a
`superseded` directory (run before a fix) are reported apart and not graded.

Total tokens mix kinds with very different prices: cached reads (the client's
fixed prompt and tool definitions, re-read on every turn), cache writes,
uncached input and output. Each session is also reported by kind and as
`weighted`, input-equivalent tokens under PRICE_RATIOS (relative to one
uncached input token; Anthropic and OpenAI publish these ratios for their
current models, adjust them if the price list changes).

usage: python analyze_variants.py test3 <run-root> [<run-root of another repetition> ...] [--json out]
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from analyze_results import grader

HERE = Path(__file__).resolve().parent
CORPORA = ("redis", "fmt", "rails", "flask", "lua")
KINDS = ("uncached_input", "cache_read", "cache_write", "output")
PRICE_RATIOS = {
    "claude": {"uncached_input": 1.0, "cache_read": 0.1, "cache_write": 1.25, "output": 5.0},
    "codex": {"uncached_input": 1.0, "cache_read": 0.1, "cache_write": 1.0, "output": 8.0},
}


def token_kinds(client: str, usage: dict) -> dict[str, int]:
    """Usage split into disjoint kinds; Codex counts cached reads inside input_tokens."""
    cached = int(usage.get("cached_input_tokens") or 0)
    raw_input = int(usage.get("input_tokens") or 0)
    kinds = {"uncached_input": raw_input - cached if client == "codex" else raw_input,
             "cache_read": cached, "cache_write": int(usage.get("cache_write_input_tokens") or 0),
             "output": int(usage.get("output_tokens") or 0)}
    ratios = PRICE_RATIOS.get(client, PRICE_RATIOS["claude"])
    kinds["weighted"] = round(sum(kinds[kind] * ratios[kind] for kind in KINDS))
    return kinds


def load_runs(split: str, root: Path, repetition: int = 1) -> list[dict]:
    specs = {task["id"]: task for corpus in CORPORA if (HERE / split / f"{corpus}_tasks.json").exists()
             for task in json.loads((HERE / split / f"{corpus}_tasks.json").read_text())["tasks"]}
    rows = []
    for summary_path in sorted(root.glob("*/*/*/*/runs/*/summary.json")):
        variant = summary_path.relative_to(root).parts[0]
        summary = json.loads(summary_path.read_text())
        task = specs[summary["task_id"]]
        run_dir = summary_path.parent
        answer_path = run_dir / "answer.txt"
        answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        facts = {fact["id"]: any(term.casefold() in answer.casefold() for term in fact["any"]) for fact in task["rubric"]}
        rows.append({"variant": variant, "repetition": repetition, "task_id": summary["task_id"], "client": summary["client"],
                     "arm": summary["arm"], "session_status": summary["session_status"],
                     "tokens": summary["usage"].get("total_tokens"), "seconds": summary["wall_seconds"],
                     **token_kinds(summary["client"], summary["usage"]),
                     "passed": sum(facts.values()), "total": len(facts),
                     "tool_calls": len(grader._tools(summary["client"], events)), "raw_directory": str(run_dir)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("split")
    parser.add_argument("run_roots", type=Path, nargs="+")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rows = [row for index, root in enumerate(args.run_roots, 1) for row in load_runs(args.split, root, index)]
    graded = [row for row in rows if row["variant"] != "superseded" and row["session_status"] == "complete"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in graded:
        groups.setdefault((row["client"], row["variant"]), []).append(row)
    summary = {f"{client}/{variant}": {
        "n": len(group),
        "mean_tokens": round(statistics.fmean(row["tokens"] for row in group)),
        "median_tokens": round(statistics.median(row["tokens"] for row in group)),
        **{f"mean_{kind}": round(statistics.fmean(row[kind] for row in group)) for kind in (*KINDS, "weighted")},
        "mean_quality": round(statistics.fmean(row["passed"] / row["total"] for row in group), 4),
        "mean_tool_calls": round(statistics.fmean(row["tool_calls"] for row in group), 1),
        "mean_seconds": round(statistics.fmean(row["seconds"] for row in group), 1)}
        for (client, variant), group in sorted(groups.items())}
    result = {"schema_version": "1.0", "split": args.split, "sessions": len(rows),
              "graded_sessions": len(graded),
              "incomplete": [f"{row['variant']}/{row['client']}/{row['task_id']}" for row in rows
                             if row["variant"] != "superseded" and row["session_status"] != "complete"],
              "summary": summary, "runs": rows}
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
