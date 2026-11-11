"""Declared type of a call's receiver, bounded by lexical scope.

`x.save()` is typed from the declarations of `x` that the call can see: those of
its enclosing block, function, type and file, the innermost first. A parameter
or local of another function never types the call, and an untyped binding of the
same name in a nearer scope hides a typed one further out.

Declarations are still found by pattern over the source with literals blanked;
the tree only says which scope each one, and each call, belongs to. A member
reached through another object (`a.b.save()`, `this.b.save()`) names a field,
which is not lexically scoped: it keeps the file-wide lookup.
"""

from __future__ import annotations

import bisect
import re
from typing import Any, Callable

SELF_RECEIVERS = {"python": {"self", "cls"}, "php": {"$this"}, "swift": {"self"}, "rust": {"self"}}
_TYPE_NAME_END = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.<>")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# `let x = x.clone();`, `x := x`, `let x = &x;` rebind the same value: its type carries over.
_SAME_VALUE = re.compile(r"\s*:?=\s*&?(?:mut\s+)?([A-Za-z_][A-Za-z0-9_]*)(?:\.clone\(\))?\s*(?:;|\n|$)")
_TYPE_TAIL = re.compile(r"[.<].*")
_AFTER = chr(0xFFFF)  # sorts after every type name: bisecting (offset, _AFTER) keeps declarations ending at offset

# (name, type) declarations, then (type, name) ones: Go writes `c *Command` and `c := &Command{}`.
# How a language writes "variable `name` has type `type`", as lookaheads so that every
# start is seen. Python and Rust annotate after the name (`shape: Shape`), so the
# C-style `Type name` pattern would only mistype them, and both bind a constructor
# result (`c = Circle(...)`, `let c = Circle::new()`, `Direction::North`).
_TYPED_NAME = r"(?=\b(?P<name>[a-z_][A-Za-z0-9_]*)\s*:\s*{prefix}(?P<type>[A-Z][A-Za-z0-9_]+)\b)"  # one letter is a generic
# `Map<String, ? extends Repo> name`: generic arguments may hold spaces, commas and wildcards.
_GENERIC_ARGUMENT = r"[A-Za-z0-9_.?,&\[\] \t]"
_GENERIC_ARGUMENTS = "<(?:%s|<(?:%s|<%s*>)*>)*>" % ((_GENERIC_ARGUMENT,) * 3)  # nested up to three deep
_TYPE_THEN_NAME = (r"(?=\b(?P<type>[A-Z][A-Za-z0-9_.]*(?:" + _GENERIC_ARGUMENTS + r")?(?:\[\])*)"
                   r"\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b)")
_DECLARATION_PATTERNS = {
    "default": (r"(?=\b(?:var|let|const|val|auto)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+(?P<type>[A-Za-z_][A-Za-z0-9_]*))",
                _TYPE_THEN_NAME),
    "go": (r"(?=\b(?P<name>[a-z_][A-Za-z0-9_]*)(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)?\s*:?=\s*[A-Za-z_][A-Za-z0-9_.]*\.\(\*?"
           r"(?:[a-z_][A-Za-z0-9_]*\.)?(?P<type>[A-Z][A-Za-z0-9_]*)\))",  # `c := in.(*Command)`
           r"(?=\b(?P<name>[a-z_][A-Za-z0-9_]*)(?:\s+(?:\*|\[\])?|\s*:=\s*(?:&|new\()?|\s*=\s*(?:&|new\())"
           r"(?:[a-z_][A-Za-z0-9_]*\.)?(?P<type>[A-Z][A-Za-z0-9_]*)\b(?!\s*\())",  # not `x := pkg.Load()`
           _TYPE_THEN_NAME),
    "typescript": (r"(?=\b(?:var|let|const)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+(?P<type>[A-Za-z_][A-Za-z0-9_]*))",
                   _TYPE_THEN_NAME,
                   r"(?=[(,]\s*(?:(?:public|private|protected|readonly)\s+)*(?P<name>[a-z_][A-Za-z0-9_]*)\??\s*:\s*(?P<type>[A-Z][A-Za-z0-9_]*)\b(?!\[))",
                   r"(?=\b(?:var|let|const)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<type>[A-Z][A-Za-z0-9_]*)\b(?!\[))"),
    "python": (_TYPED_NAME.format(prefix=r"[\"']?(?:Optional\[)?(?:[A-Za-z_][A-Za-z0-9_]*\.)*"),
               r"(?=\b(?P<name>[a-z_][A-Za-z0-9_]*)\s*=\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)*(?P<type>[A-Z][A-Za-z0-9_]*)\()"),
    "rust": (_TYPED_NAME.format(prefix=r"&?(?:'[a-z_]+\s+)?(?:mut\s+)?(?:dyn\s+|impl\s+)?(?:[A-Za-z_][A-Za-z0-9_]*::)*"),
             r"(?=\b(?P<name>[a-z_][A-Za-z0-9_]*)\s*=\s*(?:[a-z_][A-Za-z0-9_]*::)*(?P<type>[A-Z][A-Za-z0-9_]*)\s*(?:::|\{))"),
}
# `std::shared_ptr<const Repo> repo` is used as a Repo; a container of them is not.
_DECLARATION_PATTERNS["cpp"] = (*_DECLARATION_PATTERNS["default"], (
    r"(?<=_ptr<)(?:const\s+)?(?:[A-Za-z_][A-Za-z0-9_]*::)*(?P<type>[A-Z][A-Za-z0-9_]*)(?:" + _GENERIC_ARGUMENTS
    + r")?\s*>\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b"))
# A binding that names no type (`var x = load()`, `x := load()`, `let x = load()`): it
# still hides a typed `x` of an outer scope. Languages that bind by plain assignment
# have no such marker; their untyped parameters are read from the tree instead.
_UNTYPED_BINDINGS = {
    "default": (r"\b(?:var|let|const|val|auto)(?:\s+|\s*[&*]+\s*)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b",),
    "go": (r"(?=\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*\s*:=)",
           r"\bvar\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b"),
    "rust": (r"\blet\s+(?:mut\s+)?(?P<name>[a-z_][A-Za-z0-9_]*)\b",),
    "python": (), "ruby": (), "php": (),
}

_FUNCTION, _TYPE, _BLOCK, _DECLARATOR = "f", "t", "b", "d"
_FUNCTION_SCOPES = (
    "function_declaration", "function_definition", "method_declaration", "method_definition",
    "constructor_declaration", "destructor_declaration", "operator_declaration", "conversion_operator_declaration",
    "compact_constructor_declaration", "local_function_statement", "delegate_declaration", "accessor_declaration",
    "function_item", "function_signature_item", "closure_expression", "method", "singleton_method",
    "arrow_function", "function_expression", "function", "generator_function", "generator_function_declaration",
    "function_signature", "method_signature", "abstract_method_signature", "call_signature", "construct_signature",
    "function_type", "constructor_type", "lambda", "lambda_expression", "lambda_literal", "anonymous_function",
    "anonymous_function_creation_expression", "anonymous_method_expression", "func_literal", "method_elem",
    "method_spec", "init_declaration", "deinit_declaration", "protocol_function_declaration", "secondary_constructor",
    "anonymous_initializer", "getter", "setter", "computed_property", "subscript_declaration",
)
_TYPE_SCOPES = (
    "class_declaration", "abstract_class_declaration", "class_definition", "interface_declaration",
    "struct_declaration", "record_declaration", "enum_declaration", "struct_item", "enum_item", "union_item",
    "trait_item", "impl_item", "trait_declaration", "class_specifier", "struct_specifier", "union_specifier",
    "class", "module", "type_spec", "object_declaration", "companion_object", "protocol_declaration",
    "trait_definition", "object_definition", "enum_definition", "object_literal",
)
_BLOCK_SCOPES = (
    "block", "statement_block", "compound_statement", "for_statement", "for_in_statement", "for_of_statement",
    "enhanced_for_statement", "foreach_statement", "for_each_statement", "for_range_loop", "for_expression",
    "catch_clause", "catch_declaration", "catch_block", "try_with_resources_statement", "using_statement",
    "fixed_statement", "control_structure_body", "indented_block", "match_arm", "case_clause",
)
# Statements whose header binds a variable for their own body only.
_HEADER_SCOPES = {
    "go": ("if_statement", "expression_switch_statement", "type_switch_statement", "select_statement",
           "expression_case", "default_case", "type_case", "communication_case"),
    "rust": ("if_expression", "while_expression", "match_expression"),
    "cpp": ("if_statement", "switch_statement", "while_statement"),
    "swift": ("if_statement", "while_statement", "switch_entry"),
    "kotlin": ("when_entry",),
}
_UNBLOCKED_PACKS = frozenset({"python", "ruby", "php"})  # a variable lives for its whole function
# Where a bare name inside a method can be a field of its class, declared anywhere in the body.
_IMPLICIT_THIS_PACKS = frozenset({"java", "csharp", "cpp", "kotlin", "swift", "scala"})
_CPP_TYPE_NAME = re.compile(r"(?:class|struct|union)\s+(?:[A-Z][A-Z0-9_]*\s+)?([A-Za-z_][A-Za-z0-9_]*)")
_CPP_METHOD_OWNER = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^<>(){};]*>)?\s*::\s*(?:~?[A-Za-z_][A-Za-z0-9_]*|operator[^(]{1,12})\s*\(")
_KINDS: dict[str, dict[str, str]] = {}


def _scope_kinds(pack: str) -> dict[str, str]:
    """Node type -> scope kind for one language."""
    kinds = _KINDS.get(pack)
    if kinds is None:
        kinds = {**dict.fromkeys(_TYPE_SCOPES, _TYPE), **dict.fromkeys(_FUNCTION_SCOPES, _FUNCTION)}
        if pack not in _UNBLOCKED_PACKS:
            kinds.update(dict.fromkeys((*_BLOCK_SCOPES, *_HEADER_SCOPES.get(pack, ())), _BLOCK))
        if pack in ("c", "cpp"):
            kinds["function_declarator"] = _DECLARATOR
        if pack != "ruby":
            kinds.pop("module", None)  # elsewhere the whole file
        _KINDS[pack] = kinds
    return kinds


class LexicalScopes:
    """The scopes of one file in document order, recorded while its tree is visited."""

    __slots__ = ("kinds", "kind", "start", "end", "parent", "node", "_stack", "_functions")

    def __init__(self, pack: str) -> None:
        self.kinds = _scope_kinds(pack)  # node type -> scope kind
        self.kind: list[str] = []
        self.start: list[Any] = []
        self.end: list[Any] = []
        self.parent: list[int] = []
        self.node: list[Any] = []
        self._stack = [-1]  # -1 is the file
        self._functions = 0

    @property
    def current(self) -> int:
        return self._stack[-1]

    def enter(self, node: Any) -> bool:
        """Open a scope when `node` is one; the caller closes it with `leave` after its children."""
        kind = self.kinds.get(node.type)
        if kind is None:
            return False
        if kind == _DECLARATOR:
            # A C/C++ prototype (`void save(Repo repo);`) keeps its parameters to itself. The
            # declarator of a definition shares the definition's scope, and inside a body
            # `Repo repo(arg);` parses the same way while declaring a local.
            owner = node.parent
            while owner is not None and owner.type.endswith("_declarator"):
                owner = owner.parent
            if self._functions or (owner is not None and owner.type == "function_definition"):
                return False
            kind = _FUNCTION
        self.kind.append(kind)
        self.start.append(node.start_point)
        self.end.append(node.end_point)
        self.parent.append(self._stack[-1])
        self.node.append(node if kind == _FUNCTION else None)
        self._stack.append(len(self.kind) - 1)
        self._functions += kind == _FUNCTION
        return True

    def leave(self) -> None:
        self._functions -= self.kind[self._stack.pop()] == _FUNCTION


def typed_receiver(call: dict[str, Any], pack: str) -> bool:
    """Whether a call's receiver type will be looked up among the file's declarations."""
    receiver = call.get("receiver", "")
    return bool(receiver) and receiver != "this" and receiver not in SELF_RECEIVERS.get(pack, ()) \
        and not call.get("self_receiver")


def _declaration_index(patterns: tuple[str, ...], text: str) -> tuple[dict[str, list[tuple[int, str]]], ...]:
    """Index `var x = new T` and `T x` for every identifier in one pass per pattern.

    Overlapping lookaheads expose every start. Accepting a start only at or
    after the previous accepted end for the same identifier reproduces the
    non-overlapping scan a per-identifier pattern would perform.
    """
    found: tuple[dict, ...] = tuple({} for _pattern in patterns)
    for slot, pattern in enumerate(patterns):
        last_end: dict[str, int] = {}
        for match in re.finditer(pattern, text):
            name, type_name = match.group("name"), match.group("type")
            end = max(match.end("name"), match.end("type"))
            if match.start() < last_end.get(name, -1):
                continue
            last_end[name] = end
            found[slot].setdefault(name, []).append((end, type_name))
    return found


def _literal_declarations(receiver: str, text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """`var x = new T` and `T x` for a receiver that is not a plain identifier."""
    # Necessary conditions, checked with plain string search: both patterns
    # need whitespace before the receiver, preceded by `var` or by the last
    # character of a type name respectively.
    typed = declared = False
    position = text.find(receiver)
    while position != -1 and not (typed and declared):
        cursor = position - 1
        while cursor >= 0 and text[cursor].isspace():
            cursor -= 1
        if cursor >= 0 and cursor < position - 1:
            typed = typed or text[cursor] in _TYPE_NAME_END
            declared = declared or bool(re.search(r"\bvar$", text[max(0, cursor - 3):cursor + 1]))
        position = text.find(receiver, position + 1)
    escaped = re.escape(receiver)
    return (
        [(match.end(), match.group(1)) for match in re.finditer(
            rf"\bvar\s+{escaped}\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)", text)] if declared else [],
        [(match.end(), match.group(1)) for match in re.finditer(
            rf"\b([A-Z][A-Za-z0-9_.<>]*)\s+{escaped}\b", text)] if typed else [],
    )


class _ReceiverTypes:
    """Receiver lookups of one file; every index is built on first use."""

    def __init__(self, pack: str, scopes: LexicalScopes, lines: list[str], masked: Callable[[], str],
                 parameters: Callable[[Any], set[str]]) -> None:
        self.pack, self.scopes, self.lines, self.masked, self.parameters = pack, scopes, lines, masked, parameters
        self.line_start = [0]
        for text in lines:
            self.line_start.append(self.line_start[-1] + len(text) + 1)
        self._typed: tuple[dict, ...] | None = None
        self._untyped: dict[str, list[int]] | None = None
        self._spans: tuple[list[int], list[int]] | None = None
        self._by_receiver: dict[str, tuple] = {}
        self._by_scope: dict[str, dict[int, list[tuple[int, str]]]] = {}
        self._chains: dict[int, tuple[int, ...]] = {}
        self._owners: dict[int, str] = {}
        self._types: dict[str, list[int]] | None = None
        self._parameters: dict[int, set[str]] = {}

    def _slots(self, receiver: str) -> tuple:
        """Per pattern, the (end offset, type) declarations of `receiver` in file order."""
        found = self._by_receiver.get(receiver)
        if found is None:
            if _IDENTIFIER.fullmatch(receiver):
                if self._typed is None:
                    patterns = _DECLARATION_PATTERNS.get(self.pack, _DECLARATION_PATTERNS["default"])
                    self._typed = _declaration_index(patterns, self.masked())
                found = tuple(index.get(receiver, []) for index in self._typed)
            else:
                found = _literal_declarations(receiver, self.masked())
            self._by_receiver[receiver] = found
        return found

    def anywhere(self, receiver: str, line: int) -> str:
        """The type a field named `receiver` was last declared with before the end of `line`."""
        # A match inside the prefix ends at or before its final newline, so filtering
        # full-text matches by end offset equals searching every prefix again.
        limit = self.line_start[min(line, len(self.lines))] - 1
        matched = ""
        for found in self._slots(receiver):
            count = bisect.bisect_right(found, (limit, _AFTER))
            if count:
                matched = found[count - 1][1]
        return matched

    def _offset(self, point: Any) -> int:
        row, column = point[0], point[1]
        if row >= len(self.lines):
            return self.line_start[-1]
        text = self.lines[row]
        if not text.isascii():
            column = len(text.encode("utf-8")[:column].decode("utf-8", errors="replace"))
        return self.line_start[row] + min(column, len(text))

    def _scope_at(self, offset: int) -> int:
        """The innermost scope holding a character offset; -1 for the file."""
        if self._spans is None:
            self._spans = ([self._offset(point) for point in self.scopes.start],
                           [self._offset(point) for point in self.scopes.end])
        starts, ends = self._spans
        scope = bisect.bisect_right(starts, offset) - 1
        while scope >= 0 and ends[scope] <= offset:
            scope = self.scopes.parent[scope]
        return scope

    def _declared(self, receiver: str) -> dict[int, list[tuple[int, str]]]:
        """Scope -> the bindings of `receiver` made directly in it; an untyped one has type ''."""
        by_scope = self._by_scope.get(receiver)
        if by_scope is None:
            if self._untyped is None:
                self._untyped = {}
                for pattern in _UNTYPED_BINDINGS.get(self.pack, _UNTYPED_BINDINGS["default"]):
                    for match in re.finditer(pattern, self.masked()):
                        self._untyped.setdefault(match.group("name"), []).append(match.end("name"))
            by_scope = self._by_scope[receiver] = {}
            text = self.masked()
            bindings = [found for slot in self._slots(receiver) for found in slot]
            for end in self._untyped.get(receiver, ()):
                same = _SAME_VALUE.match(text, end)
                if not same or same.group(1) != receiver:
                    bindings.append((end, ""))
            for end, type_name in sorted(bindings):  # a typed binding ends after its own keyword
                scope = self._scope_at(end - 1)
                if (type_name and scope >= 0 and self.scopes.kind[scope] == _FUNCTION
                        and text.startswith(receiver, end - len(receiver)) and text[end:end + 8].lstrip()[:1] == "("):
                    # `Repo find(...)` names the function itself: `find().save()` sees it from outside.
                    scope = self.scopes.parent[scope]
                by_scope.setdefault(scope, []).append((end, type_name))
        return by_scope

    def _chain(self, scope: int) -> tuple[int, ...]:
        chain = self._chains.get(scope)
        if chain is None:
            chain = self._chains[scope] = (-1,) if scope < 0 else (scope, *self._chain(self.scopes.parent[scope]))
        return chain

    def _is_parameter(self, scope: int, receiver: str) -> bool:
        names = self._parameters.get(scope)
        if names is None:
            names = self._parameters[scope] = self.parameters(self.scopes.node[scope])
        return receiver in names

    def _bound(self, end: int, point: Any) -> bool:
        """Whether the untyped binding ending at `end` is complete where the call starts.

        In `let v = v.parse()` the right-hand side still reads the outer `v`.
        """
        text, depth = self.masked(), 0
        for index in range(end, self._offset(point) if point is not None else end):
            char = text[index]
            if char in "([":
                depth += 1
            elif char in ")]":
                depth -= 1
                if depth < 0:
                    return True  # `for (const x of items) x.run()`
            elif depth == 0 and char in ";{\n":
                return True
        return point is None

    def visible(self, receiver: str, line: int, scope: int, point: Any = None) -> str:
        """The type of the nearest binding of the variable `receiver` that the call can see."""
        by_scope = self._declared(receiver)
        if not by_scope:
            return ""
        limit = self.line_start[min(line, len(self.lines))] - 1
        inside_function = False
        for enclosing in self._chain(scope):
            kind = self.scopes.kind[enclosing] if enclosing >= 0 else ""
            if kind == _TYPE and inside_function and self.pack == "python":
                continue  # a Python method does not see its class body's names
            found = by_scope.get(enclosing)
            if found:
                count = bisect.bisect_right(found, (limit, _AFTER))
                while count and not found[count - 1][1] and not self._bound(found[count - 1][0], point):
                    count -= 1
                if count:
                    return found[count - 1][1]
                if kind == _TYPE and self.pack in _IMPLICIT_THIS_PACKS:
                    return found[0][1]  # a field declared further down its class
            if kind == _FUNCTION:
                inside_function = True
                if self._is_parameter(enclosing, receiver):
                    return ""  # an untyped parameter hides outer declarations
        if self.pack == "cpp":
            for owner in self._owner_types(scope):
                if owner in by_scope:
                    return by_scope[owner][-1][1]
        return ""

    def _owner_types(self, scope: int) -> list[int]:
        """The class bodies in this file that `Owner::method() { ... }`, defined outside them, belongs to."""
        chain = self._chain(scope)
        function = next((item for item in reversed(chain) if item >= 0 and self.scopes.kind[item] != _BLOCK), -1)
        if function < 0 or self.scopes.kind[function] != _FUNCTION:
            return []
        starts, ends = self._spans
        owner = self._owners.get(function)
        if owner is None:
            header = self.masked()[starts[function]:ends[function]].split("{", 1)[0]
            names = _CPP_METHOD_OWNER.findall(header)
            owner = self._owners[function] = names[-1] if names else ""
        if self._types is None:
            self._types = {}
            for index, kind in enumerate(self.scopes.kind):
                named = _CPP_TYPE_NAME.match(self.masked(), starts[index]) if kind == _TYPE else None
                if named:
                    self._types.setdefault(named.group(1), []).append(index)
        return self._types.get(owner, []) if owner else []


def type_receivers(calls: list[dict[str, Any]], pack: str, scopes: LexicalScopes, lines: list[str],
                   masked: Callable[[], str], parameters: Callable[[Any], set[str]]) -> None:
    """Set `receiver_type` on every call and drop the scope marker left by the visit."""
    types = _ReceiverTypes(pack, scopes, lines, masked, parameters)
    own = SELF_RECEIVERS.get(pack, ())
    for call in calls:
        scope, point = call.pop("_scope", (-1, None))
        receiver = call.get("receiver", "")
        receiver_type = ""
        if receiver == "this" or receiver in own or call.get("self_receiver"):  # own class
            receiver_type = call.get("container", "")
        elif receiver:
            if len(call.get("receiver_chain") or ()) > 1 or not _IDENTIFIER.fullmatch(receiver):
                matched = types.anywhere(receiver, int(call["line"]))
            else:
                matched = types.visible(receiver, int(call["line"]), scope, point)
            if matched:
                receiver_type = _TYPE_TAIL.sub("", matched.split("<", 1)[0].split(".")[-1])
            elif receiver[:1].isupper():
                receiver_type = receiver
        call["receiver_type"] = receiver_type
