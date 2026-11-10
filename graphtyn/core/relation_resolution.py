"""Deterministic helpers for structural symbol and relation resolution."""

from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath
from typing import Any


def unique_symbol_id(
    rel_file: str, qualified: str, kind: str, symbol: dict[str, Any], existing: set[str]
) -> str | None:
    """Build a stable ID and retain same-name/same-arity lexical definitions."""
    base = f"symbol:{rel_file}:{qualified}"
    if base not in existing:
        return base
    if kind not in {"method", "function"}:
        return None
    arity = symbol.get("parameter_count")
    overload = f"{base}/{arity if arity is not None else symbol['line']}"
    return overload if overload not in existing else f"{overload}@{symbol['line']}"


_OWN_RECEIVERS = {"self", "cls", "this", "$this"}
_PARENT_RECEIVERS = {"super"}
_TYPE_KINDS = {"class", "interface", "struct", "trait", "protocol", "enum", "record", "object", "abstract_class", "type"}
_MAX_ANCESTRY = 8


def _simple(name: Any) -> str:
    return re.split(r"::|\.", str(name or ""))[-1]


_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_JS_IMPORT = re.compile(r"\bimport\s+(?:type\s+)?(?P<clause>[^;]+?)\s+from\s+['\"](?P<module>[^'\"]+)['\"]")
_JS_REQUIRE = re.compile(r"(?P<clause>\{[^}]*\}|[A-Za-z_$][\w$]*)\s*=\s*require\(\s*['\"](?P<module>[^'\"]+)['\"]")
_JS_NAME = re.compile(r"[A-Za-z_$][\w$]*")


def _js_clause(clause: str) -> list[tuple[str, str]]:
    """(local, imported) pairs: `x`, `{a, b as c}`, `* as ns`, `x, {a}` and `{a: c}` from require."""
    clause, pairs = clause.strip(), []
    braces = re.search(r"\{([^}]*)\}", clause)
    for part in (braces.group(1).split(",") if braces else []):
        names = [name for name in re.split(r"\s+as\s+|\s*:\s*", part.replace("type ", " ").strip()) if name]
        if names and all(_JS_NAME.fullmatch(name) for name in names):
            pairs.append((names[-1], names[0]))
    namespace = re.search(r"\*\s+as\s+([A-Za-z_$][\w$]*)", clause)
    if namespace:
        pairs.append((namespace.group(1), "*"))
    default = clause.split(",", 1)[0].strip()
    if _JS_NAME.fullmatch(default):
        pairs.append((default, "default"))
    return pairs


_GO_IMPLEMENTERS = 50


def go_implementations(nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """A Go type implements an interface when its methods include every method the interface requires."""
    required: dict[str, set[str]] = {}
    declared: dict[tuple[str, str], set[str]] = {}
    types: dict[tuple[str, str], str] = {}
    interfaces: dict[tuple[str, str], str] = {}
    for node_id, node in nodes.items():
        path = str(node.get("file") or "")
        if not path.endswith(".go"):
            continue
        key = (path, str(node.get("name") or ""))
        if node.get("kind") == "interface":
            interfaces[key] = node_id
        elif node.get("kind") in {"struct", "type"}:
            types[(str(PurePosixPath(path).parent), str(node.get("name") or ""))] = node_id
        elif node.get("kind") == "method" and node.get("container"):
            owner = (path, str(node["container"]))
            required.setdefault(f"{path}\0{node['container']}", set()).add(str(node.get("name") or ""))
            declared.setdefault((str(PurePosixPath(path).parent), str(node["container"])), set()).add(str(node.get("name") or ""))
    links = []
    for (path, name), interface_id in interfaces.items():
        methods = required.get(f"{path}\0{name}", set())
        if not methods:
            continue
        found = [type_id for key, type_id in types.items() if methods <= declared.get(key, set())]
        for type_id in found[:_GO_IMPLEMENTERS]:
            links.append({"source": type_id, "target": interface_id, "label": "implementa",
                          "color": "rgba(245, 158, 11, 0.4)", "confidence": "INFERRED",
                          "file": nodes[type_id].get("file"), "line": nodes[type_id].get("line"),
                          "resolution": {"strategy": "go-method-set", "methods": sorted(methods)}})
    return links


class ClassAncestry:
    """Where a call on the caller's own object lands: its class first, then its bases.

    `self._find_error_handler(...)` inside `Flask` runs the method `Flask` inherits
    from `App`; `super().x()` skips the caller's own class. Inheritance edges must
    already be resolved, and ambiguous ones are ignored. Ruby has its own ancestry.
    """

    def __init__(self, nodes: dict[str, dict[str, Any]], links: list[dict[str, Any]]):
        self.nodes = nodes
        self.types = {}
        by_directory: dict[tuple[str, str], list[str]] = {}
        for node_id, node in nodes.items():
            if node.get("kind") in _TYPE_KINDS:
                self.types.setdefault((node.get("file"), node.get("name")), node_id)
                by_directory.setdefault((str(PurePosixPath(str(node.get("file") or "")).parent), str(node.get("name"))),
                                        []).append(node_id)
        # A Go method or an out-of-line C++ member may live beside its type, not in its file.
        self.beside = {key: ids[0] for key, ids in by_directory.items() if len(ids) == 1}
        self.bases: dict[str, list[str]] = {}
        for link in links:
            if link.get("label") in ("hereda", "implementa") and link.get("confidence") != "AMBIGUOUS":
                self.bases.setdefault(str(link.get("source")), []).append(str(link.get("target")))
        self._levels: dict[tuple[str, str], list[set[str]]] = {}

    def owner(self, rel_file: str, name: str) -> str | None:
        """The type a member of `name` in `rel_file` belongs to: in that file, or alone beside it."""
        return self.types.get((rel_file, name)) or self.beside.get((str(PurePosixPath(rel_file).parent), name))

    def _ancestry(self, rel_file: str, container: str) -> list[set[str]]:
        """The caller's type, then each generation of its bases."""
        key = (rel_file, container)
        if key not in self._levels:
            start = self.owner(rel_file, container)
            levels, frontier, seen = [], [start] if start else [], {start}
            while frontier and len(levels) <= _MAX_ANCESTRY:
                levels.append(set(frontier))
                frontier = [base for item in frontier for base in self.bases.get(item, ()) if base not in seen]
                seen.update(frontier)
            self._levels[key] = levels
        return self._levels[key]

    def dispatch(self, call: dict[str, Any], rel_file: str, targets: set[str]) -> tuple[set[str], str] | None:
        """The nearest definitions a self or super call reaches, and the class that holds them."""
        receiver = str(call.get("receiver") or "")
        # `super(Subcommand, self).__init__()` arrives with `self` as its receiver.
        parent = receiver in _PARENT_RECEIVERS or (call.get("receiver_chain") or [""])[0] in _PARENT_RECEIVERS
        own = (receiver in _OWN_RECEIVERS or bool(call.get("self_receiver"))) and not parent
        if not (own or parent) or rel_file.endswith(".rb") or not call.get("container"):
            return None
        levels = self._ancestry(rel_file, _simple(call["container"]))
        owners = {target: self.owner(str(self.nodes.get(target, {}).get("file") or ""),
                                     _simple(self.nodes.get(target, {}).get("container")))
                  for target in targets} if levels else {}
        for level in levels if own else levels[1:]:
            found = {target for target, owner in owners.items() if owner in level}
            if found:
                return found, str(self.nodes[next(iter(found))].get("container") or "")
        return None


# Above this many implementations a call is summarized, not fanned out: a one-method
# `String()` interface with fifty implementers would otherwise add fifty unverifiable
# consumers to every impact package that touches any of its call sites.
_DISPATCH_FANOUT = 8
_DISPATCH_OWNERS = {"interface", "protocol", "trait"}
_CALLABLE_KINDS = {"method", "function"}


class Implementations:
    """The concrete methods a call on an interface, trait or abstract method may run.

    Static resolution stops at the declaration (`Shape.area`); the code that runs is an
    override in an implementing type. Precision policy, from strongest to weakest:

    - The edge to the declaration keeps its own confidence: it is the static target.
    - Each override gets a method-level `implementa` edge to the declaration, as strong as
      the weakest `hereda`/`implementa` edge on the path between their types. These are
      bounded by the number of overrides, not call sites, so they are always emitted:
      impact on the declaration lists every override as affected.
    - A call site gets one INFERRED `llama` edge per override only while the declaration
      has at most `_DISPATCH_FANOUT` overrides. The runtime type is never known
      structurally, so a dispatched edge is never EXTRACTED. Above the cap the call keeps
      only the declaration edge, with `resolution.implementations` as the count.
    - A receiver typed as a concrete class already resolves to its own override through
      ranking (receiver match), so it never fans out. A `super` call runs the parent's
      body by definition and never fans out either.
    """

    def __init__(self, nodes: dict[str, dict[str, Any]], links: list[dict[str, Any]]):
        self.nodes = nodes
        self.ancestry = ClassAncestry(nodes, links)
        self.children: dict[str, list[tuple[str, str]]] = {}
        for link in links:
            if link.get("label") in ("hereda", "implementa") and link.get("confidence") != "AMBIGUOUS":
                self.children.setdefault(str(link.get("target")), []).append(
                    (str(link.get("source")), str(link.get("confidence") or "EXTRACTED")))
        self.methods: dict[tuple[str, str], list[str]] = {}
        for node_id, node in nodes.items():
            if node.get("kind") in _CALLABLE_KINDS and node.get("container"):
                owner = self.ancestry.owner(str(node.get("file") or ""), _simple(node["container"]))
                if owner:
                    self.methods.setdefault((owner, str(node.get("name") or "")), []).append(node_id)
        self._found: dict[str, list[tuple[str, str]]] = {}

    def _owner(self, target_id: str) -> str | None:
        node = self.nodes.get(target_id, {})
        if node.get("kind") not in _CALLABLE_KINDS or not node.get("container"):
            return None
        return self.ancestry.owner(str(node.get("file") or ""), _simple(node["container"]))

    def is_dispatchable(self, target_id: str) -> bool:
        """An interface, trait or protocol member (defaults included), or a method marked abstract."""
        owner = self._owner(target_id)
        if owner is None:
            return False
        return bool(self.nodes[target_id].get("abstract")) or self.nodes[owner].get("kind") in _DISPATCH_OWNERS

    def _same_signature(self, target_id: str, owner: str | None, candidates: Any) -> list[str]:
        """Among overloads, only the one with the declaration's arity overrides it.

        `serialize(Object)` is not implemented by `serialize(Object, Type)`. Without overloads on
        either side the name decides: Python and JavaScript overrides may add optional parameters.
        """
        candidates = list(candidates)
        name, arity = self.nodes[target_id].get("name"), self.nodes[target_id].get("parameter_count")
        if arity is None or (len(candidates) < 2 and len(self.methods.get((owner, str(name)), ())) < 2):
            return candidates
        return [method_id for method_id in candidates
                if self.nodes[method_id].get("parameter_count") in (None, arity)]

    def implementations(self, target_id: str) -> list[tuple[str, str]]:
        """(method id, confidence) for every same-named method of a descendant type."""
        if target_id in self._found:
            return self._found[target_id]
        name, owner = str(self.nodes[target_id].get("name") or ""), self._owner(target_id)
        found: list[tuple[str, str]] = []
        frontier, seen = [(owner, "EXTRACTED")] if owner else [], {owner}
        for _depth in range(_MAX_ANCESTRY):
            following = []
            for type_id, confidence in frontier:
                for child, edge_confidence in self.children.get(type_id, ()):
                    if child in seen:
                        continue
                    seen.add(child)
                    weakest = "INFERRED" if "INFERRED" in (confidence, edge_confidence) else "EXTRACTED"
                    following.append((child, weakest))
                    found.extend((method_id, weakest) for method_id in self._same_signature(
                        target_id, owner, self.methods.get((child, name), ())) if method_id != target_id)
            frontier = following
            if not frontier:
                break
        self._found[target_id] = sorted(found)
        return self._found[target_id]

    def override_links(self) -> list[dict[str, Any]]:
        """`implementa` edges from each override to the declaration it implements, and the count on it."""
        links = []
        for target_id, node in self.nodes.items():
            if node.get("kind") not in _CALLABLE_KINDS or not self.is_dispatchable(target_id):
                continue
            found = self.implementations(target_id)
            if found:
                node["implementations"] = len(found)
            for method_id, confidence in found:
                method = self.nodes[method_id]
                links.append({"source": method_id, "target": target_id, "label": "implementa",
                              "color": "rgba(245, 158, 11, 0.4)", "confidence": confidence,
                              "file": method.get("file"), "line": method.get("line"),
                              "resolution": {"strategy": "override", "declaration": target_id}})
        return links

    def call_links(self, link: dict[str, Any]) -> list[dict[str, Any]]:
        """The declaration edge, then one INFERRED edge per override while the fan-out is small."""
        resolution = link.get("resolution") or {}
        target_id = str(link.get("target"))
        parent = resolution.get("receiver") in _PARENT_RECEIVERS \
            or (resolution.get("receiver_chain") or [""])[0] in _PARENT_RECEIVERS
        if parent or not self.is_dispatchable(target_id):
            return [link]
        found = self.implementations(target_id)
        resolution["implementations"] = len(found)
        resolution["dispatch"] = "none" if not found else "expanded" if len(found) <= _DISPATCH_FANOUT else "summarized"
        if resolution["dispatch"] != "expanded":
            return [link]
        return [link, *({**link, "target": method_id, "confidence": "INFERRED",
                         "resolution": {**resolution, "strategy": "interface-dispatch", "declaration": target_id}}
                        for method_id, _confidence in found)]


class CandidateRanker:
    """Rank possible relation targets from structural and import evidence."""

    def __init__(self, nodes: dict[str, dict[str, Any]], imports: dict[str, list[dict[str, Any]]]):
        self.nodes = nodes
        self.imports = imports
        self._contexts: dict[str, tuple[set[str], dict[str, str], dict[str, str]]] = {}
        self._js: dict[str, dict[str, tuple[str, str]]] = {}

    @staticmethod
    def _python_module(rel_file: str, raw_module: str) -> str:
        leading_dots = len(raw_module) - len(raw_module.lstrip("."))
        if not leading_dots:
            return raw_module
        package = list(PurePosixPath(rel_file).with_suffix("").parts[:-1])
        parents = leading_dots - 1
        if parents > len(package):
            return ""
        base = package[:len(package) - parents] if parents else package
        suffix = [part for part in raw_module.lstrip(".").split(".") if part]
        return ".".join([*base, *suffix])

    def _import_context(self, rel_file: str) -> tuple[set[str], dict[str, str], dict[str, str]]:
        cached = self._contexts.get(rel_file)
        if cached is not None:
            return cached
        namespaces: set[str] = set()
        aliases: dict[str, str] = {}
        symbols: dict[str, str] = {}
        for item in self.imports.get(rel_file, []):
            text = str(item.get("text") or "")
            match = re.search(r"\busing\s+(?:(\w+)\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)", text)
            if match:
                if match.group(1):
                    aliases[match.group(1)] = match.group(2)
                else:
                    namespaces.add(match.group(2))
            python_from = re.match(r"\s*from\s+([.A-Za-z_][.A-Za-z0-9_]*)\s+import\s+(.+)", text)
            if python_from:
                module = self._python_module(rel_file, python_from.group(1))
                for part in python_from.group(2).strip().strip("()").split(","):
                    bits = re.split(r"\s+as\s+", part.strip())
                    if bits and re.fullmatch(r"[A-Za-z_]\w*", bits[0]):
                        symbols[bits[-1]] = f"{module}.{bits[0]}"
        self._contexts[rel_file] = namespaces, aliases, symbols
        return self._contexts[rel_file]

    def _js_bindings(self, rel_file: str) -> dict[str, tuple[str, str]]:
        """local name → (module, imported name) for `import`/`require` in a JavaScript or TypeScript file."""
        cached = self._js.get(rel_file)
        if cached is not None:
            return cached
        bindings: dict[str, tuple[str, str]] = {}
        for item in self.imports.get(rel_file, []) if rel_file.endswith(_JS_SUFFIXES) else []:
            text = str(item.get("text") or "")
            match = _JS_IMPORT.search(text) or _JS_REQUIRE.search(text)
            if match:
                for local, imported in _js_clause(match.group("clause")):
                    bindings[local] = (match.group("module"), imported)
        self._js[rel_file] = bindings
        return bindings

    def _js_filter(self, rel_file: str, called_name: str, targets: set[str]) -> set[str] | None:
        """Targets an imported JavaScript name can reach: none from a package, the imported file otherwise."""
        binding = self._js_bindings(rel_file).get(called_name)
        if binding is None:
            return None
        module, imported = binding
        if not module.startswith((".", "/")):
            return set()  # `import {setTimeout as delay} from 'node:timers/promises'`
        base = posixpath.normpath(posixpath.join(posixpath.dirname(rel_file), module))
        if base.endswith(_JS_SUFFIXES):
            base = posixpath.splitext(base)[0]  # TypeScript imports `./x.js` for x.ts
        stems = {base, posixpath.join(base, "index")}
        return {target for target in targets
                if posixpath.splitext(str(self.nodes.get(target, {}).get("file") or ""))[0] in stems
                and (imported in {"default", "*"} or self.nodes.get(target, {}).get("name") == imported)}

    def imported_target_name(self, rel_file: str, called_name: str) -> str:
        binding = self._js_bindings(rel_file).get(called_name)
        if binding and binding[1] not in {"default", "*"}:
            return binding[1]
        imported = self._import_context(rel_file)[2].get(called_name, "")
        return imported.rsplit(".", 1)[-1] if imported else called_name

    def is_imported(self, rel_file: str, called_name: str) -> bool:
        return called_name in self._import_context(rel_file)[2] or called_name in self._js_bindings(rel_file)

    def filter_imported_targets(self, rel_file: str, called_name: str,
                                targets: set[str]) -> set[str]:
        """Restrict imported calls to the module Python (or JavaScript) would actually load."""
        reachable = self._js_filter(rel_file, called_name, targets)
        if reachable is not None:
            return reachable
        imported = self._import_context(rel_file)[2].get(called_name, "")
        if not imported:
            return targets
        module, symbol = imported.rsplit(".", 1)
        expected_file = module.replace(".", "/")
        return {
            target_id for target_id in targets
            if self.nodes.get(target_id, {}).get("name") == symbol
            and str(self.nodes.get(target_id, {}).get("file") or "")
            .removesuffix("/__init__.py").removesuffix(".py") == expected_file
        }

    def lexical_targets(self, rel_file: str, called_name: str,
                        caller: str, targets: set[str]) -> set[str]:
        """Return definitions that shadow an imported name in Python scope.

        Import filtering is only a fallback: a nested or module-level
        definition with the same spelling wins during Python name lookup.
        An alias is treated exactly like any other binding: a local definition
        named ``fetch`` shadows an imported ``collect as fetch``.
        """
        same_file = {
            target for target in targets
            if self.nodes.get(target, {}).get("file") == rel_file
            and self.nodes.get(target, {}).get("name") == called_name
            and self.nodes.get(target, {}).get("kind") in ("function", "method")
        }
        if not same_file:
            return set()
        scoped = {target for target in same_file
                  if caller and self.nodes.get(target, {}).get("scope") == caller}
        return scoped or {
            target for target in same_file
            if not self.nodes.get(target, {}).get("scope")
        }

    def __call__(
        self, target_id: str, rel_file: str, container: str = "", receiver: str = "",
        arity: Any = None, lexical_scope: str = "", called_name: str = "",
    ) -> int:
        target = self.nodes.get(target_id, {})
        score = 4 if target.get("file") == rel_file else 0
        if lexical_scope and target.get("scope") == lexical_scope:
            score += 16
        if container and target.get("container") == container:
            score += 5
        if receiver and receiver in {target.get("container"), target.get("name")}:
            score += 12
        required, maximum = target.get("required_parameter_count"), target.get("parameter_count")
        if arity is not None and maximum == arity:
            score += 5
        elif arity is not None and required is not None and maximum is not None and required <= arity <= maximum:
            score += 5 if required == arity else 3
        source_assembly = self.nodes.get(f"file:{rel_file}", {}).get("assembly")
        if source_assembly and source_assembly == target.get("assembly"):
            score += 2
        namespaces, aliases, imported_symbols = self._import_context(rel_file)
        namespace = str(target.get("namespace") or "")
        if namespace and (namespace in namespaces or any(namespace.startswith(item + ".") for item in namespaces)):
            score += 3
        if receiver and aliases.get(receiver, "").endswith("." + str(target.get("container") or "")):
            score += 12
        imported_symbol = imported_symbols.get(called_name, "")
        if imported_symbol:
            module = imported_symbol.rsplit(".", 1)[0].replace(".", "/")
            target_file = str(target.get("file") or "").removesuffix("/__init__.py").removesuffix(".py")
            if target.get("name") == imported_symbol.rsplit(".", 1)[-1] and target_file == module:
                score += 16
        return score
