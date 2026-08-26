"""Deterministic edge calibration and deduplication."""

from __future__ import annotations

from typing import Any


_CONFIDENCE_RANK = {"AMBIGUOUS": 0, "INFERRED": 1, "EXTRACTED": 2, "REVIEWED": 3, "TYPED": 4}


def relation_score(link: dict[str, Any]) -> float:
    """Return an auditable 0..1 confidence score without inventing certainty."""
    confidence = str(link.get("confidence") or "INFERRED").upper()
    base = {"AMBIGUOUS": 0.35, "INFERRED": 0.58, "EXTRACTED": 0.82,
            "REVIEWED": 0.94, "TYPED": 0.98}.get(confidence, 0.5)
    resolution = link.get("resolution") or {}
    candidates = max(1, int(resolution.get("candidates") or 1))
    score = float(resolution.get("score") or 0)
    if candidates > 1:
        base -= min(0.3, (candidates - 1) * 0.06)
    base += min(0.12, score * 0.01)
    if link.get("file") and link.get("line"):
        base += 0.04
    return round(max(0.05, min(0.99, base)), 3)


def normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Remove exact logical duplicates and retain the strongest evidence."""
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    duplicates = 0
    for original in graph.get("links", []):
        link = dict(original)
        key = (link.get("source"), link.get("target"), link.get("label"),
               link.get("file"), link.get("line"))
        link["confidence_score"] = relation_score(link)
        previous = unique.get(key)
        if previous is None:
            unique[key] = link
            continue
        duplicates += 1
        old_rank = (_CONFIDENCE_RANK.get(str(previous.get("confidence") or "").upper(), -1),
                    previous.get("confidence_score", 0))
        new_rank = (_CONFIDENCE_RANK.get(str(link.get("confidence") or "").upper(), -1),
                    link.get("confidence_score", 0))
        if new_rank > old_rank:
            unique[key] = link
    graph["links"] = list(unique.values())
    graph.setdefault("metadata", {})["graph_hygiene"] = {
        "duplicates_removed": duplicates,
        "relations_scored": len(unique),
        "score_version": "confidence-v1",
    }
    return graph
