import json
from pathlib import Path

import pytest

from graphtyn.core import semantic_index
from graphtyn.core.answer_validation import detect_incomplete_answer, validate_context_package
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.benchmark_protocol import paired_statistics, validate_protocol
from graphtyn.core.change_analyst import _terms, classify_intent, query_intent
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


def test_semantic_search_reuses_index_for_same_in_memory_graph(monkeypatch):
    data = graph()
    original = semantic_index.build_semantic_index
    calls = 0

    def counted(graph_data, output=None):
        nonlocal calls
        calls += 1
        return original(graph_data, output)

    semantic_index._INDEX_CACHE.clear()
    semantic_index._TERM_CACHE.clear()
    monkeypatch.setattr(semantic_index, "build_semantic_index", counted)

    assert semantic_index.semantic_search(data, "signed cookie")
    assert semantic_index.semantic_search(data, "HTTP router")
    assert calls == 1


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


def test_ollama_embedding_batches_use_local_embed_endpoint(monkeypatch):
    monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "local-test")
    calls = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"embeddings":[[3,4],[0,2]]}'

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr(semantic_index.urllib.request, "urlopen", urlopen)

    vectors = semantic_index.ollama_embeddings(["first", "second"])

    assert calls == [("http://127.0.0.1:11434/api/embed", 60)]
    assert vectors[0] == pytest.approx([0.6, 0.8])
    assert vectors[1] == pytest.approx([0.0, 1.0])


def test_ollama_index_does_not_compare_hash_vector_when_query_embedding_fails(monkeypatch):
    data = graph()
    index = {
        "provider": "ollama:nomic-embed-text:cosine-v1",
        "dimensions": 2,
        "rows": [{"id": "s:session", "vector": [1.0, 0.0]}],
    }
    monkeypatch.setattr(semantic_index, "ollama_embedding", lambda _text: None)

    assert semantic_search(data, "signed cookie", index=index) == []


def test_adaptive_planner_uses_semantic_fallback_and_validates_context():
    result = query_intent(graph(), "audita la seguridad de cookies firmadas", intent="flow", max_nodes=9)
    assert result["planner"] == "adaptive-intent-v2"
    assert result["nodes"]
    assert result["validation"]["ok"] is True
    assert result["stopping"]["sufficient_evidence"] is True


def test_intent_classifier_does_not_read_comprueba_as_prueba():
    request = "Explica el almacén y cómo comprueba que las variables correspondan a la campaña"

    assert classify_intent(request) == "flow"


def test_enumerated_operational_question_overrides_requested_overview():
    request = (
        "En el proyecto responde q1) cuáles archivos necesita; "
        "q2) cómo los localiza Docker; q3) qué ocurre si falta uno"
    )

    assert classify_intent(request, "overview") == "flow"


def test_query_terms_strip_sentence_punctuation_from_identifiers():
    assert "feature_store_path" in _terms("Usa FEATURE_STORE_PATH. Después valida.")


def test_filename_suffix_does_not_anchor_same_named_method():
    data = {
        "nodes": [
            {"id": "json", "name": "json", "kind": "method", "container": "Response",
             "file": "tests/http_fixture.py", "line": 8},
            {"id": "loader", "name": "load_manifest", "kind": "function",
             "file": "backend/loader.py", "line": 20,
             "operations": [{"kind": "call", "name": "read_text", "line": 21,
                             "text": "manifest.json read_text()"}]},
        ],
        "links": [],
    }

    result = query_intent(data, "Carga manifest.json con load_manifest", "flow", 4)

    assert result["matched"][0]["id"] == "loader"


def test_generic_data_noun_does_not_anchor_unrelated_test_fixture():
    data = {
        "nodes": [
            {"id": "fixture", "name": "datos", "kind": "function",
             "file": "tests/test_variables.py", "line": 3, "degree": 80},
            {"id": "loader", "name": "obtener_almacen_variables", "kind": "function",
             "file": "backend/api/model_loader.py", "line": 118, "degree": 4},
        ],
        "links": [],
    }

    result = query_intent(data, "Explica los datos del almacén de variables", intent="flow", max_nodes=4)

    assert result["matched"][0]["id"] == "loader"


def test_multi_part_question_stays_open_when_named_concern_is_missing():
    result = query_intent(
        graph(),
        "Responde q1) firma, q2) errores, q3) borrado y q4) pruebas de SessionMiddleware",
        intent="flow",
        max_nodes=8,
    )

    assert result["missing"]
    assert result["complete_for"] == []
    assert result["stopping"]["sufficient_evidence"] is False
    assert result["do_not_expand"] is False


def test_multi_part_operational_question_can_stop_when_each_concern_is_covered():
    data = {
        "nodes": [
            {"id": "compose", "name": "services", "kind": "documentation_section",
             "file": "docker-compose.yml", "details": "FEATURE_STORE_PATH=/app/variables.parquet"},
            {"id": "load", "name": "load_store", "kind": "function", "file": "backend/loader.py",
             "operations": [{"kind": "control", "name": "is_file", "text": "if not manifest.is_file(): raise ModelArtifactError(ERR_NO_DISPONIBLES)"},
                            {"kind": "call", "name": "sha256", "text": "sha256 schema crs ID_POLIGONO"},
                            {"kind": "call", "name": "vectorizar", "text": "parcela campana geometria superficie"}]},
            {"id": "generate_table", "name": "main", "kind": "function",
             "file": "backend/procesamiento/variables/__main__.py",
             "operations": [{"kind": "call", "name": "guardar_tabla", "text": "write parquet"}]},
            {"id": "generate_manifest", "name": "main", "kind": "function",
             "file": "scripts/preparar_almacen_inferencia.py",
             "operations": [{"kind": "call", "name": "write_text", "text": "write runtime manifest"}]},
        ],
        "links": [],
    }
    request = (
        "q1) cuáles son los dos archivos tabla y manifiesto; q2) cómo los localiza Docker; "
        "q3) qué ocurre si falta uno; q4) qué integridad y esquema comprueba; "
        "q5) cómo valida parcela, campaña, geometría y superficie; "
        "q6) qué scripts generan la tabla y el manifiesto"
    )

    result = query_intent(data, request, intent="overview", max_nodes=6)

    assert result["intent"] == "flow"
    assert set(result["requested_obligations"]) == {
        "artifacts", "docker_configuration", "missing_artifact_behavior",
        "integrity_schema", "record_identity", "table_generation",
        "runtime_manifest_generation",
    }
    assert result["missing"] == []
    assert result["do_not_expand"] is True
    assert len(result["nodes"]) <= 7
    assert result["obligation_evidence"]["table_generation"] == ["generate_table"]
    assert result["obligation_evidence"]["runtime_manifest_generation"] == ["generate_manifest"]


def test_project_name_does_not_anchor_overview_nodes_for_flow_request():
    data = {
        "nodes": [
            {"id": "project", "name": "SampleApp", "kind": "module", "file": "README.md"},
            {"id": "loader", "name": "load_manifest", "kind": "function",
             "file": "backend/loader.py", "line": 10,
             "operations": [{"kind": "call", "name": "verify", "line": 12, "text": "verify(manifest)"}]},
        ],
        "links": [],
    }

    result = query_intent(data, "En SampleApp explica el manifiesto y su integridad", "flow", 4)

    assert result["matched"][0]["id"] == "loader"


def test_weak_unrelated_matches_keep_expansion_open():
    data = {
        "nodes": [
            {"id": "unrelated", "name": "obtener_imagen", "kind": "function",
             "file": "scripts/satellite.py", "line": 8,
             "operations": [{"kind": "call", "name": "download", "text": "download_image()"}]},
            {"id": "docs", "name": "Feature store notes", "kind": "documentation_section",
             "file": "BACKLOG.md", "line": 20, "details": "future manifest support"},
        ],
        "links": [],
    }

    result = query_intent(
        data, "Implementa FEATURE_STORE_MANIFEST_PATH en el cargador y sus consumidores",
        intent="flow", max_nodes=4,
    )

    assert "relevant_anchor" in result["missing"]
    assert result["anchor_fallback"]["strategy"] == "one_exact_search_then_extend"
    assert "feature_store_manifest_path" in result["anchor_fallback"]["exact_queries"]
    assert result["anchor_fallback"]["broad_search_allowed"] is False
    assert result["stopping"]["sufficient_evidence"] is False
    assert result["do_not_expand"] is False


def test_multi_obligation_task_reserves_runtime_config_test_and_verifier():
    data = {
        "nodes": [
            {"id": "loader", "name": "load_store", "kind": "function",
             "file": "backend/loader.py", "line": 10,
             "operations": [{"kind": "call", "name": "getenv", "line": 11,
                             "text": "getenv('FEATURE_STORE_PATH')"}]},
            {"id": "compose", "name": "Services", "kind": "documentation_section",
             "file": "docker-compose.yml", "line": 1,
             "details": "FEATURE_STORE_PATH: /app/store.parquet"},
            {"id": "test", "name": "test_store_manifest", "kind": "function",
             "file": "tests/test_store.py", "line": 5,
             "operations": [{"kind": "call", "name": "setenv", "line": 6,
                             "text": "setenv('FEATURE_STORE_PATH', path)"}]},
            {"id": "verify", "name": "verificar_respaldo", "kind": "function",
             "file": "scripts/verificar_respaldo.py", "line": 4,
             "operations": [{"kind": "call", "name": "getenv", "line": 5,
                             "text": "getenv('FEATURE_STORE_PATH')"}]},
            {"id": "install", "name": "main", "kind": "function",
             "file": "scripts/comprobar_instalacion.py", "line": 4,
             "operations": [{"kind": "call", "name": "is_file", "line": 5,
                             "text": "manifest.is_file()"}]},
            {"id": "noise", "name": "test_unrelated_manifest", "kind": "function",
             "file": "tests/test_unrelated.py", "line": 2,
             "details": "generic manifest rendering"},
        ],
        "links": [],
    }

    result = query_intent(
        data,
        "Añade FEATURE_STORE_MANIFEST_PATH junto a FEATURE_STORE_PATH en Docker y verificadores de instalación/respaldo; agrega tests",
        "flow", 8,
    )

    context = result["implementation_context"]
    assert {"docker-compose.yml", "scripts/comprobar_instalacion.py"} <= set(context["read_first"])
    assert context["test_files"] == ["tests/test_store.py"]
    assert "tests/test_unrelated.py" not in {item["path"] for item in context["affected_files"]}
    assert context["exploration_budget"]["dependency_install_allowed"] is False
    assert context["exploration_budget"]["max_expansions"] == 1
    assert result["missing"] == []
    assert result["do_not_expand"] is True


def test_query_intent_does_not_claim_complete_tests_without_test_evidence():
    result = query_intent(graph(), "Dime qué pruebas cubren SessionMiddleware", intent="tests", max_nodes=6)

    assert result["missing"] == ["tests"]
    assert result["complete_for"] == []
    assert result["do_not_expand"] is False
    assert result["stopping"]["sufficient_evidence"] is False


def test_change_request_includes_compact_implementation_context():
    data = {
        "nodes": [
            {"id": "loader", "name": "load_manifest", "kind": "function",
             "file": "src/loader.py", "line": 10,
             "operations": [
                 {"kind": "call", "name": "write_text", "line": 14,
                  "text": "manifest.write_text(payload)"},
             ]},
            {"id": "caller", "name": "start_worker", "kind": "function",
             "file": "src/worker.py", "line": 20},
            {"id": "test", "name": "test_load_manifest", "kind": "function",
             "file": "tests/test_loader.py", "line": 5,
             "signature": "def test_load_manifest():"},
        ],
        "links": [
            {"source": "caller", "target": "loader", "label": "llama",
             "confidence": "EXTRACTED", "line": 22},
        ],
    }

    result = query_intent(
        data, "Implementa cambios en load_manifest y actualiza sus pruebas", "auto", 8,
    )

    context = result["implementation_context"]
    assert result["intent"] == "flow"
    assert context["read_first"][0] == "src/loader.py"
    assert context["direct_consumers"][0]["file"] == "src/worker.py"
    assert context["side_effects"][0]["operation"] == "write_text"
    assert context["test_files"] == ["tests/test_loader.py"]
    assert context["suggested_test_commands"] == [
        "python -m pytest tests/test_loader.py",
    ]
    assert context["command_status"] == "suggested_from_test_files; execution_not_verified"
    assert context["execution_policy"]["max_expansions"] == 1
    assert context["execution_policy"]["dependency_install"] == "outside_edit_session"
    assert "open only read_first" in result["guidance"]
    assert "expand at most once" in result["guidance"]


def test_change_request_prefers_indexed_project_test_command():
    data = {
        "nodes": [
            {"id": "loader", "name": "load_manifest", "kind": "function",
             "file": "src/loader.py", "line": 10},
            {"id": "test", "name": "test_load_manifest", "kind": "function",
             "file": "tests/test_loader.py", "line": 5},
            {"id": "runner", "name": "Documento", "kind": "documentation_section",
             "file": ".github/workflows/tests.yml", "line_start": 20,
             "details": ".github/workflows/tests.yml:20-22\nrun: docker compose run --rm api python -m pytest tests -q"},
            {"id": "make", "name": "Documento", "kind": "documentation_section",
             "file": "Makefile", "line_start": 1,
             "details": "Makefile:1-2\ntest:\n\tpython -m pytest -q"},
        ],
        "links": [],
    }

    result = query_intent(
        data, "Implementa cambios en load_manifest y actualiza sus pruebas", "auto", 8,
    )
    context = result["implementation_context"]

    assert context["command_status"] == "extracted_from_project_source; execution_not_verified"
    assert context["suggested_test_commands"][0] == (
        "docker compose run --rm api python -m pytest tests -q"
    )
    assert context["test_command_evidence"][0] == {
        "command": "docker compose run --rm api python -m pytest tests -q",
        "source": ".github/workflows/tests.yml:20",
        "confidence": "EXTRACTED",
    }


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


def test_source_evidence_keeps_stopping_consistent_with_missing_obligations(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    package = {
        "intent": "tests", "matched": [{"id": "s:run", "name": "run", "kind": "function",
                                             "file": "service.py", "line": 1, "end_line": 2}],
        "nodes": [], "complete_for": [], "missing": ["tests"],
        "do_not_expand": False,
        "stopping": {"sufficient_evidence": True},
    }
    result = attach_source_evidence(tmp_path, package, "Describe run", "compact")
    assert result["do_not_expand"] is False
    assert result["stopping"]["sufficient_evidence"] is False


def test_source_excerpt_cannot_override_insufficient_stopping_signal(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    package = {
        "intent": "flow", "matched": [{"id": "s:run", "name": "run", "kind": "function",
                                           "file": "service.py", "line": 1, "end_line": 2}],
        "nodes": [], "complete_for": [], "missing": [], "do_not_expand": False,
        "validation": {"ok": True}, "stopping": {"sufficient_evidence": False},
    }

    result = attach_source_evidence(tmp_path, package, "Explica el orden exacto de run", "precision")

    assert result["source_evidence"]
    assert result["do_not_expand"] is False
    assert result["stopping"]["sufficient_evidence"] is False


def test_source_evidence_preserves_edit_execution_guidance(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return True\n", encoding="utf-8")
    package = {
        "intent": "flow", "matched": [{"id": "run", "name": "run", "kind": "function",
                                           "file": "service.py", "line": 1, "end_line": 2}],
        "nodes": [], "missing": [], "complete_for": ["flow"], "do_not_expand": True,
        "validation": {"ok": True}, "stopping": {"sufficient_evidence": True},
        "guidance": "Open only implementation_context.read_first and do not install dependencies.",
    }

    result = attach_source_evidence(tmp_path, package, "Explica el orden exacto de run", "precision")

    assert result["source_evidence"]
    assert result["guidance"].startswith("Open only implementation_context.read_first")
    assert "exact source excerpts" in result["guidance"]


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


def test_overview_projection_is_compact_bounded_and_does_not_duplicate_matches():
    nodes = [{"id": "file:README.md", "name": "README.md", "kind": "doc",
              "file": "README.md", "degree": 30, "details": "x" * 5000}]
    for index in range(40):
        nodes.append({"id": f"s:{index}", "name": f"Service{index}", "kind": "class",
                      "file": f"src/domain_{index}/service.py", "line": index + 1,
                      "degree": 40 - index, "details": "detail " * 1000,
                      "operations": [{"name": f"operation-{item}", "text": "body " * 200}
                                     for item in range(20)]})
    result = query_intent({"nodes": nodes, "links": []}, "arquitectura del proyecto", "overview", 12)
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    assert result["projection_version"] == "overview-compact-v2"
    assert "matched" not in result and result["matched_ids"]
    assert len(encoded) <= result["payload_budget_tokens"] * 4
    assert all(len(node.get("details", "")) <= 240 for node in result["nodes"])
    assert set(result["detail_refs"]) == {node["id"] for node in result["nodes"]}
