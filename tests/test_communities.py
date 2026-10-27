import pytest

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.communities import _label_propagation, analyze_communities, god_nodes


def _graph():
    nodes, links = [], []
    for group, prefix in (("billing", "app/billing"), ("auth", "app/auth")):
        for index in range(3):
            path = f"{prefix}/{group}_{index}.py"
            nodes.append({"id": f"file:{path}", "name": path.rsplit("/", 1)[-1], "kind": "file"})
            nodes.append({"id": f"s:{group}{index}", "name": f"{group}_fn{index}", "kind": "function",
                          "file": path, "line": 1})
    for group in ("billing", "auth"):
        for left in range(3):
            for right in range(3):
                if left != right:
                    links.append({"source": f"s:{group}{left}", "target": f"s:{group}{right}", "label": "llama"})
    links.append({"source": "s:billing0", "target": "s:auth0", "label": "llama"})
    nodes.append({"id": "file:tests/test_all.py", "name": "test_all.py", "kind": "file"})
    nodes.append({"id": "s:t", "name": "test_everything", "kind": "function", "file": "tests/test_all.py", "line": 1})
    links += [{"source": "s:t", "target": f"s:{group}0", "label": "llama"} for group in ("billing", "auth")] * 20
    links.append({"source": "file:app/billing/billing_0.py", "target": "s:billing0", "label": "contiene"})
    return {"nodes": nodes, "links": links}


def test_communities_follow_dependencies_and_ignore_tests():
    result = analyze_communities(_graph())

    labels = sorted(item["label"].split(":")[0] for item in result["communities"])
    assert labels == ["app/auth", "app/billing"]
    assert all(": " in item["label"] for item in result["communities"])
    assert all(item["files"] == 3 for item in result["communities"])
    assert result["surprising_connections"][0]["from"].startswith("app/")
    assert result["suggested_questions"]


def test_god_nodes_skip_tests_containers_and_homonym_fanout():
    graph = _graph()
    graph["nodes"] += [{"id": f"s:req{index}", "name": "require", "kind": "method", "file": f"lib/r{index}.rb",
                        "line": 1} for index in range(3)]
    graph["links"] += [{"source": "s:billing1", "target": f"s:req{index}", "label": "llama"}
                       for index in range(3)] * 50

    names = [row["name"] for row in god_nodes(graph)]

    assert "require" not in names and "test_everything" not in names
    assert names[0] == "billing_fn1"


def test_label_propagation_fallback_is_deterministic():
    weights = {("a", "b"): 3, ("b", "c"): 3, ("a", "c"): 3, ("x", "y"): 3, ("y", "z"): 3, ("c", "x"): 1}
    first = _label_propagation(sorted({n for pair in weights for n in pair}), weights)
    assert first == _label_propagation(sorted({n for pair in weights for n in pair}), weights)
    assert sorted(map(sorted, first)) == [["a", "b", "c"], ["x", "y", "z"]]


def test_bare_ruby_builtins_do_not_resolve_to_project_homonyms(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    (tmp_path / "parameters.rb").write_text(
        "class Parameters\n  def require(key)\n    key\n  end\nend\n", encoding="utf-8")
    (tmp_path / "user.rb").write_text(
        "require 'json'\nclass User\n  def load(params)\n    params.require(:user)\n  end\nend\n",
        encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    nodes = {node["id"]: node for node in graph["nodes"]}
    bare = [link for link in graph["links"] if link.get("label") == "llama"
            and nodes.get(link["target"], {}).get("name") == "require"
            and link.get("source") == "file:user.rb"]
    assert bare == []
