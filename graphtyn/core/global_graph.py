"""Deterministic cross-repository graph registry and compact queries."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from .storage import data_home


def default_registry(home: Path | None = None) -> Path:
    return (home / ".graphtyn" if home else data_home()) / "global-graph.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "projects": {}, "nodes": [], "links": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("El registro global no es un objeto JSON")
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _namespaced(tag: str, node_id: str) -> str:
    return f"{tag}::{node_id}"


def register_project(graph: dict[str, Any], project: Path, tag: str, registry: Path) -> dict[str, Any]:
    tag = tag.strip()
    if not tag or "::" in tag:
        raise ValueError("El alias debe ser no vacío y no puede contener '::'")
    data = remove_project(tag, registry, missing_ok=True)
    nodes = []
    known_ids = set()
    for raw in graph.get("nodes", []):
        if not raw.get("id"):
            continue
        node = dict(raw)
        node["local_id"] = str(raw["id"])
        node["id"] = _namespaced(tag, str(raw["id"]))
        node["project"] = tag
        node["project_path"] = str(project.resolve())
        known_ids.add(node["id"])
        nodes.append(node)
    links = []
    for raw in graph.get("links", []):
        source = raw.get("source")
        target = raw.get("target")
        source = source.get("id") if isinstance(source, dict) else source
        target = target.get("id") if isinstance(target, dict) else target
        source_id, target_id = _namespaced(tag, str(source)), _namespaced(tag, str(target))
        if source_id not in known_ids or target_id not in known_ids:
            continue
        links.append({**raw, "source": source_id, "target": target_id, "project": tag})
    digest = hashlib.sha256(json.dumps(graph, sort_keys=True, default=str).encode()).hexdigest()[:16]
    data.setdefault("projects", {})[tag] = {
        "path": str(project.resolve()), "nodes": len(nodes), "links": len(links),
        "digest": digest, "updated_at": int(time.time()),
    }
    data.setdefault("nodes", []).extend(nodes)
    data.setdefault("links", []).extend(links)
    # Cross-project candidates are explicitly AMBIGUOUS: equal symbol names are
    # useful navigation hints, never proof of a runtime dependency.
    candidates: dict[str, list[dict[str, Any]]] = {}
    for node in data["nodes"]:
        if node.get("kind") in {"class", "interface", "function", "method", "route", "table"}:
            candidates.setdefault(str(node.get("name", "")).casefold(), []).append(node)
    cross_links = []
    for same_name in candidates.values():
        projects = {node["project"] for node in same_name}
        if len(projects) < 2 or len(same_name) > 12:
            continue
        ordered = sorted(same_name, key=lambda node: node["id"])
        for left, right in zip(ordered, ordered[1:]):
            if left["project"] != right["project"]:
                cross_links.append({"source": left["id"], "target": right["id"], "label": "possible_cross_project_contract",
                                    "confidence": "AMBIGUOUS", "project": "__cross__"})
    data["links"] = [link for link in data["links"] if link.get("project") != "__cross__"] + cross_links
    _write(registry, data)
    return data


def remove_project(tag: str, registry: Path, missing_ok: bool = False) -> dict[str, Any]:
    data = _load(registry)
    if tag not in data.get("projects", {}) and not missing_ok:
        raise KeyError(tag)
    data.setdefault("projects", {}).pop(tag, None)
    data["nodes"] = [node for node in data.get("nodes", []) if node.get("project") != tag]
    prefix = f"{tag}::"
    data["links"] = [link for link in data.get("links", [])
                     if link.get("project") != tag
                     and not str(link.get("source", "")).startswith(prefix)
                     and not str(link.get("target", "")).startswith(prefix)]
    if registry.exists() or not missing_ok:
        _write(registry, data)
    return data


def list_projects(registry: Path) -> list[dict[str, Any]]:
    data = _load(registry)
    return [{"tag": tag, **meta} for tag, meta in sorted(data.get("projects", {}).items())]


def query_global(query: str, registry: Path, limit: int = 20) -> dict[str, Any]:
    data = _load(registry)
    terms = [part.casefold() for part in query.split() if len(part) > 1]
    scored = []
    for node in data.get("nodes", []):
        haystack = " ".join(str(node.get(key, "")) for key in ("name", "details", "file", "kind")).casefold()
        score = sum(term in haystack for term in terms)
        if score:
            scored.append((score, int(node.get("degree", 0)), node))
    matches = [item[2] for item in sorted(scored, key=lambda item: (-item[0], -item[1], item[2]["id"]))[:limit]]
    ids = {node["id"] for node in matches}
    links = [link for link in data.get("links", []) if link.get("source") in ids and link.get("target") in ids]
    return {"query": query, "projects": sorted({n["project"] for n in matches}), "nodes": matches, "links": links,
            "truncated": len(scored) > limit, "registry": str(registry)}
