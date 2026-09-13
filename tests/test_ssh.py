from pathlib import Path

import pytest

from graphtyn.core.ssh import ssh_command


def test_ssh_command_keeps_system_defaults_when_no_config_is_set(monkeypatch):
    monkeypatch.delenv("GRAPHTYN_SSH_CONFIG", raising=False)

    assert ssh_command("deploy@example.test") == [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "deploy@example.test"
    ]


def test_ssh_command_uses_explicit_config_before_default_options(tmp_path, monkeypatch):
    config = tmp_path / "client.conf"
    config.write_text("Host *\n", encoding="utf-8")
    monkeypatch.setenv("GRAPHTYN_SSH_CONFIG", str(config))

    assert ssh_command("deploy@example.test", connect_timeout=12) == [
        "ssh", "-F", str(config), "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
        "deploy@example.test"
    ]


def test_ssh_command_rejects_missing_config_path(tmp_path, monkeypatch):
    missing = tmp_path / "missing.conf"
    monkeypatch.setenv("GRAPHTYN_SSH_CONFIG", str(missing))

    with pytest.raises(FileNotFoundError, match="GRAPHTYN_SSH_CONFIG"):
        ssh_command("deploy@example.test")
