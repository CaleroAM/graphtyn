import json
import asyncio
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
from pathlib import Path

import httpx
import uvicorn

from graphtyn.api import main as api_main
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.core.memory_jobs import MemoryJobManager


class _LiveClient:
    """Exercise the real Uvicorn HTTP stack without Starlette TestClient."""

    def request(self, method, path, **kwargs):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        config = uvicorn.Config(api_main.app, log_level="error", lifespan="off")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        try:
            assert server.started, "Uvicorn did not start"
            return httpx.request(method, f"http://127.0.0.1:{port}{path}", timeout=20, **kwargs)
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            listener.close()

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)


def _client(tmp_path, monkeypatch):
    state = tmp_path / ".graphtyn-store"
    monkeypatch.setattr(api_main, "INDEX_STORE", state)
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    return _LiveClient()


def test_health_endpoint(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "Graphtyn"


def test_memory_watcher_waits_after_each_sync(tmp_path, monkeypatch):
    path = tmp_path / "brain"
    path.mkdir()
    key = str(path.resolve())
    calls = []

    class StopAfterWait:
        stopped = False
        waits = []

        def is_set(self):
            return self.stopped

        def wait(self, interval):
            self.waits.append(interval)
            self.stopped = True
            return True

        def set(self):
            self.stopped = True

    stop = StopAfterWait()

    def sync(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 2:
            stop.set()
        return {"ok": True}

    monkeypatch.setattr(api_main, "sync_memory_workspace", sync)
    monkeypatch.setitem(api_main._memory_watchers, key,
                        {"stop": stop, "status": "starting", "heartbeat": 0})

    api_main._memory_watch_loop(key, {"interval": 7}, stop)

    assert len(calls) == 1
    assert stop.waits == [7]
    assert key not in api_main._memory_watchers


def test_memory_http_search_context_sessions_and_auth(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    store = SharedMemoryStore(project)
    session = store.start_session("agy", "Auth memory", branch="main")
    memory = store.checkpoint(session["id"], "decision", "JWT centralizado", "AuthService validates credentials")
    monkeypatch.setenv("GRAPHTYN_MEMORY_HTTP_TOKEN", "memory-secret")
    denied = api_main.memory_status(str(project), authorization=None)
    assert denied.status_code == 401
    auth = "Bearer memory-secret"
    status = api_main.memory_status(str(project), authorization=auth)
    sessions = api_main.memory_sessions(str(project), 50, authorization=auth)
    search = api_main.memory_search({"path": str(project), "query": "credentials",
                                     "requester_agent": "opencode"}, authorization=auth)
    context = api_main.memory_context({"path": str(project), "query": "credentials",
                                       "requester_agent": "opencode", "token_budget": 500}, authorization=auth)

    assert status["memories"] == 1
    assert sessions["sessions"][0]["agent_id"] == "agy"
    assert search["results"][0]["id"] == memory["id"]
    assert context["memories"][0]["agent_id"] == "agy"
    graph = api_main.memory_graph(str(project), requester_agent="opencode", limit=300, authorization=auth)
    assert graph["ok"] is True
    assert any(node.get("kind") == "memory_agent" for node in graph["nodes"])


def test_mcp_token_does_not_lock_local_dashboard_memory_api(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.setenv("GRAPHTYN_MCP_TOKEN", "remote-only")
    project = tmp_path / "project"
    project.mkdir()
    status = api_main.memory_status(str(project), authorization=None)
    assert status["ok"] is True


def test_agent_mcp_context_is_bound_to_token_identity_and_store(tmp_path, monkeypatch):
    from graphtyn.core.history_import import save_source
    from graphtyn.core.openclaw_integration import _agent_entries, connect_openclaw

    client = _client(tmp_path, monkeypatch)
    data_root = tmp_path / "openclaw"
    (data_root / "agents" / "main").mkdir(parents=True)
    (data_root / "agents" / "qa").mkdir(parents=True)
    config = data_root / "openclaw.json"
    config.write_text(json.dumps({"agents": {"entries": {"main": {}, "qa": {}}}}))
    evi = tmp_path / "brains" / "evi"
    evi.mkdir(parents=True)
    source_config = tmp_path / "history-sources.json"
    save_source("openclaw", str(data_root / "agents" / "main"), project_path=evi,
                agent_id="openclaw/main", path=source_config)
    registry = api_main.INDEX_STORE / "openclaw-installations.json"
    installation = connect_openclaw({"ok": True, "id": "openclaw-0123456789abcdef",
        "kind": "local", "target": "local", "config_path": str(config),
        "data_root": str(data_root), "agents": _agent_entries(json.loads(config.read_text()))},
        source_config=source_config, registry=registry)
    qa_path = next(row["brain_path"] for row in installation["agents"] if row["id"] == "qa")
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({
        "qa-reader": {"role": "reader", "agent_id": "openclaw/qa", "projects": [qa_path]}}))

    def call(agent_id):
        response = api_main.mcp_http({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "memory_agent_context", "arguments": {
                "agent_id": agent_id, "query": "deployment"}}}, authorization="Bearer qa-reader")
        return json.loads(response.body)

    own = call("openclaw/qa")
    other = call("openclaw/main")
    own_text = own["result"]["content"][0]["text"]
    denied_text = other["result"]["content"][0]["text"]
    assert json.loads(own_text).get("agent_id") == "openclaw/qa", own_text
    assert own["result"].get("isError") is None
    assert other["result"]["isError"] is True
    assert "otro agente" in json.loads(denied_text)["error"]


def test_http_mcp_exposes_agent_memory_tools_in_intent_profile(monkeypatch):
    monkeypatch.setenv("GRAPHTYN_MCP_TOKEN", "mcp-token")
    monkeypatch.setenv("GRAPHTYN_HTTP_TOOL_PROFILE", "intent")
    response = api_main.mcp_http({"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
                                 authorization="Bearer mcp-token")
    names = {row["name"] for row in json.loads(response.body)["result"]["tools"]}
    assert {"memory_agent_context", "memory_agent_status", "memory_agent_publish",
            "memory_agent_revoke", "memory_agent_update"} <= names


def test_memory_http_correct_and_forget_enforce_author(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHTYN_MCP_TOKEN", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    store = SharedMemoryStore(project)
    session = store.start_session("agy", "Database")
    old = store.checkpoint(session["id"], "decision", "DB", "Use MySQL")
    corrected = api_main.memory_correct({"path": str(project), "memory_id": old["id"],
        "session_id": session["id"], "title": "DB corrected", "content": "Use PostgreSQL"})
    new_id = corrected["memory"]["id"]
    forbidden = api_main.memory_forget({"path": str(project), "memory_id": new_id, "requester_agent": "opencode"})
    forgotten = api_main.memory_forget({"path": str(project), "memory_id": new_id, "requester_agent": "agy"})

    assert corrected["ok"] is True
    assert forbidden.status_code == 403
    assert forgotten["ok"] is True


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


def test_agent_directory_respects_registered_brain_owners(tmp_path, monkeypatch):
    state = tmp_path / "store"
    monkeypatch.setattr(api_main, "INDEX_STORE", state)
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    brain = tmp_path / "legacy-mixed-brain"
    brain.mkdir()
    store = SharedMemoryStore(brain)
    store.start_session("openclaw/architect", "Architect work")
    store.start_session("openclaw/career", "Career work")

    legacy = tmp_path / "archived-shared-brain"
    legacy.mkdir()
    legacy_store = SharedMemoryStore(legacy)
    legacy_store.start_session("openclaw/architect", "Old architect work")
    legacy_store.start_session("openclaw/career", "Old career work")

    projects_file = state / "registered_projects.json"
    projects_file.write_text(json.dumps([{
        "id": "legacy-mixed-brain", "name": "Legacy mixed brain", "path": str(brain),
        "mode": "single_folder", "space_type": "agent_brain",
        "agent_ids": ["openclaw/architect"],
    }, {
        "id": "archived-shared-brain", "name": "Legacy archive", "path": str(legacy),
        "mode": "single_folder", "space_type": "agent_brain", "legacy": True,
        "agent_ids": ["openclaw/architect", "openclaw/career"],
    }]))
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", projects_file)
    (state / "registered_agents.json").write_text(json.dumps({"version": 1, "agents": [
        {"id": "openclaw/architect", "name": "Architect", "provider": "openclaw"},
        {"id": "openclaw/career", "name": "Career", "provider": "openclaw"},
    ]}))

    agents = {row["id"]: row for row in api_main._load_registered_agents()}

    assert agents["openclaw/architect"]["sessions"] == 1
    assert str(brain) in agents["openclaw/architect"]["projects"]
    assert agents["openclaw/architect"]["name"] == "Architect"
    assert str(legacy) not in agents["openclaw/architect"]["paths"]
    assert agents["openclaw/career"]["sessions"] == 0
    assert str(brain) not in agents["openclaw/career"]["paths"]
    assert str(legacy) not in agents["openclaw/career"]["paths"]

    archives = {row["path"]: row for row in api_main._load_registered_brains()}
    assert archives[str(legacy)]["legacy"] is True
    assert archives[str(legacy)]["sessions"] == 2


def test_dashboard_assets_served(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    html = client.get("/")
    assert html.status_code == 200
    assert "Graphtyn" in html.text
    assert "/dashboard.css" in html.text and "/dashboard.js" in html.text
    assert 'id="btn-openclaw"' in html.text and "OpenClaw" in html.text
    assert 'id="blast-content"' in html.text and "overflow-wrap:anywhere" in html.text
    css = client.get("/dashboard.css")
    assert css.status_code == 200
    assert "graph-container" in css.text
    js = client.get("/dashboard.js")
    assert js.status_code == 200
    assert "Object.assign(window" in js.text
    for module in ["state", "painters", "sim", "styles", "graph", "controls", "ui", "quality", "memory", "openclaw"]:
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
    assert "loadOpenClawPanel" in client.get("/js/controls.js").text
    assert "Sincronizar ahora" in client.get("/js/openclaw.js").text
    assert "openclaw-manager" in css.text
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


def test_memory_search_all_federated(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHTYN_MCP_TOKEN", raising=False)
    client = _client(tmp_path, monkeypatch)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    sa = SharedMemoryStore(a)
    s1 = sa.start_session("career", "t", capture_enabled=True)
    sa.checkpoint(s1["id"], "fact", "Entrevista AWS", "Preguntas de kubernetes y lambdas")
    sb = SharedMemoryStore(b)
    s2 = sb.start_session("opencode", "t2", capture_enabled=True)
    sb.checkpoint(s2["id"], "fact", "Nota ingles", "vocabulario stand-up")

    r = client.post("/api/memory/search-all", json={"paths": [str(a), str(b)], "query": "kubernetes entrevista"})
    assert r.status_code == 200
    data = r.json()
    stores = {item["store"] for item in data["results"]}
    assert stores <= {str(a), str(b)}
    assert any("Entrevista AWS" in item["title"] for item in data["results"])

    r2 = client.post("/api/memory/search-all", json={"paths": ["/ruta/inexistente"], "query": "x"})
    assert r2.status_code == 200 and r2.json()["results"] == []


def test_memory_search_all_enforces_token_project_scope(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    allowed, blocked = tmp_path / "allowed", tmp_path / "blocked"
    allowed.mkdir(); blocked.mkdir()
    SharedMemoryStore(allowed).start_session("agent-a", "allowed")
    SharedMemoryStore(blocked).start_session("agent-b", "blocked")
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({
        "reader-token": {"role": "reader", "projects": [str(allowed.resolve())]}
    }))
    api_main._RATE_EVENTS.clear()
    response = client.post("/api/memory/search-all", json={
        "paths": [str(allowed), str(blocked)], "query": "memory"
    }, headers={"Authorization": "Bearer reader-token"})
    assert response.status_code == 403


def test_remote_memory_api_requires_a_memory_token_even_if_mcp_is_enabled(monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS_FILE", raising=False)
    monkeypatch.setenv("GRAPHTYN_MCP_TOKEN", "mcp-secret")
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"),
                              url=SimpleNamespace(path="/api/memory/status"), headers={})
    response = asyncio.run(api_main.require_remote_memory_auth(request, lambda _request: None))
    assert response.status_code == 503

    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({"reader-token": "reader"}))
    response = asyncio.run(api_main.require_remote_memory_auth(request, lambda _request: None))
    assert response.status_code == 401
    request.headers = {"authorization": "Bearer reader-token"}
    assert asyncio.run(api_main.require_remote_memory_auth(request, lambda _request: asyncio.sleep(0, result="ok"))) == "ok"


def test_memory_sync_job_runs_each_registered_space(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    first, second = tmp_path / "brain-one", tmp_path / "brain-two"
    first.mkdir(); second.mkdir()
    manager = MemoryJobManager(tmp_path / "jobs")
    monkeypatch.setattr(api_main, "memory_jobs", manager)
    monkeypatch.setattr(api_main, "_registered_memory_paths_checked", lambda: ([first, second], []))
    calls = []

    def fake_sync(path, **kwargs):
        calls.append(str(path))
        return {"ok": True, "path": str(path), "errors": [], "import": {},
                "enrichment": {"ai_enriched": 1}}

    monkeypatch.setattr(api_main, "sync_memory_workspace", fake_sync)
    response = api_main.memory_sync({"all_spaces": True, "consent": True, "provider_model": "auto"}, authorization=None)
    job_id = response["job"]["id"]
    deadline = time.time() + 10
    while time.time() < deadline and manager.get(job_id)["status"] in {"pending", "running"}:
        time.sleep(.01)
    job = manager.get(job_id)

    assert response["paths"] == [str(first), str(second)]
    assert job["status"] == "completed", job
    assert job["result"]["space_count"] == 2
    assert calls == [str(first), str(second)]


def test_openclaw_dashboard_status_includes_each_agent_memory(monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS_FILE", raising=False)
    from graphtyn.core import openclaw_integration
    installation = {"id": "openclaw-test", "agents": [{"id": "main", "agent_id": "openclaw/main",
                                                         "brain_path": "/tmp/brain"}]}
    monkeypatch.setattr(openclaw_integration, "list_installations", lambda: [installation])
    monkeypatch.setattr(openclaw_integration, "resolve_agent", lambda *_args: {"brain_path": "/tmp/brain"})
    monkeypatch.setattr(openclaw_integration, "agent_status", lambda *_args: {"own": {"sessions": 2}})
    monkeypatch.setattr(api_main, "existing_store_db", lambda _path: Path("/tmp/memory-v2.db"))

    result = api_main.openclaw_installations()

    assert result["installations"][0]["agents"][0]["memory_status"]["own"]["sessions"] == 2


def test_openclaw_sync_job_runs_each_isolated_brain(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS_FILE", raising=False)
    from graphtyn.core import openclaw_integration
    first, second = tmp_path / "evi", tmp_path / "eve"
    first.mkdir(); second.mkdir()
    installation = {"id": "openclaw-test", "agents": [
        {"id": "nexus", "agent_id": "openclaw/nexus", "display_name": "Evi", "brain_path": str(first)},
        {"id": "career", "agent_id": "openclaw/career", "display_name": "Eve", "brain_path": str(second)},
    ]}
    monkeypatch.setattr(openclaw_integration, "get_installation", lambda _id: installation)
    manager = MemoryJobManager(tmp_path / "jobs")
    monkeypatch.setattr(api_main, "memory_jobs", manager)
    calls = []

    def fake_sync(path, **kwargs):
        calls.append((str(path), kwargs["agent_id"]))
        return {"ok": True, "path": str(path), "errors": []}

    monkeypatch.setattr(api_main, "sync_memory_workspace", fake_sync)
    response = api_main.openclaw_sync("openclaw-test")
    job_id = response["job"]["id"]
    deadline = time.time() + 2
    while time.time() < deadline and manager.get(job_id)["status"] in {"pending", "running"}:
        time.sleep(.01)
    job = manager.get(job_id)

    assert job["status"] == "completed"
    assert job["result"]["ok"] is True
    assert calls == [(str(first.resolve()), "openclaw/nexus"), (str(second.resolve()), "openclaw/career")]


def test_legacy_memory_archives_are_excluded_from_sync_and_watch(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS", raising=False)
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS_FILE", raising=False)
    state = tmp_path / "store"
    monkeypatch.setattr(api_main, "INDEX_STORE", state)
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    registry = state / "registered_projects.json"
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", registry)
    archive, active = tmp_path / "legacy-brain", tmp_path / "active-brain"
    archive.mkdir(); active.mkdir()
    SharedMemoryStore(archive).start_session("openclaw/old", "Archived conversation")
    SharedMemoryStore(active).start_session("openclaw/current", "Current conversation")
    registry.write_text(json.dumps([
        {"id": "old", "name": "Legado mixto · Cerebro antiguo", "path": str(archive),
         "mode": "single_folder", "space_type": "agent_brain", "legacy": True},
        {"id": "current", "name": "Current brain", "path": str(active),
         "mode": "single_folder", "space_type": "agent_brain", "agent_ids": ["openclaw/current"]},
    ]), encoding="utf-8")

    assert archive.resolve() not in api_main._registered_memory_paths()
    assert active.resolve() in api_main._registered_memory_paths()
    sync = api_main.memory_sync({"path": str(archive), "consent": True})
    watch = api_main.memory_watch({"path": str(archive), "consent": True, "enabled": True})
    assert sync.status_code == 409 and sync.body
    assert watch.status_code == 409 and watch.body



def test_registered_memory_sync_conflicts_are_reported_without_blocking_other_spaces(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MEMORY_HTTP_TOKEN", raising=False)
    healthy, conflicted = tmp_path / "healthy-brain", tmp_path / "conflicted-brain"
    healthy.mkdir(); conflicted.mkdir()
    manager = MemoryJobManager(tmp_path / "jobs")
    monkeypatch.setattr(api_main, "memory_jobs", manager)
    monkeypatch.setattr(api_main, "_registered_memory_paths_checked", lambda: ([healthy], [{
        "path": str(conflicted), "code": "memory_store_conflict", "error": "duplicate store"}]))
    calls = []

    def fake_sync(path, **_kwargs):
        calls.append(str(path))
        return {"ok": True, "path": str(path), "errors": []}

    monkeypatch.setattr(api_main, "sync_memory_workspace", fake_sync)
    response = api_main.memory_sync({"all_spaces": True, "consent": True}, authorization=None)
    job_id = response["job"]["id"]
    deadline = time.time() + 2
    while time.time() < deadline and manager.get(job_id)["status"] in {"pending", "running"}:
        time.sleep(.01)
    job = manager.get(job_id)

    assert calls == [str(healthy)]
    assert job["status"] == "completed"
    assert job["result"]["ok"] is False
    assert len(job["result"]["spaces"]) == 2
    assert job["result"]["spaces"][0]["code"] == "memory_store_conflict"
    assert job["result"]["spaces"][1]["path"] == str(healthy)
