import json
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
