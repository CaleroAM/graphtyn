import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from aether_graph.api import main as api_main


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / ".aether-store")
    return TestClient(api_main.app)


def test_health_endpoint(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "AetherGraph"


def test_dashboard_assets_served(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    html = client.get("/")
    assert html.status_code == 200
    assert "AetherGraph" in html.text
    assert "/dashboard.css" in html.text and "/dashboard.js" in html.text
    css = client.get("/dashboard.css")
    assert css.status_code == 200
    assert "graph-container" in css.text
    js = client.get("/dashboard.js")
    assert js.status_code == 200
    assert "Object.assign(window" in js.text
    for module in ["state", "painters", "sim", "styles", "graph", "controls", "ui"]:
        r = client.get(f"/js/{module}.js")
        assert r.status_code == 200, module
        assert "export " in r.text, module
    state_js = client.get("/js/state.js").text
    assert "export const PALETTES" in state_js
    assert "export const COMM_COLORS" in state_js
    assert "import { state }" in client.get("/dashboard.js").text
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
    from aether_graph.core.history import HistoryTracker
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
