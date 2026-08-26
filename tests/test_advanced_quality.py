import json
from pathlib import Path

import pytest

from graphtyn.core import semantic_index
from graphtyn.core.answer_validation import detect_incomplete_answer, validate_context_package
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.benchmark_protocol import paired_statistics, validate_protocol
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.graph_hygiene import normalize_graph
from graphtyn.core.semantic_index import build_semantic_index, hashed_embedding, semantic_search
from graphtyn.core.source_evidence import attach_source_evidence, select_evidence_mode


def graph():
    return {
        "nodes": [
            {"id": "s:session", "name": "SessionMiddleware", "kind": "class", "file": "src/session.py", "line": 4,
             "details": "verifies signed cookies and handles invalid signatures", "operations": [{"name": "unsign"}]},
            {"id": "s:router", "name": "Router", "kind": "class", "file": "src/router.py", "line": 8,
             "details": "dispatches HTTP routes"},
        ],
        "links": [{"source": "s:router", "target": "s:session", "label": "llama", "confidence": "EXTRACTED",
                   "file": "src/router.py", "line": 12}],
    }


def test_graph_hygiene_deduplicates_and_calibrates():
    data = graph()
    data["links"].append(dict(data["links"][0], confidence="INFERRED"))
    result = normalize_graph(data)
    assert len(result["links"]) == 1
    assert result["links"][0]["confidence"] == "EXTRACTED"
    assert result["links"][0]["confidence_score"] > 0.8
    assert result["metadata"]["graph_hygiene"]["duplicates_removed"] == 1


def test_local_semantic_index_is_incremental_and_searchable(tmp_path):
    output = tmp_path / "semantic.json"
    first = build_semantic_index(graph(), output)
    second = build_semantic_index(graph(), output)
    assert first["provider"] == "feature-hash-v2"
    assert second["incremental"]["reused"] == 2
    assert semantic_search(graph(), "signed cookie verification", index=second)[0]["node"]["id"] == "s:session"
    assert hashed_embedding("same") == hashed_embedding("same")


def test_ollama_embeddings_are_normalized_for_cosine_similarity(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b'{"embedding":[3.0,4.0]}'

    monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(semantic_index.urllib.request, "urlopen", lambda request, timeout: Response())

    vector = semantic_index.ollama_embedding("semantic query")

    assert vector == pytest.approx([0.6, 0.8])
    assert sum(value * value for value in vector) == pytest.approx(1.0)


def test_adaptive_planner_uses_semantic_fallback_and_validates_context():
    result = query_intent(graph(), "audita la seguridad de cookies firmadas", intent="flow", max_nodes=9)
    assert result["planner"] == "adaptive-intent-v2"
    assert result["nodes"]
    assert result["validation"]["ok"] is True
    assert result["stopping"]["sufficient_evidence"] is True


def test_qualified_symbol_request_anchors_method_and_owner():
    data = {
        "nodes": [
            {"id": "s:mux", "name": "Mux", "kind": "struct", "file": "mux.go", "line": 1},
            {"id": "s:serve", "name": "ServeHTTP", "container": "Mux", "kind": "method",
             "file": "mux.go", "line": 10, "end_line": 20,
             "operations": [{"kind": "call", "name": "Get", "line": 12, "text": "pool.Get()"}]},
            {"id": "s:route", "name": "Route", "kind": "method", "file": "mux.go", "line": 30,
             "operations": [{"kind": "call", "name": "Get", "line": 31, "text": "tree.Get()"}]},
        ],
        "links": [],
    }
    result = query_intent(data, "Explica el orden exacto de Mux.ServeHTTP", intent="flow", max_nodes=8)
    assert result["matched"][0]["id"] == "s:serve"


def test_qualified_method_prefers_go_receiver_over_homonym():
    data = {
        "nodes": [
            {"id": "s:wrong", "name": "Handler", "kind": "method", "file": "middleware/headers.go",
             "line": 7, "signature": "func (h HeaderRouter) Handler() http.Handler"},
            {"id": "s:right", "name": "Handler", "kind": "method", "file": "chain.go", "line": 12,
             "signature": "func (mws Middlewares) Handler(h http.Handler) http.Handler"},
        ],
        "links": [],
    }
    result = query_intent(data, "Explica Middlewares.Handler", intent="flow", max_nodes=4)
    assert result["matched"][0]["id"] == "s:right"
    assert {node["id"] for node in result["nodes"]} == {"s:right"}


def test_adaptive_source_evidence_reads_only_selected_symbol_body(tmp_path):
    source = tmp_path / "mux.go"
    source.write_text(
        "package sample\n\nfunc ServeHTTP() {\n"
        "    ctx := pool.Get()\n    defer pool.Put(ctx)\n}\n\n"
        "func UnrelatedSecret() { panic(\"must-not-leak\") }\n",
        encoding="utf-8",
    )
    package = {
        "intent": "flow", "matched": [{"id": "s:serve", "name": "ServeHTTP", "kind": "function",
                                          "file": "mux.go", "line": 3, "end_line": 6}],
        "nodes": [], "complete_for": ["flow"], "missing": [], "do_not_expand": False,
    }
    result = attach_source_evidence(tmp_path, package, "Explica el orden exacto y ciclo de vida", "auto")
    assert select_evidence_mode("Explica el orden exacto", "auto") == "precision"
    assert result["evidence_mode"] == "precision"
    assert result["source_retrieval"]["snippets"] == 1
    assert "pool.Get" in result["source_evidence"][0]["text"]
    assert "UnrelatedSecret" not in result["source_evidence"][0]["text"]
    assert result["do_not_expand"] is True


def test_compact_source_mode_never_reads_files(tmp_path):
    (tmp_path / "service.py").write_text("raise RuntimeError('secret')\n", encoding="utf-8")
    package = {"intent": "flow", "matched": [{"id": "s", "name": "run", "kind": "function",
                                                  "file": "service.py", "line": 1}], "nodes": []}
    result = attach_source_evidence(tmp_path, package, "Describe run", "compact")
    assert result["source_retrieval"]["enabled"] is False
    assert "source_evidence" not in result


def test_impact_planner_uses_directional_consumers_not_lexical_noise():
    data = graph()
    data["nodes"].append({"id": "s:noise", "name": "CallerHelper", "kind": "method",
                          "file": "tests/noise.py", "line": 3, "details": "consumer caller impact"})
    result = query_intent(data, "impacto de SessionMiddleware", intent="impact", max_nodes=8)
    assert result["planner"] == "adaptive-impact-v2"
    assert [node["id"] for node in result["nodes"]] == ["s:session", "s:router"]
    assert result["links"][0]["label"] == "llama"


def test_context_and_answer_completeness_checks():
    data = graph()
    package = {"nodes": data["nodes"], "links": data["links"]}
    assert validate_context_package(data, package)["ok"] is True
    assert detect_incomplete_answer("resultado:")["complete"] is False
    assert detect_incomplete_answer("La relación está respaldada por src/router.py:12 y termina correctamente.")["complete"] is True


def test_laravel_flow_projects_file_route_edge_to_relevant_frontend_symbol():
    route = "route:routes/web.php:returns.approve"
    frontend_file = "file:resources/js/pages/Returns/Index.tsx"
    data = {
        "nodes": [
            {"id": route, "name": "returns.approve", "kind": "route", "file": "routes/web.php"},
            {"id": "s:approve", "name": "approve", "container": "ReturnController", "kind": "method",
             "file": "app/Http/Controllers/ReturnController.php", "operations": [{"name": "update", "text": "status approved"}]},
            {"id": frontend_file, "name": "Index.tsx", "kind": "file",
             "details": "resources/js/pages/Returns/Index.tsx"},
            {"id": "s:wrong", "name": "Create", "kind": "function", "file": "resources/js/pages/Returns/Index.tsx",
             "line": 1, "end_line": 40, "operations": [{"name": f"call{i}", "text": "unrelated"} for i in range(20)]},
            {"id": "s:right", "name": "Index", "kind": "function", "file": "resources/js/pages/Returns/Index.tsx",
             "line": 50, "end_line": 120, "operations": [{"name": "route", "text": "route('returns.approve') status draft permission"}]},
        ],
        "links": [
            {"source": route, "target": "s:approve", "label": "despacha", "confidence": "EXTRACTED", "line": 10},
            {"source": frontend_file, "target": route, "label": "invoca ruta", "confidence": "EXTRACTED",
             "line": 80, "evidence": "route('returns.approve'"},
        ],
    }

    result = query_intent(data, "Traza React returns.approve hasta Laravel, permisos y estado", max_nodes=8)

    assert "s:right" in {node["id"] for node in result["nodes"]}
    assert any(link["label"] == "invoca ruta" and link["source"] == "s:right" for link in result["links"])


def test_type_sidecar_is_applied_and_parser_reports_incremental_cache(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("class Service:\n    def run(self):\n        return 1\n")
    cache = tmp_path / "cache.json"
    first = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache)
    ids = {node["name"]: node["id"] for node in first["nodes"] if node.get("name") in {"Service", "run"}}
    sidecar = tmp_path / ".graphtyn" / "type-evidence.json"
    sidecar.parent.mkdir()
    sidecar.write_text(json.dumps({"relations": [{"source": ids["Service"], "target": ids["run"],
                                                    "label": "declara", "provider": "pyright"}]}))
    second = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache)
    assert second["metadata"]["incremental"]["reused_files"] >= 1
    assert any(link["confidence"] == "TYPED" for link in second["links"])
    assert second["metadata"]["type_analysis"]["typed_relations"] == 1


def test_statistical_protocol_has_36_tasks_and_paired_statistics():
    root = Path(__file__).resolve().parent.parent
    protocol = json.loads((root / "benchmarks/statistical_protocol_36_tasks.json").read_text())
    validation = validate_protocol(protocol)
    assert validation["ok"] is True
    assert validation["tasks"] == 36
    assert validation["planned_runs"] == 108
    rows = [
        {"task_id": "a", "variant": "graphtyn", "tokens": 50, "quality": 1},
        {"task_id": "a", "variant": "no_graph", "tokens": 100, "quality": .8},
        {"task_id": "b", "variant": "graphtyn", "tokens": 60, "quality": .8},
        {"task_id": "b", "variant": "no_graph", "tokens": 120, "quality": .8},
    ]
    stats = paired_statistics(rows, bootstrap_samples=100)
    assert stats["pairs"] == 2
    assert stats["token_reduction"] == 0.5
