"""A call on an interface, trait or abstract method reaches its implementations, within a bound.

The declaration edge stays the static target. Each override gets an INFERRED call edge
only while the declaration has few of them; a receiver typed as a concrete class reaches
its own override alone; overrides always carry `implementa` to the declaration.
"""
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.relation_resolution import _DISPATCH_FANOUT


def _graph(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return ASTParser().scan_directory(tmp_path, respect_git=False)


def _edges(graph, label):
    """{(caller, "Owner.method" target, line): confidence} for one edge label."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    qualified = lambda node: f"{node.get('container') or ''}.{node.get('name')}".lstrip(".")
    return {(qualified(nodes[link["source"]]), qualified(nodes[link["target"]]), link.get("line")): link.get("confidence")
            for link in graph["links"] if link.get("label") == label}


JAVA = {
    "app/Shape.java": "package app;\n\npublic interface Shape {\n  double area();\n  default String label() { return \"shape\"; }\n}\n",
    "app/Circle.java": "package app;\n\npublic class Circle implements Shape {\n  public double area() { return 3.14; }\n}\n",
    "app/Square.java": "package app;\n\npublic class Square implements Shape {\n  public double area() { return 4.0; }\n"
                       "  public String label() { return \"square\"; }\n}\n",
    "app/Painter.java": "package app;\n\npublic abstract class Painter {\n  abstract void paint();\n"
                        "  void run(Shape shape, Square square) {\n    double a = shape.area();\n    double b = square.area();\n"
                        "    String l = shape.label();\n    this.paint();\n  }\n}\n",
    "app/Oil.java": "package app;\n\npublic class Oil extends Painter {\n  void paint() { }\n}\n",
}


def test_a_java_interface_typed_receiver_reaches_every_implementation(tmp_path):
    calls = _edges(_graph(tmp_path, JAVA), "llama")
    assert calls[("Painter.run", "Shape.area", 6)] == "EXTRACTED"
    assert calls[("Painter.run", "Circle.area", 6)] == "INFERRED"
    assert calls[("Painter.run", "Square.area", 6)] == "INFERRED"


def test_a_java_concrete_receiver_reaches_only_its_own_override(tmp_path):
    calls = _edges(_graph(tmp_path, JAVA), "llama")
    assert {target for _caller, target, line in calls if line == 7} == {"Square.area"}
    assert calls[("Painter.run", "Square.area", 7)] == "EXTRACTED"


def test_a_java_default_method_and_an_abstract_self_call_reach_their_overrides(tmp_path):
    graph = _graph(tmp_path, JAVA)
    calls, overrides = _edges(graph, "llama"), _edges(graph, "implementa")
    assert {target for _caller, target, line in calls if line == 8} == {"Shape.label", "Square.label"}
    assert calls[("Painter.run", "Oil.paint", 9)] == "INFERRED"
    assert {("Circle.area", "Shape.area"), ("Square.area", "Shape.area"), ("Square.label", "Shape.label"),
            ("Oil.paint", "Painter.paint")} <= {(source, target) for source, target, _line in overrides}


GO = {"app/shape.go": "package app\n\ntype Shape interface {\n\tArea() float64\n\tName() string\n}\n\ntype Circle struct{}\n\n"
                      "func (c Circle) Area() float64 { return 3.14 }\nfunc (c Circle) Name() string { return \"c\" }\n\n"
                      "type Square struct{}\n\nfunc (s *Square) Area() float64 { return 4 }\n"
                      "func (s *Square) Name() string { return \"s\" }\n\n"
                      "type Line struct{}\n\nfunc (l Line) Name() string { return \"l\" }\n\n"
                      "func Total(sh Shape) float64 {\n\treturn sh.Area()\n}\n\n"
                      "func Own(sq *Square) float64 {\n\treturn sq.Area()\n}\n"}


def test_a_go_method_set_with_pointer_receivers_implements_the_interface(tmp_path):
    graph = _graph(tmp_path, GO)
    calls, overrides = _edges(graph, "llama"), _edges(graph, "implementa")
    assert calls[("Total", "Shape.Area", 23)] == "EXTRACTED"
    assert calls[("Total", "Circle.Area", 23)] == "INFERRED" and calls[("Total", "Square.Area", 23)] == "INFERRED"
    # The method set decides: an inferred type edge makes an inferred override edge.
    assert overrides[("Square.Area", "Shape.Area", 15)] == "INFERRED"
    # Line has Name() but not Area(): it does not implement Shape.
    assert not any(source == "Line.Name" for source, _target, _line in overrides)


def test_a_go_concrete_pointer_receiver_reaches_only_its_own_method(tmp_path):
    calls = _edges(_graph(tmp_path, GO), "llama")
    assert {target for caller, target, _line in calls if caller == "Own"} == {"Square.Area"}


RUST = {"src/shape.rs": "pub trait Shape {\n    fn area(&self) -> f64;\n    fn label(&self) -> String { String::from(\"shape\") }\n}\n\n"
                        "pub struct Circle;\nimpl Shape for Circle {\n    fn area(&self) -> f64 { 3.14 }\n}\n\n"
                        "pub struct Square;\nimpl Shape for Square {\n    fn area(&self) -> f64 { 4.0 }\n"
                        "    fn label(&self) -> String { String::from(\"square\") }\n}\n\n"
                        "pub fn total(shape: &dyn Shape) -> f64 {\n    let _ = shape.label();\n    shape.area()\n}\n\n"
                        "pub fn own(sq: &Square) -> f64 {\n    let c = Circle::new();\n    sq.area() + c.area()\n}\n"}


def test_a_rust_trait_requires_a_method_that_its_impls_implement(tmp_path):
    graph = _graph(tmp_path, RUST)
    required = [node for node in graph["nodes"] if node.get("name") == "area" and node.get("container") == "Shape"]
    assert len(required) == 1 and required[0].get("abstract") and required[0].get("implementations") == 2
    calls = _edges(graph, "llama")
    assert calls[("total", "Shape.area", 19)] == "EXTRACTED"
    assert calls[("total", "Circle.area", 19)] == "INFERRED" and calls[("total", "Square.area", 19)] == "INFERRED"
    assert _edges(graph, "implementa")[("Circle.area", "Shape.area", 8)] == "EXTRACTED"


def test_a_rust_trait_default_method_reaches_itself_and_its_override(tmp_path):
    calls = _edges(_graph(tmp_path, RUST), "llama")
    assert {target for _caller, target, line in calls if line == 18} == {"Shape.label", "Square.label"}
    assert calls[("total", "Shape.label", 18)] == "EXTRACTED" and calls[("total", "Square.label", 18)] == "INFERRED"


def test_a_rust_receiver_typed_as_a_struct_reaches_only_that_impl(tmp_path):
    calls = _edges(_graph(tmp_path, RUST), "llama")
    assert {(target, confidence) for (caller, target, _line), confidence in calls.items() if caller == "own"} == {
        ("Square.area", "EXTRACTED"), ("Circle.area", "EXTRACTED")}


PYTHON = {"shapes.py": "from abc import ABC, abstractmethod\nfrom typing import Protocol\n\n\nclass Shape(ABC):\n    @abstractmethod\n"
                       "    def area(self) -> float: ...\n\n    def label(self) -> str:\n        return \"shape\"\n\n\n"
                       "class Circle(Shape):\n    def area(self) -> float:\n        return 3.14\n\n\n"
                       "class Square(Shape):\n    def area(self) -> float:\n        return 4.0\n\n"
                       "    def label(self) -> str:\n        return \"square\"\n\n\n"
                       "def total(shape: Shape) -> float:\n    shape.label()\n    return shape.area()\n\n\n"
                       "def own(sq: Square) -> float:\n    c = Circle()\n    return sq.area() + c.area()\n\n\n"
                       "class Store:\n    def save(self, item):\n        \"\"\"Persist one item.\"\"\"\n        raise NotImplementedError\n\n\n"
                       "class Disk(Store):\n    def save(self, item):\n        return item\n\n\n"
                       "def keep(store: Store, item):\n    return store.save(item)\n\n\n"
                       "class Reader(Protocol):\n    def read(self) -> str: ...\n\n\n"
                       "class File(Reader):\n    def read(self) -> str:\n        return \"\"\n\n\n"
                       "def load(reader: Reader) -> str:\n    return reader.read()\n"}


def test_a_python_abstractmethod_reaches_the_overrides_of_its_subclasses(tmp_path):
    graph = _graph(tmp_path, PYTHON)
    calls = _edges(graph, "llama")
    assert calls[("total", "Shape.area", 28)] == "EXTRACTED"
    assert calls[("total", "Circle.area", 28)] == "INFERRED" and calls[("total", "Square.area", 28)] == "INFERRED"
    assert _edges(graph, "implementa")[("Square.area", "Shape.area", 19)] == "EXTRACTED"
    # `label` has a body and no marker: a plain inherited method, which does not fan out.
    assert {target for _caller, target, line in calls if line == 27} == {"Shape.label"}


def test_a_python_receiver_annotated_or_built_as_a_class_reaches_only_that_class(tmp_path):
    calls = _edges(_graph(tmp_path, PYTHON), "llama")
    assert {(target, confidence) for (caller, target, _line), confidence in calls.items() if caller == "own"} == {
        ("Square.area", "EXTRACTED"), ("Circle.area", "EXTRACTED")}


def test_python_not_implemented_and_protocol_methods_are_abstract(tmp_path):
    calls = _edges(_graph(tmp_path, PYTHON), "llama")
    assert calls[("keep", "Disk.save", 48)] == "INFERRED" and calls[("keep", "Store.save", 48)] == "EXTRACTED"
    assert calls[("load", "File.read", 61)] == "INFERRED"


def test_csharp_and_typescript_interfaces_dispatch_too(tmp_path):
    graph = _graph(tmp_path, {
        "cs/Shape.cs": "namespace App {\n  public interface IShape { double Area(); }\n"
                       "  public class Circle : IShape { public double Area() { return 3.14; } }\n"
                       "  public class Painter {\n    double Run(IShape shape) { return shape.Area(); }\n  }\n}\n",
        "ts/shape.ts": "export interface Shape { area(): number; }\n"
                       "export class Disc implements Shape { area(): number { return 3.14; } }\n"
                       "export class Box implements Shape { area(): number { return 4; } }\n"
                       "export function total(shape: Shape): number { return shape.area(); }\n"
                       "export function own(box: Box): number { return box.area(); }\n",
    })
    calls = _edges(graph, "llama")
    assert calls[("Painter.Run", "IShape.Area", 5)] == "EXTRACTED" and calls[("Painter.Run", "Circle.Area", 5)] == "INFERRED"
    assert calls[("total", "Shape.area", 4)] == "EXTRACTED"
    assert calls[("total", "Disc.area", 4)] == "INFERRED" and calls[("total", "Box.area", 4)] == "INFERRED"
    assert {target for caller, target, _line in calls if caller == "own"} == {"Box.area"}


def _many_implementers(count):
    files = {"app/Named.java": "package app;\n\npublic interface Named {\n  String name();\n}\n",
             "app/Printer.java": "package app;\n\npublic class Printer {\n  String print(Named named) {\n    return named.name();\n  }\n}\n"}
    for index in range(count):
        files[f"app/Item{index}.java"] = (f"package app;\n\npublic class Item{index} implements Named {{\n"
                                          f"  public String name() {{ return \"{index}\"; }}\n}}\n")
    return files


def test_a_call_with_too_many_implementations_is_summarized_not_fanned_out(tmp_path):
    graph = _graph(tmp_path, _many_implementers(_DISPATCH_FANOUT + 1))
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = [link for link in graph["links"] if link.get("label") == "llama" and nodes[link["source"]].get("name") == "print"]
    assert [nodes[link["target"]].get("container") for link in calls] == ["Named"]
    assert calls[0]["resolution"]["implementations"] == _DISPATCH_FANOUT + 1
    assert calls[0]["resolution"]["dispatch"] == "summarized"
    # Every override is still tied to the declaration, once each, whatever the number of call sites.
    assert len(_edges(graph, "implementa")) == 2 * (_DISPATCH_FANOUT + 1)
    declaration = next(node for node in graph["nodes"] if node.get("name") == "name" and node.get("container") == "Named")
    assert declaration["implementations"] == _DISPATCH_FANOUT + 1


def test_a_call_at_the_cap_is_still_fanned_out(tmp_path):
    graph = _graph(tmp_path, _many_implementers(_DISPATCH_FANOUT))
    dispatched = [confidence for (caller, target, _line), confidence in _edges(graph, "llama").items()
                  if caller == "Printer.print" and target.startswith("Item")]
    assert dispatched == ["INFERRED"] * _DISPATCH_FANOUT


def test_a_super_call_runs_the_parent_and_never_fans_out(tmp_path):
    graph = _graph(tmp_path, {"jobs.py": "class Job:\n    def run(self):\n        raise NotImplementedError\n\n\n"
                                         "class Mail(Job):\n    def run(self):\n        return super().run()\n\n\n"
                                         "class Sms(Job):\n    def run(self):\n        return 1\n"})
    calls = _edges(graph, "llama")
    assert {target for caller, target, _line in calls if caller == "Mail.run"} == {"Job.run"}


def test_an_overloaded_declaration_reaches_only_the_override_with_its_arity(tmp_path):
    graph = _graph(tmp_path, {
        "app/Context.java": "package app;\n\npublic interface Context {\n  String write(Object src);\n"
                            "  String write(Object src, String type);\n}\n",
        "app/Impl.java": "package app;\n\npublic class Impl implements Context {\n  public String write(Object src) { return \"\"; }\n"
                         "  public String write(Object src, String type) { return type; }\n}\n",
        "app/User.java": "package app;\n\npublic class User {\n  String one(Context context) {\n    return context.write(this);\n  }\n}\n",
    })
    nodes = {node["id"]: node for node in graph["nodes"]}
    reached = {(nodes[link["target"]].get("container"), nodes[link["target"]].get("parameter_count"))
               for link in graph["links"] if link.get("label") == "llama" and nodes[link["source"]].get("name") == "one"}
    assert reached == {("Context", 1), ("Impl", 1)}
    assert sum(link.get("label") == "implementa" and link.get("resolution", {}).get("strategy") == "override"
               for link in graph["links"]) == 2


def test_a_recursive_call_through_a_typed_variable_does_not_reach_a_homonym(tmp_path):
    calls = _edges(_graph(tmp_path, {
        "tree.py": "class Node:\n    def register(self, child: \"Node\", options):\n        child.register(self, options)\n\n\n"
                   "class Serializer:\n    def register(self, tag, force):\n        return tag\n"}), "llama")
    assert not any(caller == "Node.register" for caller, _target, _line in calls)


def test_a_rust_generic_parameter_is_not_a_receiver_type(tmp_path):
    calls = _edges(_graph(tmp_path, {
        "src/lib.rs": "pub trait Matcher {\n    fn find(&self) -> usize;\n}\n\n"
                      "impl<'a, M: Matcher> Matcher for &'a M {\n    fn find(&self) -> usize { (*self).find() }\n}\n\n"
                      "pub fn run<M: Matcher>(matcher: &M) -> usize {\n    matcher.find()\n}\n"}), "llama")
    assert not any(caller == "run" for caller, _target, _line in calls)


def test_impact_on_a_declaration_lists_its_implementations_and_on_one_of_them_its_dispatched_caller(tmp_path):
    graph = _graph(tmp_path, JAVA)
    declared = query_intent(graph, "impact of changing Shape.label", intent="impact")
    consumers = {node.get("container") for node in declared["nodes"] if node.get("name") == "label"}
    assert consumers == {"Shape", "Square"}
    concrete = query_intent(graph, "impact of changing Oil.paint", intent="impact")
    assert "run" in {node.get("name") for node in concrete["nodes"]}
