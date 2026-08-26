"""Validate agent answers against graph evidence without claiming semantic proof."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STOP = {"the", "and", "for", "with", "this", "that", "from", "para", "como", "este", "esta", "con", "por", "una", "que", "del", "los", "las"}
_CITATION = re.compile(r"(?P<file>[\w./\\ -]+\.[A-Za-z0-9]+)(?::(?P<line>\d+))?")


def validate_context_package(graph: dict, package: dict[str, Any]) -> dict[str, Any]:
    """Reject dangling evidence and unsupported directional conclusions."""
    graph_nodes = {node.get("id") for node in graph.get("nodes", [])}
    selected = {node.get("id") for node in package.get("nodes", [])}
    dangling_nodes = sorted(str(node_id) for node_id in selected if node_id not in graph_nodes)
    dangling_links = []
    ambiguous = 0
    located = 0
    for link in package.get("links", []):
        if link.get("source") not in selected or link.get("target") not in selected:
            dangling_links.append({key: link.get(key) for key in ("source", "target", "label")})
        if str(link.get("confidence") or "").upper() == "AMBIGUOUS":
            ambiguous += 1
        if link.get("file") and link.get("line"):
            located += 1
    missing_locations = [node.get("id") for node in package.get("nodes", [])
                         if node.get("kind") not in {"file", "module", "doc", "image", "media"}
                         and not (node.get("file") and node.get("line"))]
    ok = bool(selected) and not dangling_nodes and not dangling_links
    return {
        "ok": ok,
        "nodes": len(selected),
        "relations": len(package.get("links", [])),
        "located_relations": located,
        "ambiguous_relations": ambiguous,
        "dangling_nodes": dangling_nodes,
        "dangling_links": dangling_links,
        "missing_node_locations": missing_locations,
        "policy": "AMBIGUOUS relations may be shown but must not be asserted as fact",
    }


def detect_incomplete_answer(answer: str) -> dict[str, Any]:
    text = str(answer or "").strip()
    reasons = []
    if len(text) < 40:
        reasons.append("too_short")
    if text and text[-1] in {",", ":", ";", "-", "("}:
        reasons.append("trailing_fragment")
    if text.count("```") % 2:
        reasons.append("unclosed_code_fence")
    if text.count("(") > text.count(")"):
        reasons.append("unclosed_parenthesis")
    return {"complete": not reasons, "reasons": reasons, "characters": len(text)}


def _terms(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z_ÁÉÍÓÚáéíóúñÑ][\wÁÉÍÓÚáéíóúñÑ.-]{2,}", text)
            if token.lower() not in _STOP}


def validate_answer(graph: dict, answer: str, claims: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Score traceability of explicit claims; it does not judge prose as true by itself."""
    nodes = {str(node.get("id")): node for node in graph.get("nodes", [])}
    links = graph.get("links", [])
    node_terms = {node_id: _terms(" ".join(str(node.get(k) or "") for k in ("name", "file", "details", "signature")))
                  for node_id, node in nodes.items()}
    if claims is None:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", answer) if len(part.strip()) >= 12]
        claims = [{"text": sentence} for sentence in sentences]
    verdicts = []
    for claim in claims:
        text = str(claim.get("text") or "").strip()
        requested = [str(item) for item in claim.get("evidence_ids", [])]
        citations = list(_CITATION.finditer(text))
        candidates = []
        for node_id, terms in node_terms.items():
            overlap = len(_terms(text) & terms)
            if node_id in requested:
                overlap += 10
            node = nodes[node_id]
            if any(str(node.get("file") or node.get("details") or "").endswith(match.group("file")) for match in citations):
                overlap += 6
            if overlap:
                candidates.append((overlap, node_id))
        candidates.sort(reverse=True)
        evidence_ids = [node_id for _, node_id in candidates[:3]]
        edge_evidence = [link for link in links if link.get("source") in evidence_ids and link.get("target") in evidence_ids]
        confidence = "unsupported"
        if evidence_ids:
            confidence = "supported" if citations or requested or edge_evidence else "partially_supported"
        verdicts.append({"claim": text, "verdict": confidence, "evidence_ids": evidence_ids,
                         "relations": [{k: link.get(k) for k in ("source", "target", "label", "confidence", "file", "line")}
                                       for link in edge_evidence[:5]]})
    supported = sum(item["verdict"] == "supported" for item in verdicts)
    partial = sum(item["verdict"] == "partially_supported" for item in verdicts)
    total = len(verdicts)
    score = (supported + partial * 0.5) / total if total else 0.0
    completeness = detect_incomplete_answer(answer)
    return {"ok": total > 0 and completeness["complete"], "traceability_score": round(score, 4), "claims": verdicts,
            "summary": {"total": total, "supported": supported, "partial": partial,
                        "unsupported": total - supported - partial},
            "completeness": completeness,
            "guidance": "SUPPORTED means traceable to indexed evidence, not formally proven. Verify INFERRED and AMBIGUOUS relations in source."}
