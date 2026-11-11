"""Declarations the grammar does not mark as such: assigned JavaScript methods and generic bounds."""
from __future__ import annotations

import re
from typing import Any, Callable

# A stub in a test (`response.text = async () => ''`) or a patched global (`Math.random = ...`)
# does not define a method that the project's calls reach.
_PATCHED_GLOBALS = frozenset({"Math", "Date", "JSON", "console", "window", "globalThis", "global", "Object",
                              "Array", "Promise", "process", "document", "navigator", "Reflect", "Symbol"})
ASSIGNED_FUNCTIONS = frozenset({"function_expression", "function", "arrow_function"})

# `S: Sink`, `S: 'a + Sink`, `S: ?Sized + io::Write` (Rust, Swift, Kotlin) and `T extends Foo` (Java, TypeScript).
_GENERIC_BOUND = re.compile(r"(?<![\w:.'])([A-Z][A-Za-z0-9]{0,2})\s*(?::|\s+extends)\s*"
                            r"(?:(?:'\w+|\?Sized)\s*\+\s*)*(?:\w+::)*([A-Z][A-Za-z0-9_]+)")


def _text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _top_level_object(source: bytes, owner: str) -> bool:
    """Only an object declared at the file's top level (`var res = ...`) is one other files can hold."""
    return re.search(rb"(?m)^(?:export\s+)?(?:default\s+)?(?:var|let|const|function|class)\s+" + re.escape(owner.encode())
                     + rb"\b", source) is not None


def _member_target(source: bytes, left) -> tuple[str, str] | None:
    """(object, method) named by the left side `res.send` or `Foo.prototype.bar` of an assignment."""
    if left is None or left.type != "member_expression":
        return None
    owner, method = left.child_by_field_name("object"), left.child_by_field_name("property")
    if owner is None or method is None:
        return None
    names = re.findall(r"[A-Za-z_$][\w$]*", re.sub(r"\.prototype$", "", _text(source, owner)))
    return (names[-1], _text(source, method)) if names and names[-1] not in {"this", "exports", "module"} else None


def _assigned_function(assignment):
    """The function at the end of `res.set = res.header = function header() {}`, or None."""
    right = assignment.child_by_field_name("right")
    while right is not None and right.type == "assignment_expression":
        right = right.child_by_field_name("right")
    return right if right is not None and right.type in ASSIGNED_FUNCTIONS else None


def _key(pair) -> str:
    key = pair.child_by_field_name("key")
    return key.text.decode("utf-8", errors="replace").strip("'\"") if key is not None and key.text else ""


def _defined_property(source: bytes, node) -> tuple[str, str] | None:
    """(object, property) for `defineGetter(req, 'host', function host() {})` or
    `Object.defineProperty(req, 'host', {get: () => ...})` on a top-level object."""
    parent = node.parent
    if parent is not None and parent.type == "pair" and _key(parent) == "get" and parent.parent is not None \
            and parent.parent.type == "object":
        parent = parent.parent.parent
    if parent is None or parent.type != "arguments" or parent.named_child_count != 3:
        return None
    owner, name = parent.named_children[0], parent.named_children[1]
    if owner.type != "identifier" or name.type != "string" or not _top_level_object(source, _text(source, owner)):
        return None
    return _text(source, owner), _text(source, name).strip("'\"`")


def assigned_method(source: bytes, node) -> tuple[str, str] | None:
    """(object, method) for `res.send = function send() {}`, `Foo.prototype.bar = () => {}` or a defined getter."""
    parent = node.parent
    if node.type not in ASSIGNED_FUNCTIONS or parent is None:
        return None
    if parent.type != "assignment_expression":
        return _defined_property(source, node)
    if parent.child_by_field_name("right") is None or parent.child_by_field_name("right").id != node.id:
        return None
    return _member_target(source, parent.child_by_field_name("left"))


def defined_property_symbol(source: bytes, call, rel_path: str, test_file: bool) -> dict[str, Any] | None:
    """A getter a call defines on a top-level object, so the calls inside it have their owner."""
    arguments = call.child_by_field_name("arguments")
    if test_file or arguments is None or arguments.named_child_count != 3:
        return None
    last = arguments.named_children[2]
    function = last if last.type in ASSIGNED_FUNCTIONS else next(
        (pair.child_by_field_name("value") for pair in last.named_children if pair.type == "pair" and _key(pair) == "get"),
        None) if last.type == "object" else None
    target = assigned_method(source, function) if function is not None else None
    if not target or target[0] in _PATCHED_GLOBALS:
        return None
    lines = _text(source, call).splitlines()
    return {"name": target[1], "kind": "method", "file": rel_path, "line": call.start_point.row + 1,
            "end_line": call.end_point.row + 1, "evidence": lines[0].strip()[:240] if lines else "",
            "bases": [], "parser": "tree-sitter", "container": target[0], "object_member": True,
            "getter": True, "parameter_count": 0}


def assigned_method_symbol(source: bytes, assignment, rel_path: str, test_file: bool) -> dict[str, Any] | None:
    """The method an assignment defines, reached through its object and never by a bare call.

    `response.json = ...` inside a function patches one value; it is not a method of the project.
    """
    if assignment.type != "assignment_expression" or test_file:
        return None
    # Each name of a chain (`res.set = res.header = function header`) is the same method.
    right = _assigned_function(assignment)
    assigned = _member_target(source, assignment.child_by_field_name("left")) if right is not None else None
    if not assigned or assigned[0] in _PATCHED_GLOBALS or not _top_level_object(source, assigned[0]):
        return None
    lines = _text(source, assignment).splitlines()
    parameters = right.child_by_field_name("parameters")
    return {"name": assigned[1], "kind": "method", "file": rel_path, "line": assignment.start_point.row + 1,
            "end_line": assignment.end_point.row + 1, "evidence": lines[0].strip()[:240] if lines else "",
            "bases": [], "parser": "tree-sitter", "container": assigned[0], "object_member": True,
            "parameter_count": parameters.named_child_count if parameters is not None else None}


def bounded_generics(members: list[dict[str, Any]], text: Callable[[], str]) -> list[dict[str, Any]]:
    """A field typed by a generic parameter (`sink: S` with `S: Sink`) is typed by its bound.

    Without the bound, `self.sink.matched()` matched a forwarding impl whose type is also
    called `S` (`impl<S: Sink> Sink for &mut S`). A name bound to two traits stays as written.
    """
    generic = {member.get("type") for member in members if re.fullmatch(r"[A-Z][A-Za-z0-9]{0,2}", str(member.get("type") or ""))}
    if not generic:
        return members
    bounds: dict[str, set[str]] = {}
    for name, bound in _GENERIC_BOUND.findall(text()):
        if name in generic:
            bounds.setdefault(name, set()).add(bound)
    for member in members:
        bound = bounds.get(member.get("type"))
        if bound and len(bound) == 1:
            member["type"] = next(iter(bound))
    return members
