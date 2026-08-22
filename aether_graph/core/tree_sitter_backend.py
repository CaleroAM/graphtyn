"""Optional tree-sitter structural extraction for high-value languages.

The module deliberately imports tree-sitter lazily so the core MCP/CLI keeps
working with zero optional dependencies. Callers receive ``None`` when the
runtime or a grammar is unavailable and can fall back to legacy extractors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


PARSER_VERSION = "treesitter-v9-laravel"


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
    if ext == ".php":
        import tree_sitter_php as grammar
        return Language(grammar.language_php())
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
    members: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    namespace = ""

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
        "trait_declaration": "interface",
    }
    call_types = {"invocation_expression", "call_expression", "call", "new_expression", "object_creation_expression", "function_call_expression", "member_call_expression", "scoped_call_expression"}
    import_types = {"using_directive", "import_statement", "import_from_statement", "import_declaration", "package_clause", "use_declaration", "namespace_use_declaration"}
    type_declarations = {"class_declaration", "class_definition", "interface_declaration", "struct_declaration", "record_declaration", "struct_item", "trait_item", "trait_declaration"}
    callable_declarations = {"function_declaration", "function_definition", "method_declaration", "method_definition", "constructor_declaration", "function_item"}

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
            type_node = node.child_by_field_name("type")
            variable_declaration = None
            if node.type in {"field_declaration", "event_field_declaration"}:
                variable_declaration = next((child for child in node.named_children if child.type == "variable_declaration"), None)
                if type_node is None and variable_declaration is not None:
                    type_node = variable_declaration.child_by_field_name("type")
            type_name = _text(source, type_node) if type_node is not None else ""
            container = _ancestor_name(source, node, type_declarations)
            if container and type_name:
                if node.type in {"property_declaration", "event_declaration"}:
                    name_node = node.child_by_field_name("name")
                    names = [_text(source, name_node)] if name_node is not None else []
                else:
                    names = []
                    if variable_declaration is not None:
                        for declaration in variable_declaration.named_children:
                            if declaration.type == "variable_declarator":
                                name_node = declaration.child_by_field_name("name")
                                if name_node is not None:
                                    names.append(_text(source, name_node))
                for member_name in names:
                    kind = "event" if node.type.startswith("event_") else ("property" if node.type == "property_declaration" else "field")
                    members.append({
                        "container": container, "name": member_name, "kind": kind,
                        "type": type_name, "file": rel_path, "line": line,
                        "end_line": end_line, "signature": evidence,
                        "evidence": evidence, "parser": "tree-sitter",
                    })
        elif node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            name_node = node.child_by_field_name("name")
            if value is not None and value.type in ("arrow_function", "function_expression") and name_node is not None:
                name = _text(source, name_node)
                symbols.append({
                    "name": name, "kind": "function", "file": rel_path,
                    "line": line, "end_line": end_line, "evidence": evidence,
                    "bases": [], "parser": "tree-sitter", "container": _ancestor_name(source, node, type_declarations),
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
                parameters = node.child_by_field_name("parameters")
                parameter_count = parameters.named_child_count if parameters is not None else None
                required_parameter_count = None
                if parameters is not None:
                    required_parameter_count = sum(
                        child.type not in ("optional_parameter", "default_parameter")
                        and "=" not in _text(source, child)
                        for child in parameters.named_children
                    )
                signature = " ".join(_text(source, node).split())
                signature = signature.split("{", 1)[0].split("=>", 1)[0].strip()[:300]
                symbols.append({
                    "name": name,
                    "kind": kind,
                    "file": rel_path,
                    "line": line,
                    "end_line": end_line,
                    "evidence": evidence,
                    "bases": bases,
                    "parser": "tree-sitter",
                    "container": _ancestor_name(source, node, type_declarations),
                    "parameter_count": parameter_count,
                    "required_parameter_count": required_parameter_count,
                    "is_constructor": node.type == "constructor_declaration",
                    "signature": signature or evidence,
                })
        elif node.type in call_types:
            name = _call_name(source, node)
            if name:
                target = node.child_by_field_name("function")
                raw_target = _text(source, target) if target is not None else ""
                receiver = raw_target.rsplit(".", 1)[0].split(".")[-1] if "." in raw_target else ""
                import re
                chain = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw_target.rsplit(".", 1)[0]) if "." in raw_target else []
                args = node.child_by_field_name("arguments")
                calls.append({
                    "name": name, "line": line, "evidence": evidence,
                    "receiver": receiver,
                    "receiver_chain": chain,
                    "argument_count": args.named_child_count if args is not None else None,
                    "caller": _ancestor_name(source, node, callable_declarations),
                    "container": _ancestor_name(source, node, type_declarations),
                    "call_kind": node.type,
                })
                operation_text = " ".join(_text(source, node).split())[:300]
                operations.append({
                    "kind": "new" if node.type in ("new_expression", "object_creation_expression") else "call",
                    "name": name, "line": line, "text": operation_text,
                    "caller": _ancestor_name(source, node, callable_declarations),
                    "container": _ancestor_name(source, node, type_declarations),
                })
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
        elif node.type in import_types:
            imports.append({"text": evidence, "line": line})
        elif node.type in {"namespace_declaration", "file_scoped_namespace_declaration", "namespace_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                namespace = _text(source, name_node)

        for child in node.named_children:
            visit(child)

    visit(tree.root_node)

    source_text = source.decode("utf-8", errors="replace")
    source_lines = source_text.splitlines()
    import re
    for call in calls:
        receiver = call.get("receiver", "")
        receiver_type = ""
        if receiver == "this":
            receiver_type = call.get("container", "")
        elif receiver:
            prefix = "\n".join(source_lines[:call["line"]])
            patterns = [
                rf"\bvar\s+{re.escape(receiver)}\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)",
                rf"\b([A-Z][A-Za-z0-9_.<>]*)\s+{re.escape(receiver)}\b",
            ]
            matches = []
            for pattern in patterns:
                matches.extend(re.findall(pattern, prefix))
            if matches:
                receiver_type = re.sub(r"[.<].*", "", matches[-1].split(".")[-1])
            elif receiver[:1].isupper():
                receiver_type = receiver
        call["receiver_type"] = receiver_type

    return {
        "file": rel_path,
        "parser": "tree-sitter",
        "has_error": bool(tree.root_node.has_error),
        "symbols": symbols,
        "calls": calls,
        "imports": imports,
        "members": members,
        "operations": operations,
        "namespace": namespace,
    }
