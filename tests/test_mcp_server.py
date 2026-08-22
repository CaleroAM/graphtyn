import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

VENV_PY = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
MCP_RUNNER = "from pathlib import Path\nfrom aether_graph.mcp_server import run_mcp_server\nrun_mcp_server(Path(%r))\n"


def _mcp_call(workspace, requests, env=None):
    lines = "\n".join(json.dumps(r) for r in requests) + "\n"
    e = dict(os.environ)
    if env:
        e.update(env)
    res = subprocess.run(
        [str(VENV_PY), "-c", MCP_RUNNER % str(workspace)],
        input=lines, capture_output=True, text=True, timeout=60, cwd=str(workspace), env=e,
    )
    responses = []
    for line in res.stdout.splitlines():
        if line.strip():
            responses.append(json.loads(line))
    return res, responses


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import helper\n\nprint(helper())\n", encoding="utf-8")
    return tmp_path


def test_mcp_initialize_and_tools_list(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    init = next(r for r in resp if r.get("id") == 1)
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert init["result"]["serverInfo"]["name"] == "aether-graph-mcp"
    tools = next(r for r in resp if r.get("id") == 2)
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"graph_neighborhood", "graph_blast_radius", "graph_search_concepts",
            "graph_context_bundle",
            "graph_history_search", "graph_history_timeline", "graph_history_get",
            "graph_register_project"} <= names


def test_mcp_graph_neighborhood(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "graph_neighborhood", "arguments": {}}},
    ])
    r = next(x for x in resp if x.get("id") == 3)
    text = r["result"]["content"][0]["text"]
    graph = json.loads(text)
    ids = {n["id"] for n in graph["nodes"]}
    assert "file:a.py" in ids and "file:b.py" in ids
    assert any(l.get("confidence") in ("EXTRACTED", "INFERRED") for l in graph["links"])
    assert graph["response_mode"] == "compact"
    assert graph["estimated_tokens"] > 0


def test_mcp_full_response_is_opt_in(workspace):
    _, resp = _mcp_call(workspace, [{"jsonrpc": "2.0", "id": 30, "method": "tools/call",
        "params": {"name": "graph_neighborhood", "arguments": {"response_mode": "full"}}}])
    graph = json.loads(resp[0]["result"]["content"][0]["text"])
    assert "response_mode" not in graph


def test_mcp_context_bundle_combines_queries(workspace):
    _, resp = _mcp_call(workspace, [{"jsonrpc": "2.0", "id": 31, "method": "tools/call",
        "params": {"name": "graph_context_bundle", "arguments": {"symbols": ["helper", "a.py"]}}}])
    result = json.loads(resp[0]["result"]["content"][0]["text"])
    assert result["symbols"] == ["helper", "a.py"]
    assert len(result["contexts"]) == 2
    assert result["estimated_tokens"] > 0


def test_mcp_graph_blast_radius(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "graph_blast_radius", "arguments": {"symbol": "helper", "depth": 2}}},
    ])
    r = next(x for x in resp if x.get("id") == 4)
    result = json.loads(r["result"]["content"][0]["text"])
    assert len(result["matched"]) >= 1
    impacted = result["impacted"]
    assert any(i["hop"] == 1 for i in impacted)
    assert all("confidence" in i for i in impacted)


def test_mcp_graph_search_concepts(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "graph_search_concepts", "arguments": {"query": "helper"}}},
    ])
    r = next(x for x in resp if x.get("id") == 5)
    result = json.loads(r["result"]["content"][0]["text"])
    assert len(result["matches"]) >= 1


def test_mcp_history_flow(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
         "params": {"name": "graph_neighborhood", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "graph_history_timeline", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
         "params": {"name": "graph_history_search", "arguments": {"query": "neighborhood"}}},
    ])
    timeline = next(x for x in resp if x.get("id") == 7)
    entries = json.loads(timeline["result"]["content"][0]["text"])["timeline"]
    assert len(entries) >= 1
    assert entries[0]["action_type"] == "neighborhood"
    search = next(x for x in resp if x.get("id") == 8)
    results = json.loads(search["result"]["content"][0]["text"])["results"]
    assert len(results) >= 1


def test_mcp_unknown_method_returns_error(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 9, "method": "nope", "params": {}},
    ])
    r = next(x for x in resp if x.get("id") == 9)
    assert r["error"]["code"] == -32601
