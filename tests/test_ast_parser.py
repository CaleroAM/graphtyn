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
from graphtyn.core.tree_sitter_backend import parse_file as parse_tree_sitter_file

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
