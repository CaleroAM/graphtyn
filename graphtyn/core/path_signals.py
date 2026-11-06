"""Path and package signals used to rank candidate code for a request."""
from __future__ import annotations

import re
from typing import Any

TEST_PATH = re.compile(r"(?:^|/)(?:tests?|specs?|fixtures?)(?:/|$|[_.])|[_.](?:test|spec)s?\.[^/.]+$", re.I)
# Vendored and minified third-party code is never the project's own flow.
VENDORED_PATH = re.compile(
    r"(?:^|/)(?:vendor|node_modules|third_party)/|\.min\.[a-z]+$|(?:^|/)@[^/]+--[^/]+\.js$", re.I)


def package_name_words(all_nodes: list[dict[str, Any]], request: str) -> dict[str, set[str]]:
    """Top-level directories named across two words ("Active Record" → activerecord/), and those words.

    Written that way the words name a package, so `record` is not a symbol of the request.
    """
    roots = _package_roots(all_nodes)
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", str(request or ""))
    named: dict[str, set[str]] = {}
    for first, second in zip(words, words[1:]):
        if (first + second).lower() in roots:
            named[(first + second).lower()] = {first.lower(), second.lower()}
    return named


def named_package_roots(all_nodes: list[dict[str, Any]], request: str) -> set[str]:
    """Top-level directories a request names ("ActiveRecord" → activerecord/ in Rails).

    Naming a package of a monorepo scopes homonyms like a qualified name does.
    """
    roots = _package_roots(all_nodes)
    written = {word.lower().replace("_", "") for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", str(request or ""))}
    return (written & roots) | set(package_name_words(all_nodes, request))


def package_root(node: dict[str, Any]) -> str:
    return str(node.get("file") or "").replace("\\", "/").split("/", 1)[0].lower()


def _package_roots(all_nodes: list[dict[str, Any]]) -> set[str]:
    roots = {package_root(node) for node in all_nodes if "/" in str(node.get("file") or "").replace("\\", "/")}
    return roots if len(roots) >= 2 else set()
