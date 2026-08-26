"""Token-bounded source excerpts for questions the graph cannot fully prove."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_PRECISION_MARKERS = (
    "exact", "exacto", "exacta", "orden", "sequence", "secuencia",
    "lifecycle", "ciclo de vida", "when", "cuándo", "cuando", "condition",
    "condición", "condicion", "why", "por qué", "porque", "safe", "safety",
    "seguro", "seguridad", "defer", "panic", "timeout", "branch", "rama",
    "deep copy", "copia profunda", "reset", "pool", "trace", "traza",
)

_OBLIGATION_MARKERS = {
    "order_and_control_flow": ("orden", "sequence", "secuencia", "flow", "flujo", "lifecycle", "ciclo de vida"),
    "conditions_and_branches": ("condition", "condición", "condicion", "branch", "rama", "when", "cuándo", "cuando"),
    "state_mutation": ("state", "estado", "reset", "pool", "copy", "copia", "safe", "segur"),
    "failure_semantics": ("panic", "error", "timeout", "recover", "fallo", "defer"),
}


def select_evidence_mode(request: str, requested: str = "auto", intent: str = "flow") -> str:
    """Choose source expansion only for questions that need body-level proof."""
    if requested in {"compact", "balanced", "precision"}:
        return requested
    text = str(request or "").lower()
    if any(marker in text for marker in _PRECISION_MARKERS):
        return "precision"
    if intent == "flow" and len(re.findall(r"\b(?:and|y|then|después|además|también)\b", text)) >= 2:
        return "balanced"
    return "compact"


def requested_obligations(request: str) -> list[str]:
    text = str(request or "").lower()
    return [name for name, markers in _OBLIGATION_MARKERS.items() if any(marker in text for marker in markers)]


def _safe_source(root: Path, relative: str) -> Path | None:
    try:
        root = root.resolve()
        candidate = (root / relative).resolve()
        candidate.relative_to(root)
        return candidate if candidate.is_file() else None
    except (OSError, ValueError):
        return None


def _numbered_excerpt(path: Path, start: int, end: int, line_budget: int) -> tuple[str, int, int]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", 0, 0
    if not lines:
        return "", 0, 0
    start = max(1, min(start, len(lines)))
    end = max(start, min(end, len(lines)))
    if end - start + 1 > line_budget:
        end = start + line_budget - 1
    text = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
    return text, start, end


def attach_source_evidence(
    root: Path,
    result: dict[str, Any],
    request: str,
    requested_mode: str = "auto",
) -> dict[str, Any]:
    """Add a few exact symbol bodies when structural evidence is insufficient.

    This runs after graph selection, so it never scans the repository or sends
    unrelated files. Limits are deliberately small and deterministic.
    """
    mode = select_evidence_mode(request, requested_mode, str(result.get("intent") or "flow"))
    result["evidence_mode"] = mode
    obligations = requested_obligations(request)
    result["requested_obligations"] = obligations
    if mode == "compact" or result.get("intent") in {"overview", "impact"}:
        result["source_retrieval"] = {"enabled": False, "reason": "structural evidence is sufficient for this request"}
        return result

    max_snippets = 1 if mode == "balanced" else 3
    line_budget = 60 if mode == "balanced" else 120
    char_budget = 5_000 if mode == "balanced" else 12_000
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Framework resolvers often know the exact JSX/TSX line that invokes a
    # backend route even when the parser does not model the nested JSX branch
    # as an operation. Read a tiny edge-centered window before broad symbol
    # bodies so UI permissions and state guards are not cut off.
    request_terms = list(dict.fromkeys([
        *(str(term).lower() for term in result.get("intent_terms", [])),
        *(term.lower() for term in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\w.-]{2,}", request)),
    ]))
    projected = [link for link in result.get("links", []) if link.get("projected_from") and link.get("file") and link.get("line")]
    projected.sort(key=lambda link: (
        -sum(term in f"{link.get('evidence', '')} {link.get('source', '')} {link.get('target', '')}".lower()
             for term in request_terms),
        str(link.get("file")), -int(link.get("line") or 0),
    ))
    projected_keys: set[str] = set()
    for link in projected:
        route_key = str(link.get("evidence") or link.get("target") or "")
        if route_key in projected_keys or len(projected_keys) >= 2:
            continue
        projected_keys.add(route_key)
        line = int(link.get("line") or 1)
        node_id = f"edge:{link.get('file')}:{line}"
        if node_id in seen:
            continue
        seen.add(node_id)
        candidates.append({
            "id": node_id, "name": link.get("evidence") or link.get("label"),
            "kind": "function", "file": link.get("file"),
            "line": max(1, line - 7), "end_line": line + 5,
        })
    for group in (result.get("matched", []), result.get("nodes", [])):
        for node in group:
            node_id = str(node.get("id") or "")
            if node_id in seen or node.get("kind") not in {"method", "function", "constructor"}:
                continue
            if not node.get("file") or not node.get("line"):
                continue
            seen.add(node_id)
            candidates.append(node)

    qualified = [
        (owner.lower(), member.lower())
        for owner, member in re.findall(r"([A-Za-z_][\w]*)\s*(?:::|\.|#)\s*([A-Za-z_][\w]*)", str(request or ""))
    ]
    primary_file = ""
    for node in candidates:
        signature = " ".join(str(node.get(key) or "") for key in ("container", "signature", "owner_signature")).lower()
        if any(str(node.get("name") or "").lower() == member and re.search(rf"\b{re.escape(owner)}\b", signature)
               for owner, member in qualified):
            primary_file = str(node.get("file") or "")
            break
    if primary_file:
        # Once a qualified declaration is resolved, keep its sibling methods
        # ahead of generic homonyms from unrelated files.
        candidates.sort(key=lambda node: str(node.get("file") or "") != primary_file)

    excerpts = []
    remaining = char_budget
    for node in candidates:
        if len(excerpts) >= max_snippets or remaining < 200:
            break
        source = _safe_source(root, str(node["file"]))
        if not source:
            continue
        start = int(node.get("line") or 1)
        declared_end = int(node.get("end_line") or start + line_budget - 1)
        text, actual_start, actual_end = _numbered_excerpt(source, start, declared_end, line_budget)
        text = text[:remaining]
        if not text:
            continue
        excerpts.append({
            "symbol": node.get("name"), "file": node.get("file"),
            "start_line": actual_start, "end_line": actual_end, "text": text,
        })
        remaining -= len(text)

    result["source_evidence"] = excerpts
    result["source_retrieval"] = {
        "enabled": bool(excerpts), "mode": mode, "snippets": len(excerpts),
        "characters": sum(len(item["text"]) for item in excerpts),
        "max_snippets": max_snippets, "line_budget_per_symbol": line_budget,
        "scope": "only graph-selected symbol bodies",
    }
    if excerpts:
        result["complete_for"] = list(dict.fromkeys([*result.get("complete_for", []), *obligations]))
        result["missing"] = [item for item in result.get("missing", []) if item not in obligations]
        result["do_not_expand"] = True
        result["guidance"] = (
            "Answer from relations, operations and exact source excerpts. Cite file:line. "
            "Use excerpt order for conditions and control flow; do not call another tool."
        )
    return result
