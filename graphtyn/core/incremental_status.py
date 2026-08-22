"""Observable, deterministic snapshots for index updates."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _records(graph: dict) -> dict[str, str]:
    records = {}
    for node in graph.get("nodes", []):
        if str(node.get("id", "")).startswith("file:"):
            value = json.dumps({k: node.get(k) for k in ("id", "details", "kind", "size", "sha256")}, sort_keys=True, ensure_ascii=False)
            records[str(node["id"])[5:]] = hashlib.sha256(value.encode()).hexdigest()
    return records


def build_update_status(graph: dict, previous: dict | None, *, mode: str, started_at: float,
                        enriched_files: int, ai_calls: int | None = None) -> dict[str, Any]:
    current, old = _records(graph), _records(previous or {})
    added = sorted(current.keys() - old.keys())
    removed = sorted(old.keys() - current.keys())
    modified = sorted(path for path in current.keys() & old.keys() if current[path] != old[path])
    duration = round(max(0.0, time.monotonic() - started_at), 4)
    deep_reasons = []
    parser_old = (previous or {}).get("metadata", {}).get("parser_version")
    parser_new = graph.get("metadata", {}).get("parser_version")
    if previous and parser_old != parser_new:
        deep_reasons.append("parser_version_changed")
    if len(added) + len(removed) + len(modified) > max(100, len(current) // 2):
        deep_reasons.append("large_change_set")
    return {"mode": mode, "duration_seconds": duration, "added": added, "modified": modified,
            "removed": removed, "changed_count": len(added) + len(modified) + len(removed),
            "enriched_files": enriched_files, "local_ai_calls": ai_calls,
            "deep_reindex_recommended": bool(deep_reasons), "deep_reindex_reasons": deep_reasons,
            "estimated_paid_tokens": 0, "token_note": "Structural indexing and local Ollama calls do not consume paid-provider tokens."}


def save_update_status(directory: Path, status: dict[str, Any]) -> Path:
    target = directory / "last-update.json"
    target.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

