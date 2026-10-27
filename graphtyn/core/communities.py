"""Subsystem communities, god nodes and cross-community bridges.

Symbol relations are aggregated into a weighted file graph, which is then
clustered with Louvain when networkx is installed (fixed seed) or with a
deterministic label propagation otherwise. Labels come from the shared path of
each community, so no model is involved and results are reproducible.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

# Containment edges describe the tree, not how code depends on other code.
STRUCTURAL_LABELS = {"contiene", "declara", "contains", "declares"}
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|testing|spec|specs|fixtures?|__tests__)(?:/|$)|_test\.|\.test\.|_spec\.", re.I)
# Self-test entry points compiled into production files (listpackTest, test_x).
_TEST_NAME = re.compile(r"(?:^test_|^test[A-Z]|Tests?$|_test$)")
# Third-party and bundled code would otherwise dominate clusters and hubs.
_VENDORED_PATH = re.compile(
    r"(?:^|/)(?:deps|vendor|vendored|third_party|thirdparty|external|node_modules|assets)(?:/|$)|\.min\.", re.I)


def _production(path: str | None) -> bool:
    return bool(path) and not _TEST_PATH.search(path) and not _VENDORED_PATH.search(path)
_CONTAINER_KINDS = {"file", "module", "dir", "folder", "asset", "image", "media", "doc", "community"}


def _node_file(node: dict[str, Any]) -> str | None:
    node_id = str(node.get("id") or "")
    if node_id.startswith("file:"):
        return node_id[5:]
    return str(node["file"]) if node.get("file") else None


def file_graph(graph: dict[str, Any]) -> dict[tuple[str, str], int]:
    files = {str(node.get("id")): _node_file(node) for node in graph.get("nodes", [])}
    weights: Counter = Counter()
    for link in graph.get("links", []):
        if str(link.get("label") or "").lower() in STRUCTURAL_LABELS:
            continue
        source, target = files.get(str(link.get("source"))), files.get(str(link.get("target")))
        if source and target and source != target and _production(source) and _production(target):
            weights[tuple(sorted((source, target)))] += 1
    return dict(weights)


def _label_propagation(nodes: list[str], weights: dict[tuple[str, str], int]) -> list[set[str]]:
    neighbours: dict[str, dict[str, int]] = defaultdict(dict)
    for (left, right), weight in weights.items():
        neighbours[left][right] = weight
        neighbours[right][left] = weight
    labels = {node: node for node in nodes}
    for _ in range(30):
        changed = False
        for node in nodes:
            scores: Counter = Counter()
            for other, weight in neighbours[node].items():
                scores[labels[other]] += weight
            if not scores:
                continue
            best = max(scores.values())
            # Ties resolve to the smallest label, so runs are reproducible.
            choice = min(label for label, score in scores.items() if score == best)
            if choice != labels[node] and scores[choice] > scores.get(labels[node], 0):
                labels[node] = choice
                changed = True
        if not changed:
            break
    groups: dict[str, set[str]] = defaultdict(set)
    for node, label in labels.items():
        groups[label].add(node)
    return list(groups.values())


def detect_communities(weights: dict[tuple[str, str], int]) -> list[set[str]]:
    nodes = sorted({name for pair in weights for name in pair})
    if not nodes:
        return []
    try:
        import networkx as nx
        graph = nx.Graph()
        graph.add_nodes_from(nodes)
        graph.add_weighted_edges_from((left, right, weight) for (left, right), weight in sorted(weights.items()))
        found = [set(group) for group in nx.community.louvain_communities(graph, weight="weight", seed=0)]
    except ImportError:
        found = _label_propagation(nodes, weights)
    return sorted(found, key=lambda group: (-len(group), min(group)))


def community_label(files: set[str]) -> str:
    """Most frequent directory (up to three levels) and the share it covers."""
    parents = Counter("/".join(PurePosixPath(path).parent.parts[:3]) or "(root)" for path in files)
    directory, count = parents.most_common(1)[0]
    share = round(100 * count / len(files))
    return directory if share == 100 else f"{directory} ({share}%)"


def god_nodes(graph: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Most connected production symbols, ignoring containment and test code."""
    degree: Counter = Counter()
    for link in graph.get("links", []):
        if str(link.get("label") or "").lower() in STRUCTURAL_LABELS:
            continue
        degree[str(link.get("source"))] += 1
        degree[str(link.get("target"))] += 1
    # Calls to a name defined in several files fan out to every homonym, so a
    # high degree there measures ambiguity, not centrality.
    definitions = Counter(str(node.get("name") or "") for node in graph.get("nodes", [])
                          if node.get("kind") not in _CONTAINER_KINDS and node.get("file"))
    rows = []
    for node in graph.get("nodes", []):
        node_id = str(node.get("id") or "")
        path = _node_file(node) or ""
        if (node.get("kind") in _CONTAINER_KINDS or not degree.get(node_id) or not node.get("line")
                or not _production(path) or definitions[str(node.get("name") or "")] > 2
                or _TEST_NAME.search(str(node.get("name") or ""))):
            continue
        rows.append({"id": node_id, "name": node.get("name"), "kind": node.get("kind"),
                     "file": path, "line": node.get("line"), "degree": degree[node_id]})
    return sorted(rows, key=lambda row: (-row["degree"], row["file"], row["line"] or 0))[:limit]


def analyze_communities(graph: dict[str, Any], *, max_communities: int = 12,
                        max_bridges: int = 6) -> dict[str, Any]:
    weights = file_graph(graph)
    groups = detect_communities(weights)
    membership = {path: index for index, group in enumerate(groups) for path in group}
    gods = god_nodes(graph, limit=40)
    communities = []
    seen_labels: Counter = Counter()
    for index, group in enumerate(groups[:max_communities]):
        internal = sum(weight for (left, right), weight in weights.items()
                       if membership.get(left) == index and membership.get(right) == index)
        central = [row["name"] for row in gods if membership.get(row["file"]) == index][:4]
        strength: Counter = Counter()
        for (left, right), weight in weights.items():
            if membership.get(left) == index and membership.get(right) == index:
                strength[left] += weight
                strength[right] += weight
        anchors = [PurePosixPath(path).stem for path, _ in strength.most_common(2)]
        label = community_label(group) + (f": {', '.join(anchors)}" if anchors else "")
        seen_labels[label] += 1
        if seen_labels[label] > 1:
            label = f"{label} · {central[0] if central else '#' + str(seen_labels[label])}"
        communities.append({"id": index, "label": label, "files": len(group),
                            "internal_relations": internal, "central_symbols": central,
                            "sample_files": sorted(group)[:3]})
    bridges: Counter = Counter()
    for (left, right), weight in weights.items():
        a, b = membership.get(left), membership.get(right)
        if a is not None and b is not None and a != b:
            bridges[(left, right)] += weight
    # A bridge is surprising when neither file's directory contains the other's.
    surprising = []
    for (left, right), weight in bridges.most_common():
        left_dir, right_dir = PurePosixPath(left).parent.parts, PurePosixPath(right).parent.parts
        shorter = min(len(left_dir), len(right_dir))
        if left_dir[:shorter] == right_dir[:shorter]:
            continue
        surprising.append({"from": left, "to": right, "relations": weight,
                           "communities": [communities[membership[left]]["label"]
                                           if membership[left] < len(communities) else str(membership[left]),
                                           communities[membership[right]]["label"]
                                           if membership[right] < len(communities) else str(membership[right])]})
        if len(surprising) >= max_bridges:
            break
    questions = [f"¿Qué depende de `{row['name']}` ({row['file']}:{row['line']}) y qué rompería un cambio?"
                 for row in gods[:2]]
    questions += [f"¿Por qué `{item['from']}` se relaciona con `{item['to']}`?" for item in surprising[:2]]
    if len(communities) >= 2:
        questions.append(f"¿Cómo fluye una petición de `{communities[0]['label']}` a `{communities[1]['label']}`?")
    return {"algorithm": _algorithm_name(), "communities": communities, "community_count": len(groups),
            "god_nodes": gods[:10], "surprising_connections": surprising, "suggested_questions": questions}


def _algorithm_name() -> str:
    try:
        import networkx  # noqa: F401
        return "louvain(networkx, seed=0)"
    except ImportError:
        return "label-propagation(deterministic)"
