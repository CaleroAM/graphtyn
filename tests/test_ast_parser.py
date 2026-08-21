import tempfile
import json
from pathlib import Path
import pytest
from aether_graph.core.ast_parser import ASTParser
from aether_graph.core.tree_sitter_backend import parse_file as parse_tree_sitter_file

def test_parse_python_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        py_file = root / "example.py"
        py_file.write_text("class MyClass:\n    def hello(self):\n        pass\n")

        parser = ASTParser()
        res = parser.parse_python_file(py_file, root)
        
        assert res["file"] == "example.py"
        symbols = {s["name"] for s in res["symbols"]}
        assert "MyClass" in symbols
        assert "hello" in symbols

def test_scan_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "app.py").write_text("class Core:\n    def run(self):\n        pass\n")

        parser = ASTParser()
        graph = parser.scan_directory(root)
        
        assert len(graph["nodes"]) >= 2
        assert len(graph["links"]) >= 1

        # Check dynamic scaling and degree metrics
        file_node = next(n for n in graph["nodes"] if n["kind"] == "file")
        assert "degree" in file_node
        assert "in_degree" in file_node
        assert "out_degree" in file_node
        assert file_node["out_degree"] >= 2  # contains Core class and run method
        assert file_node["val"] > 5  # Base val 5 + degree * 0.4

def test_agent_topology_graph_degrees():
    parser = ASTParser()
    graph = parser.get_agent_topology_graph()

    nexus_node = next(n for n in graph["nodes"] if n["id"] == "agent:nexus")
    assert nexus_node["out_degree"] > 0
    assert nexus_node["degree"] == nexus_node["out_degree"]
    assert nexus_node["val"] == 30 + (nexus_node["degree"] * 0.4)


def test_tree_sitter_csharp_extracts_evidence_when_extra_installed(tmp_path):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_c_sharp")
    source = tmp_path / "Service.cs"
    source.write_text(
        "namespace Demo;\npublic class Service : BaseService {\n  public void Run() { Helper(); }\n}\n",
        encoding="utf-8",
    )
    result = parse_tree_sitter_file(source, "Service.cs")
    assert result and result["parser"] == "tree-sitter"
    symbols = {symbol["name"]: symbol for symbol in result["symbols"]}
    assert symbols["Service"]["line"] == 2
    assert symbols["Run"]["evidence"].startswith("public void Run")
    assert any(call["name"] == "Helper" and call["line"] == 3 for call in result["calls"])


def test_tree_sitter_typescript_extracts_arrow_functions(tmp_path):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    source = tmp_path / "service.ts"
    source.write_text(
        "export class Service { run(): void { helper(); } }\n"
        "export const helper = (): void => {};\n",
        encoding="utf-8",
    )
    result = parse_tree_sitter_file(source, "service.ts")
    symbols = {(symbol["name"], symbol["kind"]) for symbol in result["symbols"]}
    assert ("Service", "class") in symbols
    assert ("run", "method") in symbols
    assert ("helper", "function") in symbols


def test_structural_cache_reuses_unchanged_tree_sitter_result(tmp_path, monkeypatch):
    source = tmp_path / "Service.cs"
    source.write_text("public class Service {}", encoding="utf-8")
    cache_path = tmp_path / "cache" / "structural.json"
    calls = []

    def fake_parse(path, rel_path):
        calls.append(path.read_text(encoding="utf-8"))
        return {
            "file": rel_path, "parser": "tree-sitter", "has_error": False, "calls": [], "imports": [],
            "symbols": [{"name": "Service", "kind": "class", "file": rel_path, "line": 1,
                         "end_line": 1, "evidence": "public class Service", "bases": [],
                         "parser": "tree-sitter"}],
        }

    monkeypatch.setattr("aether_graph.core.ast_parser.parse_tree_sitter_file", fake_parse)
    first = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache_path)
    second = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache_path)
    assert len(calls) == 1
    assert first["metadata"]["tree_sitter_files"] == 1
    assert second["metadata"]["structural_cache"] is True
    assert json.loads(cache_path.read_text(encoding="utf-8"))["files"]["Service.cs"]["sha256"]

    source.write_text("public class Service { public void Run() {} }", encoding="utf-8")
    ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache_path)
    assert len(calls) == 2
