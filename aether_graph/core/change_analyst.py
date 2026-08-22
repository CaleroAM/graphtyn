"""Deterministic, token-bounded evidence planning for code changes."""

from __future__ import annotations

import re
from typing import Any


_STOP = {
    "para", "como", "esta", "este", "esto", "that", "with", "from", "the",
    "una", "uno", "unos", "las", "los", "del", "por", "que", "and", "con",
    "change", "cambio", "modify", "modificar", "agregar", "add", "hacer",
}

_INTENT_MARKERS = {
    "bindings": ("binding", "bindings", "addscoped", "addsingleton", "addtransient", "dependency", "dependencia", "registr", "inyección", "injection"),
    "persistence": ("persist", "repository", "repositorio", "database", "base de datos", "save", "deleteasync", "addasync", "query", "consulta"),
    "tests": ("test", "tests", "prueba", "pruebas", "coverage", "cobertura"),
    "impact": ("impact", "impacto", "consumer", "consumidor", "blast", "afecta"),
    "flow": ("flow", "flujo", "trace", "traza", "desde", "hasta", "event", "evento"),
}

_INTENT_OPERATIONS = {
    "bindings": ("addscoped", "addsingleton", "addtransient", "adddbcontext", "addinterceptors", "usesql", "getconnectionstring", "register"),
    "persistence": ("repository", "addasync", "deleteasync", "updateasync", "savechanges", "fromsql", "countasync", "skip", "take", "asnotracking"),
    "tests": ("assert", "should", "equal", "returns", "substitute", "mock", "verify"),
    "impact": (),
    "flow": ("send", "publish", "dispatch", "save", "update", "route", "post", "delete", "addasync", "sendemail", "registerdomainevent"),
}

_QUERY_EXPANSIONS = {
    "eliminar": ("delete", "deleted"), "eliminación": ("delete", "deleted"),
    "borrado": ("delete", "deleted", "deleteservice"),
    "evento": ("event", "publish", "handler"), "eventos": ("event", "publish", "handler"),
    "correo": ("email", "sendemail"), "persistencia": ("repository", "save", "database"),
    "repositorio": ("repository",), "consulta": ("query",), "prueba": ("test", "assert"),
    "inyección": ("addscoped", "dependency", "service"),
    "propuesta": ("proposal", "salesproposal"), "propuestas": ("proposal", "salesproposal"),
    "factura": ("invoice", "salesinvoice"), "facturas": ("invoice", "salesinvoice"),
    "devolución": ("return", "purchasereturn"), "devoluciones": ("return", "purchasereturn"),
    "compra": ("purchase",), "compras": ("purchase",), "almacén": ("warehouse",),
    "producto": ("product",), "productos": ("product",),
    "arranque": ("bootstrap", "app.tsx", "app.blade.php", "inertia"),
    "creación": ("create", "store"), "crear": ("create", "store"),
    "conversión": ("convert", "converttoinvoice"), "convertir": ("convert", "converttoinvoice"),
    "aprobar": ("approve",), "aprobación": ("approve",),
    "completar": ("complete",), "completado": ("complete",),
    "autorización": ("authorize", "request"), "validación": ("request", "rules"),
}


def _terms(request: str) -> list[str]:
    return list(dict.fromkeys(
        token.lower() for token in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\w.]+", request)
        if len(token) >= 3 and token.lower() not in _STOP
    ))[:20]


def classify_intent(request: str, requested: str = "auto") -> str:
    if requested in _INTENT_MARKERS:
        return requested
    text = str(request or "").lower()
    scores = {intent: sum(marker in text for marker in markers) for intent, markers in _INTENT_MARKERS.items()}
    best = max(scores, key=lambda intent: scores[intent])
    return best if scores[best] else "flow"


def query_intent(graph: dict[str, Any], request: str, intent: str = "auto", max_nodes: int = 12) -> dict[str, Any]:
    """Return a one-shot, intent-specific evidence package."""
    selected_intent = classify_intent(request, intent)
    intent_node_cap = {"bindings": 7, "persistence": 7, "tests": 8, "impact": 10, "flow": 10}[selected_intent]
    max_nodes = min(max_nodes, intent_node_cap)
    markers = _INTENT_OPERATIONS[selected_intent]
    request_lower = str(request or "").lower()
    expansions = list(dict.fromkeys(
        expansion for word, values in _QUERY_EXPANSIONS.items() if word in request_lower for expansion in values
    ))
    request_terms = _terms(request) + expansions
    all_nodes = graph.get("nodes", [])
    ranked = []
    for node in all_nodes:
        operations = node.get("operations") or []
        filtered_ops = []
        for op in operations:
            searchable = f"{op.get('name', '')} {op.get('text', '')}".lower()
            operation_filters = list(markers)
            operation_name = str(op.get("name") or "").lower()
            if (not operation_filters or any(marker in searchable for marker in operation_filters)
                    or operation_name in request_terms
                    or any(term in searchable for term in request_terms)):
                filtered_ops.append(op)
        copy = dict(node)
        if node.get("container") and node.get("kind") in ("method", "function"):
            owner = next((candidate for candidate in all_nodes
                          if candidate.get("file") == node.get("file")
                          and candidate.get("name") == node.get("container")
                          and candidate.get("kind") in ("class", "interface", "struct")), None)
            if owner and owner.get("signature"):
                copy["owner_signature"] = owner["signature"]
        if filtered_ops:
            copy["operations"] = filtered_ops
        elif "operations" in copy:
            copy.pop("operations")
        kind_relevant = selected_intent == "tests" and re.search(r"test", str(node.get("file") or ""), re.I)
        fields = " ".join(str(node.get(key) or "") for key in ("name", "container", "file", "signature", "kind")).lower()
        lexical_hits = sum(term in fields for term in request_terms)
        concept_hits = sum(term in fields for term in list(markers) + expansions)
        identity = {
            str(node.get("name") or "").lower(),
            str(node.get("container") or "").lower(),
        }
        exact_hits = sum(term in identity for term in request_terms)
        if exact_hits and operations:
            # For an explicitly named component, its state transitions and
            # control flow are relevant even when operation names are generic
            # (encode, append, assign, return, etc.).
            filtered_ops = operations
            copy["operations"] = operations
        path = str(node.get("file") or "").replace("\\", "/")
        primary_bonus = 50 if path.startswith("src/") else 0
        score = (min(6, len(filtered_ops)) * 25 + lexical_hits * 10 + concept_hits * 45 + exact_hits * 400
                 + int(bool(kind_relevant)) * 100 + primary_bonus
                 + int(node.get("kind") == "route" and lexical_hits > 0) * 180
                 + int(node.get("kind") in ("method", "class", "interface")) * 10
                 + min(10, int(node.get("degree") or 0)))
        concept_allowed = selected_intent in ("flow", "tests", "impact")
        # Flow requests often name the exact framework component (for example
        # ``SessionMiddleware``) without using one of our domain operation
        # markers. Exact lexical evidence must remain eligible; otherwise
        # generic high-degree call sites crowd the requested component out.
        if filtered_ops or kind_relevant or (concept_allowed and (concept_hits or lexical_hits)) or (selected_intent in ("tests", "impact") and lexical_hits):
            ranked.append((score, copy))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    nodes = []
    seen_roles = set()
    laravel_labels = {"despacha", "invoca ruta", "valida con", "crea", "despacha evento"}
    has_laravel = any(link.get("label") in laravel_labels for link in graph.get("links", []))
    lexical_cap = max(4, max_nodes - 4) if has_laravel and selected_intent == "flow" else max_nodes
    for _, node in ranked:
        role = (str(node.get("name") or "").lower(), str(node.get("container") or "").lower(), node.get("kind"))
        if role in seen_roles:
            continue
        seen_roles.add(role)
        nodes.append(node)
        if len(nodes) >= max(1, lexical_cap):
            break
    if has_laravel and selected_intent == "flow":
        by_id = {node.get("id"): node for node in all_nodes}
        selected_ids = {node.get("id") for node in nodes}
        # Two hops connect controller↔route↔TSX while one hop brings in
        # FormRequests, models and dispatched events.
        relation_priority = {"despacha": 0, "invoca ruta": 1, "valida con": 2, "crea": 3, "despacha evento": 4}
        relevant_links = sorted(
            (link for link in graph.get("links", []) if link.get("label") in laravel_labels),
            key=lambda link: (relation_priority.get(str(link.get("label")), 9), str(link.get("source"))),
        )
        for hop in range(2):
            hop_cap = max_nodes - 1 if hop == 0 else max_nodes
            for link in relevant_links:
                if link.get("label") not in laravel_labels:
                    continue
                source, target = link.get("source"), link.get("target")
                candidate_id = target if source in selected_ids else source if target in selected_ids else None
                candidate = by_id.get(candidate_id)
                if candidate and candidate.get("kind") == "file":
                    rel_file = str(candidate.get("details") or candidate.get("name") or "")
                    file_symbols = [item for item in all_nodes if item.get("file") == rel_file and item.get("operations")]
                    if file_symbols:
                        candidate = max(file_symbols, key=lambda item: len(item.get("operations") or []))
                        candidate_id = candidate.get("id")
                if not candidate or candidate_id in selected_ids:
                    continue
                role = (str(candidate.get("name") or "").lower(), str(candidate.get("container") or "").lower(), candidate.get("kind"))
                if role in seen_roles:
                    continue
                nodes.append(candidate)
                selected_ids.add(candidate_id)
                seen_roles.add(role)
                if len(nodes) >= hop_cap:
                    break
            if len(nodes) >= max_nodes:
                break
    node_ids = {node.get("id") for node in nodes}
    links = [link for link in graph.get("links", [])
             if link.get("source") in node_ids and link.get("target") in node_ids]
    files = sorted({node.get("file") for node in nodes if node.get("file")})
    has_tests = any(re.search(r"test", str(path), re.I) for path in files)
    return {
        "request": str(request or "").strip(),
        "intent": selected_intent,
        "intent_terms": request_terms + list(markers),
        "matched": nodes[:min(5, len(nodes))],
        "nodes": nodes,
        "links": links,
        "complete_for": [selected_intent],
        "missing": ([] if has_tests or selected_intent != "tests" else ["tests"]),
        "do_not_expand": bool(nodes),
        "guidance": "Answer now from ops and relations. Cite aliases. Do not call another graph tool when do_not_expand=true.",
        "planner": "intent-v1",
        "budget": {"max_nodes": max_nodes, "selected_nodes": len(nodes)},
        "operation_limit": {"bindings": 12, "persistence": 8, "tests": 6, "impact": 5, "flow": 8}[selected_intent],
    }


def analyze_change(graph: dict[str, Any], request: str, max_nodes: int = 18) -> dict[str, Any]:
    """Build an auditable implementation brief without invoking an LLM.

    The result is intentionally suitable as direct agent context or as the
    grounded input to a local/cloud model. Every target remains backed by an
    indexed node and every dependency by an indexed edge.
    """
    request = str(request or "").strip()
    terms = _terms(request)
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    ranked: list[tuple[int, dict]] = []
    for node in nodes:
        fields = " ".join(str(node.get(key) or "") for key in
                          ("name", "container", "file", "signature", "details", "kind")).lower()
        operation_text = " ".join(
            f"{op.get('kind', '')} {op.get('name', '')} {op.get('text', '')}"
            for op in node.get("operations", [])
        ).lower()
        fields = f"{fields} {operation_text}"
        hits = sum(term in fields for term in terms)
        if not hits:
            continue
        exact = sum(term == str(node.get("name") or "").lower() for term in terms)
        kind_bonus = 15 if node.get("kind") not in ("file", "module") else 0
        operation_hits = sum(term in operation_text for term in terms)
        path = str(node.get("file") or "").replace("\\", "/")
        primary_source_bonus = 35 if path.startswith("src/") else 0
        ranked.append((hits * 20 + operation_hits * 25 + exact * 80 + kind_bonus + primary_source_bonus + min(15, int(node.get("degree") or 0)), node))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    seeds = [node for _, node in ranked[:5]]
    seed_ids = {node.get("id") for node in seeds}

    adjacent_ids = set(seed_ids)
    relevant_links = []
    for link in links:
        if link.get("source") in seed_ids or link.get("target") in seed_ids:
            relevant_links.append(link)
            adjacent_ids.update((link.get("source"), link.get("target")))
    nodes_by_id = {node.get("id"): node for node in nodes}
    selected = [nodes_by_id[node_id] for node_id in adjacent_ids if node_id in nodes_by_id]
    selected.sort(key=lambda node: (node.get("id") not in seed_ids, -int(node.get("degree") or 0), str(node.get("id"))))
    selected = selected[:max(1, max_nodes)]
    selected_ids = {node.get("id") for node in selected}
    relevant_links = [link for link in relevant_links
                      if link.get("source") in selected_ids and link.get("target") in selected_ids]

    files = sorted({str(node.get("file")) for node in selected if node.get("file")})
    tests = sorted({path for path in files if re.search(r"(?:^|[/_.])tests?(?:[/_.]|$)", path, re.I)})
    contracts = [node for node in selected if node.get("kind") in ("interface", "property", "event")]
    state = [node for node in selected if node.get("kind") in ("field", "property")]
    operation_kinds = sorted({op.get("kind") for node in selected for op in node.get("operations", []) if op.get("kind")})
    ambiguous = sum(str(link.get("confidence")) == "AMBIGUOUS" for link in relevant_links)
    confidence = "high" if seeds and not ambiguous else "medium" if seeds else "low"

    actions = []
    if seeds:
        actions.append("Modificar primero los targets y preservar sus firmas públicas salvo requisito explícito.")
        if contracts:
            actions.append("Revisar contratos, propiedades y eventos antes de ajustar consumidores.")
        if state:
            actions.append("Comprobar inicialización, mutación y ciclo de vida del estado identificado.")
        actions.append("Actualizar o crear pruebas para cada comportamiento y consumidor afectado.")
    else:
        actions.append("Aclarar nombres de símbolos o dominio: el índice no encontró evidencia suficiente.")

    risks = []
    if ambiguous:
        risks.append(f"{ambiguous} relaciones ambiguas requieren confirmación antes de editar.")
    if seeds and not tests:
        risks.append("No aparecen pruebas adyacentes en el subgrafo; buscar o crear cobertura dirigida.")
    if not seeds:
        risks.append("La solicitud no coincide con símbolos indexados.")

    return {
        "request": request,
        "intent_terms": terms,
        "matched": seeds,
        "nodes": selected,
        "links": relevant_links,
        "plan": {
            "confidence": confidence,
            "target_ids": [node.get("id") for node in seeds],
            "files": files,
            "contracts": [node.get("id") for node in contracts],
            "state": [node.get("id") for node in state],
            "operation_kinds": operation_kinds,
            "tests": tests,
            "actions": actions,
            "risks": risks,
            "answer_guidance": "ops are line-level method-body evidence; when complete=true answer from them without reconfirming source text",
        },
        "grounding": "deterministic-index; AI suggestions must cite entity aliases and must not invent edges",
    }
