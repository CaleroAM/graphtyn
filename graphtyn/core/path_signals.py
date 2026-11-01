"""Path and package signals used to rank candidate code for a request."""
from __future__ import annotations

import re
from typing import Any

TEST_PATH = re.compile(r"(?:^|/)(?:tests?|specs?|fixtures?)(?:/|$|[_.])|[_.](?:test|spec)s?\.[^/.]+$", re.I)
# Vendored and minified third-party code is never the project's own flow.
VENDORED_PATH = re.compile(
    r"(?:^|/)(?:vendor|node_modules|third_party)/|\.min\.[a-z]+$|(?:^|/)@[^/]+--[^/]+\.js$", re.I)


def named_package_roots(all_nodes: list[dict[str, Any]], request: str) -> set[str]:
    """Top-level directories a request names ("ActiveRecord" → activerecord/ in Rails).

    Naming a package of a monorepo scopes homonyms like a qualified name does.
    """
    roots = {str(node.get("file") or "").replace("\\", "/").split("/", 1)[0].lower()
             for node in all_nodes if "/" in str(node.get("file") or "").replace("\\", "/")}
    if len(roots) < 2:
        return set()
    return {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", str(request or ""))
            if word.lower() in roots}
