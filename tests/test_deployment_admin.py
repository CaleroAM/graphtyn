import json
from pathlib import Path
import pytest

from graphtyn.core.adapters import install_adapter, list_adapters, remove_adapter, validate_manifest
from graphtyn.core.deployment import apply_setup, detect_environment, manage_user_service, rotate_token, service_artifact
from graphtyn.core.memory_admin import backup_memory, restore_memory, verify_backup
from graphtyn.core.memory_extraction import deterministic_proposals
from graphtyn.core.shared_memory import SharedMemoryStore


def test_manifest_adapter_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    manifest = tmp_path / "adapter.json"
    manifest.write_text(json.dumps({"name": "company-agent", "format": "jsonl", "extensions": ["jsonl"]}))
    installed = install_adapter(manifest)
    assert installed["name"] == "company-agent"
    assert "company-agent" in {row["name"] for row in list_adapters()}
    assert remove_adapter("company-agent") is True
    with pytest.raises(ValueError): validate_manifest({"name": "bad agent"})


def test_setup_is_previewable_and_applies_without_source_edits(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"; project.mkdir()
    assert detect_environment(project)["project"] == str(project)
    result = apply_setup(project, agents=["openclaw", "hermes"], sources=[], create_token=True)
    assert result["ok"] and (project / "AGENTS.md").exists()
    assert Path(result["token_file"]).stat().st_mode & 0o777 == 0o600


def test_service_artifacts_have_no_machine_hardcodes(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "repo"; project.mkdir()
    systemd = service_artifact(project, kind="systemd", output=tmp_path / "graphtyn.service")
    compose = service_artifact(project, kind="compose", output=tmp_path / "compose.yml")
    assert "Restart=on-failure" in systemd.read_text()
    assert "serve --host 127.0.0.1 --port 9210 --path" in systemd.read_text()
    assert " --watch " not in systemd.read_text()
    assert 'ExecStart="' in systemd.read_text()
    assert "WantedBy=default.target" in systemd.read_text()
    assert "Environment=GRAPHTYN_WATCH_INTERVAL=10" in systemd.read_text()
    assert "GRAPHTYN_MEMORY_TOKENS_FILE" in compose.read_text()
    assert "192.168." not in systemd.read_text() + compose.read_text()
    watched = service_artifact(project, kind="systemd", output=tmp_path / "watched.service", watch=True)
    assert " --watch --path" in watched.read_text()


def test_user_service_management_uses_unprivileged_systemctl(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = []
    class Result:
        returncode = 0
        stdout = "active"
        stderr = ""
    def fake_run(command, **kwargs):
        calls.append(command)
        return Result()
    enabled = manage_user_service("enable", run=fake_run)
    assert enabled["ok"] and enabled["dashboard"] == "http://127.0.0.1:9210"
    assert calls == [["systemctl", "--user", "daemon-reload"],
                     ["systemctl", "--user", "enable", "--now", "graphtyn-dashboard.service"],
                     ["systemctl", "--user", "restart", "graphtyn-dashboard.service"]]
    assert all("sudo" not in command for command in calls)


def test_user_service_status_propagates_failure():
    class Result:
        returncode = 3
        stdout = "inactive"
        stderr = ""
    result = manage_user_service("status", run=lambda *args, **kwargs: Result())
    assert result["ok"] is False
    assert result["steps"][0]["command"][2] == "is-active"


def test_token_rotation_uses_private_file_and_scopes(tmp_path):
    target = tmp_path / "tokens.json"
    result = rotate_token(role="writer", projects=[str(tmp_path)], path=target)
    assert result["token"] in json.loads(target.read_text())
    assert target.stat().st_mode & 0o777 == 0o600


def test_backup_verify_preview_restore_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    source = tmp_path / "source"; source.mkdir()
    session = SharedMemoryStore(source).start_session("agent", "backup")
    SharedMemoryStore(source).checkpoint(session["id"], "decision", "Storage", "Use SQLite")
    archive = tmp_path / "memory.zip"
    backup_memory(source, archive)
    assert verify_backup(archive)["ok"]
    target = tmp_path / "target"; target.mkdir()
    assert restore_memory(target, archive)["dry_run"]
    restored = restore_memory(target, archive, apply=True)
    assert restored["ok"] and SharedMemoryStore(target).status()["memories"] == 1


def test_casual_conversation_is_not_promoted_to_durable_memory():
    assert deterministic_proposals([{"id": "1", "role": "assistant", "content": "Perfecto."}]) == []
    durable = deterministic_proposals([{"id": "2", "role": "assistant",
        "content": "Se implementó la migración de autenticación y todas las pruebas pasaron correctamente."}])
    assert durable and durable[0]["kind"] == "handoff"
