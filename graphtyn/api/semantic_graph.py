"""Build the bounded semantic view used by the dashboard API."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core.ast_parser import ASTParser


_CONTENT_KINDS = {"image", "media", "doc"}
_SEMANTIC_KINDS = {"file", "class", "module", "function", "method", "route", *_CONTENT_KINDS}
_STOPWORDS = {
    "para", "como", "este", "esta", "estos", "estas", "desde", "hasta", "entre", "sobre",
    "archivo", "imagen", "documento", "audio", "video", "muestra", "define", "contiene",
    "sirve", "serve", "utiliza", "permite", "proyecto", "proyectos", "software", "sistema",
    "artefacto", "tecnico", "técnico", "tecnica", "técnica", "mediante", "basado", "basada",
    "unitycommercedemo", "assets", "project", "resources", "file", "docs", "media",
}


def _community_of(relative_path: str) -> str:
    parts = relative_path.split("/")
    if "/" not in relative_path:
        return "raiz"
    directories = parts[:-1]
    return "/".join(directories[:2]) if directories else "raiz"


def _node_community(node_id: str) -> str:
    if node_id.startswith("file:"):
        return _community_of(node_id.removeprefix("file:"))
    if node_id.startswith("symbol:"):
        parts = node_id.split(":")
        return _community_of(parts[1] if len(parts) > 1 else "raiz")
    if node_id.startswith("dir:"):
        key = node_id.removeprefix("dir:") or "raiz"
        return "raiz" if key == "root" else key
    return "raiz"


def _semantic_tokens(node: dict[str, Any]) -> set[str]:
    name = Path(node.get("name", "")).stem
    details = node.get("details", "") or ""
    details = re.sub(r"\s*\([^()]+[/\\][^()]+\)\s*$", "", details)
    text = re.sub(
        r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", f"{name} {details}"
    ).lower()
    return {
        token for token in re.findall(r"[a-záéíóúüñ0-9]+", text)
        if len(token) >= 4 and token not in _STOPWORDS and not token.isdigit()
    }


def _load_embedding_vectors(meta: dict[str, Any], index_dir: Callable[[Path], Path]) -> dict[str, list]:
    path = index_dir(Path(meta.get("path", "proyecto"))) / "semantic_index.json"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(row.get("id")): row.get("vector")
            for row in cached.get("rows", [])
            if row.get("id") and isinstance(row.get("vector"), list)
        }
    except (OSError, ValueError, TypeError):
        return {}


def _embedding_similarity(left: dict, right: dict, vectors: dict[str, list]) -> float:
    a = vectors.get(str(left.get("id")))
    b = vectors.get(str(right.get("id")))
    if not a or not b:
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a)) or 1.0
    norm_b = math.sqrt(sum(float(y) * float(y) for y in b)) or 1.0
    return dot / (norm_a * norm_b)


def _build_communities(data: dict, project_name: str, summary: str) -> tuple:
    architecture_id = "concept:global_arch"
    nodes = [{
        "id": architecture_id,
        "name": f"Arquitectura Global: {project_name}",
        "kind": "semantic_concept",
        "val": 18,
        "color": "#ec4899",
        "details": f"Propósito General: {summary}",
    }]
    links: list[dict] = []
    node_ids = {architecture_id}
    communities: dict[str, list[dict]] = {}
    semantic_content: list[dict] = []
    for node in data.get("nodes", []):
        if node.get("kind", "") not in _SEMANTIC_KINDS:
            continue
        communities.setdefault(_node_community(node.get("id", "")), []).append(node)
        semantic_content.append(node)

    for key, members in communities.items():
        community_id = f"community:{key}"
        top = sorted(members, key=lambda item: item.get("degree", 0), reverse=True)[:4]
        nodes.append({
            "id": community_id,
            "name": f"Subsistema: {key}",
            "kind": "community",
            "val": 12,
            "color": "#10b981",
            "details": f"{len(members)} elementos · nodos clave: {', '.join(item['name'] for item in top)}",
        })
        node_ids.add(community_id)
        links.append({
            "source": architecture_id, "target": community_id, "label": "agrupa",
            "color": "rgba(236, 72, 153, 0.35)", "confidence": "EXTRACTED",
        })
        for member in members:
            nodes.append(member)
            node_ids.add(member["id"])
            links.append({
                "source": community_id, "target": member["id"], "label": "pertenece",
                "color": "rgba(16, 185, 129, 0.35)", "confidence": "EXTRACTED",
            })
    return nodes, links, node_ids, semantic_content


def _semantic_candidates(content: list[dict], token_sets: list[set[str]], vectors: dict[str, list]) -> tuple:
    token_index: dict[str, list[int]] = {}
    for index, tokens in enumerate(token_sets):
        for token in tokens:
            token_index.setdefault(token, []).append(index)
    shared_counts: dict[tuple[int, int], int] = {}
    for indexes in token_index.values():
        if len(indexes) > 50:
            continue
        for position, left in enumerate(indexes):
            for right in indexes[position + 1:]:
                shared_counts[(left, right)] = shared_counts.get((left, right), 0) + 1

    candidates = {index: [] for index in range(len(content))}
    embedded_pairs = 0
    for (left, right), common in shared_counts.items():
        embedded_score = _embedding_similarity(content[left], content[right], vectors)
        if common < 2 and embedded_score < 0.68:
            continue
        denominator = (len(token_sets[left]) * len(token_sets[right])) ** 0.5 or 1
        score = max(common / denominator, embedded_score)
        if score < 0.28:
            continue
        embedded_pairs += int(embedded_score >= 0.68)
        candidates[left].append((score, right))
        candidates[right].append((score, left))
    return candidates, embedded_pairs


def _append_semantic_links(content: list[dict], links: list[dict], vectors: dict[str, list]) -> int:
    token_sets = [_semantic_tokens(node) for node in content]
    candidates, embedded_pairs = _semantic_candidates(content, token_sets, vectors)
    selected: set[tuple[int, int]] = set()
    for left, options in candidates.items():
        for score, right in sorted(options, reverse=True)[:2]:
            pair = (min(left, right), max(left, right))
            if pair in selected:
                continue
            selected.add(pair)
            left_node, right_node = content[pair[0]], content[pair[1]]
            shared_terms = sorted(token_sets[pair[0]] & token_sets[pair[1]])[:10]
            links.append({
                "source": left_node["id"],
                "target": right_node["id"],
                "label": f"similitud semántica · {round(score * 100)}%",
                "color": "rgba(236, 72, 153, 0.4)",
                "confidence": "INFERRED",
                "evidence": {
                    "method": ("cached-embedding+description-token-overlap" if vectors
                               else "cached-description-token-overlap"),
                    "shared_terms": shared_terms,
                    "embedding_similarity": round(
                        _embedding_similarity(left_node, right_node, vectors), 4
                    ),
                    "source_excerpt": (left_node.get("details") or "")[:240],
                    "target_excerpt": (right_node.get("details") or "")[:240],
                },
                "explanation": f"Comparten términos descriptivos: {', '.join(shared_terms)}",
            })
    return embedded_pairs


def _append_structural_links(data: dict, links: list[dict], node_ids: set[str]) -> None:
    for link in data.get("links", []):
        if link.get("source") in node_ids and link.get("target") in node_ids:
            links.append({
                "source": link.get("source"),
                "target": link.get("target"),
                "label": link.get("label", "conecta"),
                "color": "rgba(56, 189, 248, 0.4)",
                "confidence": link.get("confidence", "EXTRACTED"),
            })


def build_semantic_graph(data: dict, index_dir: Callable[[Path], Path]) -> dict:
    meta = data.get("metadata", {})
    project_name = Path(meta.get("path", "proyecto")).name
    summary = meta.get("ai_summary") or f"Módulo principal del sistema {project_name}"
    nodes, links, node_ids, content = _build_communities(data, project_name, summary)
    vectors = _load_embedding_vectors(meta, index_dir)
    embedding_pairs = _append_semantic_links(content, links, vectors)

    god_ids = {
        node["id"] for node in sorted(content, key=lambda item: item.get("degree", 0), reverse=True)[:6]
        if node.get("degree", 0) > 0
    }
    for node in nodes:
        if node.get("id") in god_ids:
            node["god"] = True
            node["val"] = round(node.get("val", 3) + 6, 2)
    _append_structural_links(data, links, node_ids)

    result = ASTParser()._enrich_graph_with_degree({"nodes": nodes, "links": links})
    result["metadata"] = {
        "view": "semantic-code",
        "semantic_scope": "code+documentation+media",
        "relationship_policy": "bounded-token-overlap+structural-links",
        "embedding_pairs": embedding_pairs,
        "inferred_edges": sum(link.get("confidence") == "INFERRED" for link in links),
        "structural_edges": sum(link.get("confidence") == "EXTRACTED" for link in links),
        "note": "La similitud propone relación; la dependencia estructural conserva su evidencia AST.",
    }
    return result
