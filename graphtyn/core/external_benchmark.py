"""Adapters that score competitor graph exports against Graphtyn ground truth."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def score_graphify(graph_path: Path, truth_path: Path) -> dict[str, Any]:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph.get("nodes", [])}

    def expected_parts(symbol_id: str) -> tuple[str, str]:
        raw = symbol_id.removeprefix("symbol:")
        file, name = raw.rsplit(":", 1)
        name = re.sub(r"/[0-9]+$", "", name).split(".")[-1]
        return file, name

    def node_name(node: dict) -> str:
        label = str(node.get("label", "")).split("(", 1)[0].split(".")[-1]
        return re.sub(r"[^A-Za-z0-9_]", "", label)

    def matches(edge: dict, expected: dict) -> bool:
        source_file, source_name = expected_parts(expected["source"])
        target_file, target_name = expected_parts(expected["target"])
        source = nodes.get(edge.get("source"), {})
        target = nodes.get(edge.get("target"), {})
        line_match = re.search(r"[0-9]+", str(edge.get("source_location", "")))
        line = int(line_match.group()) if line_match else None
        return (
            edge.get("relation") in ("call", "calls")
            and source.get("source_file") == source_file and node_name(source) == source_name
            and target.get("source_file") == target_file and node_name(target) == target_name
            and (expected.get("line") is None or line == expected["line"])
        )

    expected = truth.get("expected_edges", [])
    forbidden = truth.get("forbidden_edges", [])
    found = [item for item in expected if any(matches(edge, item) for edge in graph.get("edges", []))]
    bad = [item for item in forbidden if any(matches(edge, item) for edge in graph.get("edges", []))]
    tp, fp, fn = len(found), len(bad), len(expected) - len(found)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "adapter": "graphify-v8-json",
        "nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", [])),
        "ground_truth": {
            "expected": len(expected), "forbidden": len(forbidden),
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(2 * precision * recall / max(1e-12, precision + recall), 4),
            "missing": [item for item in expected if item not in found],
            "forbidden_found": bad,
        },
    }
