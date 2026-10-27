#!/usr/bin/env python3
"""Merge, grade and audit the frozen Redis/fmt agent benchmark runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
FORBIDDEN_TOOLS = {
    "browser_subagent", "define_subagent", "invoke_subagent", "search_web",
    "webfetch", "task",
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
    candidates: list[dict] = []
    for value in _walk(events):
        if isinstance(value, dict) and value.get("planner") == "adaptive-intent-v2":
            candidates.append(value)
        elif isinstance(value, str) and "adaptive-intent-v2" in value:
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and parsed.get("planner") == "adaptive-intent-v2":
                candidates.append(parsed)
    return max(candidates, key=lambda item: len(json.dumps(item))) if candidates else None


def _tool_names(events: list[dict]) -> list[str]:
    names = []
    for event in events:
        part = event.get("part") or {}
        item = event.get("item") or {}
        update = event.get("step_update") or {}
        for value in (part.get("tool"), item.get("tool"), update.get("tool_name")):
            if value:
                names.append(str(value))
    return names


def _mcp_query_duration_ms(events: list[dict]) -> float | None:
    """Recover Antigravity MCP timing when its event stream omits tool output."""
    for event in events:
        update = event.get("step_update") or {}
        info = update.get("tool_info") or {}
        parameters = info.get("parameters") or {}
        if (update.get("state") == "DONE"
                and info.get("name") == "call_mcp_tool"
                and parameters.get("ToolName") == "graph_query_intent"):
            duration = update.get("duration_seconds")
            if isinstance(duration, (int, float)):
                return round(duration * 1000, 3)
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_citation(raw_path: str, repository: Path) -> tuple[Path | None, str]:
    """Resolve repository-relative citations and absolute workspace copies."""
    parts = Path(raw_path).parts
    for start in range(len(parts)):
        relative = Path(*parts[start:])
        source = repository / relative
        if source.is_file():
            return source, relative.as_posix()
    basename_matches = list(repository.rglob(Path(raw_path).name))
    if len(basename_matches) == 1:
        source = basename_matches[0]
        return source, source.relative_to(repository).as_posix()
    return None, raw_path


def _citations(answer: str, repository: Path) -> dict:
    pattern = re.compile(
        r"(?P<file>(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+\.(?:c|h|cc|cpp|cxx|hh|hpp|hxx))"
        r"(?::|#L)(?P<line>[0-9]+)"
    )
    checked = []
    for match in pattern.finditer(answer):
        raw_path = match.group("file")
        line = int(match.group("line"))
        source, relative = _resolve_citation(raw_path, repository)
        line_count = None
        valid = False
        if source is not None:
            line_count = len(source.read_text(encoding="utf-8", errors="ignore").splitlines())
            valid = 1 <= line <= max(1, line_count)
        checked.append({"file": relative, "line": line, "line_count": line_count, "valid": valid})
    unique = {(item["file"], item["line"]): item for item in checked}
    rows = list(unique.values())
    return {
        "total": len(rows),
        "valid": sum(item["valid"] for item in rows),
        "invalid": [item for item in rows if not item["valid"]],
    }


def _load_runs(roots: list[Path], repositories: dict[str, Path]) -> list[dict]:
    specs = {
        "REDIS_COMMAND_FLOW": json.loads((HERE / "redis_tasks.json").read_text())["tasks"][0],
        "FMT_FORMAT_FLOW": json.loads((HERE / "fmt_tasks.json").read_text())["tasks"][0],
    }
    adjudication_path = HERE / "manual_adjudication.json"
    adjudications = (json.loads(adjudication_path.read_text())
                     if adjudication_path.is_file() else {})
    rows = []
    for root in roots:
        for summary_path in sorted(root.glob("runs/*/summary.json")):
            run_dir = summary_path.parent
            summary = json.loads(summary_path.read_text())
            if summary.get("client") == "codex":
                accounting = dict(summary.get("usage_accounting") or {})
                accounting.update({
                    "reported_total_includes": ["input_including_cached", "output_including_reasoning"],
                    "cached_input_is_separate": False,
                    "cached_input_is_subset_of_input": True,
                    "reasoning_is_subset_of_output": True,
                    "technical_total_including_cache": summary.get("usage", {}).get("total_tokens"),
                    "normalization_correction": "cached input is a subset of Codex input_tokens",
                })
                summary["usage_accounting"] = accounting
            task_id = summary["task_id"]
            repository_name = "redis" if task_id.startswith("REDIS") else "fmt"
            answer_path = run_dir / "answer.txt"
            events_path = run_dir / "events.jsonl"
            answer = answer_path.read_text(encoding="utf-8", errors="replace")
            events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
            normalized = answer.casefold()
            rubric = specs[task_id]["rubric"]
            automatic_facts = {
                fact["id"]: any(term.casefold() in normalized for term in fact["any"])
                for fact in rubric
            }
            run_adjudication = adjudications.get(run_dir.name, {})
            facts = dict(automatic_facts)
            for fact_id, decision in (run_adjudication.get("facts") or {}).items():
                facts[fact_id] = bool(decision["value"])
            package = _context_package(events)
            source_retrieval = (package or {}).get("source_retrieval") or {}
            timing = (package or {}).get("timing_ms") or {}
            tools = _tool_names(events)
            rows.append({
                **summary,
                "repository": repository_name,
                "run_id": run_dir.name,
                "quality": {
                    "automatic_facts": automatic_facts,
                    "automatic_passed": sum(automatic_facts.values()),
                    "facts": facts,
                    "passed": sum(facts.values()),
                    "total": len(facts),
                    "coverage": sum(facts.values()) / len(facts),
                    "citations": _citations(answer, repositories[repository_name]),
                    "answer_bytes": len(answer.encode("utf-8")),
                    "adjudication": run_adjudication or None,
                    "grader": "deterministic frozen rubric plus disclosed non-independent adjudication",
                },
                "retrieval": ({
                    "output_captured": True,
                    "context_id": package.get("context_id"),
                    "selected_nodes": (package.get("budget") or {}).get("selected_nodes"),
                    "missing": package.get("missing"),
                    "do_not_expand": package.get("do_not_expand"),
                    "payload_tokens": package.get("payload_tokens"),
                    "payload_truncated": package.get("payload_truncated"),
                    "source_characters": source_retrieval.get("characters"),
                    "source_snippets": source_retrieval.get("snippets"),
                    "total_ms": timing.get("total"),
                } if package else ({
                    "output_captured": False,
                    "total_ms": _mcp_query_duration_ms(events),
                    "unavailable_fields": [
                        "context_id", "selected_nodes", "missing", "do_not_expand",
                        "payload_tokens", "payload_truncated", "source_characters",
                        "source_snippets",
                    ],
                } if _mcp_query_duration_ms(events) is not None else None)),
                "audit": {
                    "tool_names": tools,
                    "forbidden_tools": sorted(set(tools) & FORBIDDEN_TOOLS),
                    "answer_sha256": _sha256(answer_path),
                    "events_sha256": _sha256(events_path),
                    "raw_directory": str(run_dir),
                },
            })
    return sorted(rows, key=lambda row: (row["repository"], row["client"], row["arm"]))


def _delta(treatment: int | float | None, baseline: int | float | None) -> float | None:
    if not isinstance(treatment, (int, float)) or not isinstance(baseline, (int, float)) or baseline == 0:
        return None
    return round((treatment - baseline) * 100 / baseline, 2)


def _pairs(rows: list[dict]) -> list[dict]:
    paired = []
    for repository in ("redis", "fmt"):
        for client in ("opencode", "codex", "antigravity"):
            items = {(row["arm"]): row for row in rows
                     if row["repository"] == repository and row["client"] == client}
            if set(items) != {"baseline", "graphtyn"}:
                continue
            baseline, treatment = items["baseline"], items["graphtyn"]
            base_tokens = baseline["usage"].get("total_tokens")
            treatment_tokens = treatment["usage"].get("total_tokens")
            base_technical = baseline["usage_accounting"].get("technical_total_including_cache")
            treatment_technical = treatment["usage_accounting"].get("technical_total_including_cache")
            comparable = (
                baseline["session_status"] == treatment["session_status"] == "complete"
                and baseline["quality"]["passed"] == treatment["quality"]["passed"]
            )
            paired.append({
                "repository": repository,
                "client": client,
                "model": baseline["model"],
                "baseline": {
                    "status": baseline["session_status"], "tokens": base_tokens,
                    "technical_tokens_including_cache": base_technical,
                    "seconds": baseline["wall_seconds"], "quality": baseline["quality"]["passed"],
                },
                "graphtyn": {
                    "status": treatment["session_status"], "tokens": treatment_tokens,
                    "technical_tokens_including_cache": treatment_technical,
                    "seconds": treatment["wall_seconds"], "quality": treatment["quality"]["passed"],
                    "index_seconds": (treatment.get("index_setup") or {}).get("seconds"),
                },
                "quality_total": baseline["quality"]["total"],
                "quality_comparable": comparable,
                "token_delta_percent": _delta(treatment_tokens, base_tokens) if comparable else None,
                "technical_token_delta_percent": _delta(treatment_technical, base_technical)
                if comparable else None,
                "component_deltas_percent": {
                    key: _delta(treatment["usage"].get(key), baseline["usage"].get(key))
                    if comparable else None
                    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")
                },
                "session_time_delta_percent": _delta(treatment["wall_seconds"], baseline["wall_seconds"])
                if comparable else None,
            })
    return paired


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", action="append", type=Path, required=True)
    parser.add_argument("--redis-repo", type=Path, required=True)
    parser.add_argument("--fmt-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    rows = _load_runs(args.run_root, {"redis": args.redis_repo, "fmt": args.fmt_repo})
    pairs = _pairs(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "grades_by_run.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "schema_version": "1.0",
        "runs": len(rows),
        "complete_runs": sum(row["session_status"] == "complete" for row in rows),
        "incomplete_runs": sum(row["session_status"] != "complete" for row in rows),
        "pairs": pairs,
        "aggregation_warning": "Do not pool token totals across clients or models.",
        "raw_artifacts_preserved": all(Path(row["audit"]["raw_directory"]).is_dir() for row in rows),
    }
    (args.output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
