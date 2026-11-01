"""Ruby module composition: constant lookup for mixins and `super` along ancestors.

Rails assembles `ActiveRecord::Base` from dozens of modules, and a method such
as `save` is defined in several of them, each calling `super`. Without the
ancestor chain the graph stops at the first module; this module provides the
two pieces Ruby itself uses to continue:

* **Constant lookup.** `include Translation` inside `module ActiveRecord`
  names `ActiveRecord::Translation` before any other `Translation`.
* **Method resolution order.** `super` in `M#m` continues at the next ancestor
  of each class that includes `M` which defines `m`: prepended modules, the
  class, its included modules from last to first (each followed by its own
  includes), then the superclass.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Iterable

MAX_DISPATCH_TARGETS = 3


def qualified_name(node: dict[str, Any]) -> str:
    """`ActiveRecord::Persistence` for a module node, from its namespace and container."""
    parts = [part for part in str(node.get("namespace") or "").split("::") if part]
    container = str(node.get("container") or "")
    if container and (not parts or parts[-1] != container):
        parts.append(container)
    return "::".join([*parts, str(node.get("name") or "")])


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def canonical_owners(nodes: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Map every class/module node to one node per Ruby constant.

    A module reopened in several files (`ActiveRecord::Validations` in
    validations.rb, validations/uniqueness.rb…) is one constant; the canonical
    node is the declaration in the file named after it, else the first by path.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if node.get("kind") in ("class", "module") and str(node.get("file") or "").endswith(".rb"):
            groups.setdefault(qualified_name(node), []).append(node)
    canonical = {}
    for group in groups.values():
        chosen = min(group, key=lambda node: (PurePosixPath(str(node.get("file") or "")).stem
                                              != _snake(str(node.get("name") or "")),
                                              str(node.get("file") or ""), int(node.get("line") or 0)))
        for node in group:
            canonical[node["id"]] = chosen["id"]
    return canonical


def lexical_candidates(source: dict[str, Any], written: str, candidates: Iterable[str],
                       node_by_id: dict[str, dict[str, Any]]) -> list[str]:
    """Candidates a constant written inside `source` resolves to under Ruby's lookup.

    Scopes are tried from the innermost (`ActiveRecord::Base::X`) outwards to the
    top level; the first scope with a match wins. Returns every candidate when
    none matches, so the caller keeps its own ranking.
    """
    candidates = list(candidates)
    canonical = canonical_owners(node_by_id.get(candidate, {}) for candidate in candidates)
    by_name: dict[str, list[str]] = {}
    for candidate in candidates:
        group = by_name.setdefault(qualified_name(node_by_id.get(candidate, {})), [])
        chosen = canonical.get(candidate, candidate)
        if chosen not in group:
            group.append(chosen)
    scope = qualified_name(source).split("::")
    for depth in range(len(scope), -1, -1):
        full = "::".join([*scope[:depth], written]) if depth else written
        if full in by_name:
            return by_name[full]
    return candidates


class RubyAncestry:
    """Ancestor chains of the Ruby classes and modules of a graph.

    Mixin and inheritance relations must already be resolved; ambiguous ones
    are ignored. Reopened modules count as one constant.
    """

    def __init__(self, nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> None:
        self.node_by_id = {node.get("id"): node for node in nodes}
        canonical = canonical_owners(nodes)
        self.owner_of: dict[tuple[str, str], str] = {}
        for node in nodes:
            if node.get("kind") in ("class", "module"):
                self.owner_of.setdefault((str(node.get("file") or ""), str(node.get("name") or "")),
                                         canonical.get(node["id"], node["id"]))
        self.methods: dict[tuple[str, str], str] = {}
        for node in nodes:
            if node.get("kind") in ("method", "function") and node.get("container"):
                owner = self.owner_of.get((str(node.get("file") or ""), str(node["container"])))
                if owner:
                    self.methods.setdefault((owner, str(node.get("name") or "")), node["id"])
        self.includes: dict[str, list[tuple[int, str]]] = {}
        self.prepends: dict[str, list[tuple[int, str]]] = {}
        self.includers: dict[str, set[str]] = {}
        self.superclass: dict[str, str] = {}
        for link in links:
            if str(link.get("confidence") or "") == "AMBIGUOUS":
                continue
            source = canonical.get(link.get("source"), link.get("source"))
            target = canonical.get(link.get("target"), link.get("target"))
            if link.get("label") == "incluye" and link.get("mixin_kind") in ("include", "prepend"):
                table = self.prepends if link.get("mixin_kind") == "prepend" else self.includes
                table.setdefault(source, []).append((int(link.get("line") or 0), target))
                self.includers.setdefault(target, set()).add(source)
            elif link.get("label") == "hereda":
                self.superclass.setdefault(source, target)
        self._chains: dict[str, list[str]] = {}

    def owner(self, method_id: str) -> str | None:
        method = self.node_by_id.get(method_id) or {}
        return self.owner_of.get((str(method.get("file") or ""), str(method.get("container") or "")))

    def chain(self, owner: str) -> list[str]:
        if owner not in self._chains:
            self._chains[owner] = self._ancestors(owner, set())
        return self._chains[owner]

    def _ancestors(self, owner: str, seen: set[str]) -> list[str]:
        if owner in seen:
            return []
        seen.add(owner)
        chain = []
        for _line, module in sorted(self.prepends.get(owner, []), reverse=True):
            chain += self._ancestors(module, seen)
        chain.append(owner)
        for _line, module in sorted(self.includes.get(owner, []), reverse=True):
            chain += self._ancestors(module, seen)
        if owner in self.superclass:
            chain += self._ancestors(self.superclass[owner], seen)
        return chain

    def roots(self, module: str) -> list[str]:
        """Owners whose ancestor chains contain `module`: itself and every includer, transitively."""
        found, frontier = {module}, [module]
        while frontier:
            for includer in self.includers.get(frontier.pop(), ()):
                if includer not in found:
                    found.add(includer)
                    frontier.append(includer)
        return sorted(found)

    def dispatch(self, method_id: str, name: str, after_self: bool) -> list[str]:
        """Methods `name` reaches from `method_id`: `self.name` or, with `after_self`, `super`."""
        owner = self.owner(method_id)
        if not owner:
            return []
        targets: list[str] = []
        for root in self.roots(owner):
            chain = self.chain(root)
            if owner not in chain:
                continue
            following = chain[chain.index(owner) + 1:] if after_self else chain
            target = next((self.methods[(ancestor, name)] for ancestor in following
                           if (ancestor, name) in self.methods), None)
            if target and target != method_id and target not in targets:
                targets.append(target)
        return targets


    def call_links(self, caller_id: str, call: dict[str, Any], rel_file: str) -> list[dict[str, Any]]:
        """Relations for a receiverless call or `super` inside a Ruby method, by dispatch order.

        Empty when the caller belongs to no known class or module, or when the
        name reaches no method or too many (an unrelated set of includers).
        """
        name = str(call.get("name") or "")
        super_call = name == "super"
        if super_call:
            name = str((self.node_by_id.get(caller_id) or {}).get("name") or "")
        targets = self.dispatch(caller_id, name, after_self=super_call) if name else []
        if not targets or len(targets) > MAX_DISPATCH_TARGETS:
            return []
        # A self call that every includer dispatches to the caller's own module
        # is as certain as a same-class call; anything else depends on assembly.
        own = len(targets) == 1 and not super_call and self.owner(targets[0]) == self.owner(caller_id)
        return [{
            "source": caller_id, "target": target, "label": "llama",
            "color": "rgba(56, 189, 248, 0.35)", "confidence": "EXTRACTED" if own else "INFERRED",
            "file": rel_file, "line": call.get("line"), "evidence": call.get("evidence", ""),
            "resolution": {"strategy": "ruby-super-ancestors" if super_call else "ruby-ancestors",
                           "candidates": len(targets), "called_name": call.get("name", "")},
        } for target in targets]
