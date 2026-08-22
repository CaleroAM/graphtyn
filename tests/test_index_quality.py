from graphtyn.core.index_quality import index_quality


def test_index_quality_reports_observable_metrics_without_claiming_accuracy():
    graph = {
        "nodes": [
            {"id": "s:a", "kind": "method", "file": "a.cs", "line": 2, "degree": 2, "parser": "tree-sitter"},
            {"id": "s:b", "kind": "method", "degree": 0, "parser": "tree-sitter"},
        ],
        "links": [
            {"source": "s:a", "target": "s:b", "confidence": "EXTRACTED"},
            {"source": "s:b", "target": "s:a", "confidence": "AMBIGUOUS"},
        ],
        "metadata": {"structural_parser": "tree-sitter+fallback", "tree_sitter_files": 1},
    }
    result = index_quality(graph)
    assert result["health_score"] == 50
    assert result["confidence"] == {"AMBIGUOUS": 1, "EXTRACTED": 1}
    assert result["ambiguous_by_label"] == {"unknown": 1}
    assert "referencias" in result["warnings"][0]
    assert result["location_coverage"] == 0.5
    assert result["isolated_nodes"] == 1
    assert "ground truth" in result["accuracy_note"]


def test_index_quality_empty_and_fallback_are_explicit():
    result = index_quality({"nodes": [], "links": [], "metadata": {"structural_parser": "builtin-fallback"}})
    assert result["health_score"] == 0
    assert len(result["warnings"]) == 2


def test_index_quality_reports_framework_route_resolution():
    graph = {
        "nodes": [
            {"id": "route:web:orders.store", "kind": "route"},
            {"id": "symbol:OrdersController:store", "kind": "method"},
            {"id": "file:Create.tsx", "kind": "file"},
        ],
        "links": [
            {"source": "file:Create.tsx", "target": "route:web:orders.store", "label": "invoca ruta", "confidence": "EXTRACTED"},
            {"source": "route:web:orders.store", "target": "symbol:OrdersController:store", "label": "despacha", "confidence": "EXTRACTED"},
        ],
    }
    framework = index_quality(graph)["framework"]
    assert framework == {
        "routes": 1,
        "resolved_routes": 1,
        "unresolved_routes": 0,
        "frontend_route_calls": 1,
        "routes_with_frontend_callers": 1,
        "relations": 2,
        "ambiguous_relations": 0,
    }
