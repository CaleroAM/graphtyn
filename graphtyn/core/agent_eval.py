"""Auditable key-fact grading for code-intelligence agent benchmarks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _answer(run: dict[str, Any]) -> str:
    return str(run.get("response") or run.get("answer") or "")


def grade_answer(answer: str, task: dict[str, Any]) -> dict[str, Any]:
    covered = 0
    partial = 0
    verdicts = []
    for fact in task.get("key_facts", []):
        groups = fact.get("patterns", [])
        hits = [bool(re.search(pattern, answer, re.IGNORECASE | re.MULTILINE)) for pattern in groups]
        if hits and all(hits):
            verdict, score = "covered", 1.0
            covered += 1
        elif any(hits):
            verdict, score = "partial", 0.5
            partial += 1
        else:
            verdict, score = "missing", 0.0
        verdicts.append({"id": fact["id"], "verdict": verdict, "score": score})
    total = len(verdicts)
    contradictions = [
        item["id"] for item in task.get("forbidden_facts", [])
        if all(re.search(pattern, answer, re.IGNORECASE | re.MULTILINE) for pattern in item.get("patterns", []))
    ]
    raw = covered + 0.5 * partial
    return {
        "covered": covered, "partial": partial, "total": total,
        "quality_score": round(raw / max(1, total), 4),
        "factual_errors": len(contradictions),
        "adjusted_quality_score": round(max(0, raw - len(contradictions)) / max(1, total), 4),
        "contradictions": contradictions,
        "facts": verdicts,
    }


def grade_runs(runs_path: Path, tasks_path: Path) -> list[dict[str, Any]]:
    raw = json.loads(runs_path.read_text(encoding="utf-8"))
    runs = raw if isinstance(raw, list) else [raw]
    task_data = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks = {task["id"]: task for task in task_data["tasks"]}
    graded = []
    for run in runs:
        task_id = run.get("task_id")
        if task_id not in tasks:
            raise ValueError(f"task_id desconocido: {task_id!r}")
        grade = grade_answer(_answer(run), tasks[task_id])
        graded.append({**run, **grade})
    return graded
