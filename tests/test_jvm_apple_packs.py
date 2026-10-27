from pathlib import Path

import pytest

from graphtyn.core.ast_parser import ASTParser

SAMPLES = {
    "Invoice.kt": ("tree_sitter_kotlin", "package shop.billing\n\nimport shop.core.Money\n\ninterface Payable {\n    fun pay(): Boolean\n}\n\nenum class Status { OPEN, PAID }\n\nopen class Base\n\nclass Invoice(val total: Money) : Base(), Payable {\n    // WHY: the gateway is idempotent per invoice id, so retries are safe\n    override fun pay(): Boolean {\n        return gateway.charge(total)\n    }\n\n    fun add(item: String) {\n        log(item)\n    }\n}\n\nobject Registry {\n    fun find(id: Int): Invoice {\n        return Invoice(Money(id))\n    }\n}\n\nfun log(msg: String) {\n    println(msg)\n}\n"),
    "Invoice.swift": ("tree_sitter_swift", "import Foundation\n\nprotocol Payable {\n    func pay() -> Bool\n}\n\nstruct Money {\n    let amount: Int\n}\n\nclass Base {}\n\nclass Invoice: Base, Payable {\n    let total: Money\n    init(total: Money) {\n        self.total = total\n    }\n    func pay() -> Bool {\n        return gateway.charge(total)\n    }\n    func add(_ item: String) {\n        log(item)\n    }\n}\n\nfunc log(_ msg: String) {\n    print(msg)\n}\n"),
    "Invoice.scala": ("tree_sitter_scala", "package shop.billing\n\nimport shop.core.Money\n\ntrait Payable {\n  def pay(): Boolean\n}\n\nabstract class Base\n\ncase class Invoice(total: Money) extends Base with Payable {\n  def pay(): Boolean = gateway.charge(total)\n  def add(item: String): Unit = {\n    log(item)\n  }\n}\n\nobject Registry {\n  def find(id: Int): Invoice = Invoice(Money(id))\n}\n\nobject Logging {\n  def log(msg: String): Unit = println(msg)\n}\n"),
}


@pytest.mark.parametrize("filename", sorted(SAMPLES))
def test_jvm_and_apple_languages_extract_types_methods_inheritance_and_calls(tmp_path, filename):
    module, source = SAMPLES[filename]
    pytest.importorskip(module)
    (tmp_path / filename).write_text(source, encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    nodes = {node["id"]: node for node in graph["nodes"] if node.get("parser") == "tree-sitter"}
    by_name = {}
    for node in nodes.values():
        by_name.setdefault(node["name"], []).append(node)
    assert by_name["Payable"][0]["kind"] == "interface"
    assert {node["container"] for node in by_name["pay"] if node["kind"] == "method"} == {"Payable", "Invoice"}
    assert [node["kind"] for node in by_name["add"]] == ["method"]
    relations = {(link["label"], nodes[link["source"]]["name"], nodes[link["target"]]["name"])
                 for link in graph["links"] if link.get("source") in nodes and link.get("target") in nodes}
    assert {("hereda", "Invoice", "Base"), ("implementa", "Invoice", "Payable"), ("llama", "add", "log")} <= relations
    assert Path(filename).suffix.lstrip(".") in "".join(graph["metadata"]["language_packs"]) or         graph["metadata"]["language_packs"]


def test_kotlin_enum_class_and_swift_struct_kinds(tmp_path):
    pytest.importorskip("tree_sitter_kotlin")
    pytest.importorskip("tree_sitter_swift")
    (tmp_path / "A.kt").write_text(SAMPLES["Invoice.kt"][1], encoding="utf-8")
    (tmp_path / "A.swift").write_text(SAMPLES["Invoice.swift"][1], encoding="utf-8")

    kinds = {(node["file"], node["name"]): node["kind"]
             for node in ASTParser().scan_directory(tmp_path, respect_git=False)["nodes"] if node.get("parser")}
    assert kinds[("A.kt", "Status")] == "enum"
    assert kinds[("A.swift", "Money")] == "struct"
    assert kinds[("A.swift", "init")] == "method"
