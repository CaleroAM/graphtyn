"""Optional tree-sitter structural extraction for high-value languages.

The module deliberately imports tree-sitter lazily so the core MCP/CLI keeps
working with zero optional dependencies. Callers receive ``None`` when the
runtime or a grammar is unavailable and can fall back to legacy extractors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


PARSER_VERSION = "treesitter-v2"


def _language_for_extension(ext: str):
    from tree_sitter import Language

    if ext == ".cs":
        import tree_sitter_c_sharp as grammar
        return Language(grammar.language())
    if ext in (".js", ".jsx"):
        import tree_sitter_javascript as grammar
        return Language(grammar.language())
    if ext in (".ts", ".tsx"):
        import tree_sitter_typescript as grammar
        raw = grammar.language_tsx() if ext == ".tsx" else grammar.language_typescript()
        return Language(raw)
    grammar_modules = {
        ".py": "tree_sitter_python",
        ".java": "tree_sitter_java",
        ".go": "tree_sitter_go",
        ".rs": "tree_sitter_rust",
    }
    module = grammar_modules.get(ext)
    if module:
        import importlib
        grammar = importlib.import_module(module)
        return Language(grammar.language())
    return None


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
    return _text(source, named) if named is not None else ""


def _call_name(source: bytes, node) -> str:
    target = node.child_by_field_name("function")
    if target is None and node.named_child_count:
        target = node.named_children[0]
    raw = _text(source, target) if target is not None else ""
    # foo.Bar<T> / obj.method / method -> final callable identifier.
    import re
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw)
    return names[-1] if names else ""


def parse_file(file_path: Path, rel_path: str) -> Optional[dict[str, Any]]:
    """Return structural facts or ``None`` when tree-sitter is unavailable."""
    ext = file_path.suffix.lower()
    try:
        language = _language_for_extension(ext)
        if language is None:
            return None
        parser = _parser_for(language)
    except (ImportError, ModuleNotFoundError, OSError, TypeError, ValueError):
        return None

    source = file_path.read_bytes()
    tree = parser.parse(source)
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    symbol_types = {
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
    }
    call_types = {"invocation_expression", "call_expression", "new_expression", "object_creation_expression"}
    import_types = {"using_directive", "import_statement", "import_declaration", "package_clause", "use_declaration"}

    def visit(node) -> None:
        # Keep every ancestor Node alive while visiting descendants. Some
        # grammar/binding combinations expose child nodes backed by their
        # parent wrapper; retaining the recursive frame avoids invalid native
        # handles on deeply nested real-world files.
        line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        evidence = _text(source, node).splitlines()[0].strip()[:240]

        if node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            name_node = node.child_by_field_name("name")
            if value is not None and value.type in ("arrow_function", "function_expression") and name_node is not None:
                name = _text(source, name_node)
                symbols.append({
                    "name": name, "kind": "function", "file": rel_path,
                    "line": line, "end_line": end_line, "evidence": evidence,
                    "bases": [], "parser": "tree-sitter",
                })
        elif node.type in symbol_types:
            name = _name(source, node)
            if not name and node.type == "constructor_declaration":
                name_node = node.child_by_field_name("name")
                name = _text(source, name_node) if name_node else "constructor"
            if name:
                kind = symbol_types[node.type]
                if node.type == "function_definition":
                    ancestor = node.parent
                    while ancestor is not None:
                        if ancestor.type == "class_definition":
                            kind = "method"
                            break
                        ancestor = ancestor.parent
                bases = []
                base_node = node.child_by_field_name("bases")
                if base_node is None:
                    base_node = next((c for c in node.named_children if c.type in ("base_list", "superclass")), None)
                if base_node is not None:
                    import re
                    bases = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _text(source, base_node))
                symbols.append({
                    "name": name,
                    "kind": kind,
                    "file": rel_path,
                    "line": line,
                    "end_line": end_line,
                    "evidence": evidence,
                    "bases": bases,
                    "parser": "tree-sitter",
                })
        elif node.type in call_types:
            name = _call_name(source, node)
            if name:
                calls.append({"name": name, "line": line, "evidence": evidence})
        elif node.type in import_types:
            imports.append({"text": evidence, "line": line})

        for child in node.named_children:
            visit(child)

    visit(tree.root_node)

    return {
        "file": rel_path,
        "parser": "tree-sitter",
        "has_error": bool(tree.root_node.has_error),
        "symbols": symbols,
        "calls": calls,
        "imports": imports,
    }
