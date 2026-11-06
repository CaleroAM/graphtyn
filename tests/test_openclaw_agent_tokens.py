import json
import os

from graphtyn.core import openclaw_agent_tokens as per_agent
from graphtyn.core.storage import data_home


def _stores(tmp_path):
    code = tmp_path / "code-project"
    code.mkdir()
    brains = data_home() / "brains" / "openclaw-x"
    (brains / "nexus").mkdir(parents=True)
    (brains / "career").mkdir()
    (brains / "nexus-shared").mkdir()
    (data_home() / "registered_projects.json").write_text(json.dumps([
        {"name": "code", "path": str(code)}, {"name": "Evi", "path": str(brains / "nexus")},
        {"name": "gone", "path": str(tmp_path / "missing")}]), encoding="utf-8")
    agents = [{"id": "nexus", "brain_path": str(brains / "nexus"), "family_path": str(brains / "nexus-shared"),
               "memory_enabled": True},
              {"id": "career", "brain_path": str(brains / "career"), "memory_enabled": True},
              {"id": "video"}]
    return code.resolve(), brains.resolve(), agents


def test_server_names_are_provider_safe():
    assert per_agent.server_name("nexus") == "graphtyn-nexus"
    assert per_agent.server_name("Evi Code!") == "graphtyn-evi-code"


def test_only_code_projects_are_shared_between_agents(tmp_path):
    code, _brains, _agents = _stores(tmp_path)
    assert per_agent.code_projects() == [str(code)]


def test_each_agent_gets_a_bound_reader_token_limited_to_its_own_stores(tmp_path):
    code, brains, agents = _stores(tmp_path)
    tokens_file = tmp_path / "tokens.json"

    first = per_agent.ensure_agent_tokens(tokens_file, "openclaw-x", agents, [str(code)])
    again = per_agent.ensure_agent_tokens(tokens_file, "openclaw-x", agents, [str(code)])
    saved = json.loads(tokens_file.read_text(encoding="utf-8"))

    assert first == again and len(set(first.values())) == 3
    assert saved[first["nexus"]] == {"role": "reader", "agent_id": "openclaw/nexus", "installation": "openclaw-x",
                                     "projects": [str(code), str(brains / "nexus"), str(brains / "nexus-shared")]}
    assert saved[first["video"]]["projects"] == [str(code)]
    assert str(brains / "nexus") not in saved[first["career"]]["projects"]
    assert oct(os.stat(tokens_file).st_mode & 0o777) == "0o600"


def test_the_config_has_one_server_per_agent_and_each_denies_the_others():
    config = {"mcp": {"servers": {"graphtyn": {"url": "http://host:9210/mcp", "transport": "streamable-http",
                                               "supportsParallelToolCalls": True,
                                               "headers": {"Authorization": "Bearer shared"}},
                                  "unity": {"url": "http://host:8081/mcp"}}},
              "agents": {"entries": {"nexus": {"model": "m", "tools": {"deny": ["exec"]}}, "career": {"model": "m"}}}}

    result = per_agent.per_agent_config(config, "http://host:9210/mcp", {"nexus": "t-n", "career": "t-c"})
    servers = result["mcp"]["servers"]

    assert "graphtyn" not in servers and "unity" in servers
    assert servers["graphtyn-nexus"]["headers"] == {"Authorization": "Bearer t-n"}
    assert servers["graphtyn-nexus"]["supportsParallelToolCalls"] is True
    assert servers["graphtyn-career"]["toolFilter"] == per_agent.TOOL_FILTER
    assert result["agents"]["entries"]["nexus"]["tools"]["deny"] == ["exec", "graphtyn-career__*"]
    assert result["agents"]["entries"]["career"] == {"model": "m", "tools": {"deny": ["graphtyn-nexus__*"]}}
    assert config["mcp"]["servers"]["graphtyn"]["headers"]["Authorization"] == "Bearer shared"
    listed = per_agent.per_agent_config({"agents": {"entries": [{"id": "nexus"}]}}, "http://h/mcp", {"nexus": "t", "qa": "u"})
    assert {item["id"]: item["tools"]["deny"] for item in listed["agents"]["entries"]} == {
        "nexus": ["graphtyn-qa__*"], "qa": ["graphtyn-nexus__*"]}


def test_connecting_replaces_the_shared_token_and_revokes_it_after_writing(tmp_path):
    from graphtyn.core.openclaw_integration import configure_per_agent_mcp, registry_path

    code, brains, _agents = _stores(tmp_path)
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(json.dumps({"mcp": {"servers": {"graphtyn": {
        "url": "http://host:9210/mcp", "headers": {"Authorization": "Bearer shared"}}}},
        "agents": {"entries": {"nexus": {"model": "m"}, "career": {"model": "m"}}}}), encoding="utf-8")
    registry_path().write_text(json.dumps({"installations": [{
        "id": "openclaw-x", "kind": "local", "target": None, "config_path": str(config_path),
        "agents": [{"id": "nexus", "brain_path": str(brains / "nexus"), "memory_enabled": True}]}]}), encoding="utf-8")
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"shared": {"role": "reader", "projects": []},
                                       "admin": {"role": "admin", "projects": []}}), encoding="utf-8")

    result = configure_per_agent_mcp("openclaw-x", tokens_file)
    written = json.loads(config_path.read_text(encoding="utf-8"))
    saved = json.loads(tokens_file.read_text(encoding="utf-8"))

    assert result["ok"] and result["servers"] == {"career": "graphtyn-career", "main": "graphtyn-main",
                                                  "nexus": "graphtyn-nexus"}
    assert "shared" not in saved and "admin" in saved and result["revoked_shared_token"]
    assert set(written["mcp"]["servers"]) == {"graphtyn-career", "graphtyn-main", "graphtyn-nexus"}
    assert json.loads(open(result["backup"], encoding="utf-8").read())["mcp"]["servers"]["graphtyn"]
    assert result["projects"]["nexus"] == 2 and result["projects"]["career"] == 1


def test_a_bound_token_cannot_ask_as_another_agent(tmp_path, monkeypatch):
    from graphtyn.api import main as api_main

    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text(json.dumps({"t-n": {"role": "reader", "agent_id": "openclaw/nexus", "projects": []}}),
                           encoding="utf-8")
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS_FILE", str(tokens_file))

    assert api_main._agent_scope_denial("Bearer t-n", "openclaw/nexus") is None
    assert api_main._agent_scope_denial("Bearer t-n", "openclaw/career").status_code == 403
