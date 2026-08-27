"""Adversarial leak and boundary tests. These are intentionally strict."""
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from graphtyn.api import main as api_main
from graphtyn.core.adapters import validate_manifest
from graphtyn.core.history_import import HistoricalSession, _materialize_source, parse_history_file, save_source
from graphtyn.core.memory_admin import backup_memory, restore_memory, verify_backup
from graphtyn.core.shared_memory import SharedMemoryStore


SECRETS = [
    "ghp_abcdefghijklmnopqrstuvwxyz123456",
    "sk-abcdefghijklmnopqrstuvwxyz123456",
    "AKIAABCDEFGHIJKLMNOP",
    "eyJabcdefghijk.abcdefghijk.abcdefghijk",
    "super-private-bearer-value",
]


def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"; project.mkdir()
    return project, SharedMemoryStore(project)


def test_all_common_secret_shapes_are_absent_from_db_and_export(tmp_path, monkeypatch):
    project, store = _store(tmp_path, monkeypatch)
    session = store.start_session("red-team", "Leak audit", capture_enabled=True)
    content = (f"Authorization: Bearer {SECRETS[4]}\napi_key={SECRETS[1]}\n"
               f"aws={SECRETS[2]} jwt={SECRETS[3]} github={SECRETS[0]}\n"
               "endpoint=https://admin:database-password@example.test/private")
    store.append_message(session["id"], "user", content, metadata={
        "nested": {"authorization": f"Bearer {SECRETS[4]}", "items": [{"password": "metadata-password"}]}})
    snapshot = store.export_snapshot(include_messages=True)
    serialized = json.dumps(snapshot, ensure_ascii=False)
    raw_db = store.db_path.read_bytes()
    for secret in [*SECRETS, "database-password", "metadata-password"]:
        assert secret not in serialized
        assert secret.encode() not in raw_db
    assert serialized.count("[REDACTED]") >= 5


def test_export_removes_workspace_home_temp_and_vectors(tmp_path, monkeypatch):
    project, store = _store(tmp_path, monkeypatch)
    session = store.start_session("agent", "Portable", capture_enabled=True)
    store.append_message(session["id"], "assistant", "Implemented portable export and tests passed",
        metadata={"historical_source": str(project / "history.jsonl"), "temporary": "/tmp/graphtyn-secret/source.json"})
    store.compact_session(session["id"], "deterministic")
    payload = store.export_snapshot(include_messages=True)
    serialized = json.dumps(payload)
    assert str(project) not in serialized and str(Path.home()) not in serialized
    assert "/tmp/graphtyn-secret" not in serialized
    assert "vector_json" not in serialized and "memory_embeddings" not in serialized
    assert payload["workspace"] == project.name and len(payload["workspace_id"]) == 16


def test_system_hidden_roles_are_never_imported(tmp_path):
    history = tmp_path / "conversation.json"
    history.write_text(json.dumps({"session_id": "one", "messages": [
        {"role": "system", "content": "hidden-policy-do-not-export"},
        {"role": "developer", "content": "hidden-developer-policy"},
        {"role": "user", "content": "visible question"},
        {"role": "assistant", "content": "visible answer"}]}), encoding="utf-8")
    sessions = parse_history_file(history, "custom")
    text = json.dumps(sessions[0].messages)
    assert "hidden-policy" not in text and "hidden-developer" not in text
    assert [row["role"] for row in sessions[0].messages] == ["user", "assistant"]


def test_fingerprint_ignores_temporary_source_metadata():
    common = dict(provider="agent", agent_id="agent/one", external_session_id="s1", task="task", source="source")
    one = HistoricalSession(**common, messages=[{"role": "user", "content": "same", "metadata": {"historical_source": "/tmp/a"}}])
    two = HistoricalSession(**common, messages=[{"role": "user", "content": "same", "metadata": {"historical_source": "/tmp/b"}}])
    assert one.fingerprint == two.fingerprint


def test_remote_stderr_is_redacted_before_error_surface(monkeypatch):
    class Result:
        returncode = 1
        stderr = b"Authorization: Bearer remote-super-secret-token password=remote-password"
    monkeypatch.setattr("graphtyn.core.history_import.subprocess.run", lambda *args, **kwargs: Result())
    with pytest.raises(OSError) as caught:
        _materialize_source("ssh://ops@example.test/var/lib/history")
    error = str(caught.value)
    assert "remote-super-secret-token" not in error and "remote-password" not in error
    assert "[REDACTED]" in error


def test_source_catalog_and_alias_admin_endpoints_reject_reader(tmp_path, monkeypatch):
    project = tmp_path / "project"; project.mkdir()
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({"reader-secret": "reader"}))
    denied_sources = api_main.import_sources("Bearer reader-secret")
    denied_alias = api_main.memory_alias_save({"path": str(project), "alias": "a", "canonical": "b"}, "Bearer reader-secret")
    assert denied_sources.status_code == 403 and denied_alias.status_code == 403
    assert "reader-secret" not in denied_sources.body.decode() + denied_alias.body.decode()


def test_token_cli_masks_secret_by_default(tmp_path, monkeypatch):
    target = tmp_path / "tokens.json"
    command = [sys.executable, "-m", "graphtyn.cli", "token", "rotate",
               "--role", "writer", "--file", str(target)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    stored_token = next(iter(json.loads(target.read_text())))
    assert stored_token not in result.stdout
    assert "[stored; use --show-token only in a private terminal]" in result.stdout


def test_backup_manifest_is_portable_and_archive_shape_is_strict(tmp_path, monkeypatch):
    project, store = _store(tmp_path, monkeypatch)
    store.start_session("agent", "backup")
    backup = tmp_path / "memory.zip"
    result = backup_memory(project, backup)
    check = verify_backup(backup)
    assert str(project) not in json.dumps(check) and result["workspace"] == project.name
    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(backup) as source, zipfile.ZipFile(malicious, "w") as target:
        for name in source.namelist(): target.writestr(name, source.read(name))
        target.writestr("../escape", "no")
    with pytest.raises(ValueError, match="inesperado"):
        restore_memory(project, malicious, apply=True)
    assert not (tmp_path / "escape").exists()


def test_adapter_and_source_configuration_reject_injection(tmp_path):
    with pytest.raises(ValueError): validate_manifest({"name": "../../agent", "format": "json"})
    with pytest.raises(ValueError): save_source("bad provider", "/tmp/history", path=tmp_path / "sources.json")
    with pytest.raises(ValueError): save_source("valid-agent", "bad\x00path", path=tmp_path / "sources.json")
    with pytest.raises(ValueError, match="contraseñas"):
        save_source("valid-agent", "ssh://user:password@example.test/history", path=tmp_path / "sources.json")


def test_task_status_reason_and_source_label_are_sanitized_at_rest(tmp_path, monkeypatch):
    project, store = _store(tmp_path, monkeypatch)
    session = store.start_session("agent", "Audit token=task-super-secret")
    memory = store.checkpoint(session["id"], "fact", "Safe", "Tests passed", status="observed")
    store.set_status(memory["id"], "contested", requester_agent="agent",
                     reason="Authorization: Bearer status-super-secret-token")
    config = tmp_path / "sources.json"
    save_source("valid-agent", "/tmp/history", label="password=label-super-secret", path=config)
    raw = store.db_path.read_bytes() + config.read_bytes()
    for secret in (b"task-super-secret", b"status-super-secret-token", b"label-super-secret"):
        assert secret not in raw


def test_runtime_contains_no_private_machine_or_persona_defaults():
    root = Path(__file__).parents[1]
    runtime = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                        for path in (root / "graphtyn").rglob("*.py"))
    for forbidden in ("192.168.122.", "/home/developer", "openclaw/agent-alpha", "openclaw/agent-beta", "UnityCommerceDemo"):
        assert forbidden not in runtime
