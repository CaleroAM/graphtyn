"""Validate agent answers against graph evidence without claiming semantic proof."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_STOP = {"the", "and", "for", "with", "this", "that", "from", "para", "como", "este", "esta", "con", "por", "una", "que", "del", "los", "las"}
_CITATION = re.compile(
    r"(?<![\w.-])(?P<file>(?:(?:[A-Za-z]:)?[\\/])?(?:[\w.-]+[\\/])*[\w.-]+\.[A-Za-z][A-Za-z0-9]*)(?::(?P<line>\d+))?"
)
_NEGATIONS = {"no", "not", "never", "nunca", "jamás", "jamas", "without", "sin"}
_MODALITY = {"may", "might", "could", "possibly", "perhaps", "quizá", "quizas", "quizás", "puede", "podría", "podria"}
_CLAUSE_CONNECTORS = {
    "and", "but", "then", "which", "who", "whose", "where", "when", "while", "after", "before",
    "because", "therefore", "although", "though", "unless", "until", "whereas", "y", "pero", "entonces",
    "que", "quien", "donde", "cuando", "mientras", "después", "despues", "antes", "porque", "aunque",
}
_QUANTITY_MODIFIERS = {
    "about", "approximately", "around", "exactly", "nearly", "roughly", "total", "totals", "at", "least",
    "most", "more", "less", "fewer", "aproximadamente", "alrededor", "casi", "exactamente", "total",
    "mínimo", "minimo", "máximo", "maximo", "menos", "más", "mas",
}
_SCOPE_IGNORED = _STOP | _CLAUSE_CONNECTORS | _MODALITY | {
    "a", "an", "to", "of", "in", "on", "at", "by", "is", "are", "was", "were", "be", "been",
    "being", "do", "does", "did", "as", "also", "el", "la", "lo", "al", "de", "en", "es", "son",
    "fue", "se", "su", "sus", "un", "uno", "y", "o", "u",
}
_RELATION_WORDS = {
    "llama": {"call", "calls", "called", "invoca", "invocar", "llama"},
    "usa": {"use", "uses", "used", "usa", "utiliza"},
    "referencia": {"reference", "references", "referencia"},
    "implementa": {"implement", "implements", "implementa"},
    "hereda": {"inherit", "inherits", "hereda"},
    "suscribe": {"subscribe", "subscribes", "suscribe"},
    "escucha": {"listen", "listens", "escucha"},
    "despacha": {"dispatch", "dispatches", "despacha"},
    "invoca ruta": {"route", "routes", "ruta"},
    "valida con": {"validate", "validates", "valida"},
    "crea": {"create", "creates", "crea"},
    "despacha evento": {"event", "publish", "publishes", "evento"},
    "verifica": {"test", "tests", "verify", "verifies", "prueba", "verifica"},
}


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
    raw_tokens = re.findall(r"[A-Za-z_ÁÉÍÓÚáéíóúñÑ][\wÁÉÍÓÚáéíóúñÑ.-]*", text)
    cleaned = set()
    for token in raw_tokens:
        clean = token.strip(".,;:!?()[]{}\"'`").lower()
        if len(clean) >= 2 and clean not in _STOP:
            cleaned.add(clean)
    return cleaned


def _normalize_path(path_str: str) -> str:
    cleaned = str(path_str or "").replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    # Native Windows paths are case-insensitive. POSIX graph paths retain case
    # so Foo.py and foo.py cannot resolve each other's citations.
    return cleaned.casefold() if os.name == "nt" or re.match(r"^[A-Za-z]:/", cleaned) else cleaned


def _is_absolute_path(path_str: str) -> bool:
    normalized = _normalize_path(path_str)
    return normalized.startswith("/") or bool(re.match(r"^[a-z]:/", normalized))


def _path_matches(citation_file: str, entity_file: str,
                  project_root: Path | str | None = None) -> bool:
    """Safely check if citation_file matches entity_file."""
    c_clean = _normalize_path(citation_file)
    e_clean = _normalize_path(entity_file)
    if not c_clean or not e_clean:
        return False
    if c_clean == e_clean:
        return True

    # An absolute citation only resolves to the exact indexed path. When the
    # graph stores relative paths, its workspace identity is required; a
    # fabricated absolute prefix must never resolve merely by suffix.
    if _is_absolute_path(c_clean):
        if _is_absolute_path(e_clean):
            return c_clean == e_clean
        if project_root is None:
            return False
        root_clean = _normalize_path(str(Path(project_root).resolve()))
        return c_clean == f"{root_clean.rstrip('/')}/{e_clean.lstrip('/')}"

    # Relative citation path: citation can be a suffix of entity path components
    c_parts = [p for p in c_clean.split("/") if p and p != "."]
    e_parts = [p for p in e_clean.split("/") if p and p != "."]
    if len(c_parts) <= len(e_parts):
        return e_parts[-len(c_parts):] == c_parts
    return False


def _resolve_citation(file_part: str, line_num: int | None, nodes: dict[str, dict],
                      links: list[dict], project_root: Path | str | None = None) -> tuple[bool, str | None, list[str]]:
    """Check if a citation resolves to a known file and line in the graph."""
    clean_file = _normalize_path(file_part)
    if not clean_file:
        return False, "empty_citation_path", []

    matching_nodes = [
        node for node in nodes.values()
        if node.get("file") and _path_matches(clean_file, str(node.get("file")), project_root)
    ]

    distinct_node_files = {
        _normalize_path(str(node.get("file"))) for node in matching_nodes if node.get("file")
    }
    if len(distinct_node_files) > 1:
        return False, "ambiguous_citation_multiple_files", []

    matching_links = []
    if not matching_nodes:
        matching_links = [
            link for link in links
            if link.get("file") and _path_matches(clean_file, str(link.get("file")), project_root)
        ]
        distinct_link_files = {
            _normalize_path(str(link.get("file"))) for link in matching_links if link.get("file")
        }
        if len(distinct_link_files) > 1:
            return False, "ambiguous_citation_multiple_files", []
        if not matching_links:
            return False, "file_not_in_graph", []

    if line_num is not None:
        valid_line = False
        for node in matching_nodes:
            n_start = node.get("line_start") if node.get("line_start") is not None else node.get("line")
            n_end = node.get("line_end") if node.get("line_end") is not None else node.get("end_line")
            n_end = n_end if n_end is not None else n_start
            if n_start is not None and n_end is not None and n_start <= line_num <= n_end:
                valid_line = True
                break
        if not valid_line:
            target_links = matching_links if matching_links else [
                link for link in links
                if link.get("file") and _path_matches(clean_file, str(link.get("file")), project_root)
            ]
            for link in target_links:
                if link.get("line") == line_num:
                    valid_line = True
                    break
        if not valid_line:
            return False, "line_out_of_range", []

    node_ids = [str(node.get("id")) for node in matching_nodes if node.get("id")]
    if not node_ids and matching_links:
        node_ids = [str(link.get("source")) for link in matching_links if link.get("source")]
    return True, None, node_ids


def _normalized_words(text: str) -> list[str]:
    return [word.casefold() for word in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\wÁÉÍÓÚÜÑáéíóúüñ_-]*", text)]


def _mask_citations(text: str, citations: list[re.Match]) -> str:
    chars = list(text)
    for match in citations:
        start, end = match.span()
        for idx in range(start, end):
            chars[idx] = " "
    return "".join(chars)


def _semantic_words(text: str) -> list[str]:
    return [word for word in _normalized_words(text) if len(word) >= 2 and word not in _STOP]


def _number_contexts(text: str, value: str, radius: int = 5) -> list[dict[str, Any]]:
    """Return sentence-bounded numeric anchors and quantity units."""
    contexts: list[dict[str, Any]] = []
    for match in re.finditer(rf"(?<![\d.]){re.escape(value)}(?![\d.])", text):
        left = max((text.rfind(mark, 0, match.start()) for mark in ".!?;\n"), default=-1)
        right_candidates = [position for mark in ".!?;\n"
                            if (position := text.find(mark, match.end())) >= 0]
        right = min(right_candidates, default=len(text))
        before = _semantic_words(text[left + 1:match.start()])[-radius:]
        after = _semantic_words(text[match.end():right])[:radius]
        units = []
        for word in after:
            if word in _CLAUSE_CONNECTORS:
                break
            if word in _SCOPE_IGNORED or word in _QUANTITY_MODIFIERS:
                continue
            units.append(word)
            if len(units) == 2:
                break
        anchors = [word for word in before
                   if word not in _SCOPE_IGNORED and word not in _QUANTITY_MODIFIERS][-3:]
        quantity_terms = set(units)
        quantity_terms.update(word for word in before[-2:] if word in _QUANTITY_MODIFIERS)
        quantity_terms.update(word for word in after[:2] if word in _QUANTITY_MODIFIERS)
        if not units and anchors:
            quantity_terms.update(anchors[-2:])
        contexts.append({
            "terms": set([*before, *after]), "anchors": set(anchors), "units": set(units),
            "quantity_terms": quantity_terms, "fragment_start": left + 1, "fragment_end": right,
        })
    return contexts


def _number_context_matches(claim: dict[str, Any], evidence: dict[str, Any]) -> bool:
    claim_units, evidence_units = claim["units"], evidence["units"]
    claim_anchors, evidence_anchors = claim["anchors"], evidence["anchors"]

    # Matching a couple of words is insufficient when the remaining anchors
    # identify another subject or object (for example handler→Service versus
    # Service→Database). Accept exact anchors, or containment without a
    # conflicting anchor and with at least two shared semantic words.
    anchors_match = claim_anchors == evidence_anchors and bool(claim_anchors)
    if claim_anchors and evidence_anchors and not anchors_match:
        shared_anchors = claim_anchors & evidence_anchors
        anchors_match = (
            len(shared_anchors) >= 2
            and (claim_anchors <= evidence_anchors or evidence_anchors <= claim_anchors)
        )

    if claim_units or evidence_units:
        if not claim_units or not evidence_units or not (claim_units & evidence_units):
            return False
        return anchors_match
    return anchors_match


def _unsupported_numbers(text: str, citations: list[re.Match], evidence_text: str) -> list[str]:
    masked = _mask_citations(text, citations)
    claimed_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", masked)
    if not claimed_numbers:
        return []
    unsupported = []
    for value in claimed_numbers:
        claim_contexts = _number_contexts(masked, value)
        evidence_contexts = _number_contexts(evidence_text, value)
        # A shared entity name (for example ``Service``) does not establish
        # that the same number measures the same action or quantity.
        context_matches = any(_number_context_matches(claim_ctx, evidence_ctx)
                              for claim_ctx in claim_contexts for evidence_ctx in evidence_contexts)
        if not evidence_contexts or not context_matches:
            unsupported.append(value)
    return unsupported


def _evaluate_compound_clauses(text: str, nodes: dict[str, dict], links: list[dict],
                               matched_edges: list[dict], evidence_ids: list[str]) -> tuple[bool, str | None]:
    """Require every substantive token to belong to extracted relation or quantity evidence."""
    word_matches = list(re.finditer(
        r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\wÁÉÍÓÚÜÑáéíóúüñ_-]*", text
    ))
    words = [match.group(0).casefold() for match in word_matches]
    covered: set[int] = set()

    def occurrences(sequence: list[str]) -> list[int]:
        if not sequence:
            return []
        return [index for index in range(len(words) - len(sequence) + 1)
                if words[index:index + len(sequence)] == sequence]

    for link in matched_edges:
        source = nodes.get(str(link.get("source"))) or {}
        target = nodes.get(str(link.get("target"))) or {}
        source_words = _normalized_words(str(source.get("name") or ""))
        target_words = _normalized_words(str(target.get("name") or ""))
        relation_words = _RELATION_WORDS.get(str(link.get("label") or "").casefold(), set())
        candidates = []
        for source_at in occurrences(source_words):
            source_end = source_at + len(source_words)
            for target_at in occurrences(target_words):
                if target_at < source_end:
                    continue
                predicate_at = next((index for index in range(source_end, target_at)
                                     if words[index] in relation_words), -1)
                if predicate_at >= 0:
                    candidates.append((target_at - source_at, source_at, source_end,
                                       predicate_at, target_at, target_at + len(target_words)))
        if not candidates:
            continue
        _, source_at, source_end, predicate_at, target_at, target_end = min(candidates)
        covered.update(range(source_at, source_end))
        covered.add(predicate_at)
        covered.update(range(target_at, target_end))

    claimed_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    for value in claimed_numbers:
        for context in _number_contexts(text, value):
            for index, match in enumerate(word_matches):
                if (context["fragment_start"] <= match.start() < context["fragment_end"]
                        and words[index] in context["quantity_terms"]):
                    covered.add(index)

    residual = [word for index, word in enumerate(words)
                if index not in covered and word not in _SCOPE_IGNORED]
    if residual:
        unresolved = " ".join(residual[:8])
        return False, f"compound_claim_unsupported_clause: unresolved content: {unresolved}"
    return True, None


def _relation_matches_claim(link: dict, text: str, nodes: dict[str, dict]) -> tuple[bool, str]:
    """Require positive subject -> predicate -> object order for a relation claim."""
    source = nodes.get(str(link.get("source"))) or {}
    target = nodes.get(str(link.get("target"))) or {}
    source_name = str(source.get("name") or "").casefold()
    target_name = str(target.get("name") or "").casefold()
    normalized = text.casefold()
    source_at, target_at = normalized.find(source_name), normalized.find(target_name)
    if not source_name or not target_name or source_at < 0 or target_at < 0:
        return False, "relation_endpoints_not_asserted"
    if source_at >= target_at:
        return False, "relation_direction_reversed"
    words = _normalized_words(text)
    source_word = next((index for index, word in enumerate(words) if word == source_name), -1)
    target_word = next((index for index, word in enumerate(words) if word == target_name), -1)
    relation_words = _RELATION_WORDS.get(str(link.get("label") or "").casefold(), set())
    predicate_positions = [index for index, word in enumerate(words) if word in relation_words]
    predicate_at = next((index for index in predicate_positions
                         if source_word < index < target_word), -1)
    if predicate_at < 0:
        return False, "relation_predicate_not_asserted"
    if any(word in _NEGATIONS for word in words[max(0, predicate_at - 3):predicate_at + 1]):
        return False, "negated_relation"
    return True, "relation_direction_and_predicate_match"


def _has_modal_relation(text: str) -> bool:
    words = _normalized_words(text)
    relation_words = set().union(*_RELATION_WORDS.values())
    for index, word in enumerate(words):
        if word in relation_words and any(candidate in _MODALITY for candidate in words[max(0, index - 4):index]):
            return True
    return False


def _resolve_claim_citations(
    text: str,
    nodes: dict[str, dict],
    links: list[dict],
    project_root: Path | str | None,
) -> tuple[list[re.Match[str]], list[str], set[str], list[dict[str, Any]]]:
    """Resolve every citation once and retain the details needed by callers."""
    matches = list(_CITATION.finditer(text))
    resolved: list[str] = []
    resolved_node_ids: set[str] = set()
    unresolved: list[dict[str, Any]] = []
    for match in matches:
        file_part = match.group("file")
        line_text = match.group("line")
        line_number = int(line_text) if line_text else None
        ok, reason, node_ids = _resolve_citation(
            file_part, line_number, nodes, links, project_root
        )
        if ok:
            resolved.append(match.group(0))
            resolved_node_ids.update(node_ids)
        else:
            unresolved.append({
                "raw": match.group(0),
                "file": file_part,
                "line": line_number,
                "reason": reason,
            })
    return matches, resolved, resolved_node_ids, unresolved


def _rank_claim_evidence(
    text: str,
    requested_ids: list[str],
    citation_matches: list[re.Match[str]],
    unresolved_citations: list[dict[str, Any]],
    nodes: dict[str, dict],
    node_terms: dict[str, set[str]],
    project_root: Path | str | None,
) -> list[str]:
    """Rank graph nodes without letting an unresolved citation boost a candidate."""
    claim_terms = _terms(text)
    unresolved_raw = {item["raw"] for item in unresolved_citations}
    candidates: list[tuple[int, str]] = []
    for node_id, terms in node_terms.items():
        overlap = len(claim_terms & terms)
        if node_id in requested_ids:
            overlap += 10
        node_file = str(nodes[node_id].get("file") or "").strip()
        if node_file and any(
            match.group(0) not in unresolved_raw
            and _path_matches(match.group("file"), node_file, project_root)
            for match in citation_matches
        ):
            overlap += 6
        if overlap:
            candidates.append((overlap, node_id))
    candidates.sort(reverse=True)
    return [node_id for _, node_id in candidates[:3]]


def _match_claim_edges(
    text: str,
    evidence_ids: list[str],
    nodes: dict[str, dict],
    links: list[dict],
) -> tuple[list[dict], list[str]]:
    """Return relation evidence that matches the asserted predicate and direction."""
    claim_words = set(_normalized_words(text))
    asserted_labels = {
        label for label, relation_words in _RELATION_WORDS.items()
        if claim_words & relation_words
    }
    edge_evidence = [
        link for link in links
        if str(link.get("source")) in evidence_ids
        and str(link.get("target")) in evidence_ids
        and str(link.get("label") or "").casefold() in asserted_labels
    ]
    matched: list[dict] = []
    rejected_reasons: list[str] = []
    for link in edge_evidence:
        relation_matches, reason = _relation_matches_claim(link, text, nodes)
        if relation_matches:
            matched.append(link)
        else:
            rejected_reasons.append(reason)
    return matched, rejected_reasons


def _classify_claim(
    text: str,
    *,
    citation_matches: list[re.Match[str]],
    resolved_citations: list[str],
    citation_node_ids: set[str],
    unresolved_citations: list[dict[str, Any]],
    resolved_requested: list[str],
    unresolved_requested: list[str],
    evidence_ids: list[str],
    matched_edges: list[dict],
    rejected_edge_reasons: list[str],
    unsupported_numbers: list[str],
    nodes: dict[str, dict],
    links: list[dict],
    best_candidate_score: int,
) -> tuple[str, str]:
    """Apply the confidence policy after evidence collection is complete."""
    edge_confidences = [str(link.get("confidence") or "").upper() for link in matched_edges]
    has_ambiguous_edge = "AMBIGUOUS" in edge_confidences
    has_extracted_edge = any(value in ("EXTRACTED", "REVIEWED") for value in edge_confidences)
    has_inferred_edge = "INFERRED" in edge_confidences
    all_edges_confirmed = bool(edge_confidences) and all(
        value in ("EXTRACTED", "REVIEWED") for value in edge_confidences
    )

    if unresolved_citations:
        return "unsupported", f"citation_unresolved: {[item['raw'] for item in unresolved_citations]}"
    if unresolved_requested:
        return "unsupported", f"requested_evidence_ids_not_found: {unresolved_requested}"
    if unsupported_numbers:
        verdict = "partially_supported" if has_extracted_edge or has_inferred_edge else "unsupported"
        return verdict, f"numeric_values_not_in_evidence: {unsupported_numbers}"
    if not evidence_ids:
        return "unsupported", "no_matching_evidence_nodes"
    if matched_edges:
        compound_ok, compound_reason = _evaluate_compound_clauses(
            _mask_citations(text, citation_matches), nodes, links, matched_edges, evidence_ids
        )
        if has_ambiguous_edge:
            return "ambiguous", (
                compound_reason if not compound_ok else "claim_contains_ambiguous_relations"
            )
        if not compound_ok:
            return "partially_supported", compound_reason or "compound_claim_unsupported_clause"
        if has_inferred_edge:
            return "partially_supported", "inferred_relations_require_verification"
        if not all_edges_confirmed:
            return "partially_supported", "unverified_relation_confidence"
        if _has_modal_relation(text):
            return "partially_supported", "modal_relation_requires_verification"
        return "supported", "extracted_relations_confirmed"
    if rejected_edge_reasons:
        return "unsupported", rejected_edge_reasons[0]
    if resolved_citations and citation_node_ids:
        return "partially_supported", "citation_resolved_but_claim_semantics_unverified"
    if resolved_requested:
        return "partially_supported", "requested_evidence_id_resolved_but_claim_semantics_unverified"
    if best_candidate_score >= 3:
        return "partially_supported", "lexical_term_overlap_only"
    return "unsupported", "insufficient_evidence_overlap"


def _evaluate_claim(
    claim: dict[str, Any],
    *,
    nodes: dict[str, dict],
    links: list[dict],
    node_terms: dict[str, set[str]],
    project_root: Path | str | None,
) -> tuple[dict[str, Any], int, list[str], list[str]]:
    """Evaluate one claim and return its verdict plus resolution counters."""
    text = str(claim.get("text") or "").strip()
    requested_ids = [str(item) for item in claim.get("evidence_ids", [])]
    resolved_requested = [item for item in requested_ids if item in nodes]
    unresolved_requested = [item for item in requested_ids if item not in nodes]
    citation_matches, resolved_citations, citation_node_ids, unresolved_citations = (
        _resolve_claim_citations(text, nodes, links, project_root)
    )
    evidence_ids = _rank_claim_evidence(
        text, resolved_requested, citation_matches, unresolved_citations,
        nodes, node_terms, project_root,
    )
    matched_edges, rejected_edge_reasons = _match_claim_edges(
        text, evidence_ids, nodes, links
    )
    evidence_parts = [
        str(value)
        for node_id in evidence_ids
        for value in (
            nodes[node_id].get("details"),
            nodes[node_id].get("signature"),
            nodes[node_id].get("evidence"),
        )
        if str(value or "").strip()
    ]
    evidence_parts.extend(
        str(link.get("evidence")) for link in matched_edges
        if str(link.get("evidence") or "").strip()
    )
    unsupported_numbers = _unsupported_numbers(
        text, citation_matches, ". ".join(evidence_parts)
    )
    best_candidate_score = 0
    if evidence_ids:
        # Preserve the original lexical threshold independently of requested IDs.
        claim_terms = _terms(text)
        best_candidate_score = max(len(claim_terms & node_terms[node_id]) for node_id in evidence_ids)
        if resolved_requested:
            best_candidate_score = max(best_candidate_score, 10)
        if resolved_citations:
            best_candidate_score = max(best_candidate_score, 6)
    confidence, reason = _classify_claim(
        text,
        citation_matches=citation_matches,
        resolved_citations=resolved_citations,
        citation_node_ids=citation_node_ids,
        unresolved_citations=unresolved_citations,
        resolved_requested=resolved_requested,
        unresolved_requested=unresolved_requested,
        evidence_ids=evidence_ids,
        matched_edges=matched_edges,
        rejected_edge_reasons=rejected_edge_reasons,
        unsupported_numbers=unsupported_numbers,
        nodes=nodes,
        links=links,
        best_candidate_score=best_candidate_score,
    )
    verdict = {
        "claim": text,
        "verdict": confidence,
        "verdict_reason": reason,
        "evidence_ids": evidence_ids if confidence != "unsupported" else [],
        "resolved_citations": resolved_citations,
        "unresolved_citations": [item["raw"] for item in unresolved_citations],
        "citation_errors": unresolved_citations,
        "relations": [
            {key: link.get(key) for key in ("source", "target", "label", "confidence", "file", "line")}
            for link in matched_edges[:5]
        ],
        "ambiguity_present": any(
            str(link.get("confidence") or "").upper() == "AMBIGUOUS" for link in matched_edges
        ),
    }
    return (
        verdict,
        len(citation_matches),
        [item["raw"] for item in unresolved_citations],
        unresolved_requested,
    )


def validate_answer(graph: dict, answer: str, claims: list[dict[str, Any]] | None = None,
                    *, project_root: Path | str | None = None) -> dict[str, Any]:
    """Score traceability of explicit claims; it does not judge prose as true by itself."""
    nodes = {str(node.get("id")): node for node in graph.get("nodes", [])}
    links = graph.get("links", [])
    node_terms = {node_id: _terms(" ".join(str(node.get(k) or "") for k in ("name", "file", "details", "signature")))
                  for node_id, node in nodes.items()}
    if claims is None:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", answer) if len(part.strip()) >= 12]
        claims = [{"text": sentence} for sentence in sentences]

    verdicts: list[dict[str, Any]] = []
    total_citations_count = 0
    total_unresolved_citations = []
    total_unresolved_ids = []

    for claim in claims:
        verdict, citation_count, unresolved_citations, unresolved_ids = _evaluate_claim(
            claim,
            nodes=nodes,
            links=links,
            node_terms=node_terms,
            project_root=project_root,
        )
        verdicts.append(verdict)
        total_citations_count += citation_count
        total_unresolved_citations.extend(unresolved_citations)
        total_unresolved_ids.extend(unresolved_ids)

    supported = sum(item["verdict"] == "supported" for item in verdicts)
    partially_supported = sum(item["verdict"] == "partially_supported" for item in verdicts)
    ambiguous = sum(item["verdict"] == "ambiguous" for item in verdicts)
    unsupported = sum(item["verdict"] == "unsupported" for item in verdicts)
    abstained = sum(item["verdict"] == "abstained" for item in verdicts)
    total = len(verdicts)

    score = (supported + partially_supported * 0.5 + ambiguous * 0.25) / total if total else 0.0
    completeness = detect_incomplete_answer(answer)
    return {
        "schema_version": "2.0",
        "operation_ok": True,
        "ok": total > 0 and completeness["complete"],
        "traceability_score": round(score, 4),
        "claims": verdicts,
        "evidence_resolution": {
            "total_citations": total_citations_count,
            "unresolved_citations": total_unresolved_citations,
            "unresolved_evidence_ids": total_unresolved_ids,
        },
        "summary": {
            "total": total,
            "supported": supported,
            "partial": partially_supported + ambiguous,
            "partially_supported": partially_supported,
            "ambiguous": ambiguous,
            "unsupported": unsupported,
            "abstained": abstained,
        },
        "completeness": completeness,
        "guidance": "SUPPORTED means traceable to indexed, non-ambiguous evidence. AMBIGUOUS relations must not be asserted as fact.",
    }
