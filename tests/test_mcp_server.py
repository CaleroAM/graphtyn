import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

VENV_PY = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
MCP_RUNNER = "from pathlib import Path\nfrom graphtyn.mcp_server import run_mcp_server\nrun_mcp_server(Path(%r))\n"


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
    assert init["result"]["serverInfo"]["name"] == "graphtyn-mcp"
    tools = next(r for r in resp if r.get("id") == 2)
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"graph_neighborhood", "graph_blast_radius", "graph_search_concepts",
            "graph_context_bundle", "graph_analyze_change", "graph_query_intent",
            "graph_history_search", "graph_history_timeline", "graph_history_get",
            "graph_register_project", "memory_session_start", "memory_checkpoint",
            "memory_append", "memory_search", "memory_context", "memory_session_end",
            "memory_correct", "memory_forget", "memory_compact"} <= names
    intent_tool = next(t for t in tools["result"]["tools"] if t["name"] == "graph_query_intent")
    assert "overview" in intent_tool["inputSchema"]["properties"]["intent"]["enum"]
    assert intent_tool["inputSchema"]["properties"]["evidence_mode"]["enum"] == ["auto", "compact", "balanced", "precision"]


def test_mcp_intent_profile_exposes_only_one_tool(workspace):
    runner = "from pathlib import Path\nfrom graphtyn.mcp_server import run_mcp_server\nrun_mcp_server(Path(%r), 'intent')\n"
    res = subprocess.run(
        [str(VENV_PY), "-c", runner % str(workspace)],
        input=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n",
        capture_output=True, text=True, timeout=60, cwd=str(workspace), env=dict(os.environ),
    )
    response = json.loads(res.stdout.strip())
    assert {tool["name"] for tool in response["result"]["tools"]} == {"graph_query_intent", "memory_context"}


def test_mcp_memory_profile_exposes_memory_lifecycle_without_legacy_graph_catalog(workspace):
    runner = "from pathlib import Path\nfrom graphtyn.mcp_server import run_mcp_server\nrun_mcp_server(Path(%r), 'memory')\n"
    res = subprocess.run([str(VENV_PY), "-c", runner % str(workspace)],
        input=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n",
        capture_output=True, text=True, timeout=60, cwd=str(workspace), env=dict(os.environ))
    names = {tool["name"] for tool in json.loads(res.stdout)["result"]["tools"]}
    assert "graph_query_intent" in names and "memory_compact" in names
    assert "graph_neighborhood" not in names and all(name == "graph_query_intent" or name.startswith("memory_") for name in names)


def test_mcp_memory_cross_session_attribution(workspace):
    requests = [
        {"jsonrpc": "2.0", "id": 101, "method": "tools/call", "params": {"name": "memory_session_start", "arguments": {"agent_id": "agy", "task": "Cambiar autenticación"}}},
    ]
    _, response = _mcp_call(workspace, requests)
    session = json.loads(response[0]["result"]["content"][0]["text"])
    _, response = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 102, "method": "tools/call", "params": {"name": "memory_checkpoint", "arguments": {"session_id": session["id"], "kind": "decision", "title": "JWT centralizado", "content": "AuthService valida todos los tokens"}}},
        {"jsonrpc": "2.0", "id": 103, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"query": "quién valida los tokens", "requester_agent": "opencode"}}},
    ])
    result = json.loads(response[1]["result"]["content"][0]["text"])
    assert result["results"][0]["attribution"]["agent_id"] == "agy"


def test_mcp_change_analyst_is_compact_and_grounded(workspace):
    _, resp = _mcp_call(workspace, [{"jsonrpc": "2.0", "id": 33, "method": "tools/call",
        "params": {"name": "graph_analyze_change", "arguments": {"request": "Cambiar helper y sus consumidores"}}}])
    result = json.loads(resp[0]["result"]["content"][0]["text"])
    assert result["format"] == "evidence-v1"
    assert result["plan"]["target_ids"]
    assert all(target.startswith("N") for target in result["plan"]["target_ids"])
    assert result["grounding"].startswith("deterministic-index")


def test_mcp_query_intent_supports_one_shot_and_delta(workspace):
    (workspace / "flow.py").write_text("def run():\n    return helper()\n", encoding="utf-8")
    _, first_response = _mcp_call(workspace, [{"jsonrpc": "2.0", "id": 34, "method": "tools/call",
        "params": {"name": "graph_query_intent", "arguments": {"request": "Traza el flujo helper", "limit": 8}}}])
    first = json.loads(first_response[0]["result"]["content"][0]["text"])
    assert first["planner"] == "adaptive-intent-v2"
    assert first["do_not_expand"] is True
    assert first["context_id"]
    # Delta must be exercised in the same MCP process because contexts are
    # intentionally session-local and never persisted to the repository.
    requests = [
        {"jsonrpc": "2.0", "id": 35, "method": "tools/call", "params": {"name": "graph_query_intent", "arguments": {"request": "Traza el flujo helper", "limit": 8}}},
    ]
    _, seed_response = _mcp_call(workspace, requests)
    seed = json.loads(seed_response[0]["result"]["content"][0]["text"])
    # Use a direct server transcript with two calls so the second can extend
    # the first; obtain the deterministic context id from an equivalent call.
    _, responses = _mcp_call(workspace, [
        {"jsonrpc": "2.0", "id": 36, "method": "tools/call", "params": {"name": "graph_query_intent", "arguments": {"request": "Traza el flujo helper", "limit": 8}}},
        {"jsonrpc": "2.0", "id": 37, "method": "tools/call", "params": {"name": "graph_query_intent", "arguments": {"request": "Traza el flujo helper", "limit": 8, "extends_context_id": seed["context_id"]}}},
    ])
    delta = json.loads(responses[1]["result"]["content"][0]["text"])
    assert delta["format"] == "evidence-delta-v1"
    assert delta["entities"] == {}
    assert delta["relations"] == []
    assert delta["estimated_tokens"] < first["estimated_tokens"]


def test_mcp_query_intent_auto_adds_bounded_source_for_exact_flow(workspace):
    (workspace / "flow.py").write_text(
        "def run():\n    if helper():\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    _, responses = _mcp_call(workspace, [{
        "jsonrpc": "2.0", "id": 39, "method": "tools/call",
        "params": {"name": "graph_query_intent", "arguments": {
            "request": "Explica el orden exacto y las condiciones de run", "intent": "flow", "limit": 8,
        }},
    }])
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert result["evidence_mode"] == "precision"
    assert result["source_retrieval"]["enabled"] is True
    assert result["source_retrieval"]["characters"] < 12_000
    assert "if helper()" in result["source_evidence"][0]["text"]


def test_mcp_query_intent_overview_preserves_project_profile(workspace):
    (workspace / "README.md").write_text("# Sample service\n", encoding="utf-8")
    (workspace / "main.py").write_text("from a import helper\nprint(helper())\n", encoding="utf-8")
    _, responses = _mcp_call(workspace, [{
        "jsonrpc": "2.0", "id": 38, "method": "tools/call",
        "params": {"name": "graph_query_intent", "arguments": {
            "request": "Utiliza Graphtyn y dime de qué trata este repositorio", "limit": 10,
        }},
    }])
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert result["planner"] == "overview-v1"
    assert result["complete_for"] == ["overview"]
    assert result["project_profile"]["documentation"] == ["README.md"]
    assert result["project_profile"]["entry_points"] == ["main.py"]
    assert result["context_id"]


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
    assert "no incoming" in " ".join(result["negative_evidence"])


def test_evidence_answer_checks_make_requested_zeros_explicit():
    from graphtyn.mcp_server import evidence_result
    node = {"id": "class:AuctionService", "name": "AuctionService", "kind": "class", "file": "AuctionService.cs",
            "imports": ["using System;", "using UnityEngine;"]}
    compact = evidence_result({
        "matched": [node], "nodes": [node], "links": [],
        "intent_terms": ["dependencies", "interfaces", "consumers"],
    }, max_nodes=1)
    assert len(compact["answer_checks"]) == 3
    assert compact["entities"]["N1"]["imports"] == ["using System;", "using UnityEngine;"]


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
    from graphtyn.mcp_server import context_bundle
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
    from graphtyn.core.ast_parser import ASTParser
    from graphtyn.mcp_server import neighborhood_subgraph
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
    from graphtyn.mcp_server import evidence_result
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


def test_evidence_prioritizes_query_relevant_operations():
    from graphtyn.mcp_server import evidence_result
    node = {
        "id": "symbol:a.cs:Register", "name": "Register", "kind": "method", "file": "a.cs", "line": 1,
        "operations": [
            {"kind": "call", "name": f"Noise{i}", "line": i + 2, "text": f"Noise{i}()"}
            for i in range(15)
        ] + [{"kind": "call", "name": "AddScoped", "line": 40, "text": "services.AddScoped<IRepo, EfRepo>()"}],
    }
    compact = evidence_result({"query": "bindings AddScoped", "matches": [node], "links": []}, max_nodes=1)
    ops = compact["entities"]["N1"]["ops"]
    assert any(op[1] == "AddScoped" for op in ops)
    assert len(ops) == 10


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
