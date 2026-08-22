"""Explicit graph scopes for separating production, tests and legacy copies."""
from __future__ import annotations

_TEST_PARTS = {"test", "tests", "testing", "__tests__", "spec", "specs"}

def _node_path(node: dict) -> str:
    if node.get("file"):
        return str(node["file"])
    nid = str(node.get("id") or "")
    if nid.startswith(("file:", "dir:")):
        return nid.split(":", 1)[1]
    if nid.startswith("symbol:"):
        return nid[7:].split(":", 1)[0]
    return ""

def classify_path(path: str) -> str:
    parts = [part.lower() for part in path.replace("\\", "/").split("/") if part]
    if any("legacy" in part or "backup" in part for part in parts):
        return "legacy"
    if any(part in _TEST_PARTS or part.endswith("tests") or part.endswith("test") for part in parts):
        return "tests"
    return "production"

def filter_graph_scope(graph: dict, scope: str = "all") -> dict:
    scope = scope if scope in {"all", "production", "tests", "legacy"} else "all"
    if scope == "all":
        return graph
    nodes = [node for node in graph.get("nodes", []) if classify_path(_node_path(node)) == scope]
    ids = {node.get("id") for node in nodes}
    links = [link for link in graph.get("links", []) if link.get("source") in ids and link.get("target") in ids]
    return {**graph, "nodes": nodes, "links": links, "metadata": {**(graph.get("metadata") or {}), "scope": scope}}
