import json
from pathlib import Path

from graphtyn.api import main as api_main
from graphtyn.core.history_import import save_source
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.core.storage import project_store_dir


def _json_response(response):
    return json.loads(response.body.decode("utf-8"))


def test_agent_registry_and_dynamic_topology(tmp_path, monkeypatch):
    state = tmp_path / "state"
    project = tmp_path / "crm"
    project.mkdir()
    monkeypatch.setattr(api_main, "INDEX_STORE", state)
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", state / "registered_projects.json")
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    api_main.REGISTRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    api_main.REGISTRATION_FILE.write_text(json.dumps([{"id": "crm", "name": "CRM", "path": str(project)}]))

    db_path = project_store_dir(state, project) / "memory-v2.db"
    store = SharedMemoryStore(project, db_path=db_path)
    session = store.start_session("friday", "Reporte", capture_enabled=True)
    store.checkpoint(session["id"], "decision", "Botón reporte", "Usar color ámbar")
    registered = _json_response(api_main.register_agent({
        "id": "friday", "name": "Friday", "provider": "openclaw", "paths": [str(project)]
    }))
    assert registered["agent"]["id"] == "friday"

    saved = save_source("openclaw", "/srv/openclaw", project_path=project, agent_id="friday")
    assert saved["agent_id"] == "friday"
    agents = _json_response(api_main.list_agents())
    friday = next(item for item in agents if item["id"] == "friday")
    assert friday["status"] == "observed"
    assert str(project.resolve()) in friday["paths"]

    topology = api_main._agent_topology_graph()
    assert topology["metadata"]["dynamic"] is True
    assert any(node["kind"] == "registered_agent" and node["agent_id"] == "friday"
               for node in topology["nodes"])
    assert not any(node.get("name") == "Agent-Code Agent" for node in topology["nodes"])


def test_agent_memory_graph_is_scoped_to_registered_identity(tmp_path, monkeypatch):
    state = tmp_path / "state"
    project = tmp_path / "brain"
    project.mkdir()
    monkeypatch.setattr(api_main, "INDEX_STORE", state)
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", state / "registered_projects.json")
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    api_main.REGISTRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    api_main.REGISTRATION_FILE.write_text(json.dumps([{"id": "brain", "path": str(project)}]))
    db_path = project_store_dir(state, project) / "memory-v2.db"
    store = SharedMemoryStore(project, db_path=db_path)
    own = store.start_session("nex", "Propio", capture_enabled=True)
    store.checkpoint(own["id"], "fact", "Dato propio", "Contexto de Nex")
    other = store.start_session("evi", "Otro", capture_enabled=True)
    store.checkpoint(other["id"], "fact", "Dato ajeno", "Contexto de Evi")
    store.process_topics(own["id"])
    store.process_topics(other["id"])
    api_main.register_agent({"id": "nex", "name": "Nex", "paths": [str(project)]})

    result = _json_response(api_main.memory_agent_graph("nex", limit=400, detail=False, authorization=None))
    assert result["ok"] is True
    names = {node.get("name") for node in result["nodes"]}
    assert "Dato propio" in names
    assert "Dato ajeno" not in names


def test_brain_registry_is_separate_from_agent_identity_catalog(tmp_path, monkeypatch):
    state = tmp_path / "state"
    brain = tmp_path / "memoria-evi"
    project = tmp_path / "crm"
    brain.mkdir()
    project.mkdir()
    monkeypatch.setattr(api_main, "INDEX_STORE", state)
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", state / "registered_projects.json")
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    api_main.REGISTRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    api_main.REGISTRATION_FILE.write_text(json.dumps([
        {"id": "memoria-evi", "name": "Cerebro Evi", "path": str(brain), "space_type": "agent_brain"},
        {"id": "legacy-brain", "name": "Legacy memory", "path": str(tmp_path / "legacy-brain"), "mode": "agent_discovered"},
        {"id": "crm", "name": "CRM", "path": str(project), "space_type": "project"},
    ]))
    (tmp_path / "legacy-brain").mkdir()

    db_path = project_store_dir(state, brain) / "memory-v2.db"
    store = SharedMemoryStore(brain, db_path=db_path)
    session = store.start_session("evi", "Diseño", capture_enabled=True)
    store.checkpoint(session["id"], "decision", "Botón de reporte", "Usar azul")

    brains = _json_response(api_main.list_brains())
    assert len(brains) == 2
    evi_brain = next(row for row in brains if row["name"] == "Cerebro Evi")
    assert evi_brain["space_type"] == "agent_brain"
    assert evi_brain["sessions"] == 1
    assert evi_brain["agents"][0]["id"] == "evi"
    assert any(row["name"] == "Legacy memory" and row["space_type"] == "agent_brain" for row in brains)

    projects = _json_response(api_main.list_projects())
    assert any(row["path"] == str(project.resolve()) and row["space_type"] == "project" for row in projects)
    assert not any(row["path"] == str(brain.resolve()) and row["space_type"] == "project" for row in projects)
