"""Validate agent answers against graph evidence without claiming semantic proof."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STOP = {"the", "and", "for", "with", "this", "that", "from", "para", "como", "este", "esta", "con", "por", "una", "que", "del", "los", "las"}
_CITATION = re.compile(r"(?P<file>[\w./\\ -]+\.[A-Za-z0-9]+)(?::(?P<line>\d+))?")


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
    return {"ok": total > 0, "traceability_score": round(score, 4), "claims": verdicts,
            "summary": {"total": total, "supported": supported, "partial": partial,
                        "unsupported": total - supported - partial},
            "guidance": "SUPPORTED means traceable to indexed evidence, not formally proven. Verify INFERRED and AMBIGUOUS relations in source."}

