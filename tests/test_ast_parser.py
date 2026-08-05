import tempfile
from pathlib import Path
from aether_graph.core.ast_parser import ASTParser

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
