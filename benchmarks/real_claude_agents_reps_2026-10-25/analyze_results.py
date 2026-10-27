#!/usr/bin/env python3
"""Grade the repeated Claude Code runs and summarise per-corpus variability."""

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
grader.HERE = HERE  # read this directory's frozen tasks and write results here


def _summary(values: list[float]) -> dict:
    values = [value for value in values if value is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.fmean(values), 2),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else None,
            "min": round(min(values), 2), "max": round(max(values), 2)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--redis-repo", type=Path, required=True)
    parser.add_argument("--fmt-repo", type=Path, required=True)
    parser.add_argument("--rails-repo", type=Path, required=True)
    args = parser.parse_args()
    rows = grader._load_runs(args.run_root, {"redis": args.redis_repo, "fmt": args.fmt_repo,
                                             "rails": args.rails_repo})
    pairs = []
    for repetition in sorted({row.get("repetition", 1) for row in rows}):
        subset = [row for row in rows if row.get("repetition", 1) == repetition]
        for pair in grader._pairs(subset):
            pairs.append({**pair, "repetition": repetition})
    corpora = {}
    for repository in ("redis", "fmt", "rails"):
        items = [pair for pair in pairs if pair["repository"] == repository]
        corpora[repository] = {
            "pairs": len(items),
            "comparable_pairs": sum(pair["quality_comparable"] for pair in items),
            "quality_baseline": [pair["baseline"]["quality"] for pair in items],
            "quality_graphtyn": [pair["graphtyn"]["quality"] for pair in items],
            "token_delta_percent": _summary([pair["token_delta_percent"] for pair in items]),
            "cost_delta_percent": _summary([pair["cost_delta_percent"] for pair in items]),
            "session_time_delta_percent": _summary([pair["session_time_delta_percent"] for pair in items]),
            "baseline_tokens": _summary([pair["baseline"]["tokens"] for pair in items]),
            "graphtyn_tokens": _summary([pair["graphtyn"]["tokens"] for pair in items]),
            "citations_baseline": [pair["baseline"]["citations"] for pair in items],
            "citations_graphtyn": [pair["graphtyn"]["citations"] for pair in items],
            "graphtyn_reduced_tokens_in": sum((pair["token_delta_percent"] or 0) < 0 for pair in items),
        }
    (HERE / "grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    result = {"schema_version": "1.0", "runs": len(rows),
              "complete_runs": sum(row["session_status"] == "complete" for row in rows),
              "pairs": pairs, "corpora": corpora,
              "aggregation_warning": "Do not pool token totals across clients or models; n=3 per corpus.",
              "raw_artifacts_preserved": all(Path(row["audit"]["raw_directory"]).is_dir() for row in rows)}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(corpora, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
