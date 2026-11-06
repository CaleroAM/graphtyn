import tempfile
import json
import importlib
from pathlib import Path
import pytest
from graphtyn.core.ast_parser import ASTParser


def test_configuration_files_are_indexed_as_bounded_source_evidence(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    environment:\n      FEATURE_STORE_PATH: /app/data.parquet\n",
        encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    config = [node for node in graph["nodes"]
              if node.get("kind") == "documentation_section"
              and node.get("file") == "docker-compose.yml"]
    assert config
    assert "FEATURE_STORE_PATH" in config[0]["details"]


def test_extensionless_runners_and_package_scripts_are_indexed(tmp_path):
    (tmp_path / "Makefile").write_text(
        "test:\n\tpython -m pytest tests/test_unit.py\n", encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest run"}}\n', encoding="utf-8",
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "tests.yml").write_text(
        "steps:\n  - run: python -m pytest -q\n", encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    sections = {node.get("file"): node.get("details", "") for node in graph["nodes"]
                if node.get("kind") == "documentation_section"}

    assert "python -m pytest tests/test_unit.py" in sections["Makefile"]
    assert "FROM python:3.12-slim" in sections["Dockerfile"]
    assert '"test":"vitest run"' in sections["package.json"]
    assert "python -m pytest -q" in sections[".github/workflows/tests.yml"]
from graphtyn.core.tree_sitter_backend import (
    TREE_SITTER_EXTENSIONS,
    language_pack_contract,
    parse_file as parse_tree_sitter_file,
)


def test_language_pack_contract_has_unique_extensions_and_known_capabilities():
    contract = language_pack_contract()
    extensions = [extension for pack in contract for extension in pack["extensions"]]
    capabilities = {"symbols", "imports", "calls", "members", "inheritance", "mixins"}

    assert len(extensions) == len(set(extensions))
    assert set(extensions) == set(TREE_SITTER_EXTENSIONS)
    assert {pack["name"] for pack in contract} >= {"c", "cpp"}
    assert all(set(pack["capabilities"]) <= capabilities for pack in contract)


def test_tree_sitter_c_extracts_struct_members_includes_functions_and_calls(tmp_path):
    pytest.importorskip("tree_sitter_c")
    source = tmp_path / "service.c"
    source.write_text(
        "#include <stdio.h>\n"
        "struct Service { int value; };\n"
        "union Payload { int code; };\n"
        "int helper(int value) { return value + 1; }\n"
        "int run(struct Service *service) { return helper(service->value); }\n",
        encoding="utf-8",
    )

    result = parse_tree_sitter_file(source, "service.c")

    assert result and result["language"] == "c" and result["has_error"] is False
    assert {(symbol["name"], symbol["kind"]) for symbol in result["symbols"]} >= {
        ("Service", "struct"), ("Payload", "union"),
        ("helper", "function"), ("run", "function"),
    }
    assert any(member["container"] == "Service" and member["name"] == "value"
               for member in result["members"])
    assert any(item["text"] == "#include <stdio.h>" for item in result["imports"])
    assert any(call["caller"] == "run" and call["name"] == "helper"
               for call in result["calls"])


def test_tree_sitter_cpp_extracts_namespace_inheritance_methods_and_calls(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    source = tmp_path / "service.cpp"
    source.write_text(
        "#include <string>\n"
        "namespace demo {\n"
        "class Base { public: virtual int run() = 0; };\n"
        "int helper(int value) { return value + 1; }\n"
        "class Service : public Base { int value; public: int run() { return helper(value); } };\n"
        "}\n",
        encoding="utf-8",
    )

    result = parse_tree_sitter_file(source, "service.cpp")
    symbols = result["symbols"]

    assert result["language"] == "cpp" and result["namespace"] == "demo"
    service = next(symbol for symbol in symbols if symbol["name"] == "Service")
    assert service["bases"] == ["Base"]
    assert service["namespace"] == "demo"
    assert any(symbol["name"] == "run" and symbol["kind"] == "method"
               and symbol["container"] == "Service" for symbol in symbols)
    assert any(call["caller"] == "run" and call["name"] == "helper"
               for call in result["calls"])


def test_tree_sitter_disambiguates_c_and_cpp_dot_h_headers(tmp_path):
    pytest.importorskip("tree_sitter_c")
    pytest.importorskip("tree_sitter_cpp")
    c_header = tmp_path / "plain.h"
    cpp_header = tmp_path / "templates.h"
    c_header.write_text("struct Item { int id; };\n", encoding="utf-8")
    cpp_header.write_text(
        "namespace demo { template <typename T> T identity(T value) { return value; } }\n",
        encoding="utf-8",
    )

    c_result = parse_tree_sitter_file(c_header, "plain.h")
    cpp_result = parse_tree_sitter_file(cpp_header, "templates.h")

    assert c_result and c_result["language"] == "c" and c_result["has_error"] is False
    assert cpp_result and cpp_result["language"] == "cpp" and cpp_result["has_error"] is False
    assert any(symbol["name"] == "identity" for symbol in cpp_result["symbols"])


def test_scan_uses_c_cpp_language_packs_for_sources_and_headers(tmp_path):
    pytest.importorskip("tree_sitter_c")
    pytest.importorskip("tree_sitter_cpp")
    (tmp_path / "types.h").write_text("struct Item { int id; };\n", encoding="utf-8")
    (tmp_path / "service.cpp").write_text(
        "class Base {}; class Service : public Base {};\n", encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}

    assert graph["metadata"]["tree_sitter_files"] == 2
    assert graph["metadata"]["language_packs"] == ["c", "cpp"]
    assert any(link["label"] == "hereda"
               and nodes[link["source"]]["name"] == "Service"
               and nodes[link["target"]]["name"] == "Base"
               for link in graph["links"])


def test_tree_sitter_ruby_extracts_modules_mixins_methods_calls_and_requires(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    source = tmp_path / "order.rb"
    source.write_text(
        'require "active_record"\n'
        "module Billing\n"
        "  module Trackable\n"
        "    def audit(event)\n"
        "      Logger.info(event)\n"
        "    end\n"
        "  end\n"
        "  class Order < ApplicationRecord\n"
        "    include Trackable\n"
        "    def total(multiplier = 1)\n"
        "      audit(:total)\n"
        "    end\n"
        "    def self.find_paid(id)\n"
        "      find(id)\n"
        "    end\n"
        "  end\n"
        "end\n",
        encoding="utf-8",
    )

    result = parse_tree_sitter_file(source, "order.rb")

    assert result is not None
    assert result["language"] == "ruby" and result["has_error"] is False
    symbols = {(item["name"], item["kind"]): item for item in result["symbols"]}
    assert ("Billing", "module") in symbols and ("Trackable", "module") in symbols
    assert symbols[("Trackable", "module")]["namespace"] == "Billing"
    assert symbols[("Order", "class")]["bases"] == ["ApplicationRecord"]
    assert symbols[("Order", "class")]["mixins"][0]["name"] == "Trackable"
    assert symbols[("total", "method")]["required_parameter_count"] == 0
    assert symbols[("find_paid", "method")]["container"] == "Order"
    assert any(item["name"] == "audit" and item["caller"] == "total" for item in result["calls"])
    assert result["imports"] == [{"text": 'require "active_record"', "line": 1}]


def test_ruby_graph_distinguishes_inheritance_and_mixin_relations(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    (tmp_path / "application_record.rb").write_text(
        "class ApplicationRecord\nend\n", encoding="utf-8"
    )
    (tmp_path / "trackable.rb").write_text(
        "module Trackable\n  def audit(event)\n  end\nend\n", encoding="utf-8"
    )
    (tmp_path / "order.rb").write_text(
        'require_relative "trackable"\n'
        "class Order < ApplicationRecord\n"
        "  include Trackable\n"
        "  def total\n"
        "    audit(:total)\n"
        "  end\n"
        "end\n",
        encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    relations = {
        (nodes.get(link.get("source"), {}).get("name"), link.get("label"),
         nodes.get(link.get("target"), {}).get("name"), link.get("mixin_kind"))
        for link in graph["links"]
    }

    assert graph["metadata"]["language_packs"] == ["ruby"]
    assert ("Order", "hereda", "ApplicationRecord", None) in relations
    assert ("Order", "incluye", "Trackable", "include") in relations
    assert ("total", "llama", "audit", None) in relations


def test_large_ambiguous_call_fanout_is_suppressed(tmp_path):
    pytest.importorskip("tree_sitter_python")
    for index in range(8):
        (tmp_path / f"service_{index}.py").write_text(
            f"def process(value):\n    return value + {index}\n", encoding="utf-8",
        )
    (tmp_path / "caller.py").write_text(
        "def run(value):\n    return process(value)\n", encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    fanout = [
        link for link in graph["links"]
        if link.get("label") == "llama"
        and nodes.get(link.get("source"), {}).get("name") == "run"
        and nodes.get(link.get("target"), {}).get("name") == "process"
    ]

    assert fanout == []
    assert graph["metadata"]["relation_coverage"]["suppressed_weak_candidates"]["ambiguous_calls"] == 1

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


def test_markdown_sections_become_located_searchable_nodes_and_redact_credentials(tmp_path):
    from graphtyn.core.semantic_index import semantic_search

    readme = tmp_path / "README.md"
    readme.write_text(
        "# CRM\n\n## Reportes\nEl botón de reportes usa color turquesa y conserva el filtro mensual.\n\n"
        "## Operadores\nLa pantalla de operadores valida permisos por rol.\n\n"
        "api_key = super-secret-value\n",
        encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    sections = [node for node in graph["nodes"] if node.get("kind") == "documentation_section"]
    hits = semantic_search(graph, "color turquesa botón reportes")

    assert len(sections) >= 3
    report = next(node for node in sections if node["name"] == "Reportes")
    assert report["file"] == "README.md"
    assert report["line_start"] <= report["line_end"]
    assert "conserva el filtro mensual" in report["details"]
    assert any(hit["node"]["id"] == report["id"] for hit in hits)
    assert "super-secret-value" not in " ".join(node["details"] for node in sections)
    assert "[REDACTED]" in " ".join(node["details"] for node in sections)

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


def test_csharp_try_get_value_return_exposes_nullable_hint(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    source = tmp_path / "Selections.cs"
    source.write_text(
        "using System.Collections.Generic; public class Selections { "
        "Dictionary<int, Player> values = new(); "
        "public Player Lookup(int id) { values.TryGetValue(id, out var value); return value; } } "
        "public class Player {}",
        encoding="utf-8",
    )
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    method = next(node for node in graph["nodes"] if node.get("name") == "Lookup")
    assert method["semantic_hints"][0]["confidence"] == "INFERRED"
    assert "null" in method["semantic_hints"][0]["fact"]


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


def test_tree_sitter_python_extracts_exception_evidence(tmp_path):
    pytest.importorskip("tree_sitter_python")
    source = tmp_path / "sessions.py"
    source.write_text(
        "def decode(signer, data):\n"
        "    try:\n"
        "        return signer.unsign(data)\n"
        "    except BadSignature:\n"
        "        return None\n",
        encoding="utf-8",
    )
    result = parse_tree_sitter_file(source, "sessions.py")
    catches = [op for op in result["operations"] if op["kind"] == "catch"]
    assert catches and catches[0]["name"] == "BadSignature"


def test_csharp_cross_file_resolution_prefers_container_and_interface(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "First.cs").write_text(
        "namespace Demo; public interface IService {} public class First : IService { "
        "public void Ping() {} public void Run() { Ping(); } }", encoding="utf-8"
    )
    (tmp_path / "Second.cs").write_text(
        "namespace Other; public class Second { public void Ping() {} }", encoding="utf-8"
    )
    graph = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=tmp_path / "cache.json")
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = [link for link in graph["links"] if link.get("label") == "llama"]
    run_call = next(link for link in calls if nodes.get(link["source"], {}).get("name") == "Run")
    assert nodes[run_call["target"]]["container"] == "First"
    assert run_call["confidence"] == "EXTRACTED"
    implementation = next(link for link in graph["links"] if link.get("label") == "implementa")
    assert nodes[implementation["target"]]["name"] == "IService"


def test_unity_asmdef_assigns_nearest_assembly(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    core = tmp_path / "Core"
    core.mkdir()
    (core / "Core.asmdef").write_text('{"name":"Game.Core","rootNamespace":"Game.Core"}', encoding="utf-8")
    (core / "Service.cs").write_text("namespace Game.Core; public class Service {}", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    service = next(node for node in graph["nodes"] if node.get("name") == "Service")
    file_node = next(node for node in graph["nodes"] if node.get("id") == "file:Core/Service.cs")
    assert service["assembly"] == "Game.Core"
    assert file_node["assembly"] == "Game.Core"


def test_scan_uses_tree_sitter_for_python_java_go_and_rust(tmp_path):
    for module in ("tree_sitter_python", "tree_sitter_java", "tree_sitter_go", "tree_sitter_rust"):
        pytest.importorskip(module)
    (tmp_path / "a.py").write_text("def python_fn():\n    pass\n", encoding="utf-8")
    (tmp_path / "A.java").write_text("class A { void javaFn() {} }", encoding="utf-8")
    (tmp_path / "a.go").write_text("package demo\nfunc GoFn() {}\n", encoding="utf-8")
    (tmp_path / "a.rs").write_text("fn rust_fn() {}\n", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    expected = {"python_fn", "javaFn", "GoFn", "rust_fn"}
    parsed = {node["name"] for node in graph["nodes"] if node.get("parser") == "tree-sitter"}
    assert expected <= parsed


def test_csharp_receiver_type_disambiguates_same_method_name(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "First.cs").write_text(
        "class First { void Ping() {} void Run() { Second other = new Second(); other.Ping(); } }",
        encoding="utf-8",
    )
    (tmp_path / "Second.cs").write_text("class Second { public void Ping() {} }", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    run_call = next(
        link for link in graph["links"]
        if link.get("label") == "llama" and nodes.get(link["source"], {}).get("name") == "Run"
        and "other.Ping" in link.get("evidence", "")
    )
    assert nodes[run_call["target"]]["container"] == "Second"
    assert run_call["resolution"]["receiver_type"] == "Second"


def test_csharp_nested_member_chain_resolves_receiver_type(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "UI.cs").write_text(
        "class UI { public void Show() {} } class OtherUI { public void Show() {} }",
        encoding="utf-8",
    )
    (tmp_path / "Manager.cs").write_text(
        "class Manager { public static Manager Instance { get; set; } public UI hud; }",
        encoding="utf-8",
    )
    (tmp_path / "Caller.cs").write_text(
        "class Caller { void Run() { Manager.Instance.hud?.Show(); } }",
        encoding="utf-8",
    )
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = [link for link in graph["links"] if link.get("label") == "llama"
             and nodes.get(link["source"], {}).get("name") == "Run"]
    assert len(calls) == 1
    assert nodes[calls[0]["target"]]["container"] == "UI"
    assert calls[0]["confidence"] == "EXTRACTED"
    assert calls[0]["resolution"]["receiver_type"] == "UI"


def test_python_call_resolution_honors_lexical_bindings(tmp_path):
    pytest.importorskip("tree_sitter_python")
    (tmp_path / "scopes.py").write_text(
        "def first():\n"
        "    def call(value):\n"
        "        return value\n"
        "    return call(1)\n\n"
        "def second():\n"
        "    def call(value):\n"
        "        return value\n"
        "    return call(2)\n\n"
        "def third():\n"
        "    def call(value):\n"
        "        return value\n"
        "    return call(4)\n\n"
        "def with_callback(update):\n"
        "    return update(3)\n\n"
        "def use_builtin(items):\n"
        "    return list(items)\n",
        encoding="utf-8",
    )
    (tmp_path / "unrelated.py").write_text(
        "def update(value):\n    return value\n\n"
        "def list(value):\n    return value\n",
        encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = [link for link in graph["links"] if link.get("label") == "llama"]

    scoped = [link for link in calls if link.get("evidence") in {"call(1)", "call(2)", "call(4)"}]
    assert len(scoped) == 3
    assert all(nodes[link["target"]]["scope"] == nodes[link["source"]]["name"] for link in scoped)
    assert all(link["confidence"] == "EXTRACTED" for link in scoped)
    assert not any(link.get("evidence") in {"update(3)", "list(items)"} for link in calls)
    suppressed = graph["metadata"]["relation_coverage"]["suppressed_weak_candidates"]
    assert suppressed["bound_calls"] == 1
    assert suppressed["runtime_calls"] == 1


def test_python_import_disambiguates_same_named_functions(tmp_path):
    pytest.importorskip("tree_sitter_python")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "metrics.py").write_text(
        "def collect(value):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "other.py").write_text(
        "def collect(value):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "consumer.py").write_text(
        "from tools.metrics import collect\n\ndef run(value):\n    return collect(value)\n",
        encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    call = next(
        link for link in graph["links"]
        if link.get("label") == "llama" and link.get("evidence") == "collect(value)"
    )

    assert call["target"].startswith("symbol:tools/metrics.py:collect")
    assert call["confidence"] == "EXTRACTED"


def test_python_relative_import_resolves_from_consumer_package(tmp_path):
    pytest.importorskip("tree_sitter_python")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text("def collect(value):\n    return value\n", encoding="utf-8")
    (tmp_path / "helpers.py").write_text("def collect(value):\n    return value\n", encoding="utf-8")
    (package / "consumer.py").write_text(
        "from .helpers import collect\n\ndef run():\n    return collect(1)\n", encoding="utf-8"
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    call = next(link for link in graph["links"] if link.get("evidence") == "collect(1)")

    assert call["target"].startswith("symbol:pkg/helpers.py:collect")
    assert call["confidence"] == "EXTRACTED"


def test_python_local_definition_shadows_same_named_import(tmp_path, monkeypatch):
    pytest.importorskip("tree_sitter_python")
    package = tmp_path / "shadowpkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text(
        "def collect(value):\n    return \"IMPORTED\"\n", encoding="utf-8"
    )
    (package / "consumer.py").write_text(
        "from .helpers import collect\n\n"
        "def run():\n"
        "    def collect(value):\n"
        "        return \"LOCAL\"\n"
        "    return collect(1)\n",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    executed = importlib.import_module("shadowpkg.consumer")
    assert executed.run() == "LOCAL"

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    call = next(link for link in graph["links"]
                if link.get("label") == "llama" and link.get("evidence") == "collect(1)")

    assert nodes[call["target"]]["file"] == "shadowpkg/consumer.py"
    assert nodes[call["target"]]["scope"] == "run"
    assert call["confidence"] == "EXTRACTED"


def test_python_import_alias_resolves_before_candidate_selection(tmp_path):
    pytest.importorskip("tree_sitter_python")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text("def collect(value):\n    return value\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from pkg.helpers import collect as fetch\n\ndef run():\n    return fetch(1)\n", encoding="utf-8"
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    call = next(link for link in graph["links"] if link.get("evidence") == "fetch(1)")

    assert call["target"].startswith("symbol:pkg/helpers.py:collect")
    assert call["confidence"] == "EXTRACTED"
    assert call["resolution"]["called_name"] == "fetch"
    assert call["resolution"]["target_name"] == "collect"


def test_python_runtime_bindings_match_graph_for_parameter_and_alias(tmp_path, monkeypatch):
    pytest.importorskip("tree_sitter_python")
    package = tmp_path / "bindingpkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text(
        "def collect(value):\n    return \"IMPORTED\"\n", encoding="utf-8"
    )
    (package / "consumer.py").write_text(
        "from .helpers import collect as fetch\n\n"
        "def parameter_shadow(collect):\n"
        "    return collect(1)\n\n"
        "def alias_shadow():\n"
        "    def fetch(value):\n"
        "        return \"LOCAL\"\n"
        "    return fetch(1)\n\n"
        "def alias_call():\n"
        "    return fetch(1)\n",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    executed = importlib.import_module("bindingpkg.consumer")
    assert executed.parameter_shadow(lambda _value: "PARAMETER") == "PARAMETER"
    assert executed.alias_shadow() == "LOCAL"
    assert executed.alias_call() == "IMPORTED"

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    links = [link for link in graph["links"] if link.get("label") == "llama"]
    alias_links = [link for link in links if link.get("evidence") == "fetch(1)"]
    alias_shadow_link = next(link for link in alias_links
                             if nodes[link["source"]].get("name") == "alias_shadow")
    alias_link = next(link for link in alias_links
                      if nodes[link["source"]].get("name") == "alias_call")

    assert nodes[alias_shadow_link["target"]]["file"] == "bindingpkg/consumer.py"
    assert nodes[alias_link["target"]]["file"] == "bindingpkg/helpers.py"
    assert not any(nodes[link["source"]].get("name") == "parameter_shadow"
                   for link in links if link.get("evidence") == "collect(1)")


def test_external_python_import_alias_does_not_bind_to_local_homonym(tmp_path):
    pytest.importorskip("tree_sitter_python")
    (tmp_path / "local.py").write_text("def collect(value):\n    return value\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from external.helpers import collect as fetch\n\ndef run():\n    return fetch(1)\n",
        encoding="utf-8",
    )

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    assert not any(link.get("evidence") == "fetch(1)" for link in graph["links"])


def test_duplicate_document_mentions_do_not_create_ambiguous_edges(tmp_path):
    pytest.importorskip("tree_sitter_python")
    (tmp_path / "a.py").write_text("def status():\n    return 'a'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def status():\n    return 'b'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("The status appears here.\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    assert not any(
        link.get("source") == "file:README.md" and link.get("label") == "usa"
        for link in graph["links"]
    )
    suppressed = graph["metadata"]["relation_coverage"]["suppressed_weak_candidates"]
    assert suppressed["ambiguous_mentions"] >= 1


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

    monkeypatch.setattr("graphtyn.core.ast_parser.parse_tree_sitter_file", fake_parse)
    first = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache_path)
    second = ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache_path)
    assert len(calls) == 1
    assert first["metadata"]["tree_sitter_files"] == 1
    assert second["metadata"]["structural_cache"] is True
    assert json.loads(cache_path.read_text(encoding="utf-8"))["files"]["Service.cs"]["sha256"]

    source.write_text("public class Service { public void Run() {} }", encoding="utf-8")
    ASTParser().scan_directory(tmp_path, respect_git=False, cache_path=cache_path)
    assert len(calls) == 2


def test_ruby_bare_method_calls_link_without_locals_or_other_languages(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    (tmp_path / "record.rb").write_text(
        "class Record\n"
        "  def destroy(force = false)\n"
        "    destroy_associations\n"
        "    total = 1\n"
        "    persisted? && destroy_row > total + force\n"
        "  end\n\n"
        "  def destroy_associations; end\n"
        "  def destroy_row; 1; end\n"
        "  def total; 0; end\n"
        "  def force; end\n"
        "end\n", encoding="utf-8")
    (tmp_path / "asset.js").write_text("function destroy_row() { return 2 }\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {(nodes[link["source"]]["name"], nodes[link["target"]]["name"], nodes[link["target"]]["file"])
             for link in graph["links"] if link.get("label") == "llama"}
    assert ("destroy", "destroy_associations", "record.rb") in calls
    assert ("destroy", "destroy_row", "record.rb") in calls
    # `total` is a local and `force` a parameter of destroy; JS homonyms are another language.
    assert not {call for call in calls if call[0] == "destroy" and call[1] in {"total", "force"}}
    assert not {call for call in calls if call[2] == "asset.js"}


def test_ruby_calls_keep_the_bang_and_predicate_suffix_of_the_method_name(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    (tmp_path / "app.rb").write_text(
        "class App\n"
        "  def call(env)\n"
        "    dup.call!(env)\n"
        "  end\n\n"
        "  def call!(env)\n"
        "    invoke { dispatch! } if ready?\n"
        "  end\n\n"
        "  def dispatch!; route!; end\n"
        "  def route!; end\n"
        "  def route(path); end\n"
        "  def ready?; true; end\n"
        "  def invoke; yield; end\n"
        "end\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {(nodes[link["source"]]["name"], nodes[link["target"]]["name"])
             for link in graph["links"] if link.get("label") == "llama"}
    assert {("call", "call!"), ("call!", "dispatch!"), ("call!", "ready?"), ("dispatch!", "route!")} <= calls
    # route! and route are different methods; the suffix must not be dropped.
    assert ("dispatch!", "route") not in calls


def test_ruby_mixins_resolve_lexically_and_super_follows_the_ancestor_chain(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "persistence.rb").write_text(
        "module ActiveRecord\n  module Persistence\n    def save(**options)\n      create_or_update\n    end\n\n"
        "    def create_or_update; end\n  end\nend\n", encoding="utf-8")
    (lib / "validations.rb").write_text(
        "module ActiveRecord\n  module Validations\n    def save(**options)\n      valid? ? super : false\n    end\n\n"
        "    def valid?; true; end\n  end\nend\n", encoding="utf-8")
    (lib / "transactions.rb").write_text(
        "module ActiveRecord\n  module Transactions\n    def save(**options)\n      with_transaction { super(**options) }\n"
        "    end\n\n    def with_transaction; yield; end\n  end\nend\n", encoding="utf-8")
    (lib / "translation.rb").write_text("module ActiveRecord\n  module Translation; end\nend\n", encoding="utf-8")
    (lib / "other_translation.rb").write_text("module ActiveModel\n  module Translation; end\nend\n", encoding="utf-8")
    (lib / "base.rb").write_text(
        "module ActiveRecord\n  class Base\n    include Persistence\n    include Translation\n"
        "    include Validations\n    include Transactions\n  end\nend\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    nodes = {node["id"]: node for node in graph["nodes"]}
    def label(node_id):
        node = nodes[node_id]
        return f"{node.get('container') or node.get('namespace')}#{node['name']}"
    mixins = {(label(link["source"]), nodes[link["target"]]["file"], link["confidence"])
              for link in graph["links"] if link.get("label") == "incluye"}
    # `include Translation` inside ActiveRecord is ActiveRecord::Translation only.
    assert ("ActiveRecord#Base", "lib/translation.rb", "INFERRED") in mixins or \
        ("ActiveRecord#Base", "lib/translation.rb", "EXTRACTED") in mixins
    assert not {mixin for mixin in mixins if mixin[1] == "lib/other_translation.rb"}
    supers = {(label(link["source"]), label(link["target"]))
              for link in graph["links"] if (link.get("resolution") or {}).get("strategy") == "ruby-super-ancestors"}
    # Ancestors of Base: Transactions, Validations, Translation, Persistence.
    assert supers == {("Transactions#save", "Validations#save"), ("Validations#save", "Persistence#save")}


def test_a_qualified_ruby_base_is_not_dropped_among_homonyms(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    for package in ("ActiveJob", "ActiveRecord", "ActionMailer", "ActionController", "ActiveStorage"):
        (tmp_path / f"{package.lower()}_base.rb").write_text(
            f"module {package}\n  class Base\n    def perform\n    end\n  end\nend\n", encoding="utf-8")
    (tmp_path / "mail_delivery_job.rb").write_text(
        "module ActionMailer\n  class MailDeliveryJob < ActiveJob::Base\n    def perform\n    end\n  end\nend\n",
        encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    parents = [(nodes[link["target"]].get("file"), link.get("confidence")) for link in graph["links"]
               if link.get("label") == "hereda" and nodes.get(link["source"], {}).get("name") == "MailDeliveryJob"]

    assert parents == [("activejob_base.rb", parents[0][1])] and parents[0][1] != "AMBIGUOUS"


def test_test_blocks_are_the_callers_of_what_they_run(tmp_path):
    pytest.importorskip("tree_sitter_ruby")
    pytest.importorskip("tree_sitter_javascript")
    (tmp_path / "lib").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "lib" / "billing.rb").write_text("class Billing\n  def charge(amount)\n    amount\n  end\nend\n",
                                                 encoding="utf-8")
    (tmp_path / "test" / "billing_test.rb").write_text(
        'class BillingTest < Minitest::Test\n  setup do\n    charge(0)\n  end\n\n'
        '  test "charges the amount" do\n    charge(10)\n  end\nend\n', encoding="utf-8")
    (tmp_path / "src" / "pay.js").write_text("export function pay(x) { return x }\n", encoding="utf-8")
    (tmp_path / "src" / "pay.test.js").write_text(
        "import { pay } from './pay'\ndescribe('pay', () => {\n  it('pays once', () => { pay(1) })\n})\n",
        encoding="utf-8")
    # Outside a test file the same DSL is ordinary code.
    (tmp_path / "lib" / "workflow.rb").write_text('class Workflow\n  def run\n    it "x" do\n      charge(1)\n    end\n  end\nend\n',
                                                  encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {(nodes[link["source"]].get("name"), nodes[link["target"]].get("name"))
             for link in graph["links"] if link.get("label") == "llama"}

    assert {("test_charges_the_amount", "charge"), ("setup_block", "charge"), ("it_pays_once", "pay")} <= calls
    assert ("run", "charge") in calls
    assert not any(node.get("name") == "it_x" for node in graph["nodes"])


def test_python_self_calls_resolve_to_the_callers_own_class(tmp_path):
    (tmp_path / "app.py").write_text(
        "class App:\n"
        "    def ensure_sync(self, func):\n"
        "        return func\n\n"
        "    def dispatch(self, view):\n"
        "        return self.ensure_sync(view)()\n\n"
        "    @classmethod\n"
        "    def build(cls):\n"
        "        return cls.ensure_sync(None)\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {(nodes[link["source"]].get("name"), nodes[link["target"]].get("name"))
             for link in graph["links"] if link.get("label") == "llama"}

    assert {("dispatch", "ensure_sync"), ("build", "ensure_sync")} <= calls


def _calls(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    return {(nodes[link["source"]].get("name"), nodes[link["target"]].get("container"), nodes[link["target"]].get("name"),
             link.get("confidence"))
            for link in graph["links"] if link.get("label") == "llama"}


def test_python_classes_record_their_bases(tmp_path):
    (tmp_path / "base.py").write_text("class App:\n    pass\n\nclass M:\n    pass\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import base as mixins\nfrom typing import Generic, TypeVar\nfrom base import App\nT = TypeVar('T')\n\n"
        "class Flask(App, mixins.M, Generic[T], metaclass=type):\n    pass\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    bases = {(nodes[link["source"]]["name"], nodes[link["target"]]["name"])
             for link in graph["links"] if link.get("label") == "hereda"}

    assert {("Flask", "App"), ("Flask", "M")} <= bases


def test_self_calls_reach_the_nearest_inherited_definition(tmp_path):
    (tmp_path / "sansio.py").write_text(
        "class Scaffold:\n    def describe(self):\n        return 'scaffold'\n\n"
        "class App(Scaffold):\n    def find_handler(self, error):\n        return None\n\n"
        "    def describe(self):\n        return 'app'\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "from sansio import App\n\nclass Flask(App):\n"
        "    def handle(self, error):\n        return self.find_handler(error)\n\n"
        "    def name(self):\n        return self.describe()\n\n"
        "    def find_handler(self, error):\n        return super().find_handler(error)\n\n"
        "class Quart(Flask):\n    def __init__(self):\n        super(Quart, self).__init__()\n\n"
        "    def handle(self, error):\n        return super(Quart, self).handle(error)\n", encoding="utf-8")

    calls = _calls(ASTParser().scan_directory(tmp_path, respect_git=False))

    # The class's own override wins for self; super() skips it; the nearest base wins over Scaffold.
    assert ("handle", "Flask", "find_handler", "EXTRACTED") in calls
    assert ("find_handler", "App", "find_handler", "EXTRACTED") in calls
    assert ("name", "App", "describe", "EXTRACTED") in calls
    assert ("handle", "Flask", "handle", "EXTRACTED") in calls
    assert not any(caller == "name" and container == "Scaffold" for caller, container, _name, _confidence in calls)


def test_this_calls_reach_an_inherited_typescript_method(tmp_path):
    (tmp_path / "base.ts").write_text("export class Base {\n  helper(): number { return 1; }\n}\n", encoding="utf-8")
    (tmp_path / "child.ts").write_text(
        "import { Base } from './base';\n\nexport class Child extends Base {\n  run(): number { return this.helper(); }\n}\n",
        encoding="utf-8")

    calls = _calls(ASTParser().scan_directory(tmp_path, respect_git=False))

    assert ("run", "Base", "helper", "EXTRACTED") in calls
