import atexit
import os
import shutil
import tempfile

import pytest

# Modules such as graphtyn.api.main resolve the data home when they are
# imported, before any fixture runs; a session-wide temporary home keeps those
# imports out of the real ~/.graphtyn too.
_SESSION_HOME = tempfile.mkdtemp(prefix="graphtyn-test-home-")
os.environ["GRAPHTYN_HOME"] = _SESSION_HOME
# Hand-written test indexes carry no parser version: they must not start real rebuilds.
os.environ["GRAPHTYN_AUTO_REINDEX"] = "0"
# Reindex jobs run in-process so tests can patch the scan; test_reindex_worker covers the process.
os.environ["GRAPHTYN_REINDEX_WORKER"] = "thread"
atexit.register(shutil.rmtree, _SESSION_HOME, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_claude_cli(monkeypatch):
    """Keep tests from registering MCP servers in the real ~/.claude.json."""
    from graphtyn.core import project_integrations
    monkeypatch.setattr(project_integrations, "_claude_executable", lambda: None)


@pytest.fixture(autouse=True)
def _isolate_graphtyn_home(monkeypatch, tmp_path_factory):
    """Keep tests from writing project stores and memory into the real ~/.graphtyn.

    A test that needs a particular home still sets GRAPHTYN_HOME itself; child
    processes inherit this one through the environment.
    """
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path_factory.mktemp("graphtyn-home")))
