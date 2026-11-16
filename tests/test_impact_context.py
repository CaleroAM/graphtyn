"""An impact package says what a change reaches: call lines, own effects, callers of callers, tests."""
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.impact_context import attach_impact_context
from graphtyn.core.path_signals import scope_words


def _project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "errors.py").write_text(
        "class App:\n"
        "    def find_handler(self, error):\n"
        "        if error is None:\n"
        "            raise TypeError(\n"
        "                'no error')\n"
        "        return None\n\n"
        "    def handle(self, error):\n"
        "        handler = self.find_handler(error)\n"
        "        return handler or error\n\n"
        "    def dispatch(self, error):\n"
        "        return self.handle(error)\n", encoding="utf-8")
    (tmp_path / "tests" / "test_find_handler.py").write_text("def test_it():\n    assert True\n", encoding="utf-8")
    (tmp_path / "docs.md").write_text("handle\n", encoding="utf-8")
    nodes = [
        {"id": "c", "name": "App", "kind": "class", "file": "app/errors.py", "line": 1, "end_line": 12},
        {"id": "f", "name": "find_handler", "kind": "method", "container": "App", "file": "app/errors.py",
         "line": 2, "end_line": 6},
        {"id": "h", "name": "handle", "kind": "method", "container": "App", "file": "app/errors.py", "line": 8, "end_line": 10},
        {"id": "d", "name": "dispatch", "kind": "method", "container": "App", "file": "app/errors.py", "line": 12, "end_line": 13},
        {"id": "doc", "name": "docs.md", "kind": "documentation_section", "file": "docs.md"},
        {"id": "file:tests/test_find_handler.py", "name": "test_find_handler.py", "kind": "file"},
    ]
    links = [{"source": "h", "target": "f", "label": "llama", "file": "app/errors.py", "line": 9},
             {"source": "d", "target": "h", "label": "llama", "file": "app/errors.py", "line": 13},
             {"source": "doc", "target": "h", "label": "usa"}]
    return {"nodes": nodes, "links": links}


def test_an_impact_package_carries_call_lines_effects_indirect_callers_and_tests(tmp_path):
    graph = _project(tmp_path)
    request = "Si cambio find_handler en App, ¿qué se rompe?"
    package = query_intent(graph, request, "impact", 10)

    attach_impact_context(tmp_path, graph, package, request)

    assert [row[:2] for row in package["direct_consumers"]["call_lines"]] == [["handle", "app/errors.py:9"]]
    assert package["direct_consumers"]["call_lines"][0][2] == "handler = self.find_handler(error)"
    # A raise split over lines arrives whole.
    assert ["find_handler", "app/errors.py:4", "raise TypeError( 'no error')"] in package["target_effects"]
    assert package["indirect_consumers"]["listed"] == [
        ["dispatch", "app/errors.py:13", "return self.handle(error)", "handle"]]
    assert package["related_tests"] == [["tests/test_find_handler.py", "named after it"]]
    assert package["do_not_expand"] is not False


def test_requested_tests_that_are_not_found_withdraw_the_stop_signal(tmp_path):
    graph = _project(tmp_path)
    graph["nodes"] = [node for node in graph["nodes"] if not node["id"].startswith("file:")]
    request = "Si cambio find_handler, ¿qué pruebas se rompen?"
    package = query_intent(graph, request, "impact", 10)

    attach_impact_context(tmp_path, graph, package, request)

    assert "tests" in package["missing"] and package["do_not_expand"] is False and package["complete_for"] == []


def test_the_owner_and_the_project_root_named_after_a_preposition_are_scope():
    nodes = [{"name": "popStack", "kind": "method", "container": "JsonTreeReader", "file": "gson/src/JsonTreeReader.java"},
             {"name": "JsonTreeReader", "kind": "class", "file": "gson/src/JsonTreeReader.java"},
             {"name": "Gson", "kind": "class", "file": "gson/src/Gson.java"},
             {"name": "Helper", "kind": "class", "file": "extras/Helper.java"}]

    assert scope_words(nodes, "Si cambio popStack en JsonTreeReader de Gson", ["popstack", "jsontreereader", "gson"]) == {
        "jsontreereader", "gson"}
    # Naming the class alone keeps it as the target.
    assert scope_words(nodes, "Si cambio JsonTreeReader, ¿qué se rompe?", ["jsontreereader"]) == set()


def test_impact_context_gives_way_before_the_evidence_an_answer_cites():
    import json

    from graphtyn.core.impact_context import shrink_impact_context

    output = {"entities": {"N1": {"name": "touch"}}, "relations": [["N2", "llama", "N1", "E", 3]],
              "direct_consumers": {"others": [["save", "a.rb:3", "x" * 400]], "call_lines": [["run", "b.rb:9", "y" * 400]]},
              "target_effects": [["touch", "c.rb:1", "return z"]],
              "indirect_consumers": {"total": 1, "listed": [["main", "d.rb:2", "w" * 400, "run"]]},
              "related_tests": [["test/touch_test.rb", "named after it"]]}
    budget = len(json.dumps({key: output[key] for key in ("entities", "relations")})) + 120

    shrink_impact_context(output, lambda: len(json.dumps(output)) > budget)

    assert output["entities"] and output["relations"]
    assert "indirect_consumers" not in output and "related_tests" not in output
    assert output["direct_consumers"]["others"] == [["save", "a.rb:3"]]
