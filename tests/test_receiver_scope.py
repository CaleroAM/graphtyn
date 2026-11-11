"""A receiver's type comes from the declarations its call can see, the innermost first.

`x.save()` is typed by the `x` of its own block, function, type or file. A parameter or
local of another function never types it, and an untyped `x` nearer the call hides a
typed one further out. A field reached through an object keeps its file-wide lookup.
"""
import pytest

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.tree_sitter_backend import parse_file


def _receiver_types(tmp_path, name, text):
    """[(line, receiver, type)] for every call with a receiver, in source order."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    parsed = parse_file(path, name)
    if parsed is None:
        pytest.skip(f"no grammar for {name}")
    assert all("_scope" not in call for call in parsed["calls"])
    return [(call["line"], call["receiver"], call["receiver_type"])
            for call in sorted(parsed["calls"], key=lambda call: call["line"]) if call.get("receiver")]


def _by_line(tmp_path, name, text):
    typed = {}
    for line, _receiver, receiver_type in _receiver_types(tmp_path, name, text):
        typed.setdefault(line, []).append(receiver_type)
    return typed


JAVA = """class A {
  Repo field;
  void typed(Repo x) { x.save(); }
  void other(Other x) { x.save(); }
  void none() { x.save(); }
  void nested(Repo x) {
    for (Other y : ys) {
      Other x = y;
      x.save();
    }
    x.save();
  }
  void lambda(Repo x) { run(x -> x.save()); }
  void ownField() { field.save(); this.field.save(); }
}
"""


def test_java_parameters_stay_in_their_method_and_the_inner_block_wins(tmp_path):
    typed = _by_line(tmp_path, "A.java", JAVA)
    assert typed[3] == ["Repo"] and typed[4] == ["Other"]
    assert typed[5] == [""]  # `x` of the methods above is not visible here
    assert typed[9] == ["Other"] and typed[11] == ["Repo"]
    assert "" in typed[13]  # the lambda's own untyped `x` hides the method's
    assert typed[14] == ["Repo", "Repo"]  # a field is visible to every method of its class


CSHARP = """class A {
  Repo field;
  void Typed(Repo x) { x.Save(); }
  void Untyped() { var x = Load(); x.Save(); }
  void None() { x.Save(); }
  void Pattern() { if (!map.TryGet(out Other found)) return; found.Save(); }
  void Loop() { foreach (Other field in items) { field.Save(); } field.Save(); }
}
"""


def test_csharp_locals_hide_fields_only_inside_their_block(tmp_path):
    typed = _by_line(tmp_path, "A.cs", CSHARP)
    assert typed[3] == ["Repo"]
    assert typed[4] == [""] and typed[5] == [""]
    assert typed[6][-1] == "Other"  # an `out` variable outlives its `if`
    assert typed[7] == ["Other", "Repo"]


TYPESCRIPT = """class A {
  typed(x: Repo) { x.save(); }
  untyped(x) { x.save(); }
  shadow() {
    const x = new Other();
    if (ready) { const x = load(); x.save(); }
    x.save();
  }
  callbackType(done: (x: Repo) => void) { x.save(); }
}
function outer(x: Repo) { items.forEach(x => x.save()); x.save(); }
"""


def test_typescript_parameters_and_block_constants_are_scoped(tmp_path):
    typed = _by_line(tmp_path, "a.ts", TYPESCRIPT)
    assert typed[2] == ["Repo"] and typed[3] == [""]
    assert typed[6] == [""] and typed[7] == ["Other"]
    assert typed[9] == [""]  # the parameter of a function type declares nothing
    assert sorted(typed[11]) == ["", "", "Repo"]  # `items`, the arrow's own `x`, then the function's


JAVASCRIPT = """var shared = new Repo();
function creates() { var x = new Repo(); x.save(); }
function takes(x) { x.save(); }
function none() { x.save(); }
function usesShared() { shared.save(); }
function hidesShared(shared) { shared.save(); }
"""


def test_javascript_function_locals_do_not_leak_and_file_variables_stay_visible(tmp_path):
    typed = _by_line(tmp_path, "a.js", JAVASCRIPT)
    assert typed[2] == ["Repo"]
    assert typed[3] == [""] and typed[4] == [""]
    assert typed[5] == ["Repo"] and typed[6] == [""]


GO = """package a

type Service struct { repo *Repo }

func typed(x *Repo) { x.Save() }
func none() { x.Save(); repo.Save() }
func shadow() {
	x := &Other{}
	if x := load(); x != nil { x.Save() }
	x.Save()
}
func (s *Service) field() { s.repo.Save() }
"""


def test_go_parameters_short_declarations_and_struct_fields_are_scoped(tmp_path):
    typed = _by_line(tmp_path, "a.go", GO)
    assert typed[5] == ["Repo"]
    assert typed[6] == ["", ""]  # neither another function's parameter nor a struct field
    assert typed[9] == [""] and typed[10] == ["Other"]
    assert typed[12] == ["Repo"]  # reached through the receiver, it is still the field


RUST = """struct Service { repo: Repo }
fn typed(x: &Repo) { x.save(); }
fn none() { x.save(); repo.save(); }
fn shadow(x: Repo) {
    { let x = load(); x.save(); }
    x.save();
    let each = |x| x.save();
}
impl Service { fn field(&self) { self.repo.save(); } }
"""


def test_rust_bindings_shadow_by_block_and_closure(tmp_path):
    typed = _by_line(tmp_path, "a.rs", RUST)
    assert typed[2] == ["Repo"] and typed[3] == ["", ""]
    assert typed[5] == [""] and typed[6] == ["Repo"] and typed[7] == [""]
    assert typed[9] == ["Repo"]


CPP = """void prototype(Repo x);
class A { void declared(Other x); void inlined(Repo x) { x.save(); } };
void none() { x.save(); }
void shadow(Other x) {
  x.save();
  { auto x = load(); x.save(); }
  Repo local(1);
  local.save();
}
"""


def test_cpp_prototype_parameters_do_not_type_later_functions(tmp_path):
    typed = _by_line(tmp_path, "a.cpp", CPP)
    assert typed[2] == ["Repo"] and typed[3] == [""]
    assert typed[5] == ["Other"] and typed[6] == [""]
    assert typed[8] == ["Repo"]


PYTHON = """shared = Repo()


class A:
    attribute: Other = None

    def typed(self, x: Other):
        x.save()

    def none(self):
        x.save()
        attribute.save()
        shared.save()

    def untyped(self, shared):
        shared.save()
        self.repo = Repo()

    def field(self):
        self.repo.save()
"""


def test_python_methods_see_the_module_but_not_other_methods_or_the_class_body(tmp_path):
    typed = _by_line(tmp_path, "a.py", PYTHON)
    assert typed[8] == ["Other"]
    assert typed[11] == [""] and typed[12] == [""] and typed[13] == ["Repo"]
    assert typed[16] == [""]
    assert typed[20] == ["Repo"]  # `self.repo` set in another method


SCALA = """class A {
  def creates(): Unit = { var x = new Repo(); x.save() }
  def none(): Unit = { x.save() }
}
"""


def test_scala_locals_do_not_leak(tmp_path):
    typed = _by_line(tmp_path, "a.scala", SCALA)
    assert typed[2] == ["Repo"] and typed[3] == [""]


@pytest.mark.parametrize("name, text", [
    ("a.kt", "class A {\n  fun typed(x: Repo) { x.save() }\n  fun none() { x.save() }\n}\n"),
    ("a.swift", "class A {\n  func typed(x: Repo) { x.save() }\n  func none() { x.save() }\n}\n"),
    ("a.php", "<?php\nclass A {\n  function typed(Repo $x) { $x->save(); }\n  function none() { $x->save(); }\n}\n"),
])
def test_languages_without_declared_receivers_never_borrow_a_type(tmp_path, name, text):
    assert all(receiver_type in ("", "A") for _line, _receiver, receiver_type in _receiver_types(tmp_path, name, text))


def test_a_non_ascii_line_does_not_shift_the_scopes(tmp_path):
    text = ('class A {\n  void first(Repo x) { String s = "ñandú → ok"; x.save(); }\n'
            '  void second() { String s = "ñ"; x.save(); } void third(Other x) { x.save(); }\n}\n')
    assert _by_line(tmp_path, "A.java", text) == {2: ["Repo"], 3: ["", "Other"]}


def test_a_rebinding_still_reads_the_outer_variable_on_its_right_hand_side(tmp_path):
    rust = "fn update(v: FlagValue) {\n    let v = v.unwrap_value();\n    v.parse();\n}\n"
    assert _by_line(tmp_path, "a.rs", rust) == {2: ["FlagValue"], 3: [""]}
    go = "package a\n\nfunc run(c *Command) {\n\tc := c.Root()\n\tc.Execute()\n}\n"
    assert _by_line(tmp_path, "a.go", go) == {4: ["Command"], 5: [""]}


def test_rebinding_a_variable_to_itself_keeps_its_type(tmp_path):
    rust = ("fn configs(builder: SearcherBuilder) {\n    {\n        let mut builder = builder.clone();\n"
            "        builder.heap_limit(1);\n    }\n    let builder = &builder;\n    builder.build();\n}\n")
    typed = _by_line(tmp_path, "a.rs", rust)
    assert typed[4] == ["SearcherBuilder"] and typed[7] == ["SearcherBuilder"]
    go = "package a\n\nfunc run(cmd *Command) {\n\tgo func() {\n\t\tcmd := cmd\n\t\tcmd.Execute()\n\t}()\n}\n"
    assert _by_line(tmp_path, "a.go", go)[6] == ["Command"]


def test_a_cpp_smart_pointer_is_typed_by_what_it_points_to_and_a_container_is_not(tmp_path):
    cpp = ("struct Adapter {\n  std::shared_ptr<ActionInterface<F>> impl_;\n  std::vector<Repo> items_;\n"
           "  void run() { impl_->Perform(); items_.size(); }\n};\n")
    assert _by_line(tmp_path, "a.cc", cpp)[4] == ["ActionInterface", ""]


def test_a_field_declared_below_its_use_and_a_method_return_type_are_visible_in_the_class(tmp_path):
    java = ("class A {\n  void run() { repo.save(); find().save(); }\n  Other find() { return null; }\n"
            "  void wild(TypeAdapter<?> delegate, Map<String, Repo> byName) { delegate.read(); byName.get(); }\n"
            "  private Repo repo;\n}\n")
    typed = _by_line(tmp_path, "A.java", java)
    assert typed[2] == ["Repo", "Other"]
    assert typed[4] == ["TypeAdapter", "Map"]


def test_a_java_var_built_with_generic_arguments_or_an_anonymous_body_keeps_its_type(tmp_path):
    java = ("class A {\n  void run(Entry<String, String>[] entries) {\n    var map = new LinkedTreeMap<String, String>(true);\n"
            "    for (var entry : entries) {\n      map.put(entry);\n    }\n"
            "    var token = new TypeToken<Optional<String>>() {};\n    token.getType();\n  }\n}\n")
    typed = _by_line(tmp_path, "A.java", java)
    assert typed[5] == ["LinkedTreeMap"] and typed[8] == ["TypeToken"]


def test_a_cpp_method_defined_outside_its_class_sees_the_class_fields(tmp_path):
    cpp = ("class Worker {\n public:\n  int inlined() { return late_.Get(); }\n  int Role();\n private:\n"
           "  Handle handle_;\n  Late late_;\n};\nint Worker::Role() { return handle_.Get(); }\n"
           "int unrelated() { return handle_.Get(); }\n")
    assert _by_line(tmp_path, "a.cc", cpp) == {3: ["Late"], 9: ["Handle"], 10: [""]}


def test_go_assertions_pointers_and_new_declare_a_type_but_a_call_result_does_not(tmp_path):
    go = ("package a\n\nfunc run(in interface{}) {\n\tc := in.(*Command)\n\tc.Execute()\n\tvar root = &Command{}\n"
          "\troot.Execute()\n\tbuf := new(bytes.Buffer)\n\tbuf.String()\n\tflags := c.Flags()\n\tflags.Parse()\n}\n")
    typed = _by_line(tmp_path, "a.go", go)
    assert typed[5] == ["Command"] and typed[7] == ["Command"] and typed[9] == ["Buffer"]
    assert typed[11] == [""]


def test_typescript_annotated_constants_are_typed_but_arrays_are_not_their_element(tmp_path):
    text = ("function run() {\n  const repo: Repo = load();\n  repo.save();\n  const many: Repo[] = [];\n  many.push(repo);\n}\n"
            "function other(items: Repo[]) { items.push(null); }\n")
    assert _by_line(tmp_path, "a.ts", text) == {3: ["Repo"], 5: [""], 7: [""]}


def test_a_same_named_variable_elsewhere_no_longer_draws_a_call_edge(tmp_path):
    files = {
        "app/Repo.java": "package app;\n\npublic class Repo {\n  public void save() { }\n}\n",
        "app/Cache.java": "package app;\n\npublic class Cache {\n  public void save() { }\n}\n",
        "app/Service.java": "package app;\n\npublic class Service {\n  void store(Repo target) {\n    target.save();\n  }\n"
                            "  void flush(Cache target) {\n    target.save();\n  }\n}\n",
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {(nodes[link["source"]]["name"], nodes[link["target"]].get("container"), link.get("confidence"))
             for link in graph["links"] if link.get("label") == "llama"}
    assert calls == {("store", "Repo", "EXTRACTED"), ("flush", "Cache", "EXTRACTED")}
