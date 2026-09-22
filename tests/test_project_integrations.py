import json
import shutil
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

from graphtyn.core.project_integrations import (
    configure_project_integrations,
    ensure_project_identity,
    project_integration_status,
    remove_project_integrations,
    verify_project_mcp,
)
from graphtyn.core.history_import import ProjectIdentityRegistry
from graphtyn.core.agent_installer import install_agent


def test_project_identity_survives_folder_rename(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    first = tmp_path / "E50E"
    first.mkdir()

    before = ensure_project_identity(first)
    moved = tmp_path / "E50E-new-name"
    first.rename(moved)
    after = ensure_project_identity(moved)

    assert before["id"] == after["id"]
    assert str(moved) in after["paths"]
    assert ".graphtyn/" in (moved / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert json.loads((moved / ".graphtyn/graphtyn.json").read_text())["project_id"] == before["id"]


def test_project_mcp_configs_are_scoped_idempotent_and_preserve_other_servers(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    root = tmp_path / "TourMuseosPuebla"
    root.mkdir()
    (root / "opencode.json").write_text(json.dumps({
        "mcp": {"other": {"type": "local", "command": ["other-mcp"], "enabled": True}}
    }))
    (root / ".mcp.json").write_text(json.dumps({
        "mcpServers": {"other": {"command": "other-mcp", "args": []}}
    }))
    platforms = ["codex", "opencode", "claude", "cursor", "antigravity", "openclaw"]

    configured = configure_project_integrations(root, platforms, tool_profile="full")
    config_files = [Path(value) for value in configured["files"]]
    first_contents = {path: path.read_text(encoding="utf-8") for path in config_files}
    alias = configured["mcp_server"]
    expected_args = ["mcp", "--tool-profile", "full", "--path", "."]

    codex = tomllib.loads((root / ".codex/config.toml").read_text(encoding="utf-8"))
    assert codex["mcp_servers"][alias]["command"] == "graphtyn"
    assert codex["mcp_servers"][alias]["args"] == expected_args
    assert codex["mcp_servers"][alias]["cwd"] == str(root.resolve())
    opencode = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
    assert opencode["mcp"]["other"]["command"] == ["other-mcp"]
    assert opencode["mcp"][alias]["command"] == ["graphtyn", *expected_args]
    claude = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert claude["mcpServers"]["other"]["command"] == "other-mcp"
    assert claude["mcpServers"][alias]["args"] == expected_args
    cursor = json.loads((root / ".cursor/mcp.json").read_text(encoding="utf-8"))
    assert cursor["mcpServers"][alias]["args"] == expected_args
    antigravity = json.loads((root / ".agents/mcp_config.json").read_text())
    assert antigravity["mcpServers"][alias]["args"] == expected_args
    assert next(item for item in configured["clients"] if item["platform"] == "openclaw")["status"] == "dynamic_scope"

    configure_project_integrations(root, platforms, tool_profile="full")
    assert {path: path.read_text(encoding="utf-8") for path in config_files} == first_contents


def test_agent_install_status_and_remove_only_touch_managed_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    root = tmp_path / "sample-project"
    root.mkdir()
    cursor_config = root / ".cursor/mcp.json"
    cursor_config.parent.mkdir(parents=True)
    cursor_config.write_text(json.dumps({"mcpServers": {"user-server": {
        "command": "user-mcp", "args": []
    }}}))

    install_agent(root, ["codex", "cursor"], tool_profile="memory")
    status = project_integration_status(root)
    assert status["project_id"]
    assert status["mcp_server"].startswith("graphtyn_sample_project_")
    assert status["runtime"]["binary_scope"] == "global"
    assert status["runtime"]["project_configuration_scope"] == "project"
    assert status["runtime"]["project_configuration_required"] is True
    assert {item["platform"] for item in status["clients"] if item["status"] == "configured"} == {"codex", "cursor"}

    removed = remove_project_integrations(root, ["codex", "cursor"])
    assert removed["removed"] == ["codex", "cursor"]
    assert json.loads(cursor_config.read_text())["mcpServers"] == {"user-server": {
        "command": "user-mcp", "args": []
    }}
    codex_config = root / ".codex/config.toml"
    assert "GRAPHTYN MCP PROJECT" not in codex_config.read_text(encoding="utf-8")
    assert all(item["status"] == "removed" for item in project_integration_status(root)["clients"])


def test_invalid_client_json_is_preserved_and_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    root = tmp_path / "invalid-json-project"
    root.mkdir()
    config = root / "opencode.json"
    original = '{ // comments require manual merge\n'
    config.write_text(original, encoding="utf-8")

    result = configure_project_integrations(root, ["opencode"])

    assert config.read_text(encoding="utf-8") == original
    assert result["clients"][0]["status"] == "needs_review"
    assert "JSON válido" in result["clients"][0]["note"]


def test_antigravity_migrates_only_its_previous_plugin_server(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    root = tmp_path / "agy-project"
    root.mkdir()
    legacy = root / ".agents/plugins/graphtyn/mcp_config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"mcpServers": {
        "graphtyn": {"command": "graphtyn", "args": ["mcp", "--tool-profile", "intent"]},
        "other": {"command": "other", "args": []},
    }}))
    manifest = root / ".graphtyn/agent-install.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"platforms": ["antigravity"], "files": [str(legacy)]}))
    install_agent(root, "antigravity")

    migrated = json.loads(legacy.read_text(encoding="utf-8"))
    workspace = json.loads((root / ".agents/mcp_config.json").read_text(encoding="utf-8"))
    alias = project_integration_status(root)["mcp_server"]
    assert "graphtyn" not in migrated["mcpServers"]
    assert migrated["mcpServers"]["other"]["command"] == "other"
    assert workspace["mcpServers"][alias]["args"][-1] == "."


def test_project_mcp_stdio_handshake_verifies_memory_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    root = tmp_path / "mcp-project"
    root.mkdir()
    install_agent(root, "codex", tool_profile="intent")

    result = verify_project_mcp(root)
    status = project_integration_status(root)

    assert result["ok"] is True, result
    assert "memory_context" in result["tools"]
    assert status["mcp_verification"]["ok"] is True


def test_status_recognizes_matching_codex_user_config_without_rewriting_it(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    root = tmp_path / "openclaw"
    other = tmp_path / "other-project"
    root.mkdir()
    other.mkdir()
    identity = ProjectIdentityRegistry().register(root, aliases=["OpenClaw"])
    config = codex_home / "config.toml"
    config.parent.mkdir(parents=True)
    command = shutil.which("graphtyn") or "graphtyn"
    original = (
        "[mcp_servers.graphtyn_openclaw]\n"
        f"command = {json.dumps(command)}\n"
        f"args = [\"mcp\", \"--tool-profile\", \"full\", \"--path\", {json.dumps(str(root))}]\n"
        "enabled = true\n"
        "\n[mcp_servers.unrelated]\n"
        f"command = {json.dumps(command)}\n"
        f"args = [\"mcp\", \"--tool-profile\", \"full\", \"--path\", {json.dumps(str(other))}]\n"
        "enabled = true\n"
    )
    config.write_text(original, encoding="utf-8")

    status = project_integration_status(root)

    assert status["project_id"] == identity["id"]
    assert "OpenClaw" in status["project_aliases"]
    assert status["mcp_server"] == "graphtyn_openclaw"
    codex = [item for item in status["clients"] if item["platform"] == "codex"]
    assert len(codex) == 1
    assert codex[0]["alias"] == "graphtyn_openclaw"
    assert codex[0]["configuration_scope"] == "global"
    assert codex[0]["configuration"] == str(config.resolve())
    assert config.read_text(encoding="utf-8") == original


def test_verify_uses_existing_codex_user_entry_and_preserves_global_config(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("GRAPHTYN_HOME", str(state))
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    root = tmp_path / "openclaw"
    root.mkdir()
    ProjectIdentityRegistry().register(root, aliases=["OpenClaw"])
    config = codex_home / "config.toml"
    config.parent.mkdir(parents=True)
    command = shutil.which("graphtyn") or "graphtyn"
    original = (
        "[mcp_servers.graphtyn_openclaw]\n"
        f"command = {json.dumps(command)}\n"
        f"args = [\"mcp\", \"--tool-profile\", \"full\", \"--path\", {json.dumps(str(root))}]\n"
        f"env = {{ GRAPHTYN_HOME = {json.dumps(str(state))} }}\n"
        "enabled = true\n"
    )
    config.write_text(original, encoding="utf-8")

    result = verify_project_mcp(root)

    assert result["ok"] is True, result
    assert "memory_context" in result["tools"]
    assert result["alias"] == "graphtyn_openclaw"
    assert result["configuration_scope"] == "global"
    assert config.read_text(encoding="utf-8") == original
