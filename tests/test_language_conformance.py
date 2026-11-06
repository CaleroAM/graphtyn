"""Every language pack produces what it declares.

Each pack declares capabilities (symbols, imports, calls, members, inheritance, mixins).
Python declared inheritance and Java declared calls for months while producing neither,
and nothing noticed. One canonical fixture per pack checks each declared capability
against the graph: a base type with a method, a child type that imports it, holds a typed
field and calls its own method and the inherited one.
"""
from __future__ import annotations

import pytest

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.tree_sitter_backend import LANGUAGE_PACKS, parse_file

CLASSES = {"Base", "Child"}

# name: (extension, base file, child file, expected symbols, expected calls, expected bases)
FIXTURES = {
    "python": ("py", "class Base:\n    def helper(self):\n        return 1\n",
               "from base import Base\n\nclass Child(Base):\n    def own(self):\n        return 2\n\n"
               "    def run(self):\n        self.own()\n        return self.helper()\n",
               CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "javascript": ("js", "export class Base {\n  helper() { return 1; }\n}\n",
                   "import { Base } from './base.js';\nexport class Child extends Base {\n  base = new Base();\n"
                   "  own() { return 2; }\n  run() { this.own(); return this.helper(); }\n}\n",
                   CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "typescript": ("ts", "export class Base {\n  helper(): number { return 1; }\n}\n",
                   "import { Base } from './base';\nexport class Child extends Base {\n  private base: Base;\n"
                   "  own(): number { return 2; }\n  run(): number { this.own(); return this.helper(); }\n}\n",
                   CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "java": ("java", "package app;\n\npublic class Base {\n  public int helper() { return 1; }\n}\n",
             "package app;\n\nimport app.Base;\n\npublic class Child extends Base {\n  private Base base;\n"
             "  int own() { return 2; }\n  int run() { this.own(); return this.helper(); }\n}\n",
             CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "csharp": ("cs", "namespace App {\n  public class Base {\n    public int Helper() { return 1; }\n  }\n}\n",
               "using App;\nnamespace App {\n  public class Child : Base {\n    private Base _base;\n"
               "    int Own() { return 2; }\n    int Run() { this.Own(); return this.Helper(); }\n  }\n}\n",
               CLASSES | {"Helper", "Own", "Run"}, {("Run", "Own"), ("Run", "Helper")}, {("Child", "Base")}),
    "php": ("php", "<?php\nnamespace App;\n\nclass Base {\n  public function helper() { return 1; }\n}\n",
            "<?php\nnamespace App;\n\nuse App\\Base;\n\nclass Child extends Base {\n  private Base $base;\n"
            "  public function own() { return 2; }\n  public function run() { $this->own(); return $this->helper(); }\n}\n",
            CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "kotlin": ("kt", "package app\n\nopen class Base {\n  fun helper(): Int = 1\n}\n",
               "package app\n\nimport app.Base\n\nclass Child : Base() {\n  fun own(): Int = 2\n"
               "  fun run(): Int { this.own(); return this.helper() }\n}\n",
               CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "swift": ("swift", "class Base {\n  func helper() -> Int { return 1 }\n}\n",
              "import Foundation\n\nclass Child: Base {\n  func own() -> Int { return 2 }\n"
              "  func run() -> Int { _ = self.own(); return self.helper() }\n}\n",
              CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "scala": ("scala", "package app\n\nclass Base {\n  def helper(): Int = 1\n}\n",
              "package app\n\nimport app.Base\n\nclass Child extends Base {\n  def own(): Int = 2\n"
              "  def run(): Int = { this.own(); this.helper() }\n}\n",
              CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "cpp": ("cpp", "class Base {\n public:\n  int helper() { return 1; }\n};\n",
            "#include \"base.cpp\"\n\nclass Child : public Base {\n  Base* base;\n public:\n  int own() { return 2; }\n"
            "  int run() { this->own(); return this->helper(); }\n};\n",
            CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    "ruby": ("rb", "module Greeting\nend\n\nclass Base\n  def helper\n    1\n  end\nend\n",
             "require_relative 'base'\n\nclass Child < Base\n  include Greeting\n\n  def own\n    2\n  end\n\n"
             "  def run\n    own\n    helper\n  end\nend\n",
             CLASSES | {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Child", "Base")}),
    # Rust inherits through supertraits; `impl Trait for Type` is not modelled.
    "rust": ("rs", "pub trait Base {}\n\npub fn helper() -> i32 { 1 }\n",
             "use crate::base::helper;\n\npub trait Shape: Base {}\n\npub struct Child { base: Shape }\n\nimpl Child {\n"
             "    fn own(&self) -> i32 { 2 }\n    fn run(&self) -> i32 { self.own(); helper() }\n}\n",
             {"Base", "Child", "Shape", "helper", "own", "run"}, {("run", "own"), ("run", "helper")}, {("Shape", "Base")}),
    # Go promotes the methods of an embedded type: Child embeds Base.
    "go": ("go", "package app\n\ntype Base struct{}\n\nfunc (b *Base) Helper() int { return 1 }\n",
           "package app\n\nimport \"fmt\"\n\ntype Child struct {\n\tBase\n\tname string\n}\n\n"
           "func (c *Child) Own() int { return 2 }\n\nfunc (c *Child) Run() int { fmt.Println(c.Own()); return c.Helper() }\n",
           CLASSES | {"Helper", "Own", "Run"}, {("Run", "Own"), ("Run", "Helper")}, {("Child", "Base")}),
    "c": ("c", "int helper(void) { return 1; }\n",
          "#include \"base.h\"\n\nstruct child { struct base *base; };\n\nstatic int own(void) { return 2; }\n\n"
          "int run(void) { own(); return helper(); }\n",
          {"helper", "own", "run"}, {("run", "own"), ("run", "helper")}, set()),
}
PACKS = {pack.name: pack for pack in LANGUAGE_PACKS}


def test_every_language_pack_has_a_conformance_fixture():
    assert set(FIXTURES) == set(PACKS)


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    results = {}
    for name, (extension, base, child, *_expected) in FIXTURES.items():
        root = tmp_path_factory.mktemp(name)
        (root / f"base.{extension}").write_text(base, encoding="utf-8")
        (root / f"child.{extension}").write_text(child, encoding="utf-8")
        graph = ASTParser().scan_directory(root, respect_git=False)
        nodes = {node["id"]: node for node in graph["nodes"]}
        pair = lambda label: {(nodes[link["source"]].get("name"), nodes[link["target"]].get("name"))  # noqa: E731
                              for link in graph["links"] if link.get("label") in label}
        facts = parse_file(root / f"child.{extension}", f"child.{extension}") or {}
        results[name] = {"symbols": {node.get("name") for node in graph["nodes"] if node.get("kind") != "file"},
                         "calls": pair({"llama"}), "bases": pair({"hereda", "implementa"}), "mixins": pair({"incluye"}),
                         "imports": facts.get("imports") or [], "members": facts.get("members") or []}
    return results


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_each_declared_capability_is_produced(name, produced):
    _extension, _base, _child, symbols, calls, bases = FIXTURES[name]
    capabilities, facts = PACKS[name].capabilities, produced[name]

    assert symbols <= facts["symbols"], "symbols"
    if "imports" in capabilities:
        assert facts["imports"], "imports"
    if "calls" in capabilities:
        # The child calls its own method and the one it inherits (a free function where there are no classes).
        assert calls <= facts["calls"], "calls"
    if "inheritance" in capabilities:
        assert bases <= facts["bases"], "inheritance"
    if "members" in capabilities:
        assert any(member.get("type") for member in facts["members"]), "members"
    if "mixins" in capabilities:
        assert ("Child", "Greeting") in facts["mixins"], "mixins"
