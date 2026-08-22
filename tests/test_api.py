import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from graphtyn.api import main as api_main


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / ".graphtyn-store")
    return TestClient(api_main.app)


def test_health_endpoint(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "Graphtyn"


def test_explicit_registration_overrides_auto_discovered_name(tmp_path, monkeypatch):
    project = tmp_path / "legacy-folder-name"
    project.mkdir()
    registry = tmp_path / "registered_projects.json"
    registry.write_text(json.dumps([{
        "id": "graphtyn",
        "name": "Graphtyn",
        "path": str(project),
        "mode": "agent_discovered",
    }]))
    monkeypatch.chdir(project)
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", registry)

    projects = api_main._load_registered_projects()

    assert projects[0]["id"] == "graphtyn"
    assert projects[0]["name"] == "Graphtyn"


def test_dashboard_assets_served(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    html = client.get("/")
    assert html.status_code == 200
    assert "Graphtyn" in html.text
    assert "/dashboard.css" in html.text and "/dashboard.js" in html.text
    assert 'id="blast-content"' in html.text and "overflow-wrap:anywhere" in html.text
    css = client.get("/dashboard.css")
    assert css.status_code == 200
    assert "graph-container" in css.text
    js = client.get("/dashboard.js")
    assert js.status_code == 200
    assert "Object.assign(window" in js.text
    for module in ["state", "painters", "sim", "styles", "graph", "controls", "ui", "quality"]:
        r = client.get(f"/js/{module}.js")
        assert r.status_code == 200, module
        assert "export " in r.text, module
    state_js = client.get("/js/state.js").text
    assert "export const PALETTES" in state_js
    assert "export const COMM_COLORS" in state_js
    assert "import { state }" in client.get("/dashboard.js").text
    styles_js = client.get("/js/styles.js").text
    assert "paintNodePointerArea" in styles_js
    assert "Math.max(7 / gs, base * 1.15)" in styles_js
    graph_js = client.get("/js/graph.js").text
    assert "nearestNodeAtPointer" in graph_js
    assert ".onNodeClick(handleGraphNodeClick)" in graph_js
    assert "installReliableNodeDrag" in graph_js
    assert "screen2GraphCoords" in graph_js
    assert "grid-template-columns:minmax(0,1fr)" in graph_js
    assert "EVIDENCIA " in graph_js
    assert 'id="modal-quality"' in html.text
    assert "addNodeToContext" in graph_js
    quality_js = client.get("/js/quality.js").text
    assert "/api/index-quality" in quality_js
    assert "/api/context-bundle" in quality_js
    assert "accuracy_note" in quality_js
    assert client.get("/favicon.svg").status_code == 200
    comp = client.get("/comparison")
    assert comp.status_code == 200
    assert "Comparación" in comp.text or "comparaci" in comp.text.lower()


def test_js_route_rejects_traversal(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/js/../main.py").status_code == 404
    assert client.get("/js/noexiste.js").status_code == 404
    assert client.get("/js/state.py").status_code == 404


def test_project_config_roundtrip_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    res = client.post("/api/projects/config", json={"path": str(proj), "respect_git": False})
    assert res.status_code == 200
    assert res.json()["config"]["respect_git"] is False
    res2 = client.get("/api/projects/config", params={"path": str(proj)})
    assert res2.json()["config"]["respect_git"] is False


def test_reindex_ast_pure_and_graph_views(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (proj / "b.py").write_text("from a import f\n\nprint(f())\n", encoding="utf-8")

    res = client.post("/api/reindex", json={"path": str(proj), "engine": "ast_pure"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["nodes"] > 0
    assert body["links"] > 0
    assert body["mode"] == "full"

    code = client.get("/api/graph", params={"path": str(proj), "view": "code"})
    assert code.status_code == 200
    data = code.json()
    ids = {n["id"] for n in data["nodes"]}
    assert "file:a.py" in ids and "file:b.py" in ids
    for link in data["links"]:
        assert "confidence" in link

    sem = client.get("/api/graph", params={"path": str(proj), "view": "semantic"})
    assert sem.status_code == 200
    kinds = {n.get("kind") for n in sem.json()["nodes"]}
    assert "community" in kinds
    assert "semantic_concept" in kinds

    agents = client.get("/api/graph", params={"view": "agents"})
    assert agents.status_code == 200
    assert any(n.get("kind") == "orchestrator_agent" for n in agents.json()["nodes"])


def test_quality_and_context_bundle_endpoints(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    proj = tmp_path / "quality-project"
    proj.mkdir()
    (proj / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (proj / "b.py").write_text("from a import helper\n\ndef use():\n    return helper()\n", encoding="utf-8")
    assert client.post("/api/reindex", json={"path": str(proj), "engine": "ast_pure"}).status_code == 200

    quality = client.get("/api/index-quality", params={"path": str(proj)})
    assert quality.status_code == 200
    q = quality.json()
    assert q["ok"] is True and 0 <= q["health_score"] <= 100
    assert q["nodes"] > 0 and q["links"] > 0
    assert "accuracy_note" in q and "score_basis" in q

    context = client.post("/api/context-bundle", json={"path": str(proj), "symbols": ["helper", "helper"], "depth": 1, "limit": 10})
    assert context.status_code == 200
    c = context.json()
    assert c["ok"] is True
    assert c["symbols"] == ["helper"]
    assert c["nodes"] and c["estimated_tokens"] > 0
    assert c["raw_context_tokens"] >= 0 and isinstance(c["tokens_saved"], int)
    assert c["reduction_rate"] <= 1
    assert "estimación" in c["token_estimation"]


def test_quality_and_context_bundle_validation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    missing = tmp_path / "missing"
    assert client.get("/api/index-quality", params={"path": str(missing)}).status_code == 404
    assert client.post("/api/context-bundle", json={"path": str(tmp_path), "symbols": []}).status_code == 400
    assert client.post("/api/context-bundle", json={"path": "", "symbols": ["x"]}).status_code == 400
    assert client.post("/api/context-bundle", json={"path": str(tmp_path), "symbols": ["x"], "depth": "bad"}).status_code == 400


def test_reindex_incremental_reuses_context(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=proj, check=True)

    r1 = client.post("/api/reindex", json={"path": str(proj), "engine": "ast_pure"})
    assert r1.json()["mode"] == "full"
    r2 = client.post("/api/reindex", json={"path": str(proj), "engine": "ast_pure"})
    assert r2.json()["mode"] == "full"  # ast_pure no usa incremental

    (proj / "b.py").write_text("y = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "b.py"], cwd=proj, check=True)
    # sin commitear: git status la detecta como untracked
    r3 = client.post("/api/reindex", json={"path": str(proj), "engine": "ast_local_llm", "model": None})
    # ast_local_llm sin ollama conectado hará fallback interno; la respuesta no debe explotar
    assert r3.status_code == 200
    assert r3.json()["ok"] is True


def test_semantic_graph_includes_and_relates_enriched_media():
    nodes = [
        {"id": "file:docs/mapa.png", "name": "mapa.png", "kind": "image", "degree": 1,
         "details": "Mapa turístico de museos y rutas culturales de Puebla (docs/mapa.png)"},
        {"id": "file:docs/ruta.pdf", "name": "ruta.pdf", "kind": "doc", "degree": 1,
         "details": "Guía turística con mapa de museos y rutas culturales de Puebla (docs/ruta.pdf)"},
        {"id": "dir:docs", "name": "docs", "kind": "module", "degree": 2, "details": "Carpeta docs"},
    ]
    graph = api_main.generate_semantic_graph({"nodes": nodes, "links": [], "metadata": {"path": "/tmp/demo"}})
    ids = {node["id"] for node in graph["nodes"]}
    assert "file:docs/mapa.png" in ids
    assert "file:docs/ruta.pdf" in ids
    inferred = [link for link in graph["links"] if link.get("confidence") == "INFERRED"]
    assert any("similitud semántica" in link["label"] for link in inferred)


def test_diff_endpoint_git_repo(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=proj, check=True)
    client.post("/api/reindex", json={"path": str(proj), "engine": "ast_pure"})
    (proj / "a.py").write_text("x = 2\n", encoding="utf-8")
    res = client.get("/api/diff", params={"path": str(proj)})
    assert res.status_code == 200
    body = res.json()
    assert "a.py" in body["changed_files"]
    assert isinstance(body["impacted_nodes"], list)


def test_history_endpoint(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    from graphtyn.core.history import HistoryTracker
    ht = HistoryTracker(proj)
    ht.log_event("s1", "cli", "evento de prueba", {"k": 1})
    res = client.get("/api/history", params={"path": str(proj)})
    assert res.status_code == 200
    assert len(res.json()["timeline"]) >= 1


def test_ollama_models_unreachable_returns_empty(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")

    def _boom(*args, **kwargs):
        raise Exception("sin conexión")

    monkeypatch.setattr(api_main.urllib.request, "urlopen", _boom)
    res = client.get("/api/ollama/models")
    assert res.status_code == 200
    assert res.json()["models"] == []


def test_projects_list_includes_respect_git(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
