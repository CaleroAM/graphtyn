#!/usr/bin/env python3
"""Grade the Graphify arm and compare it with the repeated baseline/Graphtyn runs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "real_claude_agents_reps_2026-10-25"
_SPEC = importlib.util.spec_from_file_location(
    "single_run_grader", HERE.parent / "real_claude_agents_2026-10-25" / "analyze_results.py")
grader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(grader)
grader.HERE = HERE  # same frozen tasks, copied into this directory


def _summary(values: list[float]) -> dict:
    values = [value for value in values if value is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.fmean(values), 2),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else None,
            "min": round(min(values), 2), "max": round(max(values), 2)}


def _side(row: dict) -> dict:
    return {"status": row["session_status"], "tokens": row["usage"]["total_tokens"],
            "usage": row["usage"], "seconds": row["wall_seconds"],
            "quality": row["quality"]["passed"], "citations": row["quality"]["citations"]["valid"],
            "cost_usd": row["usage"].get("provider_cost"),
            "index_seconds": (row.get("index_setup") or {}).get("seconds"),
            "mcp": row.get("claude_mcp"), "tool_counts": row["audit"]["tool_counts"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--redis-repo", type=Path, required=True)
    parser.add_argument("--fmt-repo", type=Path, required=True)
    parser.add_argument("--rails-repo", type=Path, required=True)
    args = parser.parse_args()
    graphify_rows = grader._load_runs(args.run_root, {"redis": args.redis_repo, "fmt": args.fmt_repo,
                                                      "rails": args.rails_repo})
    prior_rows = json.loads((PRIOR / "grades_by_run.json").read_text(encoding="utf-8"))
    rows = prior_rows + graphify_rows
    triples = []
    for repository in ("redis", "fmt", "rails"):
        for repetition in (1, 2, 3):
            arms = {row["arm"]: row for row in rows
                    if row["repository"] == repository and row.get("repetition", 1) == repetition}
            if set(arms) != {"baseline", "graphtyn", "graphify"}:
                continue
            base, graphtyn, graphify = (_side(arms[name]) for name in ("baseline", "graphtyn", "graphify"))
            triples.append({
                "repository": repository, "repetition": repetition, "model": arms["graphify"]["model"],
                "baseline": base, "graphtyn": graphtyn, "graphify": graphify,
                "graphify_mcp_called": bool((graphify["mcp"] or {}).get("tool_calls")),
                "quality_total": arms["baseline"]["quality"]["total"],
                "graphify_vs_baseline_tokens_percent": grader._delta(graphify["tokens"], base["tokens"]),
                "graphtyn_vs_baseline_tokens_percent": grader._delta(graphtyn["tokens"], base["tokens"]),
                "graphtyn_vs_graphify_tokens_percent": grader._delta(graphtyn["tokens"], graphify["tokens"]),
                "graphify_vs_baseline_cost_percent": grader._delta(graphify["cost_usd"], base["cost_usd"]),
                "graphtyn_vs_graphify_cost_percent": grader._delta(graphtyn["cost_usd"], graphify["cost_usd"]),
            })
    corpora = {}
    for repository in ("redis", "fmt", "rails"):
        items = [item for item in triples if item["repository"] == repository]
        corpora[repository] = {
            "repetitions": len(items),
            "quality": {arm: [item[arm]["quality"] for item in items] for arm in ("baseline", "graphtyn", "graphify")},
            "tokens": {arm: _summary([item[arm]["tokens"] for item in items])
                       for arm in ("baseline", "graphtyn", "graphify")},
            "cost_usd": {arm: _summary([item[arm]["cost_usd"] for item in items])
                         for arm in ("baseline", "graphtyn", "graphify")},
            "seconds": {arm: _summary([item[arm]["seconds"] for item in items])
                        for arm in ("baseline", "graphtyn", "graphify")},
            "graphify_vs_baseline_tokens_percent": _summary(
                [item["graphify_vs_baseline_tokens_percent"] for item in items]),
            "graphtyn_vs_graphify_tokens_percent": _summary(
                [item["graphtyn_vs_graphify_tokens_percent"] for item in items]),
            "graphtyn_vs_graphify_cost_percent": _summary(
                [item["graphtyn_vs_graphify_cost_percent"] for item in items]),
            "graphify_index_seconds": _summary([item["graphify"]["index_seconds"] for item in items]),
            "graphify_tool_calls": [item["graphify"]["mcp"]["tool_calls"] if item["graphify"]["mcp"] else None
                                    for item in items],
        }
    (HERE / "grades_by_run.json").write_text(json.dumps(graphify_rows, ensure_ascii=False, indent=2) + "\n")
    result = {"schema_version": "1.0", "graphify_runs": len(graphify_rows),
              "complete_graphify_runs": sum(row["session_status"] == "complete" for row in graphify_rows),
              "triples": triples, "corpora": corpora,
              "comparison_warning": ("Baseline and Graphtyn arms come from real_claude_agents_reps_2026-10-25; "
                                     "the Graphify arm ran later, so prompt-cache state and cost are not "
                                     "contemporaneous. Token totals are the primary metric."),
              "raw_artifacts_preserved": all(Path(row["audit"]["raw_directory"]).is_dir() for row in graphify_rows)}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(corpora, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
