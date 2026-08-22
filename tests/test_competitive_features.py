import json
import subprocess

import pytest

from aether_graph.api import main as api_main
from aether_graph.core.benchmark import run_benchmark
from aether_graph.core.impact import analyze_impact
from aether_graph.core.ast_parser import ASTParser
from aether_graph.core.tree_sitter_backend import parse_file


@pytest.mark.parametrize("module,filename,source,expected", [
    ("tree_sitter_python", "sample.py", "class Service:\n    def run(self):\n        helper()\n", {"Service", "run"}),
    ("tree_sitter_java", "Service.java", "class Service { void run() { helper(); } }", {"Service", "run"}),
    ("tree_sitter_go", "service.go", "package demo\nfunc Run() { helper() }\n", {"Run"}),
    ("tree_sitter_rust", "service.rs", "struct Service;\nfn run() { helper(); }\n", {"Service", "run"}),
])
def test_extended_tree_sitter_languages(tmp_path, module, filename, source, expected):
    pytest.importorskip("tree_sitter")
    pytest.importorskip(module)
    path = tmp_path / filename
    path.write_text(source, encoding="utf-8")
    result = parse_file(path, filename)
    assert result and expected <= {symbol["name"] for symbol in result["symbols"]}


def test_benchmark_ground_truth(tmp_path):
    (tmp_path / "service.py").write_text("class Service:\n    def run(self):\n        pass\n", encoding="utf-8")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"expected_symbols": [
        {"file": "service.py", "name": "Service", "kind": "class"},
        {"file": "service.py", "name": "run", "kind": "method"},
    ]}), encoding="utf-8")
    result = run_benchmark(tmp_path, truth, tmp_path / "cache.json")
    assert result["ground_truth"]["symbol_recall"] == 1
    assert result["quality"]["dangling_edges"] == 0


def test_pr_impact_reports_risk_and_changed_file(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "service.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    source.write_text("def run():\n    return 2\n", encoding="utf-8")
    report = analyze_impact(tmp_path, ASTParser().scan_directory(tmp_path), None)
    assert report["changed_files"] == ["service.py"]
    assert report["risk"]["score"] > 0
    assert "conflict_detection" in report


def test_symbol_level_diff_impacts_callers_not_every_symbol(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import helper\ndef run():\n    return helper()\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py", "b.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=True)
    report = analyze_impact(tmp_path, graph)
    assert {symbol["name"] for symbol in report["changed_symbols"]} == {"helper"}
    impacted_names = {item["node"].get("name") for item in report["impacted_nodes"]}
    assert "run" in impacted_names


def test_http_mcp_requires_token_and_serves_tools(monkeypatch):
    monkeypatch.delenv("AETHER_MCP_TOKEN", raising=False)
    disabled = api_main.mcp_http({"id": 1, "method": "tools/list"}, authorization=None)
    assert disabled.status_code == 503
    monkeypatch.setenv("AETHER_MCP_TOKEN", "secret")
    denied = api_main.mcp_http({"id": 1, "method": "tools/list"}, authorization="Bearer wrong")
    assert denied.status_code == 401
    allowed = api_main.mcp_http({"id": 1, "method": "tools/list"}, authorization="Bearer secret")
    body = json.loads(allowed.body)
    assert allowed.status_code == 200
    assert "graph_pr_impact" in {tool["name"] for tool in body["result"]["tools"]}
    assert "graph_context_bundle" in {tool["name"] for tool in body["result"]["tools"]}


def test_semantic_media_edges_include_auditable_evidence():
    nodes = [
        {"id": "file:a.png", "name": "mapa.png", "kind": "image", "details": "Mapa interactivo del museo con rutas de visitantes"},
        {"id": "file:b.pdf", "name": "rutas.pdf", "kind": "doc", "details": "Documento del museo con mapa de rutas para visitantes"},
    ]
    graph = api_main.generate_semantic_graph({"nodes": nodes, "links": [], "metadata": {"path": "/tmp/demo"}})
    inferred = [link for link in graph["links"] if link.get("confidence") == "INFERRED"]
    assert inferred and inferred[0]["evidence"]["shared_terms"]
    assert inferred[0]["explanation"]
