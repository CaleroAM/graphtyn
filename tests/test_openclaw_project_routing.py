import json
from pathlib import Path

import pytest

from graphtyn.core import history_import
from graphtyn.core.openclaw_project_routing import (registered_project_targets,
    resolve_registered_project, route_openclaw_sessions)
from graphtyn.core.shared_memory import SharedMemoryStore


def _registrations(home: Path, *rows):
    home.mkdir(parents=True, exist_ok=True)
    (home / "registered_projects.json").write_text(json.dumps(list(rows)), encoding="utf-8")


def test_registered_project_targets_exclude_brains_and_load_aliases(tmp_path):
    project = tmp_path / "TourMuseosPuebla"
    project.mkdir()
    brain = tmp_path / "evi-brain"
    brain.mkdir()
    _registrations(tmp_path, {"id": "tour", "name": "TourMuseosPuebla", "path": str(project),
                              "space_type": "project"},
                   {"id": "evi", "name": "Evi", "path": str(brain),
                    "space_type": "agent_brain", "agent_ids": ["openclaw/nexus"]})
    (tmp_path / "project-identities.json").write_text(json.dumps({"version": 1, "projects": [{
        "id": "stable-tour", "canonical_name": "TourMuseosPuebla", "aliases": ["Museos"],
        "paths": [str(project)],
    }]}), encoding="utf-8")

    targets = registered_project_targets(home=tmp_path)

    assert len(targets) == 1
    assert targets[0]["id"] == "stable-tour"
    assert {"TourMuseosPuebla", "Museos"}.issubset(set(targets[0]["aliases"]))


def test_resolve_registered_project_requires_exact_unique_identity(tmp_path):
    project_a = tmp_path / "crm-a"
    project_b = tmp_path / "crm-b"
    project_a.mkdir(); project_b.mkdir()
    _registrations(tmp_path,
        {"id": "crm-a", "name": "CRM Operadores", "path": str(project_a),
         "space_type": "project", "aliases": ["CRM"]},
        {"id": "crm-b", "name": "CRM Reportes", "path": str(project_b),
         "space_type": "project", "aliases": ["CRM"]})
    targets = registered_project_targets(home=tmp_path)

    ambiguous = resolve_registered_project("CRM", targets=targets)
    by_id = resolve_registered_project("crm-a", targets=targets)
    by_path = resolve_registered_project(str(project_b), targets=targets)
    fuzzy = resolve_registered_project("el proyecto CRM operadores", targets=targets)

    assert ambiguous["status"] == "ambiguous"
    assert {item["id"] for item in ambiguous["candidates"]} == {"crm-a", "crm-b"}
    assert by_id["project"]["id"] == "crm-a"
    assert by_path["project"]["id"] == "crm-b"
    assert fuzzy["status"] == "unresolved"


def test_route_openclaw_session_to_each_explicit_project_per_turn(tmp_path):
    tour = tmp_path / "TourMuseosPuebla"
    crm = tmp_path / "crm-suite"
    tour.mkdir(); crm.mkdir()
    _registrations(tmp_path,
        {"id": "tour", "name": "TourMuseosPuebla", "path": str(tour), "space_type": "project"},
        {"id": "crm", "name": "CRM", "path": str(crm), "space_type": "project"})
    targets = registered_project_targets(home=tmp_path)
    sessions = [{"provider": "openclaw", "agent_id": "openclaw/nexus",
        "external_session_id": "native-session-1", "task": "Conversación de Evi", "source": "agent.sqlite",
        "workspace": "/home/node/.openclaw/workspace/nexus", "fingerprint": "whole-session-v1",
        "messages": [
            {"role": "user", "content": "Revisemos el proyecto TourMuseosPuebla", "metadata": {"source_message_id": "m1"}},
            {"role": "assistant", "content": "La decisión para TourMuseosPuebla es conservar el flujo actual.", "metadata": {"source_message_id": "m2"}},
            {"role": "user", "content": "Ahora revisemos el proyecto CRM", "metadata": {"source_message_id": "m3"}},
            {"role": "assistant", "content": "Para CRM decidimos validar operadores por rol.", "metadata": {"source_message_id": "m4"}},
        ]}]

    routed = route_openclaw_sessions(sessions, targets=targets)

    assert routed["summary"]["routed_segments"] == 2
    assert routed["summary"]["routed_messages"] == 4
    by_name = {row["project_name"]: row for row in routed["segments"]}
    assert [m["metadata"]["source_message_id"] for m in by_name["TourMuseosPuebla"]["messages"]] == ["m1", "m2"]
    assert [m["metadata"]["source_message_id"] for m in by_name["CRM"]["messages"]] == ["m3", "m4"]
    assert by_name["TourMuseosPuebla"]["agent_id"] == "openclaw/nexus"
    assert by_name["CRM"]["external_session_id"].endswith(":crm")


def test_route_ambiguous_turn_and_default_agent_workspace_stays_unassigned(tmp_path):
    tour = tmp_path / "TourMuseosPuebla"
    crm = tmp_path / "CRM"
    tour.mkdir(); crm.mkdir()
    _registrations(tmp_path,
        {"id": "tour", "name": "TourMuseosPuebla", "path": str(tour), "space_type": "project"},
        {"id": "crm", "name": "CRM", "path": str(crm), "space_type": "project"})
    targets = registered_project_targets(home=tmp_path)
    session = {"provider": "openclaw", "agent_id": "openclaw/nexus", "external_session_id": "ambiguous",
        "task": "General chat", "workspace": "/home/node/.openclaw/workspace/nexus", "messages": [
            {"role": "user", "content": "Compara el proyecto TourMuseosPuebla con el proyecto CRM"},
            {"role": "assistant", "content": "¿Cuál proyecto quieres priorizar?"},
        ]}

    ambiguous = route_openclaw_sessions([session], targets=targets)
    unassigned = route_openclaw_sessions([{"provider": "openclaw", "agent_id": "openclaw/nexus",
        "external_session_id": "generic", "task": "General chat",
        "workspace": "/home/node/.openclaw/workspace/nexus",
        "messages": [{"role": "user", "content": "¿Qué opinas del plan?"}]}], targets=targets)

    assert not ambiguous["segments"]
    assert ambiguous["sessions"][0]["status"] == "ambiguous"
    assert unassigned["sessions"][0]["status"] == "unassigned"


def test_agent_brain_sync_captures_default_openclaw_workspace_without_project_guess(tmp_path, monkeypatch):
    home = tmp_path / "graphtyn-home"
    brain = tmp_path / "brain-nexus"
    project = tmp_path / "OpenClaw"
    brain.mkdir(); project.mkdir()
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    _registrations(home,
        {"id": "openclaw-project", "name": "OpenClaw", "path": str(project), "space_type": "project"},
        {"id": "nexus", "name": "Nexus", "path": str(brain), "space_type": "agent_brain",
         "agent_ids": ["openclaw/nexus"]})
    source = tmp_path / "session.jsonl"
    external_id = "native-default-workspace-session"
    source.write_text("\n".join(json.dumps(row) for row in [
        {"type": "session_meta", "payload": {"id": external_id,
         "workspace": "/home/node/.openclaw/workspace/nexus"}},
        {"sessionId": external_id, "id": "message-1", "role": "user", "content": "Consulta general."},
        {"sessionId": external_id, "id": "message-2", "role": "assistant", "content": "Respuesta general."},
    ]) + "\n", encoding="utf-8")
    discovered = {"ok": True, "count": 1, "sessions": [{
        "provider": "openclaw", "agent_id": "openclaw/nexus", "external_session_id": external_id,
        "task": "Consulta general", "source": str(source),
        "workspace": "/home/node/.openclaw/workspace/nexus", "streaming_source": True,
        "messages": [], "fingerprint": "native-default-workspace-v1",
    }], "errors": [], "warnings": [], "excluded": [], "excluded_count": 0}
    monkeypatch.setattr(history_import, "discover_histories", lambda *args, **kwargs: discovered)

    result = history_import.sync_memory_workspace(brain, provider="openclaw", agent_id="openclaw/nexus",
        provider_model="deterministic", enrich=False)

    assert result["ok"] is True
    assert len(result["import"]["imported"]) == 1
    assert result["import"]["ambiguous"] == []
    assert result["project_routing"]["unassigned_sessions"] == 1
    brain_store = SharedMemoryStore(brain)
    with brain_store._connect() as db:
        rows = db.execute("SELECT content,metadata_json FROM messages ORDER BY created_at,id").fetchall()
    project_store = SharedMemoryStore(project)
    with project_store._connect() as db:
        project_sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert [row["content"] for row in rows] == ["Consulta general.", "Respuesta general."]
    assert all(json.loads(row["metadata_json"])["agent_workspace"] ==
               "/home/node/.openclaw/workspace/nexus" for row in rows)
    assert project_sessions == 0


@pytest.mark.parametrize(("message", "expected_project"), [
    ("Revisa el proyecto TourMuseosPuebla usando Graphtyn.", "TourMuseosPuebla"),
    ("Cambiando al proyecto Graphtyn, no a TourMuseosPuebla.", "Graphtyn"),
])
def test_explicit_project_cue_wins_over_incidental_registered_tool_name(tmp_path, message, expected_project):
    tour = tmp_path / "TourMuseosPuebla"
    graphtyn = tmp_path / "graphtyn"
    tour.mkdir(); graphtyn.mkdir()
    _registrations(tmp_path,
        {"id": "tour", "name": "TourMuseosPuebla", "path": str(tour), "space_type": "project"},
        {"id": "graphtyn", "name": "Graphtyn", "path": str(graphtyn), "space_type": "project"})
    session = {"provider": "openclaw", "agent_id": "openclaw/nexus",
        "external_session_id": "tool-name-is-not-target", "task": "Revisión", "messages": [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "Haré la revisión solicitada."},
        ]}

    routed = route_openclaw_sessions([session], targets=registered_project_targets(home=tmp_path))

    assert routed["sessions"][0]["status"] == "routed"
    assert len(routed["segments"]) == 1
    assert routed["segments"][0]["project_name"] == expected_project


@pytest.mark.parametrize("provider", ["openclaw", None])
def test_sync_memory_workspace_imports_named_openclaw_project_turn(tmp_path, monkeypatch, provider):
    home = tmp_path / "graphtyn-home"
    brain = tmp_path / "brain-evi"
    project = tmp_path / "TourMuseosPuebla"
    brain.mkdir(); project.mkdir()
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    _registrations(home, {"id": "tour", "name": "TourMuseosPuebla", "path": str(project),
                          "space_type": "project"},
                   {"id": "evi", "name": "Evi", "path": str(brain), "space_type": "agent_brain",
                    "agent_ids": ["openclaw/nexus"]})
    discovered = {"ok": True, "count": 1, "sessions": [{
        "provider": "openclaw", "agent_id": "openclaw/nexus", "external_session_id": "native-1",
        "task": "Revisa el proyecto TourMuseosPuebla", "source": "ssh://openclaw/agents/nexus/agent.sqlite",
        "workspace": "/home/node/.openclaw/workspace/nexus", "capture_mode": "incremental_sync",
        "fingerprint": "source-session-v1", "explicit_project_selection": True,
        "messages": [
            {"role": "user", "content": "Revisa el proyecto TourMuseosPuebla", "metadata": {"source_message_id": "u1"}},
            {"role": "assistant", "content": "Decidimos mantener el acceso actual a los reportes.",
             "metadata": {"source_message_id": "a1"}},
        ]}], "errors": [], "warnings": [], "excluded": [], "excluded_count": 0}
    monkeypatch.setattr(history_import, "discover_histories", lambda *args, **kwargs: discovered)

    result = history_import.sync_memory_workspace(brain, provider=provider, agent_id="openclaw/nexus",
                                                  provider_model="deterministic", enrich=False)

    assert result["ok"] is True
    assert result["project_routing"]["imported_segments"] == 1
    project_store = SharedMemoryStore(project)
    with project_store._connect() as db:
        session = db.execute("select id,agent_id,task from sessions").fetchone()
        messages = db.execute("select role,metadata_json from messages order by created_at").fetchall()
    assert session["agent_id"] == "openclaw/nexus"
    assert "TourMuseosPuebla" in session["task"]
    assert len(messages) == 2
    metadata = [json.loads(row["metadata_json"]) for row in messages]
    assert {item["source_message_id"] for item in metadata} == {"u1", "a1"}
    stable_project_id = result["project_routing"]["projects"][0]["id"]
    assert stable_project_id != "tour"
    assert all(item["project_id"] == stable_project_id for item in metadata)
    assert all(item["capture_mode"] == "project_routed_incremental" for item in metadata)
    assert SharedMemoryStore(brain).status()["project_routing"]["routed"] == 1

    # Native sync presents the updated transcript under the same stable source
    # session ID. New turns append to the project segment, and a repeat sync is
    # idempotent.
    discovered["sessions"][0]["messages"].append({
        "role": "assistant", "content": "También acordamos conservar la atribución del agente.",
        "metadata": {"source_message_id": "a2"},
    })
    discovered["sessions"][0]["fingerprint"] = "source-session-v2"
    second = history_import.sync_memory_workspace(brain, provider=provider, agent_id="openclaw/nexus",
        provider_model="deterministic", enrich=False)
    repeated = history_import.sync_memory_workspace(brain, provider=provider, agent_id="openclaw/nexus",
        provider_model="deterministic", enrich=False)
    with project_store._connect() as db:
        message_rows = db.execute("select metadata_json from messages order by created_at,id").fetchall()
        project_session_count = db.execute("select count(*) from sessions").fetchone()[0]
    source_ids = [json.loads(row[0])["source_message_id"] for row in message_rows]
    assert second["project_routing"]["imported_segments"] == 1
    assert repeated["project_routing"]["reused_segments"] == 1
    assert len(source_ids) == 3
    assert set(source_ids) == {"u1", "a1", "a2"}
    assert project_session_count == 1
