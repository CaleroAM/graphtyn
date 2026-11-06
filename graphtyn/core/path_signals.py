"""Path and package signals used to rank candidate code for a request."""
from __future__ import annotations

import re
from typing import Any

TEST_PATH = re.compile(r"(?:^|/)(?:tests?|specs?|fixtures?)(?:/|$|[_.])|[_.](?:test|spec)s?\.[^/.]+$", re.I)
# Vendored and minified third-party code is never the project's own flow.
VENDORED_PATH = re.compile(
    r"(?:^|/)(?:vendor|node_modules|third_party)/|\.min\.[a-z]+$|(?:^|/)@[^/]+--[^/]+\.js$", re.I)


def package_name_words(all_nodes: list[dict[str, Any]], request: str) -> dict[str, set[str]]:
    """Components named across two words ("Active Record" → activerecord/), and those words.

    A component is a top-level directory, a directory anywhere (`lib/action_dispatch`) or a
    namespace (`ActionDispatch::Routing`). Written that way the words name a component, so
    `record` is not a symbol of the request.
    """
    scopes = _scope_names(all_nodes)
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", str(request or ""))
    named: dict[str, set[str]] = {}
    for first, second in zip(words, words[1:]):
        if (first + second).lower() in scopes:
            named[(first + second).lower()] = {first.lower(), second.lower()}
    return named


_SCOPE_PHRASE = re.compile(
    r"\b(?:en|in|de|del|of|no|na|do|da|dans|du|im|nel|nella|di)\s+(?:(?:el|la|the|o|a|le|der|die|das|il|lo)\s+)?"
    r"([A-Za-z][A-Za-z0-9_-]*)", re.IGNORECASE)


def scope_words(all_nodes: list[dict[str, Any]], request: str) -> set[str]:
    """Words naming a component after a preposition ("ensure_sync en Flask"): where to look, not what.

    Flask also names a class of its repository, so taken as a symbol it filled an impact
    package with every use of that class.
    """
    scopes = _scope_names(all_nodes)
    return {word.lower() for word in _SCOPE_PHRASE.findall(str(request or "")) if _normalized(word) in scopes}


def named_package_roots(all_nodes: list[dict[str, Any]], request: str) -> set[str]:
    """Components a request names ("ActiveRecord" → activerecord/ in Rails).

    Naming a package of a monorepo scopes homonyms like a qualified name does. A single
    word must be a top-level directory; two words may name any component.
    """
    roots = _package_roots(all_nodes)
    written = {word.lower().replace("_", "") for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", str(request or ""))}
    return (written & roots) | set(package_name_words(all_nodes, request))


# A workspace member is a package of its own: crates/globset in a Cargo workspace,
# packages/router in a JavaScript monorepo.
_WORKSPACE_DIRS = frozenset({"crates", "packages", "libs", "modules", "apps", "services", "plugins", "components", "projects"})


def package_root(node: dict[str, Any]) -> str:
    parts = str(node.get("file") or "").replace("\\", "/").lower().split("/")
    return parts[1] if parts[0] in _WORKSPACE_DIRS and len(parts) > 2 else parts[0]


def in_named_scope(node: dict[str, Any], scopes: set[str]) -> bool:
    """Whether a node lives in one of the named components: its root, a directory or its namespace."""
    return bool(scopes) and (package_root(node) in scopes or not scopes.isdisjoint(_node_scopes(node)))


def _node_scopes(node: dict[str, Any]) -> set[str]:
    directories = str(node.get("file") or "").replace("\\", "/").split("/")[:-1]
    namespace = [part for part in re.split(r"::|\.|\\", str(node.get("namespace") or "")) if part]
    return {_normalized(part) for part in directories + namespace}


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]", "", name.lower())


_SCOPE_CACHE: dict[int, tuple[int, set[str]]] = {}


def _scope_names(all_nodes: list[dict[str, Any]]) -> set[str]:
    cached = _SCOPE_CACHE.get(id(all_nodes))
    if cached and cached[0] == len(all_nodes):
        return cached[1]
    if not _package_roots(all_nodes):
        names: set[str] = set()
    else:
        names = {scope for node in all_nodes for scope in _node_scopes(node) if len(scope) >= 5}
    _SCOPE_CACHE.clear()
    _SCOPE_CACHE[id(all_nodes)] = (len(all_nodes), names)
    return names


def _package_roots(all_nodes: list[dict[str, Any]]) -> set[str]:
    roots = {package_root(node) for node in all_nodes if "/" in str(node.get("file") or "").replace("\\", "/")}
    return roots if len(roots) >= 2 else set()
