import pytest


@pytest.fixture(autouse=True)
def _isolate_claude_cli(monkeypatch):
    """Keep tests from registering MCP servers in the real ~/.claude.json."""
    from graphtyn.core import project_integrations
    monkeypatch.setattr(project_integrations, "_claude_executable", lambda: None)
