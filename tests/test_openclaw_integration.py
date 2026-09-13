import json
import os
import time
from pathlib import Path

import pytest

from graphtyn.core.history_import import save_source, discover_histories
from graphtyn.core.openclaw_integration import (
    _agent_entries, agent_context, configure_openclaw_mcp, connect_openclaw, discover_openclaw, publish_agent_memory,
    assert_agent_memory_enabled, paths_for_installation, resolve_agent, revoke_agent_memory,
    set_agent_memory_enabled, set_parent,
)
from graphtyn.core.shared_memory import SharedMemoryStore, _resolve_store_path
from graphtyn.core.storage import data_home


def _installation(tmp_path: Path):
    config = tmp_path / "openclaw.json"
    config.write_text(json.dumps({"meta": {"lastTouchedVersion": "2026.9.4"},
        "agents": {"entries": {
            "main": {"identity": {"name": "Evi"}},
            "career": {"identity": {"name": "Eve"}},
            "devops": {}, "design": {}, "qa": {},
        }}}), encoding="utf-8")
    for agent_id in ("main", "career", "devops", "design", "qa"):
        (tmp_path / "agents" / agent_id).mkdir(parents=True, exist_ok=True)
    return {"ok": True, "id": "openclaw-0123456789abcdef", "kind": "local",
            "target": "local", "config_path": str(config), "data_root": str(tmp_path),
            "version": "2026.9.4", "agents": _agent_entries(json.loads(config.read_text()))}


def test_agent_entries_do_not_guess_parent_from_display_names():
    agents = _agent_entries({"agents": {"entries": {
        "evi": {"identity": {"name": "Evi DevOps"}},
        "career": {"identity": {"name": "Eve"}},
    }}})
    by_id = {item["id"]: item for item in agents}
    assert by_id["evi"]["parent_id"] is None
    assert by_id["career"]["parent_id"] is None
    assert by_id["evi"]["relation_status"] == "pending"


def test_discover_openclaw_uses_only_explicit_ssh_environment(tmp_path, monkeypatch):
    import graphtyn.core.openclaw_integration as integration
    monkeypatch.setattr(integration, "configured_sources", lambda: [])
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHTYN_OPENCLAW_SSH_TARGET", "root@192.0.2.10")
    monkeypatch.setenv("GRAPHTYN_OPENCLAW_DATA_ROOT", "/srv/openclaw/data")
    monkeypatch.setattr(integration, "_read_config", lambda path, ssh_target=None: {
        "meta": {"lastTouchedVersion": "2026.9.4"},
        "agents": {"entries": {"main": {}}},
    })

    found = discover_openclaw()

    assert len(found) == 1
    assert found[0]["ok"] is True
    assert found[0]["kind"] == "ssh"
    assert found[0]["target"] == "root@192.0.2.10"
    assert found[0]["data_root"] == "/srv/openclaw/data"


def test_discover_openclaw_requires_ssh_target_and_root_together(monkeypatch):
    monkeypatch.setattr("graphtyn.core.openclaw_integration.configured_sources", lambda: [])
    monkeypatch.setenv("GRAPHTYN_OPENCLAW_SSH_TARGET", "root@192.0.2.10")
    monkeypatch.delenv("GRAPHTYN_OPENCLAW_DATA_ROOT", raising=False)
    with pytest.raises(ValueError, match="deben configurarse juntos"):
        discover_openclaw()


def test_remote_openclaw_config_uses_explicit_ssh_config(tmp_path, monkeypatch):
    import graphtyn.core.openclaw_integration as integration
    ssh_config = tmp_path / "ssh.conf"
    ssh_config.write_text("Host *\n", encoding="utf-8")
    calls = []

    class Completed:
        returncode = 0
        stdout = '{"agents":{"entries":{"main":{}}}}'
        stderr = ""

    monkeypatch.setenv("GRAPHTYN_SSH_CONFIG", str(ssh_config))
    monkeypatch.setattr(integration.subprocess, "run",
                        lambda command, **kwargs: (calls.append(command), Completed())[1])

    config = integration._read_config("/srv/openclaw/data/openclaw.json",
                                       ssh_target="root@192.0.2.10")

    assert config["agents"]["entries"]["main"] == {}
    assert calls[0][:7] == ["ssh", "-F", str(ssh_config), "-o", "BatchMode=yes",
                            "-o", "ConnectTimeout=8"]
    assert calls[0][7] == "root@192.0.2.10"
    assert calls[0][8] == "cat -- /srv/openclaw/data/openclaw.json"


def test_mcp_config_update_keeps_backup_and_does_not_return_token(tmp_path, monkeypatch):
    discovered = _installation(tmp_path)
    config_path = Path(discovered["config_path"])
    original = config_path.read_text(encoding="utf-8")
    monkeypatch.setenv("GRAPHTYN_MCP_TOKEN", "never-return-this-token")
    configured = configure_openclaw_mcp(discovered, mcp_url="https://graphtyn.test/mcp")

    assert configured["ok"] and configured["changed"]
    assert "never-return-this-token" not in json.dumps(configured)
    backup = Path(configured["backup"])
    assert backup.read_text(encoding="utf-8") == original
    current = json.loads(config_path.read_text(encoding="utf-8"))
    assert current["agents"] == json.loads(original)["agents"]
    assert current["mcp"]["servers"]["graphtyn"]["url"] == "https://graphtyn.test/mcp"
    assert current["mcp"]["servers"]["graphtyn"]["headers"]["Authorization"] == \
        "Bearer never-return-this-token"


def test_connect_keeps_roots_and_children_isolated_and_family_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    source_config = tmp_path / "history-sources.json"
    evi, eve = tmp_path / "brains" / "evi", tmp_path / "brains" / "eve"
    evi.mkdir(parents=True); eve.mkdir(parents=True)
    save_source("openclaw", str(tmp_path / "agents" / "main"), project_path=evi,
                agent_id="openclaw/main", path=source_config)
    save_source("openclaw", str(tmp_path / "agents" / "career"), project_path=eve,
                agent_id="openclaw/career", path=source_config)

    result = connect_openclaw(_installation(tmp_path), parents={"devops": "main", "design": "main"},
        independent={"career"},
        source_config=source_config, registry=tmp_path / "openclaw-installations.json")
    agents = {item["id"]: item for item in result["agents"]}

    assert agents["main"]["brain_path"] == str(evi.resolve())
    assert agents["career"]["brain_path"] == str(eve.resolve())
    assert agents["devops"]["relation_status"] == "confirmed"
    assert agents["design"]["relation_status"] == "confirmed"
    assert agents["qa"]["relation_status"] == "pending"
    assert "family_path" not in agents["qa"]
    assert agents["devops"]["brain_path"] != agents["main"]["brain_path"]
    assert agents["qa"]["brain_path"] not in {agents["main"]["brain_path"], agents["career"]["brain_path"]}
    assert agents["devops"]["family_path"] == agents["main"]["family_path"]
    assert agents["career"]["family_path"] != agents["main"]["family_path"]
    assert agents["devops"]["relation_evidence"] == "user-confirmed"

    registered = json.loads((tmp_path / "graphtyn-home" / "registered_projects.json").read_text())
    owners = {row["path"]: row.get("agent_ids") for row in registered}
    assert owners[agents["devops"]["brain_path"]] == ["openclaw/devops"]
    names = {row["path"]: row.get("name") for row in registered}
    assert names[agents["main"]["brain_path"]] == "Evi"
    assert names[agents["main"]["family_path"]] == "Familia · Evi"
    assert set(owners[agents["main"]["family_path"]]) == {
        "openclaw/main", "openclaw/devops", "openclaw/design"}
    registered_agents = json.loads((tmp_path / "graphtyn-home" / "registered_agents.json").read_text())
    canonical_agents = {item["id"]: item for item in registered_agents["agents"]}
    assert canonical_agents["openclaw/main"]["name"] == "Evi"
    assert canonical_agents["openclaw/career"]["name"] == "Eve"
    assert registered_agents["openclaw_installations"][result["id"]]["openclaw/main"] == \
        agents["main"]["brain_path"]

    baseline = next(row["capture_from"] for row in json.loads(source_config.read_text())["sources"]
                    if row["source"].endswith("/agents/devops"))
    reconnected = connect_openclaw(_installation(tmp_path), independent={"career"},
        source_config=source_config, registry=tmp_path / "openclaw-installations.json")
    reconnected_agents = {item["id"]: item for item in reconnected["agents"]}
    assert reconnected_agents["devops"]["relation_status"] == "confirmed"
    assert reconnected_agents["devops"]["parent_id"] == "main"
    assert next(row["capture_from"] for row in json.loads(source_config.read_text())["sources"]
                if row["source"].endswith("/agents/devops")) == baseline


def test_agents_do_not_reuse_a_legacy_brain_shared_by_multiple_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    source_config = tmp_path / "history-sources.json"
    legacy = tmp_path / "brains" / "legacy-evi"
    legacy.mkdir(parents=True)
    for agent_id in ("main", "qa"):
        save_source("openclaw", str(tmp_path / "agents" / agent_id),
                    project_path=legacy, agent_id=f"openclaw/{agent_id}",
                    path=source_config)

    result = connect_openclaw(_installation(tmp_path), source_config=source_config,
        registry=tmp_path / "openclaw-installations.json")
    agents = {item["id"]: item for item in result["agents"]}

    assert agents["main"]["brain_path"] != str(legacy.resolve())
    assert agents["qa"]["brain_path"] != str(legacy.resolve())
    assert agents["main"]["brain_path"] != agents["qa"]["brain_path"]
    assert agents["qa"]["relation_status"] == "pending"


def test_connect_uses_the_same_central_store_as_its_watcher(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "user-home"))
    monkeypatch.delenv("GRAPHTYN_HOME", raising=False)
    source_config = tmp_path / "history-sources.json"
    result = connect_openclaw(_installation(tmp_path), source_config=source_config,
        registry=tmp_path / "openclaw-installations.json")
    brain = Path(next(item for item in result["agents"] if item["id"] == "main")["brain_path"])

    assert os.environ["GRAPHTYN_HOME"] == str(Path.home() / ".graphtyn")
    assert _resolve_store_path(brain, create=False).is_file()
    assert not (brain / ".graphtyn" / "memory-v2.db").exists()


def test_memory_policy_is_per_installation_persists_and_removes_only_its_source(tmp_path, monkeypatch):
    from graphtyn.core.history_import import import_histories

    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    source_config = tmp_path / "history-sources.json"
    registry = data_home() / "openclaw-installations.json"
    first = connect_openclaw(_installation(tmp_path), source_config=source_config, registry=registry)
    first_agents = {item["id"]: item for item in first["agents"]}
    assert first_agents["main"]["memory_enabled"] is True

    disabled = set_agent_memory_enabled(first["id"], "main", False,
        reason="default system agent; keep its brain empty", registry=registry,
        source_config=source_config)

    assert disabled["ok"] and disabled["changed"] and not disabled["memory_enabled"]
    current = json.loads(registry.read_text())["installations"][0]
    assert next(row for row in current["agents"] if row["id"] == "main")["memory_enabled"] is False
    assert any(event["agent_id"] == "openclaw/main" and not event["memory_enabled"]
               for event in current["memory_policy_events"])
    sources = json.loads(source_config.read_text())["sources"]
    assert not any(row.get("agent_id") == "openclaw/main" for row in sources)
    assert any(row.get("agent_id") == "openclaw/career" for row in sources)
    assert first_agents["main"]["brain_path"] not in paths_for_installation(first["id"], registry=registry)
    with pytest.raises(PermissionError, match="memoria de openclaw/main está desactivada"):
        assert_agent_memory_enabled(first_agents["main"]["brain_path"], "dashboard", registry=registry)
    from graphtyn.mcp_server import _validate_memory_owner
    with pytest.raises(PermissionError, match="memoria de openclaw/main está desactivada"):
        _validate_memory_owner(Path(first_agents["main"]["brain_path"]), "openclaw/main")
    with pytest.raises(PermissionError, match="memoria de openclaw/main está desactivada"):
        publish_agent_memory(first["id"], "main", "any-memory-id", registry=registry)
    blocked_import = import_histories(first_agents["main"]["brain_path"], [{
        "provider": "openclaw", "agent_id": "openclaw/main", "external_session_id": "should-not-save",
        "workspace": None, "explicit_project_selection": True,
        "messages": [{"role": "user", "content": "Do not persist this transcript."}],
    }], consent=True, agent_ids=["openclaw/main"])
    assert blocked_import["selected"] == 0
    assert blocked_import["excluded"][0]["reason"].startswith("la memoria de openclaw/main está desactivada")
    from graphtyn.core.history_stream import ingest_jsonl
    stream_source = tmp_path / "main-history.jsonl"
    stream_source.write_text('{"id":"m1","role":"user","content":"blocked"}\n')
    with pytest.raises(PermissionError, match="memoria de openclaw/main está desactivada"):
        ingest_jsonl(SharedMemoryStore(Path(first_agents["main"]["brain_path"])), stream_source,
            provider="openclaw", external_session_id="stream-should-not-save",
            agent_id="openclaw/main", consent=True, explicit_project_selection=True)

    reconnected = connect_openclaw(_installation(tmp_path), source_config=source_config, registry=registry)
    assert next(row for row in reconnected["agents"] if row["id"] == "main")["memory_enabled"] is False
    assert not any(row.get("agent_id") == "openclaw/main" for row in json.loads(source_config.read_text())["sources"])

    second_discovery = _installation(tmp_path)
    second_discovery["id"] = "openclaw-fedcba9876543210"
    second = connect_openclaw(second_discovery, source_config=source_config, registry=registry)
    second_main = next(row for row in second["agents"] if row["id"] == "main")
    assert second_main["memory_enabled"] is True
    assert second_main["brain_path"] != first_agents["main"]["brain_path"]
    assert_agent_memory_enabled(second_main["brain_path"], "openclaw/main", registry=registry)
    from graphtyn.api.main import _require_role
    _, denied = _require_role(None, "writer", first_agents["main"]["brain_path"])
    _, allowed = _require_role(None, "writer", second_main["brain_path"])
    assert denied is not None and denied.status_code == 403
    assert allowed is None


def test_private_child_memory_requires_explicit_family_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    installation = connect_openclaw(_installation(tmp_path), parents={"devops": "main"},
        source_config=tmp_path / "history-sources.json",
        registry=tmp_path / "openclaw-installations.json")
    child = resolve_agent(installation["id"], "devops", registry=tmp_path / "openclaw-installations.json")
    store = SharedMemoryStore(Path(child["brain_path"]))
    session = store.start_session("openclaw/devops", "Tune the Redis connection pool",
                                  client="openclaw", capture_enabled=True)
    memory = store.checkpoint(session["id"], "decision", "Redis pool limit",
        "Set the Redis connection pool limit to 24 after load testing.", status="observed")

    private_context = agent_context(installation["id"], "main", "Redis connection pool",
        registry=tmp_path / "openclaw-installations.json")
    assert not any("Redis pool limit" in item.get("title", "")
                   for item in private_context["memories"])

    published = publish_agent_memory(installation["id"], "devops", memory["id"],
        registry=tmp_path / "openclaw-installations.json")
    published_again = publish_agent_memory(installation["id"], "devops", memory["id"],
        registry=tmp_path / "openclaw-installations.json")
    assert published["shared_memory_id"] == published_again["shared_memory_id"]
    shared_context = agent_context(installation["id"], "main", "Redis connection pool",
        registry=tmp_path / "openclaw-installations.json")
    assert any(item.get("memory_origin") == "family_shared" and
               item.get("title") == "Redis pool limit" for item in shared_context["memories"])

    revoked = revoke_agent_memory(installation["id"], "devops", published["shared_memory_id"],
        registry=tmp_path / "openclaw-installations.json")
    assert revoked["ok"]
    after_revoke = agent_context(installation["id"], "main", "Redis connection pool",
        registry=tmp_path / "openclaw-installations.json")
    assert not any(item.get("title") == "Redis pool limit" for item in after_revoke["memories"])


def test_set_parent_rejects_cycles_and_recomputes_family_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    registry = tmp_path / "openclaw-installations.json"
    installation = connect_openclaw(_installation(tmp_path), parents={"devops": "main"},
        source_config=tmp_path / "history-sources.json", registry=registry)
    with pytest.raises(ValueError, match="ciclos"):
        set_parent(installation["id"], "main", "devops", confirm=True, registry=registry)
    result = set_parent(installation["id"], "design", "devops", confirm=True, registry=registry)
    assert result["parent_id"] == "devops"
    assert result["family_id"] == resolve_agent(installation["id"], "devops", registry=registry)["family_id"]
    saved = json.loads(registry.read_text())
    events = saved["installations"][0]["relationship_events"]
    assert any(event["agent_id"] == "openclaw/design" and
               event["previous_parent_id"] is None and event["parent_id"] == "devops" and
               event["evidence"] == "user-confirmed" for event in events)


def test_different_installations_get_separate_child_and_family_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    source_config = tmp_path / "history-sources.json"
    root_brain = tmp_path / "brains" / "evi"
    root_brain.mkdir(parents=True)
    save_source("openclaw", str(tmp_path / "agents" / "main"), project_path=root_brain,
                agent_id="openclaw/main", path=source_config)
    first = connect_openclaw(_installation(tmp_path), parents={"devops": "main"},
        source_config=source_config, registry=tmp_path / "registry.json")
    second_description = _installation(tmp_path)
    second_description["id"] = "openclaw-fedcba9876543210"
    second = connect_openclaw(second_description, parents={"devops": "main"},
        source_config=source_config, registry=tmp_path / "registry.json")
    first_agents = {item["id"]: item for item in first["agents"]}
    second_agents = {item["id"]: item for item in second["agents"]}

    assert first_agents["main"]["brain_path"] == second_agents["main"]["brain_path"]
    assert first_agents["devops"]["brain_path"] != second_agents["devops"]["brain_path"]
    assert first_agents["main"]["family_path"] != second_agents["main"]["family_path"]


def test_capture_baseline_excludes_old_sessions_and_keeps_new_sessions(tmp_path, monkeypatch):
    source = tmp_path / "openclaw"
    agent_dir = source / "agents" / "main" / "sessions"
    agent_dir.mkdir(parents=True)
    old = agent_dir / "old.jsonl"
    old.write_text(json.dumps({"sessionId": "old", "role": "user", "content": "old chat"}) + "\n")
    baseline = time.time() - 10
    os.utime(old, (baseline - 10, baseline - 10))
    config = tmp_path / "history-sources.json"
    brain = tmp_path / "brain"
    brain.mkdir()
    save_source("openclaw", str(source), project_path=brain, agent_id="openclaw/main", capture_from=baseline,
                path=config)
    monkeypatch.setattr("graphtyn.core.history_import.sources_config_file", lambda: config)

    preview = discover_histories("openclaw", project_path=brain, agent_id="openclaw/main")
    assert preview["count"] == 0
    assert any(row.get("reason") == "before_capture_baseline" for row in preview["excluded"])

    fresh = agent_dir / "fresh.jsonl"
    fresh.write_text(json.dumps({"sessionId": "fresh", "role": "user", "content": "new chat"}) + "\n")
    os.utime(fresh, (baseline + 10, baseline + 10))
    preview = discover_histories("openclaw", project_path=brain, agent_id="openclaw/main")
    assert preview["count"] == 1
    assert preview["sessions"][0]["external_session_id"] == "fresh"
