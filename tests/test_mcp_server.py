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
    assert {Path(path).name for path in graph["files"].values()} >= {"a.py", "b.py"}
    assert graph["relations"]
    assert graph["format"] == "evidence-v1"
    assert graph["estimated_tokens"] > 0


def test_mcp_compact_coverage_reports_zero_as_negative_evidence(workspace):
    _, resp = _mcp_call(workspace, [{"jsonrpc": "2.0", "id": 32, "method": "tools/call",
        "params": {"name": "graph_neighborhood", "arguments": {"symbol": "helper", "depth": 0}}}])
    result = json.loads(resp[0]["result"]["content"][0]["text"])
    assert result["complete"] is True
    assert result["coverage"]["incoming_calls_or_uses"] == 0
    assert result["coverage"]["outgoing_calls_or_uses"] == 0
    assert result["coverage"]["zero_is_evidence_when_complete"] is True


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
    assert result["entities"] and result["relations"]
    assert result["estimated_tokens"] > 0
    assert result["planner"] == "relevance-v1"
    assert len(result["entities"]) <= result["budget"]["max_nodes"]


def test_context_bundle_enforces_one_global_budget(tmp_path):
    from aether_graph.mcp_server import context_bundle
    graph = {"nodes": [], "links": []}
    graph["nodes"].append({"id": "file:large.cs", "name": "large.cs", "kind": "file", "degree": 12})
    for i in range(12):
        nid = f"symbol:large.cs:M{i}"
        graph["nodes"].append({"id": nid, "name": f"M{i}", "kind": "method", "file": "large.cs", "line": i + 1, "degree": 1})
        graph["links"].append({"source": "file:large.cs", "target": nid, "label": "contiene", "confidence": "EXTRACTED"})
    result = context_bundle(graph, ["large.cs", "M11"], depth=1, max_nodes=5)
    ids = {node["id"] for node in result["nodes"]}
    assert len(result["nodes"]) == 5
    assert "file:large.cs" in ids and "symbol:large.cs:M11" in ids
    assert result["omitted"]["nodes"] > 0
    assert result["contexts"][0]["truncated"] is True


def test_qualified_selector_disambiguates_same_named_methods(tmp_path):
    (tmp_path / "a.py").write_text("class A:\n    def run(self): pass\nclass B:\n    def run(self): pass\n")
    from aether_graph.core.ast_parser import ASTParser
    from aether_graph.mcp_server import neighborhood_subgraph
    graph = ASTParser().scan_directory(tmp_path)
    result = neighborhood_subgraph(graph, "A.run", 0)
    assert len(result["matched"]) == 1
    assert result["matched"][0]["container"] == "A"


def test_mcp_graph_blast_radius(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "graph_blast_radius", "arguments": {"symbol": "helper", "depth": 2}}},
    ])
    r = next(x for x in resp if x.get("id") == 4)
    result = json.loads(r["result"]["content"][0]["text"])
    assert result["entities"]
    impacted = result["impact"]
    assert any(i[1] == 1 for i in impacted)
    assert result["format"] == "evidence-v1"


def test_mcp_graph_search_concepts(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "graph_search_concepts", "arguments": {"query": "helper"}}},
    ])
    r = next(x for x in resp if x.get("id") == 5)
    result = json.loads(r["result"]["content"][0]["text"])
    assert len(result["entities"]) >= 1


def test_mcp_search_concepts_matches_individual_query_terms(workspace):
    _, resp = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 51, "method": "tools/call",
         "params": {"name": "graph_search_concepts",
                    "arguments": {"query": "missing phrase helper", "limit": 3}}},
    ])
    result = json.loads(resp[0]["result"]["content"][0]["text"])
    assert any(entity["name"] == "helper" for entity in result["entities"].values())
    assert len(result["entities"]) <= 3


def test_evidence_format_deduplicates_paths_and_reduces_payload():
    from aether_graph.mcp_server import evidence_result
    path = "Assets/Very/Long/Repeated/Path/GameManager.cs"
    nodes = [
        {"id": f"symbol:{path}:M{i}", "name": f"M{i}", "kind": "method", "file": path,
         "line": i + 1, "signature": f"public void M{i}()"}
        for i in range(8)
    ]
    links = [
        {"source": nodes[i]["id"], "target": nodes[i + 1]["id"], "label": "llama",
         "confidence": "EXTRACTED", "file": path, "line": i + 1}
        for i in range(7)
    ]
    raw = {"nodes": nodes, "links": links}
    compact = evidence_result(raw)
    compact_text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    raw_text = json.dumps(raw, ensure_ascii=False)
    assert len(compact_text) < len(raw_text) * 0.6
    assert list(compact["files"].values()) == [path]
    assert len(compact["relations"]) == 7


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
