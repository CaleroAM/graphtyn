"""Reproducible structural and retrieval benchmarks for real repositories."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .ast_parser import ASTParser


def run_benchmark(root: Path, ground_truth_path: Path | None = None, cache_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    parser = ASTParser()
    started = time.perf_counter()
    graph = parser.scan_directory(root, respect_git=True, cache_path=cache_path)
    elapsed = time.perf_counter() - started
    warm_started = time.perf_counter()
    parser.scan_directory(root, respect_git=True, cache_path=cache_path)
    warm_elapsed = time.perf_counter() - warm_started
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    node_ids = {n.get("id") for n in nodes}
    dangling = [l for l in links if l.get("source") not in node_ids or l.get("target") not in node_ids]
    unique_edges = {
        (l.get("source"), l.get("target"), l.get("label"), l.get("file") if l.get("label") == "llama" else None,
         l.get("line") if l.get("label") == "llama" else None)
        for l in links
    }
    duplicates = len(links) - len(unique_edges)
    calls = [link for link in links if link.get("label") == "llama"]
    ambiguous_calls = sum(link.get("confidence") == "AMBIGUOUS" for link in calls)
    kinds: dict[str, int] = {}
    parsers: dict[str, int] = {}
    for node in nodes:
        kinds[node.get("kind", "unknown")] = kinds.get(node.get("kind", "unknown"), 0) + 1
        parser_name = node.get("parser")
        if parser_name:
            parsers[parser_name] = parsers.get(parser_name, 0) + 1

    result: dict[str, Any] = {
        "schema_version": 1,
        "project": root.name,
        "path": str(root),
        "elapsed_seconds": round(elapsed, 4),
        "warm_cache_seconds": round(warm_elapsed, 4),
        "warm_cache_speedup": round(elapsed / warm_elapsed, 2) if warm_elapsed else None,
        "nodes": len(nodes),
        "links": len(links),
        "node_kinds": kinds,
        "parsers": parsers,
        "quality": {
            "dangling_edges": len(dangling),
            "duplicate_edges": duplicates,
            "structural_validity": round(1 - (len(dangling) / max(1, len(links))), 4),
            "call_edges": len(calls),
            "ambiguous_calls": ambiguous_calls,
            "ambiguous_call_rate": round(ambiguous_calls / max(1, len(calls)), 4),
            "symbol_to_symbol_calls": sum(str(link.get("source", "")).startswith("symbol:") for link in calls),
        },
    }
    if ground_truth_path:
        truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        def node_file(node: dict) -> str | None:
            if node.get("file"):
                return node["file"]
            node_id = node.get("id", "")
            if node_id.startswith("symbol:"):
                return node_id[len("symbol:"):].rsplit(":", 1)[0]
            return None

        actual_symbols = {(node_file(n), n.get("name"), n.get("kind")) for n in nodes}
        expected = {
            (item["file"], item["name"], item["kind"])
            for item in truth.get("expected_symbols", [])
        }
        found = expected & actual_symbols
        result["ground_truth"] = {
            "name": truth.get("name", ground_truth_path.stem),
            "expected_symbols": len(expected),
            "found_symbols": len(found),
            "symbol_recall": round(len(found) / max(1, len(expected)), 4),
            "missing_symbols": [
                {"file": f, "name": n, "kind": k} for f, n, k in sorted(expected - found)
            ],
        }
    return result


def benchmark_markdown(result: dict[str, Any]) -> str:
    quality = result["quality"]
    truth = result.get("ground_truth", {})
    lines = [
        f"# Benchmark: {result['project']}", "",
        f"- Tiempo: **{result['elapsed_seconds']} s**",
        f"- Segunda pasada con caché: **{result['warm_cache_seconds']} s** ({result['warm_cache_speedup']}×)",
        f"- Nodos/aristas: **{result['nodes']} / {result['links']}**",
        f"- Validez estructural: **{quality['structural_validity'] * 100:.2f}%**",
        f"- Aristas colgantes/duplicadas: **{quality['dangling_edges']} / {quality['duplicate_edges']}**",
        f"- Llamadas ambiguas: **{quality['ambiguous_calls']}/{quality['call_edges']} ({quality['ambiguous_call_rate'] * 100:.2f}%)**",
    ]
    if truth:
        lines.append(f"- Recall de símbolos etiquetados: **{truth['symbol_recall'] * 100:.2f}%** ({truth['found_symbols']}/{truth['expected_symbols']})")
    lines.extend(["", "## Cobertura por tipo", "", "| Tipo | Cantidad |", "|---|---:|"])
    lines.extend(f"| {kind} | {count} |" for kind, count in sorted(result["node_kinds"].items()))
    return "\n".join(lines) + "\n"
