"""Optional tree-sitter structural extraction for high-value languages.

The module deliberately imports tree-sitter lazily so the core MCP/CLI keeps
working with zero optional dependencies. Callers receive ``None`` when the
runtime or a grammar is unavailable and can fall back to legacy extractors.
"""

from __future__ import annotations

import bisect
import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


PARSER_VERSION = "treesitter-v21-kotlin-swift-scala"


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
    LanguagePack("javascript", (".js", ".jsx"), "tree_sitter_javascript"),
    LanguagePack("typescript", (".ts", ".tsx"), "tree_sitter_typescript",
                 factories=((".ts", "language_typescript"), (".tsx", "language_tsx")),
                 capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("php", (".php",), "tree_sitter_php", factories=((".php", "language_php"),),
                 capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("python", (".py",), "tree_sitter_python", capabilities=("symbols", "imports", "calls", "inheritance")),
    LanguagePack("java", (".java",), "tree_sitter_java", capabilities=("symbols", "imports", "calls", "members", "inheritance")),
    LanguagePack("go", (".go",), "tree_sitter_go"),
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


def _call_name(source: bytes, node) -> str:
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
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw)
    return names[-1] if names else ""


def _ancestor_name(source: bytes, node, types: set[str]) -> str:
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in types:
            return _name(source, ancestor)
        ancestor = ancestor.parent
    return ""


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


@dataclass(frozen=True)
class _FileContext:
    """What every node handler needs to know about the file being parsed."""
    source: bytes
    rel_path: str
    ext: str
    pack: Any
    type_declarations: frozenset
    callable_declarations: frozenset


def _member_facts(ctx: _FileContext, node, line: int, end_line: int, evidence: str,
                  members: list, symbols: list) -> None:
    """Fields, properties and events of a type, plus C++ in-class method declarations."""
    type_node = node.child_by_field_name("type")
    variable_declaration = None
    if node.type in {"field_declaration", "event_field_declaration"}:
        variable_declaration = next((child for child in node.named_children if child.type == "variable_declaration"), None)
        if type_node is None and variable_declaration is not None:
            type_node = variable_declaration.child_by_field_name("type")
    type_name = _text(ctx.source, type_node) if type_node is not None else ""
    container = _ancestor_name(ctx.source, node, ctx.type_declarations)
    if container and type_name:
        if node.type in {"property_declaration", "event_declaration"}:
            name_node = node.child_by_field_name("name")
            names = [_text(ctx.source, name_node)] if name_node is not None else []
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
        base_node = node.child_by_field_name("bases") or node.child_by_field_name("superclass")
        if base_node is None:
            base_node = next((c for c in node.named_children if c.type in (
                "base_list", "superclass", "base_class_clause", "delegation_specifiers", "extends_clause")), None)
        if base_node is not None:
            if ctx.pack.name == "ruby":
                qualified = re.findall(
                    r"[A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*",
                    _text(ctx.source, base_node),
                )
                bases = [qualified[-1].rsplit("::", 1)[-1]] if qualified else []
            else:
                bases = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _text(ctx.source, base_node))
                bases = [base for base in bases if base not in {"public", "protected", "private", "virtual", "final", "extends", "with"}]
        if ctx.pack.name == "swift":
            bases = [_text(ctx.source, child.child_by_field_name("inherits_from") or child).split("<", 1)[0]
                     for child in node.named_children if child.type == "inheritance_specifier"]
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
            "container": _ancestor_name(ctx.source, node, ctx.type_declarations), "scope": _ancestor_name(ctx.source, node, ctx.callable_declarations),
            "namespace": _ancestor_namespace(ctx.source, node),
            "parameter_count": parameter_count,
            "required_parameter_count": required_parameter_count,
            "is_constructor": node.type == "constructor_declaration",
            "signature": signature or evidence,
        }
    return None


def _call_facts(ctx: _FileContext, node, line: int, evidence: str, calls: list, operations: list,
                imports: list, ruby_mixins: list) -> None:
    """A call or instantiation, its operation and Ruby require/mixin side facts."""
    name = _call_name(ctx.source, node)
    if name:
        target = node.child_by_field_name("function") or node.child_by_field_name("method")
        raw_target = _text(ctx.source, target) if target is not None else ""
        target_names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw_target)
        chain = target_names[:-1]
        receiver_node = node.child_by_field_name("receiver")
        receiver = (_text(ctx.source, receiver_node) if receiver_node is not None
                    else (chain[-1] if chain else ""))
        args = node.child_by_field_name("arguments")
        calls.append({
            "name": name, "line": line, "evidence": evidence,
            "receiver": receiver,
            "receiver_chain": chain,
            "argument_count": args.named_child_count if args is not None else None,
            "caller": _ancestor_name(ctx.source, node, ctx.callable_declarations),
            "container": _ancestor_name(ctx.source, node, ctx.type_declarations),
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

_CALL_TYPES = frozenset({"invocation_expression", "call_expression", "call", "new_expression", "object_creation_expression", "function_call_expression", "member_call_expression", "scoped_call_expression"})
_IMPORT_TYPES = frozenset({"using_directive", "import_statement", "import_from_statement", "import_declaration", "package_clause", "use_declaration", "namespace_use_declaration", "preproc_include"})
_TYPE_DECLARATIONS = frozenset({"class_declaration", "class_definition", "interface_declaration", "struct_declaration", "record_declaration", "struct_item", "trait_item", "trait_declaration", "class_specifier", "struct_specifier", "union_specifier", "class"})
_CALLABLE_DECLARATIONS = frozenset({"function_declaration", "function_definition", "method_declaration", "method_definition", "constructor_declaration", "function_item", "method", "singleton_method"})


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

    symbol_types = _SYMBOL_TYPES
    call_types = _CALL_TYPES
    import_types = set(_IMPORT_TYPES)
    if pack.name == "kotlin":
        import_types |= {"import", "package_header"}
    type_declarations = set(_TYPE_DECLARATIONS)
    if pack.name == "ruby":
        type_declarations.add("module")
    callable_declarations = set(_CALLABLE_DECLARATIONS)
    if pack.name in _JVM_APPLE_PACKS:
        type_declarations |= {"object_declaration", "protocol_declaration", "trait_definition", "object_definition"}
        callable_declarations |= {"init_declaration", "protocol_function_declaration"}

    ctx = _FileContext(source, rel_path, ext, pack, frozenset(type_declarations), frozenset(callable_declarations))

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

        if node.type in {"field_declaration", "property_declaration", "event_declaration", "event_field_declaration"}:
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
            _call_facts(ctx, node, line, evidence, calls, operations, imports, ruby_mixins)
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
        elif node.type in import_types:
            imports.append({"text": evidence, "line": line})
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
    joined = "\n".join(source_lines)
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
        patterns = (
            r"(?=\bvar\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*))",
            r"(?=\b([A-Z][A-Za-z0-9_.<>]*)\s+([A-Za-z_][A-Za-z0-9_]*)\b)",
        )
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
        if receiver == "this":
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
        "symbols": symbols,
        "calls": calls,
        "imports": imports,
        "members": members,
        "operations": operations,
        "namespace": namespace,
    }
