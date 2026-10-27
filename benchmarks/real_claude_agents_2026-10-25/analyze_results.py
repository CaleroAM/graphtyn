#!/usr/bin/env python3
"""Grade the Claude Code replica of the frozen Redis, fmt and Rails benchmarks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
CORPORA = {"REDIS_COMMAND_FLOW": "redis", "FMT_FORMAT_FLOW": "fmt", "RAILS_SAVE_FLOW": "rails"}
EXTENSIONS = "c|h|cc|cpp|cxx|hh|hpp|hxx|rb"
# Claude Code names for the tools the read-only protocol forbids.
FORBIDDEN_TOOLS = {"Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent"}
PRIOR_RESULTS = {
    "redis": "benchmarks/real_c_cpp_agents_2026-10-20/results.json",
    "fmt": "benchmarks/real_c_cpp_agents_2026-10-20/results.json",
    "rails": "benchmarks/real_ruby_agents_2026-10-20/results.json",
}


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _context_package(events: list[dict]) -> dict | None:
    candidates = []
    for value in _walk(events):
        if isinstance(value, str) and "adaptive-intent-v2" in value:
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and parsed.get("planner") == "adaptive-intent-v2":
                candidates.append(parsed)
    return max(candidates, key=lambda item: len(json.dumps(item))) if candidates else None


def _tool_names(events: list[dict]) -> list[str]:
    return [block.get("name", "") for event in events if event.get("type") == "assistant"
            for block in (event.get("message") or {}).get("content") or []
            if isinstance(block, dict) and block.get("type") == "tool_use"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_citation(raw_path: str, repository: Path) -> tuple[Path | None, str]:
    parts = Path(raw_path).parts
    for start in range(len(parts)):
        relative = Path(*parts[start:])
        if (repository / relative).is_file():
            return repository / relative, relative.as_posix()
    matches = list(repository.rglob(Path(raw_path).name))
    if len(matches) == 1:
        return matches[0], matches[0].relative_to(repository).as_posix()
    return None, raw_path


def _citations(answer: str, repository: Path) -> dict:
    pattern = re.compile(rf"(?P<file>(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+\.(?:{EXTENSIONS}))"
                         r"(?::|#L)(?P<line>[0-9]+)")
    rows = {}
    for match in pattern.finditer(answer):
        source, relative = _resolve_citation(match.group("file"), repository)
        line = int(match.group("line"))
        count = len(source.read_text(encoding="utf-8", errors="ignore").splitlines()) if source else None
        rows[(relative, line)] = {"file": relative, "line": line, "line_count": count,
                                  "valid": bool(count) and 1 <= line <= count}
    return {"total": len(rows), "valid": sum(item["valid"] for item in rows.values()),
            "invalid": [item for item in rows.values() if not item["valid"]]}


def _load_runs(root: Path, repositories: dict[str, Path]) -> list[dict]:
    specs = {}
    for name in ("redis", "fmt", "rails"):
        task = json.loads((HERE / f"{name}_tasks.json").read_text())["tasks"][0]
        specs[task["id"]] = task
    rows = []
    for summary_path in sorted(root.glob("*/runs/*/summary.json")):
        run_dir = summary_path.parent
        summary = json.loads(summary_path.read_text())
        repository = CORPORA[summary["task_id"]]
        answer_path, events_path = run_dir / "answer.txt", run_dir / "events.jsonl"
        answer = answer_path.read_text(encoding="utf-8", errors="replace")
        events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
        normalized = answer.casefold()
        facts = {fact["id"]: any(term.casefold() in normalized for term in fact["any"])
                 for fact in specs[summary["task_id"]]["rubric"]}
        package = _context_package(events)
        tools = _tool_names(events)
        rows.append({
            **summary,
            "repository": repository,
            "run_id": run_dir.name,
            "quality": {"facts": facts, "passed": sum(facts.values()), "total": len(facts),
                        "citations": _citations(answer, repositories[repository]),
                        "answer_bytes": len(answer.encode("utf-8")),
                        "grader": "deterministic frozen rubric; no manual adjudication"},
            "retrieval": ({
                "context_id": package.get("context_id"),
                "selected_nodes": (package.get("budget") or {}).get("selected_nodes"),
                "missing": package.get("missing"),
                "do_not_expand": package.get("do_not_expand"),
                "payload_tokens": package.get("payload_tokens"),
                "payload_truncated": package.get("payload_truncated"),
                "total_ms": (package.get("timing_ms") or {}).get("total"),
            } if package else None),
            "audit": {"tool_counts": {name: tools.count(name) for name in sorted(set(tools))},
                      "forbidden_tools": sorted(set(tools) & FORBIDDEN_TOOLS),
                      "answer_sha256": _sha256(answer_path),
                      "events_sha256": _sha256(events_path),
                      "raw_directory": str(run_dir)},
        })
    return sorted(rows, key=lambda row: (row["repository"], row["arm"]))


def _delta(treatment, baseline) -> float | None:
    if not isinstance(treatment, (int, float)) or not isinstance(baseline, (int, float)) or not baseline:
        return None
    return round((treatment - baseline) * 100 / baseline, 2)


def _pairs(rows: list[dict]) -> list[dict]:
    paired = []
    for repository in ("redis", "fmt", "rails"):
        items = {row["arm"]: row for row in rows if row["repository"] == repository}
        if set(items) != {"baseline", "graphtyn"}:
            continue
        base, treat = items["baseline"], items["graphtyn"]
        valid_treatment = bool((treat.get("claude_mcp") or {}).get("tool_calls"))
        comparable = (base["session_status"] == treat["session_status"] == "complete"
                      and base["quality"]["passed"] == treat["quality"]["passed"] and valid_treatment)
        side = lambda row: {"status": row["session_status"], "tokens": row["usage"]["total_tokens"],
                            "usage": row["usage"], "seconds": row["wall_seconds"],
                            "quality": row["quality"]["passed"],
                            "citations": row["quality"]["citations"]["valid"],
                            "cost_usd": row["usage"].get("provider_cost")}
        paired.append({
            "repository": repository, "client": "claude", "model": base["model"],
            "baseline": side(base),
            "graphtyn": {**side(treat), "index_seconds": (treat.get("index_setup") or {}).get("seconds"),
                         "mcp": treat.get("claude_mcp")},
            "quality_total": base["quality"]["total"],
            "graphtyn_mcp_called": valid_treatment,
            "quality_comparable": comparable,
            "token_delta_percent": _delta(treat["usage"]["total_tokens"], base["usage"]["total_tokens"]),
            "cost_delta_percent": _delta(treat["usage"].get("provider_cost"), base["usage"].get("provider_cost")),
            "session_time_delta_percent": _delta(treat["wall_seconds"], base["wall_seconds"]),
            "component_deltas_percent": {key: _delta(treat["usage"].get(key), base["usage"].get(key))
                                         for key in ("input_tokens", "cached_input_tokens",
                                                     "cache_write_input_tokens", "output_tokens")},
        })
    return paired


def _prior(repository: str) -> list[dict]:
    path = HERE.parents[1] / PRIOR_RESULTS[repository]
    pairs = json.loads(path.read_text()).get("pairs", [])
    return [{"client": item["client"], "model": item.get("model"),
             "token_delta_percent": item.get("token_delta_percent"),
             "quality": f"{item['baseline'].get('quality')}→{item['graphtyn'].get('quality')}"}
            for item in pairs if item.get("repository", repository) == repository]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--redis-repo", type=Path, required=True)
    parser.add_argument("--fmt-repo", type=Path, required=True)
    parser.add_argument("--rails-repo", type=Path, required=True)
    args = parser.parse_args()
    rows = _load_runs(args.run_root, {"redis": args.redis_repo, "fmt": args.fmt_repo,
                                      "rails": args.rails_repo})
    pairs = _pairs(rows)
    (HERE / "grades_by_run.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    result = {
        "schema_version": "1.0",
        "runs": len(rows),
        "complete_runs": sum(row["session_status"] == "complete" for row in rows),
        "pairs": pairs,
        "prior_clients_same_tasks": {name: _prior(name) for name in ("redis", "fmt", "rails")},
        "aggregation_warning": "Do not pool token totals across clients or models.",
        "raw_artifacts_preserved": all(Path(row["audit"]["raw_directory"]).is_dir() for row in rows),
    }
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
