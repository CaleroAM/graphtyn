import json
import sqlite3
import time
from pathlib import Path
import pytest

from graphtyn.core.history_import import (
    ProjectIdentityRegistry, discover_histories, import_histories, parse_history_file,
    parse_history_database, configured_sources, save_source, _materialize_source,
    import_history_archive,
)
from graphtyn.core.memory_jobs import MemoryJobManager
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.api import main as api_main


def _openclaw_history(root: Path) -> Path:
    path = root / "agents" / "agent-beta" / "sessions" / "old-session.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "sessionId": "before-graphtyn-1", "workspaceDir": str(root / "UnityCommerceDemo"),
        "messages": [
            {"role": "user", "content": "Trabajamos en el proyecto UnityCommerceDemo"},
            {"role": "assistant", "content": "Se corrigió GameManager y las pruebas pasaron."},
        ],
    }) + "\n", encoding="utf-8")
    return path


def test_openclaw_history_discovery_preserves_attribution(tmp_path):
    source = tmp_path / "openclaw"
    path = _openclaw_history(source)

    sessions = parse_history_file(path, "openclaw")
    discovered = discover_histories("openclaw", [str(source)])

    assert len(sessions) == 1
    assert sessions[0].agent_id == "openclaw/agent-beta"
    assert sessions[0].external_session_id == "before-graphtyn-1"
    assert sessions[0].workspace.endswith("UnityCommerceDemo")
    assert discovered["count"] == 1
    assert discovered["sessions"][0]["fingerprint"]


def test_invalid_ssh_history_source_is_rejected_without_execution():
    result = discover_histories("openclaw", ["ssh://bad host/tmp/history"])
    assert result["count"] == 0
    assert result["errors"] and "SSH inválido" in result["errors"][0]["error"]


def test_history_sources_are_deployment_configuration(tmp_path):
    config = tmp_path / "history-sources.json"
    save_source("openclaw", "docker://agent/home/node/.openclaw/agents", path=config)
    save_source("custom-agent", "ssh://ops@example.test/var/lib/agent", path=config)

    rows = configured_sources(config)
    assert {row["provider"] for row in rows} == {"openclaw", "custom-agent"}
    assert config.stat().st_mode & 0o777 == 0o600


def test_docker_history_source_uses_read_only_archive(tmp_path, monkeypatch):
    calls = []
    class Result:
        returncode = 1
        stderr = b"not running"
    def fake_run(command, **kwargs):
        calls.append(command)
        return Result()
    monkeypatch.setattr("graphtyn.core.history_import.subprocess.run", fake_run)

    with pytest.raises(OSError):
        _materialize_source("docker://my-agent/home/node/.openclaw/agents")
    assert calls[0][:4] == ["docker", "exec", "my-agent", "tar"]
    assert not any(part in {"rm", "mv", "cp"} for part in calls[0])


def test_remote_docker_source_does_not_assume_host_or_container(monkeypatch):
    calls = []
    class Result:
        returncode = 1
        stderr = b"unavailable"
    monkeypatch.setattr("graphtyn.core.history_import.subprocess.run",
                        lambda command, **kwargs: (calls.append(command), Result())[1])
    with pytest.raises(OSError):
        _materialize_source("ssh+docker://deploy@example.test:runtime-7/var/lib/agent/history")
    assert calls[0][:7] == ["ssh", "-o", "BatchMode=yes", "deploy@example.test",
                            "docker", "exec", "runtime-7"]


def test_no_persona_or_machine_identity_is_hardcoded_in_runtime():
    root = Path(__file__).parents[1] / "graphtyn"
    runtime = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                        for path in root.rglob("*.py"))
    for forbidden in ("openclaw/agent-alpha", "openclaw/agent-beta", "198.51.100.27"):
        assert forbidden not in runtime


def test_codex_nested_payload_and_sqlite_histories(tmp_path):
    codex = tmp_path / "codex.jsonl"
    codex.write_text("\n".join(json.dumps(item) for item in [
        {"session_id": "codex-old", "payload": {"role": "user", "content": [{"text": "Proyecto CRM"}]}},
        {"session_id": "codex-old", "payload": {"role": "assistant", "content": [{"text": "Se añadió facturación"}]}},
    ]), encoding="utf-8")
    db = tmp_path / "hermes.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE messages(session_id TEXT, role TEXT, content TEXT, workspace TEXT)")
    conn.executemany("INSERT INTO messages VALUES(?,?,?,?)", [
        ("hermes-old", "user", "Proyecto ERP", "/work/erp"),
        ("hermes-old", "assistant", "Se corrigió inventario", "/work/erp")])
    conn.commit(); conn.close()

    codex_sessions = parse_history_file(codex, "codex")
    hermes_sessions = parse_history_database(db, "hermes")

    assert [m["content"] for m in codex_sessions[0].messages] == ["Proyecto CRM", "Se añadió facturación"]
    assert hermes_sessions[0].external_session_id == "hermes-old"
    assert hermes_sessions[0].workspace == "/work/erp"


def test_historical_import_is_idempotent_and_searchable(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "UnityCommerceDemo"
    project.mkdir()
    source = tmp_path / "openclaw"
    _openclaw_history(source)
    sessions = discover_histories("openclaw", [str(source)])["sessions"]

    first = import_histories(project, sessions, consent=True, provider="deterministic")
    second = import_histories(project, sessions, consent=True, provider="deterministic")
    found = SharedMemoryStore(project).search("GameManager pruebas", requester_agent="codex")

    assert first["ok"] and len(first["imported"]) == 1
    assert second["imported"] == [] and len(second["reused"]) == 1
    assert found and found[0]["agent_id"] == "openclaw/agent-beta"


def test_project_identity_recognizes_renamed_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "graphtyn"
    project.mkdir()
    registry = ProjectIdentityRegistry()
    saved = registry.register(project, ["aether-graph"])

    assert registry.resolve("conversation in aether-graph")["id"] == saved["id"]
    assert registry.resolve(str(project))["canonical_name"] == "graphtyn"


def test_import_does_not_mix_unknown_project_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "graphtyn"; project.mkdir()
    session = {"provider": "openclaw", "agent_id": "openclaw/agent-beta", "external_session_id": "other",
               "task": "Other project", "workspace": "/work/UnityCommerceDemo", "source": "history.jsonl",
               "messages": [{"role": "user", "content": "Change GameManager"}], "fingerprint": "other1"}

    result = import_histories(project, [session], consent=True, dry_run=True)

    assert result["selected"] == 0
    assert result["ambiguous"][0]["suggested_project"] == "UnityCommerceDemo"


def test_explicit_archive_import_keeps_all_projects_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    archive = tmp_path / "historical-agent-memory"; archive.mkdir()
    sessions = [{"provider": "custom", "agent_id": "custom/alfa", "external_session_id": "one",
        "task": "Legacy", "workspace": "/srv/another-project", "source": "legacy.jsonl",
        "messages": [{"role": "user", "content": "Remember billing migration"}], "fingerprint": "archive1"}]

    first = import_history_archive(archive, sessions, consent=True)
    second = import_history_archive(archive, sessions, consent=True)
    exported = SharedMemoryStore(archive).export_snapshot(include_messages=True)

    assert len(first["imported"]) == 1 and first["ambiguous"] == []
    assert len(second["reused"]) == 1
    assert exported["messages"][0]["metadata"]["original_workspace"] == "/srv/another-project"


def test_historical_session_can_grow_after_it_was_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    archive = tmp_path / "archive"; archive.mkdir()
    base = {"provider": "agent", "agent_id": "agent/one", "external_session_id": "same",
            "task": "Growing", "source": "one.jsonl", "workspace": None}
    first = {**base, "fingerprint": "v1", "messages": [{"role": "user", "content": "first"}]}
    grown = {**base, "fingerprint": "v2", "messages": [{"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"}]}

    import_history_archive(archive, [first], consent=True)
    result = import_history_archive(archive, [grown], consent=True)
    exported = SharedMemoryStore(archive).export_snapshot(include_messages=True)

    assert len(result["imported"]) == 1 and result["errors"] == []
    assert [(m["role"], m["content"]) for m in exported["messages"]] == [
        ("user", "first"), ("assistant", "second")]


def test_memory_job_persists_progress_and_result(tmp_path):
    manager = MemoryJobManager(tmp_path / "jobs")
    job = manager.create("discover", {})
    manager.run(job["id"], lambda update: (update(50, "half"), {"sessions": 3})[1])
    for _ in range(100):
        current = manager.get(job["id"])
        if current["status"] == "completed": break
        time.sleep(.01)

    assert current["progress"] == 100
    assert current["result"] == {"sessions": 3}


def test_v1_role_auth_and_discovery_job(tmp_path, monkeypatch):
    source = tmp_path / "openclaw"
    _openclaw_history(source)
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({"read": "reader", "admin": "admin"}))
    monkeypatch.setattr(api_main, "memory_jobs", MemoryJobManager(tmp_path / "api-jobs"))

    denied = api_main.import_discover({"provider": "openclaw", "sources": [str(source)]}, "Bearer read")
    started = api_main.import_discover({"provider": "openclaw", "sources": [str(source)]}, "Bearer admin")
    assert denied.status_code == 403
    job_id = started["job"]["id"]
    for _ in range(100):
        job = api_main.memory_jobs.get(job_id)
        if job["status"] == "completed": break
        time.sleep(.01)
    assert job["result"]["count"] == 1


def test_v1_source_catalog_combines_builtins_and_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    save_source("company-agent", str(tmp_path / "history"))
    result = api_main.import_sources(None)
    assert "company-agent" in result["providers"]
    assert any(row["provider"] == "company-agent" for row in result["sources"])


def test_v1_token_project_acl_and_rate_limit(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"; allowed.mkdir()
    blocked = tmp_path / "blocked"; blocked.mkdir()
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({
        "scoped": {"role": "writer", "projects": [str(allowed)]}}))
    monkeypatch.setenv("GRAPHTYN_MEMORY_RATE_LIMIT", "1")
    api_main._RATE_EVENTS.clear()

    role, first = api_main._require_role("Bearer scoped", "reader", str(allowed))
    _, blocked_response = api_main._require_role("Bearer scoped", "reader", str(blocked))
    _, limited = api_main._require_role("Bearer scoped", "reader", str(allowed))

    assert role == "writer" and first is None
    assert blocked_response.status_code == 403
    assert limited.status_code == 429


def test_export_and_retention_protect_verified_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"; project.mkdir()
    store = SharedMemoryStore(project)
    session = store.start_session("codex", "governance", capture_enabled=True)
    proposed = store.checkpoint(session["id"], "fact", "Old proposal", "temporary", status="proposed")
    verified = store.checkpoint(session["id"], "fact", "Verified", "durable", status="verified")
    with store._connect() as conn:
        conn.execute("UPDATE memories SET updated_at=0 WHERE id IN (?,?)", (proposed["id"], verified["id"]))

    preview = store.apply_retention(1)
    applied = store.apply_retention(1, dry_run=False)
    exported = store.export_snapshot(include_messages=False)

    assert proposed["id"] in preview["memory_ids"] and verified["id"] not in preview["memory_ids"]
    assert applied["affected"] == 1
    assert [m["id"] for m in exported["memories"]] == [verified["id"]]
    assert exported["messages"] == []


def test_federated_v1_context_lists_preintegration_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("GRAPHTYN_MEMORY_TOKENS", raising=False)
    api_main._RATE_EVENTS.clear()
    for name, agent in (("UnityCommerceDemo", "antigravity"), ("graphtyn", "openclaw/agent-beta")):
        project = tmp_path / name; project.mkdir()
        ProjectIdentityRegistry().register(project)
        store = SharedMemoryStore(project)
        session = store.start_session(agent, f"Trabajo histórico en {name}")
        store.checkpoint(session["id"], "outcome", f"Proyecto histórico {name}",
                         f"Antes de Graphtyn se trabajó en {name}", status="observed",
                         metadata={"capture_mode": "historical_import", "occurred_at": 1})

    result = api_main.memory_v1_context({"query": "¿Qué proyectos teníamos antes de Graphtyn?",
        "requester_agent": "openclaw", "scope": {"projects": ["*"]}, "token_budget": 1200}, None)

    assert len(result["stores_consulted"]) == 2
    assert {Path(item["store"]).name for item in result["memories"]} == {"UnityCommerceDemo", "graphtyn"}
    assert {item["canonical_name"] for item in result["projects"]} == {"UnityCommerceDemo", "graphtyn"}


def test_optional_memory_encryption_hides_plaintext_at_rest(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("GRAPHTYN_MEMORY_ENCRYPTION_KEY", "test-only-secret")
    project = tmp_path / "encrypted"; project.mkdir()
    store = SharedMemoryStore(project)
    session = store.start_session("codex", "Encrypted", capture_enabled=True)
    message = store.append_message(session["id"], "user", "private roadmap phrase")
    memory = store.checkpoint(session["id"], "decision", "Private decision", "private implementation phrase")
    raw = store.db_path.read_bytes()

    assert b"private roadmap phrase" not in raw
    assert b"private implementation phrase" not in raw
    assert store.get_message(message["id"], "codex")["content"] == "private roadmap phrase"
    assert store.get(memory["id"], "codex")["content"] == "private implementation phrase"
