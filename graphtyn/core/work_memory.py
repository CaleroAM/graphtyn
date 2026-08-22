"""Outcome memory with recency weighting and source-staleness detection."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _memory_dir(root: Path) -> Path:
    return root / ".graphtyn" / "memory"


def _fingerprint(root: Path, files: list[str]) -> dict[str, str]:
    result = {}
    for name in files:
        path = root / name
        if path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return result


def save_result(root: Path, question: str, answer: str, nodes: list[str], outcome: str,
                files: list[str] | None = None, correction: str | None = None) -> Path:
    if outcome not in {"useful", "dead_end", "corrected"}:
        raise ValueError("outcome debe ser useful, dead_end o corrected")
    directory = _memory_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.time()
    record = {"version": 1, "timestamp": stamp, "question": question, "answer": answer,
              "nodes": sorted(set(nodes)), "outcome": outcome, "correction": correction,
              "files": _fingerprint(root, files or [])}
    target = directory / f"{int(stamp * 1000)}-{hashlib.sha256(question.encode()).hexdigest()[:8]}.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def reflect(root: Path, half_life_days: float = 30.0) -> dict[str, Any]:
    records = []
    for path in sorted(_memory_dir(root).glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stale_files = [name for name, old in item.get("files", {}).items()
                       if _fingerprint(root, [name]).get(name) != old]
        age_days = max(0.0, (time.time() - float(item.get("timestamp", 0))) / 86400)
        weight = 0.5 ** (age_days / max(0.01, half_life_days))
        records.append({**item, "weight": round(weight, 4), "stale": bool(stale_files), "stale_files": stale_files})
    by_node: dict[str, dict[str, Any]] = {}
    values = {"useful": 1.0, "dead_end": -0.75, "corrected": -1.0}
    for item in records:
        for node in item.get("nodes", []):
            entry = by_node.setdefault(node, {"score": 0.0, "signals": 0, "stale_signals": 0})
            entry["score"] += values.get(item.get("outcome"), 0) * item["weight"]
            entry["signals"] += 1
            entry["stale_signals"] += int(item["stale"])
    overlay = {}
    for node, entry in by_node.items():
        score = round(entry.pop("score"), 4)
        label = "preferred" if score >= 0.5 else "contested" if score <= -0.5 else "tentative"
        overlay[node] = {"label": label, "score": score, **entry}
    result = {"version": 1, "generated_at": int(time.time()), "records": len(records), "nodes": overlay,
              "stale_records": sum(item["stale"] for item in records)}
    output = root / ".graphtyn" / "learning-overlay.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lessons = ["# Graphtyn learned outcomes", ""]
    for node, item in sorted(overlay.items(), key=lambda pair: (-abs(pair[1]["score"]), pair[0])):
        stale = " — source changed; re-verify" if item["stale_signals"] else ""
        lessons.append(f"- **{node}**: {item['label']} ({item['score']:+.2f}, {item['signals']} signals){stale}")
    lessons_path = root / ".graphtyn" / "LESSONS.md"
    lessons_path.write_text("\n".join(lessons) + "\n", encoding="utf-8")
    return {**result, "overlay": str(output), "lessons": str(lessons_path)}


def attach_learning(result: dict[str, Any], root: Path) -> dict[str, Any]:
    """Attach only learning signals relevant to the bounded result nodes."""
    overlay_path = root / ".graphtyn" / "learning-overlay.json"
    try:
        overlay = json.loads(overlay_path.read_text(encoding="utf-8")).get("nodes", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return result
    keys = set()
    for node in result.get("nodes", []):
        keys.update(str(node.get(field) or "") for field in ("id", "name") if node.get(field))
    hints = {key: overlay[key] for key in sorted(keys) if key in overlay}
    if hints:
        result["learning"] = hints
        result["learning_guidance"] = "preferred is prior outcome evidence; tentative/contested or stale_signals require source re-verification."
    return result
