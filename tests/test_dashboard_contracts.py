import json
import re
from pathlib import Path

from graphtyn.api import main as api_main

WEB = Path(__file__).resolve().parents[1] / "graphtyn" / "web"


def _body(response):
    return json.loads(response.body)


def test_quality_endpoint_logic_without_http_lifespan(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("def helper():\n    return 1\n")
    data = _body(api_main.get_index_quality(str(project)))
    assert data["ok"] is True
    assert data["nodes"] > 0
    assert 0 <= data["health_score"] <= 100
    assert "ground truth" in data["accuracy_note"]


def test_report_endpoint_returns_auditable_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo\n\nDemo processes orders through a small local API for retail teams.\n")
    (project / "main.py").write_text("def main():\n    return 1\n")
    data = _body(api_main.get_graphtyn_report(str(project)))
    assert data["ok"] is True
    assert data["filename"] == "GRAPHTYN_REPORT.md"
    assert "Demo processes orders" in data["content"]
    assert "```mermaid" in data["content"]
    assert data["metrics"]["estimated_tokens"] > 0


def test_reindex_persists_report_next_to_index(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setattr(api_main, "INDEX_STORE", store)
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo\n\nDemo manages inventory for independent stores and warehouses.\n")
    (project / "main.py").write_text("def main():\n    return 1\n")
    data = _body(api_main.reindex_project({"path": str(project), "engine": "ast_pure", "full": True}))
    assert data["ok"] is True
    report = Path(data["report"])
    assert report.name == "GRAPHTYN_REPORT.md" and report.is_file()
    assert report.parent == api_main._index_dir(project)
    assert "manages inventory" in report.read_text(encoding="utf-8")


def test_context_endpoint_logic_and_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("def helper():\n    return 1\n")
    data = _body(api_main.create_context_bundle({"path": str(project), "symbols": ["helper", "helper"], "depth": 99, "limit": 999}))
    assert data["ok"] is True
    assert data["symbols"] == ["helper"]
    assert data["contexts"][0]["symbol"] == "helper"
    assert data["reduction_rate"] <= 1
    assert data["unmatched_symbols"] == []


def test_context_uses_safe_nested_root_from_index_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    source = inner / "a.py"
    source.write_text("def helper():\n    return 1\n")
    graph = api_main.parser.scan_directory(inner)
    graph.setdefault("metadata", {})["path"] = str(inner)
    index_dir = api_main._index_dir(outer)
    (index_dir / "index.json").write_text(json.dumps(graph))
    data = _body(api_main.create_context_bundle({"path": str(outer), "symbols": ["helper", "missing"]}))
    assert data["raw_context_tokens"] > 0
    assert data["unmatched_symbols"] == ["missing"]


def test_context_endpoint_rejects_bad_inputs(tmp_path):
    response = api_main.create_context_bundle({"path": str(tmp_path), "symbols": ["x"], "depth": "bad"})
    assert response.status_code == 400
    assert "enteros" in _body(response)["error"]


def test_raw_context_size_cannot_escape_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    assert api_main._safe_project_file_size(project, "../secret.txt") == 0
    assert api_main._safe_project_file_size(project, "missing.txt") == 0


def test_dashboard_quality_controls_are_wired_end_to_end():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    graph = (WEB / "js" / "graph.js").read_text()
    handlers = (WEB / "js" / "__handlers.js").read_text()
    quality = (WEB / "js" / "quality.js").read_text()
    assert 'id="modal-quality"' in html and 'id="quality-summary"' in html
    assert 'id="context-selection"' in html and 'id="context-output"' in html
    assert "openQualityPanel" in dashboard and "generateContextBundle" in dashboard
    assert "addNodeToContext" in graph and "from './quality.js'" in handlers
    assert "/api/index-quality" in quality and "/api/context-bundle" in quality
    assert "accuracy_note" in quality and "token_estimation" in quality
    assert 'id="context-scope"' in html and "scope" in quality
    assert 'id="index-update"' in html and 'id="ambiguity-queue"' in html
    assert 'id="answer-validation-input"' in html
    for endpoint in ("/api/index-update", "/api/ambiguities", "/api/validate-answer", "/api/change-report"):
        assert endpoint in quality
    for handler in ("loadIndexUpdate", "loadAmbiguities", "reviewAmbiguity", "validateAgentAnswer", "generateChangeReport"):
        assert handler in dashboard and handler in handlers


def test_dashboard_shared_memory_is_separate_and_wired_end_to_end():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    handlers = (WEB / "js" / "__handlers.js").read_text()
    memory = (WEB / "js" / "memory.js").read_text()
    css = (WEB / "dashboard.css").read_text()
    assert 'id="modal-memory"' in html and 'id="memory-results"' in html
    assert 'id="memory-sessions"' in html and 'id="memory-token"' in html
    assert "openMemoryPanel" in dashboard and "searchSharedMemory" in handlers
    for endpoint in ("/api/memory/status", "/api/memory/sessions", "/api/memory/search",
                     "/api/memory/correct", "/api/memory/forget", "/api/memory/graph"):
        assert endpoint in memory
    assert 'id="memory-graph-btn"' in html and 'id="memory-agent-legend"' in html
    assert "showSharedMemoryGraph" in handlers and "agent_color" in (WEB / "js" / "painters.js").read_text()
    assert 'id="btn-memory-view"' in html and "Memoria del proyecto" in html
    assert "state.activeView === 'memory'" in (WEB / "js" / "graph.js").read_text()
    assert "/api/memory/graph?path=" in (WEB / "js" / "graph.js").read_text()
    assert "textContent" in memory and "esc(" in memory
    assert ".memory-layout" in css and "grid-template-columns" in css
    assert 'id="memory-import-provider"' in html and 'id="memory-import-apply"' in html
    assert "/api/v1/imports/discover" in memory and "/api/v1/imports" in memory
    assert "discoverHistoricalMemory" in dashboard and "applyHistoricalMemory" in handlers
    assert "saveHistoricalSource" in memory and "testHistoricalSource" in handlers
    assert "removeHistoricalSource" in memory and "saveMemoryAlias" in handlers
    assert 'id="memory-alias"' in html and 'id="memory-canonical"' in html
    assert ".memory-import-panel" in css


def test_dashboard_exposes_framework_flow_filters_and_route_metadata():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    graph = (WEB / "js" / "graph.js").read_text()
    painters = (WEB / "js" / "painters.js").read_text()
    quality = (WEB / "js" / "quality.js").read_text()
    assert 'id="f-route"' in html
    assert html.count('class="f-relation"') == 5
    assert "AMBIGUOUS" in html and "AMBIGUOUS" in graph
    assert "focusWebFlow" in dashboard and "clearWebFlow" in dashboard
    assert "http_method" in graph and "node.path" in graph
    assert "k === 'route'" in painters
    assert "framework.resolved_routes" in quality


def test_dashboard_separates_graph_design_from_index_engine_and_wraps_status():
    html = (WEB / "dashboard.html").read_text()
    css = (WEB / "dashboard.css").read_text()
    ui = (WEB / "js" / "ui.js").read_text()
    assert 'id="dd-appearance"' in html and "Diseño del grafo" in html
    assert 'id="dd-engine"' in html and "Motor de índice" in html
    assert "Paleta & Motor" not in html and 'id="dd-settings"' not in html
    for element_id in ("palette-sel", "style-sel", "shape-sel", "link-style-sel",
                       "engine-sel", "code-model-sel", "vision-model-sel",
                       "f-repulsion", "f-distance"):
        assert html.count(f'id="{element_id}"') == 1
    assert 'class="graph-status"' in html
    assert html.count('class="confidence-item') == 3
    assert "flex-wrap:wrap" in css and "max-height:min(650px" in css
    assert "aria-expanded" in ui


def test_dashboard_groups_navigation_and_secondary_actions_into_menus():
    html = (WEB / "dashboard.html").read_text()
    css = (WEB / "dashboard.css").read_text()
    controls = (WEB / "js" / "controls.js").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    for menu_id in ("dd-explore", "dd-viewport", "dd-actions"):
        assert f'id="{menu_id}"' in html
    assert 'id="active-view-label"' in html
    assert 'class="dd-panel nav-menu"' in html
    assert 'class="dd-panel action-menu"' in html
    assert html.count('id="reindex-btn"') == 1
    assert "Calidad y contexto" in html and "Administrar memoria" in html
    assert "Exportar datos JSON" in html and "Exportar imagen PNG" in html
    assert ".menu-item" in css and ".dimension-switch" in css
    assert "activeLabel.textContent" in controls
    assert "closeDropdownMenus" in dashboard


def test_dashboard_control_ids_are_unique_and_dropdowns_are_accessible():
    html = (WEB / "dashboard.html").read_text()
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "duplicate element ids make controls unreliable"
    for menu_id in ("dd-explore", "dd-viewport", "dd-filter", "dd-appearance", "dd-engine", "dd-actions"):
        block = html[html.index(f'id="{menu_id}"'):]
        opening_button = block[:block.index("</button>")]
        assert 'aria-haspopup="true"' in opening_button
        assert 'aria-expanded="false"' in opening_button
