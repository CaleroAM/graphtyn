import json
from pathlib import Path
import pytest

from graphtyn.core.memory_scope import (
    ensure_project_memory_scope,
    expand_agent_aliases,
    resolve_memory_scope,
)
from graphtyn.core.agent_installer import install_agent
from graphtyn.core.history_import import _agent_id_matches


def test_expand_agent_aliases():
    assert expand_agent_aliases("antigravity") == {"antigravity", "agy"}
    assert expand_agent_aliases("agy") == {"antigravity", "agy"}
    assert expand_agent_aliases(["codex", "agy"]) == {"codex", "antigravity", "agy"}
    assert expand_agent_aliases(None) == set()
    assert expand_agent_aliases("") == set()


def test_agent_id_matches_with_aliases():
    assert _agent_id_matches("antigravity", "agy") is True
    assert _agent_id_matches("agy", "antigravity") is True
    assert _agent_id_matches("antigravity", "antigravity") is True
    assert _agent_id_matches("codex", "codex") is True
    assert _agent_id_matches("codex", "antigravity") is False
    assert _agent_id_matches(None, "antigravity") is False


def test_ensure_project_memory_scope_registers_and_expands_aliases(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    project = tmp_path / "modIAceb"
    project.mkdir()

    res = ensure_project_memory_scope(project, agent_ids=["antigravity"])
    assert res["ok"] is True
    assert "antigravity" in res["agent_ids"]
    assert "agy" in res["agent_ids"]

    # Call again with another agent; preserves existing and adds new
    res2 = ensure_project_memory_scope(project, agent_ids=["codex"])
    assert set(res2["agent_ids"]) == {"agy", "antigravity", "codex"}


def test_install_agent_updates_memory_scope_automatically(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    project = tmp_path / "my_project"
    project.mkdir()

    # Pre-register project with codex
    ensure_project_memory_scope(project, agent_ids=["codex"])

    # Now install antigravity
    install_agent(project, "antigravity", tool_profile="full")

    scope = resolve_memory_scope(project)
    assert scope["space_type"] == "project"
    assert "codex" in scope["agent_ids"]
    assert "antigravity" in scope["agent_ids"]
    assert "agy" in scope["agent_ids"]
    assert scope["restricted"] is False


def test_project_memory_scope_not_restricted_by_default(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    project = tmp_path / "shared_proj"
    project.mkdir()

    # Project registered with agent_ids is still shared (restricted is False)
    registry_file = home / "registered_projects.json"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps([{
        "id": "shared_proj",
        "name": "shared_proj",
        "path": str(project),
        "space_type": "project",
        "agent_ids": ["codex"]
    }]), encoding="utf-8")

    scope = resolve_memory_scope(project)
    assert scope["space_type"] == "project"
    assert scope["restricted"] is False
    assert "codex" in scope["agent_ids"]


def test_agent_brain_is_restricted_by_default(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    brain = tmp_path / "personal_brain"
    brain.mkdir()

    registry_file = home / "registered_projects.json"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps([{
        "id": "personal_brain",
        "name": "personal_brain",
        "path": str(brain),
        "space_type": "agent_brain",
        "agent_ids": ["openclaw/career"]
    }]), encoding="utf-8")

    scope = resolve_memory_scope(brain)
    assert scope["space_type"] == "agent_brain"
    assert scope["restricted"] is True
    assert "openclaw/career" in scope["agent_ids"]
