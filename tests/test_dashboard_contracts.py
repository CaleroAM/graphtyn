import json
from pathlib import Path

from aether_graph.api import main as api_main

WEB = Path(__file__).resolve().parents[1] / "aether_graph" / "web"


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
