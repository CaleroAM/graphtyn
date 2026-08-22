from aether_graph.core.graph_scope import classify_path, filter_graph_scope

def test_scope_classifies_production_tests_and_legacy():
    assert classify_path("Assets/Game.cs") == "production"
    assert classify_path("Assets/Tests/GameTests.cs") == "tests"
    assert classify_path("LegacyEditorBackup/Game.cs") == "legacy"

def test_scope_filters_nodes_and_cross_scope_links():
    graph = {"nodes": [
        {"id": "file:src/a.py", "name": "a.py"},
        {"id": "file:tests/a_test.py", "name": "a_test.py"},
    ], "links": [{"source": "file:tests/a_test.py", "target": "file:src/a.py"}], "metadata": {}}
    production = filter_graph_scope(graph, "production")
    assert [node["id"] for node in production["nodes"]] == ["file:src/a.py"]
    assert production["links"] == []
