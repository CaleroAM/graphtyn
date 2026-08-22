"""Deterministic, auditable health metrics for an Graphtyn index."""

from __future__ import annotations

from collections import Counter


def index_quality(graph: dict) -> dict:
    """Summarize observable index quality without claiming ground-truth accuracy."""
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    metadata = graph.get("metadata") or {}
    confidence = Counter(str(link.get("confidence") or "UNKNOWN").upper() for link in links)
    parsers = Counter(str(node.get("parser") or "unknown") for node in nodes)
    structural_nodes = [n for n in nodes if n.get("kind") in {"class", "function", "method", "interface", "struct"}]
    evidenced = sum(bool(n.get("file") and n.get("line")) for n in structural_nodes)
    ambiguous = confidence["AMBIGUOUS"]
    ambiguous_by_label = Counter(str(link.get("label") or "unknown") for link in links if str(link.get("confidence") or "").upper() == "AMBIGUOUS")
    unresolved = confidence["UNRESOLVED"]
    inferred = confidence["INFERRED"]
    framework_labels = {"despacha", "invoca ruta", "valida con", "crea", "despacha evento"}
    route_nodes = [node for node in nodes if node.get("kind") == "route"]
    route_ids = {node.get("id") for node in route_nodes}
    framework_links = [link for link in links if link.get("label") in framework_labels]
    resolved_route_ids = {link.get("source") for link in framework_links if link.get("label") == "despacha" and link.get("source") in route_ids}
    frontend_route_ids = {link.get("target") for link in framework_links if link.get("label") == "invoca ruta" and link.get("target") in route_ids}
    total_links = len(links)
    observable_rate = (ambiguous + unresolved) / max(1, total_links)
    health_score = round(max(0.0, 1.0 - observable_rate) * 100, 2) if nodes else 0.0
    warnings = []
    if not nodes:
        warnings.append("El índice no contiene nodos.")
    if ambiguous:
        ambiguous_calls = ambiguous_by_label.get("llama", 0)
        if ambiguous_calls:
            warnings.append(f"Hay {ambiguous_calls} llamadas ambiguas y {ambiguous - ambiguous_calls} referencias ambiguas.")
        else:
            warnings.append(f"No hay llamadas de código ambiguas; quedan {ambiguous} referencias textuales ambiguas.")
    if unresolved:
        warnings.append(f"Hay {unresolved} relaciones no resueltas.")
    if metadata.get("structural_parser") == "builtin-fallback":
        warnings.append("Tree-sitter no se utilizó; el índice usa el parser de respaldo.")
    return {
        "health_score": health_score,
        "score_basis": "1 - (relaciones ambiguas + no resueltas) / relaciones totales",
        "nodes": len(nodes),
        "links": total_links,
        "isolated_nodes": sum(int(n.get("degree") or 0) == 0 for n in nodes),
        "structural_nodes": len(structural_nodes),
        "structural_nodes_with_location": evidenced,
        "location_coverage": round(evidenced / max(1, len(structural_nodes)), 4),
        "confidence": dict(sorted(confidence.items())),
        "ambiguous_rate": round(ambiguous / max(1, total_links), 4),
        "ambiguous_by_label": dict(sorted(ambiguous_by_label.items())),
        "ambiguous_calls": ambiguous_by_label.get("llama", 0),
        "inferred_rate": round(inferred / max(1, total_links), 4),
        "parser": metadata.get("structural_parser", "unknown"),
        "tree_sitter_files": int(metadata.get("tree_sitter_files") or 0),
        "parsers_by_node": dict(sorted(parsers.items())),
        "reindex_mode": metadata.get("reindex_mode"),
        "enriched_files": int(metadata.get("enriched_files") or 0),
        "framework": {
            "routes": len(route_nodes),
            "resolved_routes": len(resolved_route_ids),
            "unresolved_routes": len(route_ids - resolved_route_ids),
            "frontend_route_calls": sum(link.get("label") == "invoca ruta" for link in framework_links),
            "routes_with_frontend_callers": len(frontend_route_ids),
            "relations": len(framework_links),
            "ambiguous_relations": sum(str(link.get("confidence") or "").upper() == "AMBIGUOUS" for link in framework_links),
        },
        "warnings": warnings,
        "accuracy_note": "La precisión/recall requieren un ground truth; este panel reporta salud observable del índice.",
    }
