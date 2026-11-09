"""Edges the precision audit found wrong, and the extraction gaps it left, stay fixed."""
from pathlib import Path
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.change_analyst import _terms, query_intent
from graphtyn.core.impact_context import attach_impact_context


def _graph(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return ASTParser().scan_directory(tmp_path, respect_git=False)


def _calls(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return {(nodes[link["source"]].get("name"), nodes[link["target"]].get("file"), nodes[link["target"]].get("name"))
            for link in graph["links"] if link.get("label") == "llama"}


def test_a_name_imported_from_a_package_does_not_reach_a_project_homonym(tmp_path):
    graph = _graph(tmp_path, {
        "source/utils/delay.ts": "export function delay(ms: number) { return ms; }\n",
        "source/index.ts": "export function run(): number { return 1; }\n",
        "test/retry.ts": "import {setTimeout as delay} from 'node:timers/promises';\nimport {run} from '../source/index.js';\n"
                         "async function waits() { await delay(10); return run(); }\n",
    })
    calls = _calls(graph)

    assert ("waits", "source/index.ts", "run") in calls  # `./x.js` names x.ts
    assert not any(name == "delay" for _caller, _file, name in calls)


def test_a_bare_call_never_reaches_a_method_of_an_object_literal(tmp_path):
    graph = _graph(tmp_path, {"a.ts": "const options = {\n  delay(attempt: number) { return attempt; },\n};\n"
                                      "function go() { return delay(3); }\nfunction use() { return options.delay(1); }\n"})

    assert not any(caller == "go" for caller, _file, _name in _calls(graph))


def test_a_declaration_inside_a_string_does_not_type_a_receiver(tmp_path):
    graph = _graph(tmp_path, {
        "TypeToken.java": "class TypeToken {\n  private final Type type;\n"
                          "  void check() { throw new IllegalArgumentException(\"TypeToken type argument is wrong\"); }\n"
                          "  boolean same(Type from) { return type.equals(from); }\n"
                          "  public boolean equals(Object o) { return false; }\n}\n"})

    assert not any(caller == "same" and name == "equals" for caller, _file, name in _calls(graph))


def test_a_go_parameter_types_its_variable(tmp_path):
    graph = _graph(tmp_path, {"command.go": "package cobra\n\ntype Command struct{}\n\nfunc (c *Command) merge() {}\n\n"
                                            "func strip(args []string, c *Command) { c.merge() }\n\n"
                                            "func build() { root := &Command{}; root.merge() }\n"})
    calls = _calls(graph)

    assert ("strip", "command.go", "merge") in calls and ("build", "command.go", "merge") in calls


def test_python_typed_attributes_type_the_chain_through_self(tmp_path):
    graph = _graph(tmp_path, {
        "sessions.py": "class SessionInterface:\n    def save_session(self, app):\n        return None\n",
        "app.py": "from sessions import SessionInterface\n\nclass App:\n    session_interface: SessionInterface = SessionInterface()\n\n"
                  "    def process_response(self):\n        return self.session_interface.save_session(self)\n"})

    assert ("process_response", "sessions.py", "save_session") in _calls(graph)


def test_a_rust_impl_of_a_std_trait_does_not_inherit_from_a_project_struct(tmp_path):
    graph = _graph(tmp_path, {"lib.rs": "pub struct Error;\npub trait Flag {}\npub struct CommandError;\n"
                                        "impl std::error::Error for CommandError {}\nimpl Flag for CommandError {}\n"})
    nodes = {node["id"]: node for node in graph["nodes"]}
    bases = {(nodes[link["source"]]["name"], nodes[link["target"]]["name"]) for link in graph["links"]
             if link.get("label") in ("hereda", "implementa")}

    assert bases == {("CommandError", "Flag")}


def test_a_citation_format_is_not_a_requested_symbol():
    assert "line" not in _terms("What breaks if I change detect_binary? Cite file:line.")
    assert "línea" not in _terms("Si cambio x, ¿qué se rompe? Cita archivo:línea.")
    assert "line" in _terms("Si cambio line en ColorSpecs, ¿qué se rompe?")
    # An imperative that introduces what to report is not a symbol either.
    assert "list" not in _terms("What breaks if I change getIndent? List the direct consumers with file:line evidence.")
    assert "list" in _terms("What breaks if I change list in Registry?")


def test_an_impact_package_lists_what_the_target_calls_and_who_reads_a_property(tmp_path):
    graph = _graph(tmp_path, {
        "helpers.py": "def split_path(name):\n    out = [name]\n    out.extend(split_path(name.rpartition('.')[0]))\n    return out\n",
        "wrappers.py": "from helpers import split_path\n\nclass Request:\n    def blueprints(self):\n        return split_path(self.name)\n",
        "app.py": "class App:\n    def handle(self, request):\n        return request.blueprints\n"})
    request = "Si cambio split_path, ¿qué se rompe?"
    package = query_intent(graph, request, "impact", 10)

    attach_impact_context(tmp_path, graph, package, request)

    assert ["split_path", "helpers.py:3", "rpartition"] in package["target_calls"]
    assert ["handle", "app.py:3", "return request.blueprints", "blueprints"] in package["indirect_consumers"]["listed"]
    assert any(check.startswith("consumers: name each direct consumer (blueprints") for check in package["answer_checks"])


def test_a_bare_ruby_constant_does_not_reach_a_class_under_another_top_level_module(tmp_path):
    graph = _graph(tmp_path, {
        "activerecord/lib/file.rb": "module ActiveRecord\n  class FixtureSet\n    class File\n      def self.open(path)\n        path\n"
                                    "      end\n    end\n  end\nend\n",
        "railties/lib/task.rb": "module Rails\n  class Task\n    def configure\n      File.open('x')\n    end\n  end\nend\n",
        "activerecord/lib/loader.rb": "module ActiveRecord\n  class FixtureSet\n    class Loader\n      def load\n"
                                      "        File.open('y')\n      end\n    end\n  end\nend\n",
    })
    callers = {caller for caller, _file, name in _calls(graph) if name == "open"}

    assert "configure" not in callers  # Ruby's own File
    assert "load" in callers  # ActiveRecord::FixtureSet::File, visible from inside ActiveRecord


def test_reindex_with_another_home_never_goes_through_the_local_service(monkeypatch, tmp_path):
    from graphtyn import cli

    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    assert cli._foreign_home()
    monkeypatch.setenv("GRAPHTYN_HOME", str(Path.home() / ".graphtyn"))
    assert not cli._foreign_home()
    monkeypatch.delenv("GRAPHTYN_HOME")
    assert not cli._foreign_home()
