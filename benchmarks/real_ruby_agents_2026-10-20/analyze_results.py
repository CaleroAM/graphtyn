#!/usr/bin/env python3
"""Audit and grade the frozen Rails agent benchmark without rerunning models."""

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
    candidates = []
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
    parts = Path(raw_path).parts
    for start in range(len(parts)):
        relative = Path(*parts[start:])
        source = repository / relative
        if source.is_file():
            return source, relative.as_posix()
    matches = list(repository.rglob(Path(raw_path).name))
    if len(matches) == 1:
        return matches[0], matches[0].relative_to(repository).as_posix()
    return None, raw_path


def _citations(answer: str, repository: Path) -> dict:
    pattern = re.compile(
        r"(?P<file>(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+\.rb)"
        r"(?::|#L)(?P<line>[0-9]+)"
    )
    checked = []
    for match in pattern.finditer(answer):
        source, relative = _resolve_citation(match.group("file"), repository)
        line = int(match.group("line"))
        line_count = None
        valid = False
        if source is not None:
            line_count = len(source.read_text(encoding="utf-8", errors="ignore").splitlines())
            valid = 1 <= line <= max(1, line_count)
        checked.append({
            "file": relative, "line": line, "line_count": line_count,
            "resolved": source is not None, "valid": valid,
        })
    rows = list({(item["file"], item["line"]): item for item in checked}.values())
    return {
        "total": len(rows),
        "resolved": sum(item["resolved"] for item in rows),
        "valid": sum(item["valid"] for item in rows),
        "invalid": [item for item in rows if item["resolved"] and not item["valid"]],
        "unresolved_short_or_ambiguous": [item for item in rows if not item["resolved"]],
    }


def _load_runs(root: Path, repository: Path) -> list[dict]:
    task = json.loads((HERE / "tasks.json").read_text())["tasks"][0]
    adjudications = json.loads((HERE / "manual_adjudication.json").read_text())
    rows = []
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
        answer_path = run_dir / "answer.txt"
        events_path = run_dir / "events.jsonl"
        answer = answer_path.read_text(encoding="utf-8", errors="replace")
        events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
        normalized = answer.casefold()
        automatic = {
            fact["id"]: any(term.casefold() in normalized for term in fact["any"])
            for fact in task["rubric"]
        }
        adjudication = adjudications.get(run_dir.name, {})
        facts = dict(automatic)
        for fact_id, decision in (adjudication.get("facts") or {}).items():
            facts[fact_id] = bool(decision["value"])
        package = _context_package(events)
        source_retrieval = (package or {}).get("source_retrieval") or {}
        timing = (package or {}).get("timing_ms") or {}
        tools = _tool_names(events)
        fallback_ms = _mcp_query_duration_ms(events)
        rows.append({
            **summary,
            "run_id": run_dir.name,
            "quality": {
                "automatic_facts": automatic,
                "automatic_passed": sum(automatic.values()),
                "facts": facts,
                "passed": sum(facts.values()),
                "total": len(facts),
                "coverage": sum(facts.values()) / len(facts),
                "task_complete": bool(adjudication.get("task_complete", True)),
                "task_complete_reason": adjudication.get("task_complete_reason"),
                "citations": _citations(answer, repository),
                "answer_bytes": len(answer.encode("utf-8")),
                "adjudication": adjudication or None,
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
                "total_ms": fallback_ms,
                "unavailable_fields": [
                    "context_id", "selected_nodes", "missing", "do_not_expand",
                    "payload_tokens", "payload_truncated", "source_characters",
                    "source_snippets",
                ],
            } if fallback_ms is not None else None)),
            "audit": {
                "tool_names": tools,
                "forbidden_tools": sorted(set(tools) & FORBIDDEN_TOOLS),
                "answer_sha256": _sha256(answer_path),
                "events_sha256": _sha256(events_path),
                "raw_directory": str(run_dir),
            },
        })
    return sorted(rows, key=lambda row: (row["client"], row["arm"]))


def _delta(treatment: int | float | None, baseline: int | float | None) -> float | None:
    if not isinstance(treatment, (int, float)) or not isinstance(baseline, (int, float)) or baseline == 0:
        return None
    return round((treatment - baseline) * 100 / baseline, 2)


def _pairs(rows: list[dict]) -> list[dict]:
    pairs = []
    for client in ("opencode", "codex", "antigravity"):
        items = {row["arm"]: row for row in rows if row["client"] == client}
        if set(items) != {"baseline", "graphtyn"}:
            continue
        baseline, treatment = items["baseline"], items["graphtyn"]
        comparable = (
            baseline["session_status"] == treatment["session_status"] == "complete"
            and baseline["quality"]["passed"] == treatment["quality"]["passed"]
            and baseline["quality"]["task_complete"]
            and treatment["quality"]["task_complete"]
        )
        base_tokens = baseline["usage"].get("total_tokens")
        treatment_tokens = treatment["usage"].get("total_tokens")
        base_technical = baseline["usage_accounting"].get("technical_total_including_cache")
        treatment_technical = treatment["usage_accounting"].get("technical_total_including_cache")
        index_seconds = (treatment.get("index_setup") or {}).get("seconds")
        pairs.append({
            "client": client,
            "model": baseline["model"],
            "baseline": {
                "status": baseline["session_status"], "tokens": base_tokens,
                "technical_tokens_including_cache": base_technical,
                "seconds": baseline["wall_seconds"], "quality": baseline["quality"]["passed"],
                "task_complete": baseline["quality"]["task_complete"],
            },
            "graphtyn": {
                "status": treatment["session_status"], "tokens": treatment_tokens,
                "technical_tokens_including_cache": treatment_technical,
                "seconds": treatment["wall_seconds"], "quality": treatment["quality"]["passed"],
                "task_complete": treatment["quality"]["task_complete"],
                "index_seconds": index_seconds,
                "first_use_seconds": round(treatment["wall_seconds"] + index_seconds, 3)
                if isinstance(index_seconds, (int, float)) else None,
            },
            "quality_total": baseline["quality"]["total"],
            "quality_comparable": comparable,
            "token_delta_percent": _delta(treatment_tokens, base_tokens) if comparable else None,
            "technical_token_delta_percent": _delta(treatment_technical, base_technical) if comparable else None,
            "component_deltas_percent": {
                key: _delta(treatment["usage"].get(key), baseline["usage"].get(key)) if comparable else None
                for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")
            },
            "session_time_delta_percent": _delta(treatment["wall_seconds"], baseline["wall_seconds"])
            if comparable else None,
            "first_use_time_delta_percent": _delta(treatment["wall_seconds"] + index_seconds,
                                                    baseline["wall_seconds"])
            if comparable and isinstance(index_seconds, (int, float)) else None,
        })
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--rails-repo", type=Path, required=True)
    args = parser.parse_args()
    rows = _load_runs(args.run_root, args.rails_repo)
    pairs = _pairs(rows)
    (HERE / "grades_by_run.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "schema_version": "1.0",
        "runs": len(rows),
        "complete_runs": sum(row["session_status"] == "complete" for row in rows),
        "incomplete_runs": sum(row["session_status"] != "complete" for row in rows),
        "pairs": pairs,
        "aggregation_warning": "Do not pool token totals across clients or models.",
        "monetary_warning": "Provider cost is zero only for the free OpenCode model and unavailable for the other clients.",
        "raw_artifacts_preserved": all(Path(row["audit"]["raw_directory"]).is_dir() for row in rows),
    }
    (HERE / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
