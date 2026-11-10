"""`the matched method of the Sink trait`: the named owner's member, its implementations, and generic bounds."""
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.impact_references import _calls_first, named_owner_members
from graphtyn.core.tree_sitter_backend import _bounded_generics, parse_file


def test_the_named_owner_keeps_its_member_and_what_implements_it():
    nodes = [{"id": "decl", "name": "matched", "kind": "function", "container": "Sink"},
             {"id": "impl", "name": "matched", "kind": "function", "container": "JSONSink"},
             {"id": "other", "name": "matched", "kind": "function", "container": "Gitignore"},
             {"id": "trait", "name": "Sink", "kind": "trait"}]
    links = [{"source": "impl", "target": "decl", "label": "implementa"}]

    named = nodes[:3]
    chosen = named_owner_members(named, "the matched method of the Sink trait", links)

    assert [node["id"] for node in chosen] == ["decl", "impl"]
    # Written in lower case, `sink` is a word, not the owner.
    assert named_owner_members(named, "what does the sink do when matched", links) == []


def test_member_calls_come_before_prose_mentions():
    references = [["doc", "a.rs:1", False], ["run", "b.rs:2", True], ["log", "c.rs:3", False]]
    assert _calls_first(references) == [["run", "b.rs:2"], ["doc", "a.rs:1"], ["log", "c.rs:3"]]


def test_a_field_of_a_generic_type_takes_the_bound():
    members = [{"name": "sink", "type": "S"}, {"name": "out", "type": "W"}, {"name": "repo", "type": "Repo"}]
    text = "struct Core<S> { sink: S }\nimpl<'s, S: Sink, W: io::Write> Core<S> {}\nimpl<W: Display> X for W {}\n"
    typed = {member["name"]: member["type"] for member in _bounded_generics(members, lambda: text)}
    assert typed == {"sink": "Sink", "out": "W", "repo": "Repo"}  # W is bound twice: left as written


def test_a_call_through_a_generic_field_reaches_the_trait_and_its_implementations(tmp_path):
    (tmp_path / "lib.rs").write_text(
        "pub trait Sink {\n    fn matched(&mut self) -> bool;\n}\n\n"
        "impl<S: Sink> Sink for Box<S> {\n    fn matched(&mut self) -> bool { (**self).matched() }\n}\n\n"
        "pub struct Printer;\nimpl Sink for Printer {\n    fn matched(&mut self) -> bool { true }\n}\n\n"
        "pub struct Core<S> {\n    sink: S,\n}\n\nimpl<S: Sink> Core<S> {\n"
        "    fn sink_matched(&mut self) -> bool { self.sink.matched() }\n}\n", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}

    targets = {nodes[link["target"]].get("container") for link in graph["links"] if link.get("label") == "llama"
               and nodes[link["source"]].get("name") == "sink_matched"}

    assert "Sink" in targets and "Printer" in targets and "S" not in targets


def test_enum_constant_bodies_implement_the_interface_of_their_enum(tmp_path):
    (tmp_path / "Strategy.java").write_text("package app;\npublic interface Strategy { String translate(String f); }\n",
                                            encoding="utf-8")
    (tmp_path / "Policy.java").write_text(
        "package app;\npublic enum Policy implements Strategy {\n  IDENTITY() {\n"
        "    @Override public String translate(String f) { return f; }\n  },\n  UPPER() {\n"
        "    @Override public String translate(String f) { return up(f); }\n  };\n"
        "  static String up(String s) { return s; }\n}\n", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    implementations = [nodes[link["source"]] for link in graph["links"] if link.get("label") == "implementa"
                       and nodes[link["target"]].get("name") == "translate"]

    assert [node.get("container") for node in implementations] == ["Policy", "Policy"]


def test_a_bound_written_in_a_comment_does_not_type_the_field(tmp_path):
    # No call here has a receiver to type, so the literal mask is computed only for the bounds.
    source = ("// Earlier this was `impl<S: Other> Core<S>`.\nstruct Core<S> { sink: S }\n"
              "impl<S: Sink> Core<S> {\n    fn run(&self) {}\n}\n")
    (tmp_path / "core.rs").write_text(source, encoding="utf-8")
    facts = parse_file(tmp_path / "core.rs", "core.rs") or {}
    assert {member["name"]: member["type"] for member in facts["members"]}.get("sink") == "Sink"
