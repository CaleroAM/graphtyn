"""Optional tree-sitter structural extraction for high-value languages.

The module deliberately imports tree-sitter lazily so the core MCP/CLI keeps
working with zero optional dependencies. Callers receive ``None`` when the
runtime or a grammar is unavailable and can fall back to legacy extractors.
"""

from __future__ import annotations

import bisect
import importlib
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


PARSER_VERSION = "treesitter-v29-literal-free-declarations"


_TYPE_NAME_END = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.<>")


@dataclass(frozen=True)
class LanguagePack:
    """Declarative contract between a file extension and its grammar features."""

    name: str
    extensions: tuple[str, ...]
    grammar_module: str
    factories: tuple[tuple[str, str], ...] = ()
    capabilities: tuple[str, ...] = ("symbols", "imports", "calls", "members")

    def factory_for(self, extension: str) -> str:
        return dict(self.factories).get(extension, "language")


LANGUAGE_PACKS = (
    LanguagePack("csharp", (".cs",), "tree_sitter_c_sharp", capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("javascript", (".js", ".jsx"), "tree_sitter_javascript",
                 capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("typescript", (".ts", ".tsx"), "tree_sitter_typescript",
                 factories=((".ts", "language_typescript"), (".tsx", "language_tsx")),
                 capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("php", (".php",), "tree_sitter_php", factories=((".php", "language_php"),),
                 capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("python", (".py",), "tree_sitter_python", capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("java", (".java",), "tree_sitter_java", capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("go", (".go",), "tree_sitter_go", capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("rust", (".rs",), "tree_sitter_rust", capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("c", (".c", ".h"), "tree_sitter_c"),
    LanguagePack("cpp", (".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"), "tree_sitter_cpp",
                 capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("ruby", (".rb",), "tree_sitter_ruby",
                 capabilities=("symbols", "imports", "calls", "inheritance", "mixins")),
    # JVM/Apple languages: classes, objects, protocols/traits, functions,
    # calls, imports and inheritance. Members are not modelled yet.
    LanguagePack("kotlin", (".kt", ".kts"), "tree_sitter_kotlin",
                 capabilities=("symbols", "imports", "calls", "inheritance")),
    LanguagePack("swift", (".swift",), "tree_sitter_swift",
                 capabilities=("symbols", "imports", "calls", "inheritance")),
    LanguagePack("scala", (".scala",), "tree_sitter_scala",
                 capabilities=("symbols", "imports", "calls", "inheritance")),
)

_PACK_BY_EXTENSION = {
    extension: pack for pack in LANGUAGE_PACKS for extension in pack.extensions
}
TREE_SITTER_EXTENSIONS = frozenset(_PACK_BY_EXTENSION)

_CPP_HEADER_CUES = re.compile(
    rb"(?:\bnamespace\s+[A-Za-z_]|\btemplate\s*<|\bclass\s+[A-Za-z_]|"
    rb"\b(?:constexpr|consteval|decltype|typename|nullptr|noexcept|static_cast|"
    rb"dynamic_cast|reinterpret_cast)\b|\bstd::|\busing\s+[A-Za-z_]\w*\s*=|"
    rb"\b(?:public|private|protected)\s*:)",
)


def language_pack_contract() -> tuple[dict[str, Any], ...]:
    """Return the stable, serializable language-pack contract."""
    return tuple({
        "name": pack.name,
        "extensions": pack.extensions,
        "grammar_module": pack.grammar_module,
        "capabilities": pack.capabilities,
    } for pack in LANGUAGE_PACKS)

_RUNTIME_BUILTINS = {
    ".py": {
        "abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray", "bytes",
        "callable", "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir",
        "divmod", "enumerate", "eval", "exec", "filter", "float", "format", "frozenset",
        "getattr", "globals", "hasattr", "hash", "help", "hex", "id", "input", "int",
        "isinstance", "issubclass", "iter", "len", "list", "locals", "map", "max",
        "memoryview", "min", "next", "object", "oct", "open", "ord", "pow", "print",
        "property", "range", "repr", "reversed", "round", "set", "setattr", "slice",
        "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
    },
}
# Kernel/Module methods Ruby code calls without a receiver. A project method
# with the same name (e.g. Parameters#require) is only its target when the call
# has a receiver, so these are flagged for bare calls only.
_RUBY_SELF_RECEIVERS = {"self", "dup", "clone"}
_SELF_RECEIVERS = {"python": {"self", "cls"}, "php": {"$this"}, "swift": {"self"}, "rust": {"self"}}
_RUBY_BARE_BUILTINS = {
    "require", "require_relative", "load", "include", "extend", "prepend", "raise", "fail",
    "puts", "print", "p", "pp", "printf", "sprintf", "format", "sleep", "rand", "loop",
    "lambda", "proc", "catch", "throw", "binding", "block_given?", "attr_accessor",
    "attr_reader", "attr_writer", "private", "protected", "public", "module_function",
    "private_constant", "define_method", "instance_variable_get", "instance_variable_set",
}


_JVM_APPLE_PACKS = {"kotlin", "swift", "scala"}


def _jvm_apple_kind(source: bytes, node, kind: str) -> str:
    """Kotlin and Swift reuse class_declaration for interfaces, structs and enums."""
    declared = node.child_by_field_name("declaration_kind")
    keyword = _text(source, declared) if declared is not None else next(
        (child.type for child in node.children if child.type in {"interface", "enum", "fun"}), "")
    modifiers = next((child for child in node.named_children if child.type == "modifiers"), None)
    if not keyword and modifiers is not None and re.search(r"\benum\b", _text(source, modifiers)):
        keyword = "enum"  # Kotlin: `enum class` carries enum as a class modifier.
    return {"interface": "interface", "struct": "struct", "enum": "enum",
            "protocol": "interface", "extension": "class"}.get(keyword, kind)


def missing_grammars() -> list[str]:
    """Language packs that cannot load: their files fall back to the parser without exact calls."""
    modules = ["tree_sitter", *(pack.grammar_module for pack in LANGUAGE_PACKS)]
    return sorted({module for module in modules if importlib.util.find_spec(module) is None})


def _pack_for_source(ext: str, source: bytes) -> LanguagePack | None:
    """Choose C++ for conventional ``.h`` files that contain C++ syntax."""
    if ext == ".h" and _CPP_HEADER_CUES.search(source):
        return next(pack for pack in LANGUAGE_PACKS if pack.name == "cpp")
    return _PACK_BY_EXTENSION.get(ext)


def _language_for_extension(ext: str, source: bytes = b""):
    from tree_sitter import Language

    pack = _pack_for_source(ext, source)
    if pack is None:
        return None
    grammar = importlib.import_module(pack.grammar_module)
    factory = getattr(grammar, pack.factory_for(ext))
    return Language(factory())


_ESM_PACKS = {"javascript", "typescript"}
# (name, type) declarations, then (type, name) ones: Go writes `c *Command` and `c := &Command{}`.
_DECLARATION_PATTERNS = {
    "default": (r"(?=\bvar\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*))",
                r"(?=\b([A-Z][A-Za-z0-9_.<>]*)\s+([A-Za-z_][A-Za-z0-9_]*)\b)"),
    "go": (r"(?=\b([a-z_][A-Za-z0-9_]*)(?:\s+(?:\*|\[\])?|\s*:=\s*&?)(?:[a-z_][A-Za-z0-9_]*\.)?([A-Z][A-Za-z0-9_]*)\b)",
           r"(?=\b([A-Z][A-Za-z0-9_.<>]*)\s+([A-Za-z_][A-Za-z0-9_]*)\b)"),
}
_OWNER_DECLARATIONS = {"rust": "impl_item", "go": "type_spec"}
_HERITAGE_FIELDS = ("bases", "superclass", "superclasses", "interfaces", "bounds")
_HERITAGE_TYPES = frozenset({"base_list", "superclass", "base_class_clause", "delegation_specifiers", "extends_clause",
                             "class_heritage", "base_clause", "class_interface_clause", "super_interfaces",
                             "extends_interfaces"})


def _heritage_nodes(node: Any) -> list[Any]:
    """Every clause naming a declaration's bases: Java and PHP write `extends` and `implements` apart."""
    found = [child for child in (node.child_by_field_name(field) for field in _HERITAGE_FIELDS) if child is not None]
    ids = {child.id for child in found}
    return found + [child for child in node.named_children if child.type in _HERITAGE_TYPES and child.id not in ids]


def _go_receiver(source: bytes, node: Any) -> tuple[str, str]:
    """(variable, type) of the Go method around a node: `func (c *List[T]) Run()` gives ("c", "List")."""
    while node is not None and node.type != "method_declaration":
        node = node.parent
    receiver = node.child_by_field_name("receiver") if node is not None else None
    declaration = next((child for child in receiver.named_children if child.type == "parameter_declaration"), None) \
        if receiver is not None else None
    if declaration is None:
        return "", ""
    variable, written = declaration.child_by_field_name("name"), declaration.child_by_field_name("type")
    names = re.findall(r"[A-Za-z_]\w*", _text(source, written).split("[", 1)[0]) if written is not None else []
    return (_text(source, variable) if variable is not None else ""), (names[-1] if names else "")


def _go_type(source: bytes, node: Any) -> tuple[str, list[str]]:
    """Kind of a Go `type` spec and the types a struct embeds, whose methods it promotes."""
    written = node.child_by_field_name("type")
    kind = {"struct_type": "struct", "interface_type": "interface"}.get(written.type if written is not None else "", "type")
    fields = next((child for child in written.named_children if child.type == "field_declaration_list"), None) \
        if kind == "struct" else None
    embedded = [_text(source, field.child_by_field_name("type")).lstrip("*").rsplit(".", 1)[-1]
                for field in (fields.named_children if fields is not None else [])
                if field.type == "field_declaration" and field.child_by_field_name("name") is None
                and field.child_by_field_name("type") is not None]
    return kind, embedded


def _without_literals(root: Any, lines: list[str]) -> str:
    """The source with comments and string literals blanked, every line keeping its length.

    Receiver types are inferred from `Type name` declarations found by pattern; a message such
    as "TypeToken type argument must not..." made `type` a TypeToken.
    """
    masked, encoded = [list(line) for line in lines], [line.encode("utf-8") for line in lines]

    def column(row: int, offset: int) -> int:
        return len(encoded[row][:offset].decode("utf-8", errors="replace")) if row < len(encoded) else 0

    stack = [root]
    while stack:
        node = stack.pop()
        if "comment" in node.type or "string" in node.type or node.type in {"heredoc_body", "char_literal", "character_literal"}:
            (start_row, start_col), (end_row, end_col) = node.start_point, node.end_point
            for row in range(start_row, min(end_row, len(masked) - 1) + 1):
                first = column(row, start_col) if row == start_row else 0
                last = column(row, end_col) if row == end_row else len(masked[row])
                masked[row][first:last] = " " * max(0, last - first)
            continue
        stack.extend(node.children)
    return "\n".join("".join(line) for line in masked)


def _with_trait_impls(pack: str, symbols: list[dict[str, Any]], root: Any, source: bytes) -> list[dict[str, Any]]:
    """`impl fmt::Display for Child` makes Child implement Display, when Child is declared in the file."""
    if pack != "rust":
        return symbols
    types = {symbol["name"]: symbol for symbol in symbols if symbol.get("kind") in {"struct", "enum", "type", "interface"}}
    stack = [root]
    while stack:
        node = stack.pop()
        trait = node.child_by_field_name("trait") if node.type == "impl_item" else None
        owner = types.get(_name(source, node)) if trait is not None else None
        if owner is not None:
            names = re.findall(r"[A-Za-z_]\w*", _text(source, trait).split("<", 1)[0])
            if names and names[-1] not in owner["bases"]:
                owner["bases"].append(names[-1])
        stack.extend(node.named_children)
    return symbols


def _python_members(pack: str, root: Any, source: bytes, rel_path: str) -> list[dict[str, Any]]:
    """Typed attributes of a Python class: `x: Router = ...` in its body, `self.x: T` or `self.x = T()` in a method."""
    if pack != "python":
        return []
    members, stack = [], [root]
    while stack:
        node = stack.pop()
        stack.extend(node.named_children)
        if node.type != "assignment":
            continue
        left, written, right = (node.child_by_field_name(field) for field in ("left", "type", "right"))
        owner = node.parent
        while owner is not None and owner.type != "class_definition":
            owner = owner.parent
        if owner is None or left is None:
            continue
        if left.type == "attribute" and _text(source, left.child_by_field_name("object")) in {"self", "cls"}:
            name = _text(source, left.child_by_field_name("attribute"))
        elif left.type == "identifier" and node.parent is not None and node.parent.parent is not None \
                and node.parent.parent.parent is not None and node.parent.parent.parent.id == owner.id:
            name = _text(source, left)
        else:
            continue
        type_name = _text(source, written).strip() if written is not None else ""
        if not type_name and right is not None and right.type == "call":
            callee = re.findall(r"[A-Za-z_]\w*", _text(source, right.child_by_field_name("function")))
            type_name = callee[-1] if callee and callee[-1][:1].isupper() else ""
        if name and type_name:
            line = node.start_point.row + 1
            members.append({"container": _name(source, owner), "name": name, "kind": "field", "type": type_name,
                            "file": rel_path, "line": line, "end_line": node.end_point.row + 1,
                            "signature": " ".join(_text(source, node).split())[:200],
                            "evidence": " ".join(_text(source, node).split())[:200], "parser": "tree-sitter"})
    return members


def _python_bases(source: bytes, superclasses: Any) -> list[str]:
    """`class Flask(App, mixins.M, Generic[T], metaclass=Meta)` names App, M and Generic."""
    bases = []
    for argument in superclasses.named_children:
        if argument.type == "subscript":
            argument = argument.child_by_field_name("value") or argument
        if argument.type == "attribute":
            argument = argument.child_by_field_name("attribute") or argument
        if argument.type == "identifier":
            bases.append(_text(source, argument))
    return bases


def _parser_for(language):
    from tree_sitter import Parser

    try:
        return Parser(language)
    except TypeError:  # Compatibility with tree-sitter 0.22.
        parser = Parser()
        parser.language = language
        return parser


def _text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _name(source: bytes, node) -> str:
    if node.type == "impl_item":  # `impl<T> fmt::Display for Child<T>` belongs to Child
        names = re.findall(r"[A-Za-z_]\w*", _text(source, node.child_by_field_name("type")).split("<", 1)[0])
        return names[-1] if names else ""
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(source, named)
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        if declarator.type in {"identifier", "field_identifier", "type_identifier"}:
            return _text(source, declarator)
        named = declarator.child_by_field_name("name")
        if named is not None:
            return _text(source, named)
        nested = declarator.child_by_field_name("declarator")
        if nested is None:
            candidates = [child for child in declarator.named_children
                          if child.type in {"identifier", "field_identifier", "type_identifier"}]
            return _text(source, candidates[-1]) if candidates else ""
        declarator = nested
    return ""


def _parameters(node):
    parameters = node.child_by_field_name("parameters")
    declarator = node.child_by_field_name("declarator")
    while parameters is None and declarator is not None:
        parameters = declarator.child_by_field_name("parameters")
        declarator = declarator.child_by_field_name("declarator")
    return parameters


_TEMPLATE_TARGETS = {"template_function", "template_method", "qualified_identifier", "field_expression", "generic_function"}
_TEMPLATE_ARGS = re.compile(r"<[^<>()]*>")


def _without_template_args(raw: str) -> str:
    """`detail::write<Char>` calls `write`: its template arguments are not the callee."""
    while (bare := _TEMPLATE_ARGS.sub("", raw)) != raw:
        raw = bare
    return re.sub(r"\btemplate\s+", "", raw)  # `s.template m<T>()`


# Java `this.own()` and PHP `$this->own()` / `Base::make()` keep the callee in `name` and the
# receiver in `object` or `scope`; PHP's `parent::` and `self::` name the caller's own classes.
_PHP_SCOPES = {"parent": "super", "self": "$this", "static": "$this"}


def _member_call(source: bytes, node) -> tuple[str, str] | None:
    """(callee, receiver) of a call written as `object.name(...)` or `scope::name(...)`."""
    name = node.child_by_field_name("name")
    if name is None or node.child_by_field_name("function") is not None:
        return None
    receiver = node.child_by_field_name("object") or node.child_by_field_name("scope")
    text = _text(source, receiver) if receiver is not None else ""
    return _text(source, name), _PHP_SCOPES.get(text, text) if receiver is not None and receiver.type == "relative_scope" else text


def _call_name(source: bytes, node, ruby: bool = False) -> str:
    member = _member_call(source, node)
    if member:
        return member[0]
    target = node.child_by_field_name("function") or node.child_by_field_name("method")
    if target is None and node.named_child_count:
        target = node.named_children[0]
    raw = _text(source, target) if target is not None else ""
    # foo.Bar<T> / obj.method / method -> final callable identifier.
    import re
    # For ``new List<Artwork>()`` the callable is List, not the final generic
    # argument Artwork. Treating the latter as a constructor created false
    # project edges and large ambiguous candidate sets.
    if target is not None and target.type in ("generic_name", "generic_type"):
        named = target.child_by_field_name("name")
        if named is None and target.named_child_count:
            named = target.named_children[0]
        raw = _text(source, named) if named is not None else raw.split("<", 1)[0]
    # A Ruby method name keeps its ! or ? suffix: route! and route are different methods.
    if target is not None and target.type in _TEMPLATE_TARGETS:
        raw = _without_template_args(raw)
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*[!?]?" if ruby else r"[A-Za-z_][A-Za-z0-9_]*", raw)
    return names[-1] if names else ""


def _ancestor_name(source: bytes, node, types: set[str]) -> str:
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in types:
            return _name(source, ancestor)
        if _TEST_BLOCKS in types and ancestor.type in {"call", "call_expression"}:
            name = _test_block_name(source, ancestor)
            if name:
                return name
        ancestor = ancestor.parent
    return ""


# Test frameworks declare examples with a call and a block: `test "saves" do`, `it("saves", () => {})`.
# In a test file each one is the caller of what it runs, as Minitest's generated `test_saves` method is.
_TEST_BLOCKS = "test_block"
_TEST_BLOCK_PACKS = {"ruby", "javascript", "typescript"}
_TEST_EXAMPLES = {"test": "test", "it": "it", "specify": "it", "example": "it", "scenario": "scenario"}
_TEST_HOOKS = {"setup", "teardown", "before", "after", "around", "beforeEach", "afterEach", "beforeAll", "afterAll"}
_TEST_FILE = re.compile(r"(?:^|/)(?:tests?|specs?|__tests__)(?:/|$)|[_.](?:test|spec)s?\.[^/.]+$", re.I)


def _test_block_name(source: bytes, node) -> str:
    """`test_saves_record` for `test "saves record" do`, `setup_block` for `setup do`, else ''.

    A hook block is not named like the framework method it calls (`setup`), or that call
    would resolve to the block itself.
    """
    if node.type == "call":
        method = node.child_by_field_name("method")
        if node.child_by_field_name("receiver") is not None or method is None or node.child_by_field_name("block") is None:
            return ""
        verb, arguments = _text(source, method), node.child_by_field_name("arguments")
    else:
        function, arguments = node.child_by_field_name("function"), node.child_by_field_name("arguments")
        if function is None or function.type != "identifier" or arguments is None or not any(
                child.type in {"arrow_function", "function_expression", "function"} for child in arguments.named_children):
            return ""
        verb = _text(source, function)
    if verb in _TEST_HOOKS:
        return f"{verb}_block"
    first = arguments.named_children[0] if verb in _TEST_EXAMPLES and arguments is not None and arguments.named_child_count else None
    if first is None or first.type not in {"string", "template_string", "string_literal"}:
        return ""
    title = re.sub(r"\W+", "_", _text(source, first).strip("'\"`")).strip("_").lower()[:80]
    return f"{_TEST_EXAMPLES[verb]}_{title}" if title else ""


def _test_block_symbol(ctx: "_FileContext", node, line: int, end_line: int, evidence: str) -> Optional[dict[str, Any]]:
    if _TEST_BLOCKS not in ctx.callable_declarations:
        return None
    name = _test_block_name(ctx.source, node)
    return {"name": name, "kind": "method", "file": ctx.rel_path, "line": line, "end_line": end_line,
            "evidence": evidence, "bases": [], "parser": "tree-sitter", "test_block": True,
            "container": _ancestor_name(ctx.source, node, ctx.type_declarations),
            "namespace": _ancestor_namespace(ctx.source, node)} if name else None


def _ancestor_namespace(source: bytes, node) -> str:
    """Return the lexical namespace path for a declaration."""
    names: list[str] = []
    ancestor = node.parent
    namespace_types = {
        "namespace_declaration", "file_scoped_namespace_declaration", "namespace_definition",
        "module",
    }
    while ancestor is not None:
        if ancestor.type in namespace_types:
            name_node = ancestor.child_by_field_name("name")
            if name_node is not None:
                names.insert(0, _text(source, name_node))
        ancestor = ancestor.parent
    return "::".join(name for name in names if name)


def _parameter_names(source: bytes, parameters) -> set[str]:
    """Extract declared parameter names without confusing type identifiers."""
    if parameters is None:
        return set()
    names: set[str] = set()
    for parameter in parameters.named_children:
        name_node = parameter.child_by_field_name("name")
        if name_node is None:
            declared_name = _name(source, parameter)
            if declared_name:
                names.add(declared_name.lstrip("$"))
                continue
        if name_node is None and parameter.type in {"identifier", "variable_name"}:
            name_node = parameter
        if name_node is None:
            pending = list(parameter.named_children)
            while pending and name_node is None:
                child = pending.pop(0)
                if child.type in {"identifier", "variable_name"}:
                    name_node = child
                    break
                pending[0:0] = child.named_children
        if name_node is not None:
            names.add(_text(source, name_node).lstrip("$"))
    return names


def _is_parameter_binding(source: bytes, node, name: str, callable_types: set[str]) -> bool:
    """Whether a call name is a parameter in its current lexical closure."""
    ancestor = node.parent
    scope_types = callable_types | {
        "lambda", "lambda_expression", "anonymous_function", "arrow_function",
    }
    while ancestor is not None:
        if ancestor.type in scope_types:
            parameters = _parameters(ancestor)
            if name in _parameter_names(source, parameters):
                return True
        ancestor = ancestor.parent
    return False


def _call_binding_metadata(source: bytes, node, name: str, callable_types: set[str], ext: str) -> dict[str, Any]:
    return {
        "call_kind": node.type,
        "bound_locally": _is_parameter_binding(source, node, name, callable_types),
        "runtime_builtin": name in _RUNTIME_BUILTINS.get(ext, set()),
    }


# Ruby calls a zero-argument method without parentheses or receiver
# (`destroy_associations`, `persisted? && destroy_row`); tree-sitter reports a
# bare identifier. It is a call when used as a statement or condition operand
# and is neither a parameter nor a local assigned in the enclosing method.
_RUBY_BARE_CALL_PARENTS = frozenset({
    "body_statement", "then", "else", "begin", "if_modifier", "unless_modifier", "while_modifier",
    "until_modifier", "binary", "unary", "conditional", "parenthesized_statements", "return"})


def _ruby_method_locals(source: bytes, method) -> set[str]:
    names: set[str] = set()
    stack = [method]
    while stack:
        current = stack.pop()
        if current.type in {"assignment", "operator_assignment"}:
            left = current.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                names.add(_text(source, left))
        elif current.type in {"identifier"} and current.parent is not None and current.parent.type in {
                "method_parameters", "optional_parameter", "keyword_parameter", "splat_parameter",
                "hash_splat_parameter", "block_parameter", "block_parameters", "lambda_parameters"}:
            names.add(_text(source, current))
        stack.extend(current.named_children)
    return names


def _is_ruby_bare_call(ctx: "_FileContext", node, locals_cache: dict[int, set[str]]) -> bool:
    parent = node.parent
    if parent is None or parent.type not in _RUBY_BARE_CALL_PARENTS:
        return False
    method = parent
    while method is not None and method.type not in {"method", "singleton_method"}:
        method = method.parent
    if method is None:
        return False
    if method.start_byte not in locals_cache:
        locals_cache[method.start_byte] = _ruby_method_locals(ctx.source, method)
    return _text(ctx.source, node) not in locals_cache[method.start_byte]


def _ruby_bare_call_facts(ctx: "_FileContext", node, line: int, evidence: str,
                          calls: list, operations: list) -> None:
    name = _text(ctx.source, node)
    caller = _ancestor_name(ctx.source, node, ctx.callable_declarations)
    container = _ancestor_name(ctx.source, node, ctx.type_declarations)
    calls.append({"name": name, "line": line, "evidence": evidence, "receiver": "", "receiver_chain": [],
                  "argument_count": 0, "caller": caller, "container": container,
                  **_call_binding_metadata(ctx.source, node, name, ctx.callable_declarations, ctx.ext)})
    operations.append({"kind": "call", "name": name, "line": line, "text": name,
                       "caller": caller, "container": container})


@dataclass(frozen=True)
class _FileContext:
    """What every node handler needs to know about the file being parsed."""
    source: bytes
    rel_path: str
    ext: str
    pack: Any
    type_declarations: frozenset
    callable_declarations: frozenset


_MEMBER_TYPES = frozenset({"field_declaration", "property_declaration", "event_declaration", "event_field_declaration",
                           "public_field_definition", "field_definition"})


def _member_type(ctx: _FileContext, node) -> str:
    """A field's written type; `base = new Base()` in JavaScript types it by its constructor."""
    type_node = node.child_by_field_name("type")
    if type_node is not None:
        return _text(ctx.source, type_node).lstrip(":").strip()
    value = node.child_by_field_name("value")
    if value is not None and value.type == "new_expression":
        return _call_name(ctx.source, value)
    return ""


def _member_facts(ctx: _FileContext, node, line: int, end_line: int, evidence: str,
                  members: list, symbols: list) -> None:
    """Fields, properties and events of a type, plus C++ in-class method declarations."""
    type_node = node.child_by_field_name("type")
    variable_declaration = None
    if node.type in {"field_declaration", "event_field_declaration"}:
        variable_declaration = next((child for child in node.named_children if child.type == "variable_declaration"), None)
        if type_node is None and variable_declaration is not None:
            type_node = variable_declaration.child_by_field_name("type")
    type_name = _text(ctx.source, type_node) if type_node is not None else _member_type(ctx, node)
    if node.type == "public_field_definition":
        type_name = _member_type(ctx, node)
    container = _ancestor_name(ctx.source, node, ctx.type_declarations)
    # Go and Rust fields, and TypeScript and JavaScript class fields, name themselves directly.
    own_name = node.child_by_field_name("name") or node.child_by_field_name("property")
    if container and type_name:
        if node.type in {"property_declaration", "event_declaration"}:
            name_node = node.child_by_field_name("name")
            names = [_text(ctx.source, name_node)] if name_node is not None else [
                _text(ctx.source, element.child_by_field_name("name") or element).lstrip("$")
                for element in node.named_children if element.type == "property_element"]  # PHP `Base $base`
        elif variable_declaration is None and node.child_by_field_name("declarator") is None and own_name is not None:
            names = [_text(ctx.source, own_name)]
        else:
            names = []
            if variable_declaration is not None:
                for declaration in variable_declaration.named_children:
                    if declaration.type == "variable_declarator":
                        name_node = declaration.child_by_field_name("name")
                        if name_node is not None:
                            names.append(_text(ctx.source, name_node))
            else:
                declarator = node.child_by_field_name("declarator")
                if declarator is not None and declarator.type != "function_declarator":
                    member_name = _name(ctx.source, node)
                    if member_name:
                        names.append(member_name)
        for member_name in names:
            kind = "event" if node.type.startswith("event_") else ("property" if node.type == "property_declaration" else "field")
            members.append({
                "container": container, "name": member_name, "kind": kind,
                "type": type_name, "file": ctx.rel_path, "line": line,
                "end_line": end_line, "signature": evidence,
                "evidence": evidence, "parser": "tree-sitter",
            })
    declarator = node.child_by_field_name("declarator")
    if (container and declarator is not None
            and declarator.type == "function_declarator"):
        method_name = _name(ctx.source, node)
        parameters = _parameters(node)
        if method_name:
            symbols.append({
                "name": method_name, "kind": "method", "file": ctx.rel_path,
                "line": line, "end_line": end_line, "evidence": evidence,
                "bases": [], "parser": "tree-sitter", "container": container,
                "scope": "", "namespace": _ancestor_namespace(ctx.source, node),
                "parameter_count": parameters.named_child_count if parameters is not None else None,
                "required_parameter_count": parameters.named_child_count if parameters is not None else None,
                "is_constructor": False, "signature": evidence,
            })


def _symbol_fact(ctx: _FileContext, node, line: int, end_line: int, evidence: str) -> Optional[dict[str, Any]]:
    """A declared class, function, method or similar, with bases and signature."""
    name = _name(ctx.source, node)
    if node.type in {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier"} \
            and node.child_by_field_name("body") is None:
        name = ""
    if not name and node.type == "constructor_declaration":
        name_node = node.child_by_field_name("name")
        name = _text(ctx.source, name_node) if name_node else "constructor"
    if name:
        kind = _SYMBOL_TYPES[node.type]
        if ctx.pack.name in _JVM_APPLE_PACKS:
            kind = _jvm_apple_kind(ctx.source, node, kind)
        if node.type == "function_definition" or (
                ctx.pack.name in _JVM_APPLE_PACKS and node.type == "function_declaration"):
            ancestor = node.parent
            while ancestor is not None:
                if ancestor.type in ctx.type_declarations:
                    kind = "method"
                    break
                ancestor = ancestor.parent
        bases = []
        heritage = _heritage_nodes(node)
        if heritage:
            base_node = heritage[0]
            if ctx.pack.name == "ruby":
                qualified = re.findall(
                    r"[A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*",
                    _text(ctx.source, base_node),
                )
                bases = qualified[-1:]  # `ActiveJob::Base`: the qualifier picks among the many `Base`
            elif ctx.pack.name == "python":
                bases = _python_bases(ctx.source, base_node)
            else:
                bases = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", " ".join(_text(ctx.source, item) for item in heritage))
                bases = [base for base in bases
                         if base not in {"public", "protected", "private", "virtual", "final", "extends", "implements", "with"}]
        if ctx.pack.name == "swift":
            bases = [_text(ctx.source, child.child_by_field_name("inherits_from") or child).split("<", 1)[0]
                     for child in node.named_children if child.type == "inheritance_specifier"]
        if node.type == "type_spec":
            kind, bases = _go_type(ctx.source, node)
        parameters = _parameters(node)
        parameter_count = parameters.named_child_count if parameters is not None else None
        required_parameter_count = None
        if parameters is not None:
            required_parameter_count = sum(
                child.type not in ("optional_parameter", "default_parameter")
                and "=" not in _text(ctx.source, child)
                for child in parameters.named_children
            )
        body = node.child_by_field_name("body")
        declaration_text = ctx.source[node.start_byte:body.start_byte].decode("utf-8", errors="replace") if body is not None else _text(ctx.source, node)
        signature = " ".join(declaration_text.split())
        signature = signature.split("{", 1)[0].split("=>", 1)[0].strip()[:300]
        return {
            "name": name,
            "kind": kind,
            "file": ctx.rel_path,
            "line": line,
            "end_line": end_line,
            "evidence": evidence,
            "bases": bases,
            "parser": "tree-sitter",
            "container": (_go_receiver(ctx.source, node)[1] if ctx.pack.name == "go" and node.type == "method_declaration"
                          else _ancestor_name(ctx.source, node, ctx.type_declarations)),
            "scope": _ancestor_name(ctx.source, node, ctx.callable_declarations),
            "namespace": _ancestor_namespace(ctx.source, node),
            "parameter_count": parameter_count,
            "required_parameter_count": required_parameter_count,
            "is_constructor": node.type == "constructor_declaration",
            "signature": signature or evidence,
            # `{delay(n) {...}}` is reached as `options.delay(n)`, never by a bare `delay(n)`.
            **({"object_member": True} if node.type == "method_definition" and node.parent is not None
               and node.parent.type == "object" else {}),
        }
    return None


def _call_facts(ctx: _FileContext, node, line: int, evidence: str, calls: list, operations: list,
                imports: list, ruby_mixins: list, symbols: list | None = None) -> None:
    """A call or instantiation, its operation, Ruby require/mixin side facts and test blocks."""
    block = _test_block_symbol(ctx, node, line, node.end_point.row + 1, evidence)
    if block and symbols is not None:
        symbols.append(block)
    name = _call_name(ctx.source, node, ruby=ctx.pack.name == "ruby")
    if name:
        target = node.child_by_field_name("function") or node.child_by_field_name("method")
        raw_target = _text(ctx.source, target) if target is not None else ""
        if target is not None and target.type in _TEMPLATE_TARGETS:
            raw_target = _without_template_args(raw_target)
        target_names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw_target)
        chain = target_names[:-1]
        receiver_node = node.child_by_field_name("receiver")
        receiver = (_text(ctx.source, receiver_node) if receiver_node is not None
                    else (chain[-1] if chain else ""))
        member = _member_call(ctx.source, node)
        if member:
            # `this.base.helper()` is sent to `base`, reached through `this`, as in other languages.
            chain = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", member[1])
            receiver = member[1] if member[1] in {"super", "$this"} else (chain[-1] if chain else "")
        if ctx.pack.name == "ruby" and receiver in _RUBY_SELF_RECEIVERS:
            # self.x, dup.x and clone.x dispatch on the caller's own class, like a bare call.
            receiver, chain = "", []
        args = node.child_by_field_name("arguments")
        container = _ancestor_name(ctx.source, node, ctx.type_declarations)
        # A Go method's receiver variable is its `self`: `c.Own()` inside `func (c Child)`.
        variable, owner = _go_receiver(ctx.source, node) if ctx.pack.name == "go" else ("", "")
        if variable and chain[:1] == [variable]:
            chain = ["this", *chain[1:]]  # `c.base.Helper()` walks Child's fields like `this.base`
        calls.append({
            "name": name, "line": line, "evidence": evidence,
            "receiver": receiver,
            "receiver_chain": chain,
            "argument_count": args.named_child_count if args is not None else None,
            "caller": _ancestor_name(ctx.source, node, ctx.callable_declarations),
            "container": owner or container,
            **({"self_receiver": True} if variable and receiver == variable else {}),
            **_call_binding_metadata(ctx.source, node, name, ctx.callable_declarations, ctx.ext),
        })
        operation_text = " ".join(_text(ctx.source, node).split())[:300]
        operations.append({
            "kind": "new" if node.type in ("new_expression", "object_creation_expression") else "call",
            "name": name, "line": line, "text": operation_text,
            "caller": _ancestor_name(ctx.source, node, ctx.callable_declarations),
            "container": _ancestor_name(ctx.source, node, ctx.type_declarations),
        })
        if ctx.pack.name == "ruby" and name in {"require", "require_relative", "load", "autoload"}:
            imports.append({"text": evidence, "line": line})
        if ctx.pack.name in _ESM_PACKS and name == "require" and node.parent is not None:
            imports.append({"text": " ".join(_text(ctx.source, node.parent.parent or node.parent).split())[:600], "line": line})
        if ctx.pack.name == "ruby" and name in {"include", "prepend", "extend"}:
            argument_text = _text(ctx.source, args) if args is not None else ""
            mixin_names = re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*\b", argument_text)
            container = _ancestor_name(ctx.source, node, ctx.type_declarations)
            for mixin_name in mixin_names:
                ruby_mixins.append({
                    "container": container,
                    "name": mixin_name.rsplit("::", 1)[-1],
                    "qualified_name": mixin_name,
                    "kind": name,
                    "line": line,
                    "evidence": evidence,
                })


# Node types per role, shared by every grammar; packs add their own below.
_SYMBOL_TYPES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "struct_declaration": "struct",
    "enum_declaration": "enum",
    "record_declaration": "class",
    "function_declaration": "function",
    "method_declaration": "method",
    "method_definition": "method",
    "constructor_declaration": "method",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "class_definition": "class",
    "function_definition": "function",
    "constructor_declaration": "method",
    "record_declaration": "class",
    "function_item": "function",
    "struct_item": "struct",
    "enum_item": "enum",
    "trait_item": "interface",
    "type_declaration": "type",
    "type_spec": "type",
    "method_elem": "method",  # a method a Go interface requires
    "trait_declaration": "interface",
    "class_specifier": "class",
    "struct_specifier": "struct",
    "union_specifier": "union",
    "enum_specifier": "enum",
    "class": "class",
    "module": "module",
    "method": "method",
    "singleton_method": "method",
    "object_declaration": "class",
    "protocol_declaration": "interface",
    "protocol_function_declaration": "method",
    "init_declaration": "method",
    "trait_definition": "interface",
    "object_definition": "class",
}

_CALL_TYPES = frozenset({"invocation_expression", "call_expression", "call", "new_expression", "object_creation_expression", "function_call_expression", "member_call_expression", "nullsafe_member_call_expression", "scoped_call_expression", "method_invocation"})
_IMPORT_TYPES = frozenset({"using_directive", "import_statement", "import_from_statement", "import_declaration", "package_clause", "use_declaration", "namespace_use_declaration", "preproc_include"})
_TYPE_DECLARATIONS = frozenset({"class_declaration", "class_definition", "interface_declaration", "struct_declaration", "record_declaration", "struct_item", "trait_item", "trait_declaration", "class_specifier", "struct_specifier", "union_specifier", "class"})
_CALLABLE_DECLARATIONS = frozenset({"function_declaration", "function_definition", "method_declaration", "method_definition", "constructor_declaration", "function_item", "method", "singleton_method"})


def _declaration_types(pack_name: str, rel_path: str = "") -> tuple[set[str], set[str], set[str]]:
    """Import, type and callable node types, with the additions of one language pack."""
    import_types = set(_IMPORT_TYPES)
    if pack_name == "kotlin":
        import_types |= {"import", "package_header"}
    type_declarations = set(_TYPE_DECLARATIONS)
    if pack_name == "ruby":
        type_declarations.add("module")
    if pack_name in _OWNER_DECLARATIONS:
        type_declarations.add(_OWNER_DECLARATIONS[pack_name])
    callable_declarations = set(_CALLABLE_DECLARATIONS)
    if pack_name in _JVM_APPLE_PACKS:
        type_declarations |= {"object_declaration", "protocol_declaration", "trait_definition", "object_definition"}
        callable_declarations |= {"init_declaration", "protocol_function_declaration"}
    if pack_name in _TEST_BLOCK_PACKS and _TEST_FILE.search(rel_path):
        callable_declarations.add(_TEST_BLOCKS)
    return import_types, type_declarations, callable_declarations


def parse_file(file_path: Path, rel_path: str) -> Optional[dict[str, Any]]:
    """Return structural facts or ``None`` when tree-sitter is unavailable."""
    ext = file_path.suffix.lower()
    source = file_path.read_bytes()
    pack = _pack_for_source(ext, source)
    try:
        language = _language_for_extension(ext, source)
        if language is None:
            return None
        parser = _parser_for(language)
    except (ImportError, ModuleNotFoundError, OSError, TypeError, ValueError):
        return None

    tree = parser.parse(source)
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    ruby_mixins: list[dict[str, Any]] = []
    namespace = ""

    symbol_types, call_types = _SYMBOL_TYPES, _CALL_TYPES
    import_types, type_declarations, callable_declarations = _declaration_types(pack.name, rel_path)

    ctx = _FileContext(source, rel_path, ext, pack, frozenset(type_declarations), frozenset(callable_declarations))
    ruby_locals: dict[int, set[str]] = {}

    def visit(node) -> None:
        nonlocal namespace
        # Keep every ancestor Node alive while visiting descendants. Some
        # grammar/binding combinations expose child nodes backed by their
        # parent wrapper; retaining the recursive frame avoids invalid native
        # handles on deeply nested real-world files.
        line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        node_lines = _text(source, node).splitlines()
        evidence = node_lines[0].strip()[:240] if node_lines else ""

        if node.type in _MEMBER_TYPES:
            _member_facts(ctx, node, line, end_line, evidence, members, symbols)
        elif node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            name_node = node.child_by_field_name("name")
            if value is not None and value.type in ("arrow_function", "function_expression") and name_node is not None:
                name = _text(source, name_node)
                symbols.append({
                    "name": name, "kind": "function", "file": rel_path,
                    "line": line, "end_line": end_line, "evidence": evidence,
                    "bases": [], "parser": "tree-sitter", "container": _ancestor_name(source, node, type_declarations),
                    "namespace": _ancestor_namespace(source, node),
                })
        elif node.type in symbol_types:
            symbol = _symbol_fact(ctx, node, line, end_line, evidence)
            if symbol:
                symbols.append(symbol)
        elif node.type in call_types:
            _call_facts(ctx, node, line, evidence, calls, operations, imports, ruby_mixins, symbols)
        elif pack.name == "ruby" and node.type == "identifier" and _is_ruby_bare_call(ctx, node, ruby_locals):
            _ruby_bare_call_facts(ctx, node, line, evidence, calls, operations)
        elif pack.name == "ruby" and node.type == "super" and (node.parent is None or node.parent.type != "call"):
            # A bare `super` forwards the arguments; `super(...)` arrives as a call.
            _ruby_bare_call_facts(ctx, node, line, evidence, calls, operations)
        elif node.type in {"assignment_expression", "assignment", "augmented_assignment_expression"}:
            left = node.child_by_field_name("left")
            operations.append({
                "kind": "assign", "name": _text(source, left)[:80] if left is not None else "",
                "line": line, "text": " ".join(_text(source, node).split())[:300],
                "caller": _ancestor_name(source, node, callable_declarations),
                "container": _ancestor_name(source, node, type_declarations),
            })
        elif node.type == "return_statement":
            operations.append({
                "kind": "return", "name": "", "line": line, "text": " ".join(_text(source, node).split())[:300],
                "caller": _ancestor_name(source, node, callable_declarations),
                "container": _ancestor_name(source, node, type_declarations),
            })
        elif node.type in {"local_declaration_statement", "lexical_declaration"}:
            operations.append({
                "kind": "declare", "name": "", "line": line, "text": " ".join(_text(source, node).split())[:300],
                "caller": _ancestor_name(source, node, callable_declarations),
                "container": _ancestor_name(source, node, type_declarations),
            })
        elif node.type in {"if_statement", "for_statement", "while_statement", "switch_statement", "throw_statement"}:
            header = " ".join(_text(source, node).split())
            # Keep the condition/header, not the entire nested body.
            header = header.split("{", 1)[0].strip()[:300]
            operations.append({
                "kind": "control", "name": node.type.removesuffix("_statement"),
                "line": line, "text": header,
                "caller": _ancestor_name(source, node, callable_declarations),
                "container": _ancestor_name(source, node, type_declarations),
            })
        elif node.type in {"except_clause", "catch_clause"}:
            raw = " ".join(_text(source, node).split())
            match = re.search(r"(?:except|catch)\s*\(?\s*([A-Za-z_][A-Za-z0-9_.]*)", raw)
            operations.append({
                "kind": "catch", "name": match.group(1) if match else "exception",
                "line": line, "text": raw[:220],
                "caller": _ancestor_name(source, node, callable_declarations),
                "container": _ancestor_name(source, node, type_declarations),
            })
        elif node.type in import_types:  # a JavaScript import spans lines: `import {\n a,\n b } from 'x'`
            imports.append({"text": " ".join(_text(source, node).split())[:600] if pack.name in _ESM_PACKS else evidence, "line": line})
        elif node.type in {"namespace_declaration", "file_scoped_namespace_declaration", "namespace_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                namespace = _text(source, name_node)

        for child in node.named_children:
            visit(child)

    visit(tree.root_node)

    if ruby_mixins:
        for symbol in symbols:
            if symbol.get("kind") not in {"class", "module"}:
                continue
            symbol["mixins"] = [
                item for item in ruby_mixins if item.get("container") == symbol.get("name")
            ]

    source_text = source.decode("utf-8", errors="replace")
    source_lines = source_text.splitlines()
    joined = _without_literals(tree.root_node, source_lines)
    # prefix_end[n] is len("\n".join(source_lines[:n])): the text a call on
    # line n may use to infer its receiver's declared type.
    prefix_end = [0]
    for index, text in enumerate(source_lines):
        prefix_end.append(prefix_end[-1] + len(text) + (1 if index else 0))
    declarations: dict[str, tuple[list[tuple[int, str]], list[tuple[int, str]]]] = {}
    identifier_declarations: tuple[dict, dict] | None = None

    def _identifier_declarations() -> tuple[dict, dict]:
        """Index `var x = new T` and `T x` for every identifier in one pass.

        Overlapping lookaheads expose every start. Accepting a start only at or
        after the previous accepted end for the same identifier reproduces the
        non-overlapping scan a per-identifier pattern would perform.
        """
        found: tuple[dict, dict] = ({}, {})
        patterns = _DECLARATION_PATTERNS.get(pack.name, _DECLARATION_PATTERNS["default"])
        for slot, pattern in enumerate(patterns):
            last_end: dict[str, int] = {}
            for match in re.finditer(pattern, joined):
                name, type_name = ((match.group(1), match.group(2)) if slot == 0
                                   else (match.group(2), match.group(1)))
                if match.start() < last_end.get(name, -1):
                    continue
                last_end[name] = match.end(2)
                found[slot].setdefault(name, []).append((match.end(2), type_name))
        return found

    def _receiver_declarations(receiver: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
        nonlocal identifier_declarations
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", receiver):
            if identifier_declarations is None:
                identifier_declarations = _identifier_declarations()
            return tuple(index.get(receiver, []) for index in identifier_declarations)
        # Necessary conditions, checked with plain string search: both patterns
        # need whitespace before the receiver, preceded by `var` or by the last
        # character of a type name respectively.
        typed = declared = False
        position = joined.find(receiver)
        while position != -1 and not (typed and declared):
            cursor = position - 1
            while cursor >= 0 and joined[cursor].isspace():
                cursor -= 1
            if cursor >= 0 and cursor < position - 1:
                typed = typed or joined[cursor] in _TYPE_NAME_END
                declared = declared or bool(re.search(r"\bvar$", joined[max(0, cursor - 3):cursor + 1]))
            position = joined.find(receiver, position + 1)
        escaped = re.escape(receiver)
        return (
            [(match.end(), match.group(1)) for match in re.finditer(
                rf"\bvar\s+{escaped}\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)", joined)] if declared else [],
            [(match.end(), match.group(1)) for match in re.finditer(
                rf"\b([A-Z][A-Za-z0-9_.<>]*)\s+{escaped}\b", joined)] if typed else [],
        )

    for call in calls:
        receiver = call.get("receiver", "")
        if pack.name == "ruby" and not receiver and call.get("name") in _RUBY_BARE_BUILTINS:
            call["runtime_builtin"] = True
        receiver_type = ""
        if receiver == "this" or receiver in _SELF_RECEIVERS.get(pack.name, ()) or call.get("self_receiver"):  # own class
            receiver_type = call.get("container", "")
        elif receiver:
            # Each receiver is resolved once per file. A match inside the
            # prefix ends at or before its final newline, so filtering full-text
            # matches by end offset equals searching every prefix again.
            if receiver not in declarations:
                declarations[receiver] = _receiver_declarations(receiver)
            limit = prefix_end[min(int(call["line"]), len(source_lines))]
            matches = []
            for found in declarations[receiver]:
                count = bisect.bisect_right(found, (limit, "\uffff"))
                if count:
                    matches.append(found[count - 1][1])
            if matches:
                receiver_type = re.sub(r"[.<].*", "", matches[-1].split(".")[-1])
            elif receiver[:1].isupper():
                receiver_type = receiver
        call["receiver_type"] = receiver_type

    return {
        "file": rel_path,
        "language": pack.name,
        "parser": "tree-sitter",
        "has_error": bool(tree.root_node.has_error),
        "symbols": _with_trait_impls(pack.name, symbols, tree.root_node, source),
        "calls": calls,
        "imports": imports,
        "members": members + _python_members(pack.name, tree.root_node, source, rel_path),
        "operations": operations,
        "namespace": namespace,
    }
