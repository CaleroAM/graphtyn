import json
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, Any

from .core.ast_parser import ASTParser
from .core.change_analyst import analyze_change, query_intent
from .core.history import HistoryTracker
from .core.storage import project_store_dir

def _cached_index_dir(workspace: Path) -> Path:
    return project_store_dir(Path.home() / ".aether-graph", workspace)

def get_workspace_graph(workspace: Path, parser: ASTParser) -> dict:
    try:
        cached = _cached_index_dir(workspace) / "index.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
    except Exception:
        pass
    return parser.scan_directory(workspace)

def _prune_node(n: dict) -> dict:
    return {k: v for k, v in n.items() if k not in ("color", "val")}


_HIGH_VALUE_OPERATIONS = {
    "addscoped", "addsingleton", "addtransient", "publish", "send", "addasync",
    "deleteasync", "updateasync", "savechanges", "savechangesasync", "usesqlserver",
    "usesqlite", "addinterceptors", "skip", "take", "countasync", "asnotracking",
    "registerdomainevent", "return",
}


def _select_operations(node: dict, terms: list[str] | None = None, limit: int = 12) -> list[dict]:
    terms = [str(term).lower() for term in (terms or []) if term]
    ranked = []
    seen = set()
    for index, op in enumerate(node.get("operations") or []):
        name = str(op.get("name") or "")
        text = str(op.get("text") or "")
        key = (op.get("kind"), name.lower(), int(op.get("line") or 0), text)
        if key in seen:
            continue
        seen.add(key)
        searchable = f"{name} {text}".lower()
        term_hits = sum(term in searchable for term in terms)
        high_value = name.lower() in _HIGH_VALUE_OPERATIONS or op.get("kind") in ("assign", "return", "control")
        score = term_hits * 100 + int(high_value) * 30 - index * 0.01
        ranked.append((score, index, op))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [item[2] for item in ranked[:limit]]
    selected.sort(key=lambda op: (int(op.get("line") or 0), str(op.get("kind") or ""), str(op.get("name") or "")))
    return selected


def _compact_node(node: dict, terms: list[str] | None = None) -> dict:
    """Keep the evidence an agent needs without shipping dashboard/index internals."""
    keep = ("id", "name", "kind", "file", "line", "end_line", "signature",
            "container", "namespace", "parser", "degree", "member_type", "owner_signature")
    compact = {key: node[key] for key in keep if node.get(key) not in (None, "", [])}
    details = str(node.get("details") or "").strip()
    redundant = details == str(node.get("file") or "") or details.startswith(("Class en ", "Method en ", "Function en ", "Carpeta: "))
    if details and not redundant:
        compact["details"] = details[:240]
    operations = _select_operations(node, terms)
    if operations:
        compact["operations"] = operations
    return compact


def _compact_link(link: dict) -> dict:
    keep = ("source", "target", "label", "confidence", "file", "line", "explanation")
    return {key: link[key] for key in keep if link.get(key) not in (None, "", [])}


def evidence_result(result: dict, max_nodes: int = 24, max_links: int | None = None) -> dict:
    """Encode graph evidence once, then reference it with short aliases."""
    raw_nodes: list[dict] = []
    for key in ("matched", "matches", "nodes"):
        raw_nodes.extend(result.get(key, []))
    raw_nodes.extend(item.get("node", {}) for item in result.get("impacted", []))
    unique: dict[str, dict] = {}
    for node in raw_nodes:
        node_id = str(node.get("id") or "")
        if node_id and node_id not in unique:
            unique[node_id] = node
    selected = list(unique.values())[:max_nodes]
    aliases = {node["id"]: f"N{index}" for index, node in enumerate(selected, 1)}
    files: dict[str, str] = {}

    def file_alias(path: str) -> str:
        if path not in files:
            files[path] = f"F{len(files) + 1}"
        return files[path]

    evidence_terms = result.get("intent_terms") or re.findall(r"[\w.]+", str(result.get("query") or result.get("symbol") or "").lower())
    entities: dict[str, dict] = {}
    for node in selected:
        item = {"name": node.get("name"), "kind": node.get("kind")}
        path = str(node.get("file") or "")
        if not path and str(node.get("id", "")).startswith("file:"):
            path = str(node["id"])[5:]
        if path:
            item["at"] = file_alias(path) + (f":{node['line']}" if node.get("line") else "")
        for key in ("signature", "container", "namespace", "member_type", "owner_signature"):
            if node.get(key):
                item[key] = node[key]
        details = str(node.get("details") or "").strip()
        if details and details != path:
            item["detail"] = details[:160]
        operations = _select_operations(node, evidence_terms, int(result.get("operation_limit") or 10))
        if operations:
            item["ops"] = [
                [op.get("kind"), op.get("name"), op.get("line"), str(op.get("text") or "")[:300]]
                for op in operations
            ]
        entities[aliases[node["id"]]] = item

    link_limit = max_links if max_links is not None else max_nodes * 2
    relations = []
    relation_counts: dict[str, int] = {}
    for link in result.get("links", []):
        label = str(link.get("label") or "conecta").lower()
        relation_counts[label] = relation_counts.get(label, 0) + 1
    for link in result.get("links", []):
        source, target = aliases.get(link.get("source")), aliases.get(link.get("target"))
        if not source or not target:
            continue
        confidence = str(link.get("confidence") or "EXTRACTED")
        relation = [source, link.get("label", "conecta"), target,
                    "E" if confidence == "EXTRACTED" else "I" if confidence == "INFERRED" else "A"]
        if link.get("line"):
            relation.append(link["line"])
        relations.append(relation)
        if len(relations) >= link_limit:
            break

    matched_ids = {node.get("id") for node in result.get("matched", []) if node.get("id")}
    incoming_calls = outgoing_calls = implementations = inheritance = 0
    for link in result.get("links", []):
        label = str(link.get("label") or "").lower()
        if label in ("llama", "usa"):
            incoming_calls += int(link.get("target") in matched_ids)
            outgoing_calls += int(link.get("source") in matched_ids)
        if label == "implementa" and (link.get("source") in matched_ids or link.get("target") in matched_ids):
            implementations += 1
        if label == "hereda" and (link.get("source") in matched_ids or link.get("target") in matched_ids):
            inheritance += 1

    impacted = []
    for item in result.get("impacted", []):
        alias = aliases.get(item.get("node", {}).get("id"))
        if alias:
            impacted.append([alias, item.get("hop"), item.get("label"), item.get("via")])

    output = {key: value for key, value in result.items()
              if key not in ("matched", "matches", "nodes", "links", "impacted", "estimated_tokens")}
    if "contexts" in output:
        output["contexts"] = [
            {**{key: value for key, value in context.items() if key != "matched_ids"},
             "matches": [aliases[node_id] for node_id in context.get("matched_ids", []) if node_id in aliases]}
            for context in output["contexts"]
        ]
    if "plan" in output:
        plan = dict(output["plan"])
        for key in ("target_ids", "contracts", "state"):
            plan[key] = [aliases.get(node_id, node_id) for node_id in plan.get(key, [])]
        output["plan"] = plan
    output.update({
        "format": "evidence-v1",
        "files": {alias: path for path, alias in files.items()},
        "entities": entities,
        "relations": relations,
        "legend": "relation=[source,label,target,E|I|A,line?]; E=extraída,I=inferida,A=ambigua",
        "complete": len(unique) <= len(selected) and len(result.get("links", [])) <= len(relations),
    })
    if matched_ids:
        output["coverage"] = {
            "incoming_calls_or_uses": incoming_calls,
            "outgoing_calls_or_uses": outgoing_calls,
            "implementations": implementations,
            "inheritance": inheritance,
            "relations_by_label": relation_counts,
            "zero_is_evidence_when_complete": True,
        }
    if impacted:
        output["impact"] = impacted
    omitted_nodes = max(0, len(unique) - len(selected))
    omitted_links = max(0, len(result.get("links", [])) - len(relations))
    if omitted_nodes or omitted_links:
        output["omitted"] = {"nodes": omitted_nodes, "links": omitted_links}
        output["next"] = "Solicita response_mode=full sólo si falta evidencia necesaria."
    output["estimated_tokens"] = len(json.dumps(output, ensure_ascii=False, separators=(",", ":"))) // 4
    return output


def compact_result(result: dict, max_nodes: int = 40) -> dict:
    """Bound MCP context while reporting truncation instead of silently losing evidence."""
    output = {k: v for k, v in result.items() if k not in ("nodes", "matched", "links", "impacted")}
    allowed_ids: set[str] = set()
    for key in ("matched", "nodes"):
        original = result.get(key, [])
        selected = original[:max_nodes]
        output[key] = [_compact_node(n) for n in selected]
        allowed_ids.update(n.get("id", "") for n in selected)
        if len(original) > len(selected):
            output[f"{key}_truncated"] = len(original) - len(selected)
    if "links" in result:
        links = [l for l in result["links"] if not allowed_ids or
                 (l.get("source") in allowed_ids and l.get("target") in allowed_ids)]
        output["links"] = [_compact_link(link) for link in links[:max_nodes * 2]]
        if len(links) > len(output["links"]):
            output["links_truncated"] = len(links) - len(output["links"])
    if "impacted" in result:
        impacted = result["impacted"][:max_nodes]
        output["impacted"] = [
            {**{k: item[k] for k in ("hop", "via", "label", "confidence") if k in item},
             "node": _compact_node(item.get("node", {}))}
            for item in impacted
        ]
        if len(result["impacted"]) > len(impacted):
            output["impacted_truncated"] = len(result["impacted"]) - len(impacted)
    output["response_mode"] = "compact"
    output["estimated_tokens"] = len(json.dumps(output, ensure_ascii=False)) // 4
    return output


def context_bundle(graph: dict, symbols: list[str], depth: int = 1, max_nodes: int = 20) -> dict:
    """Serve focused context under one global, relevance-ranked budget."""
    unique = list(dict.fromkeys(s.strip() for s in symbols if s and s.strip()))[:10]
    contexts = []
    candidates: dict[str, dict] = {}
    scores: dict[str, float] = {}
    all_links: dict[tuple, dict] = {}
    matched_ids: set[str] = set()
    label_score = {"implementa": 900, "hereda": 850, "llama": 750, "usa": 650, "importa": 600, "declara": 500, "contiene": 120}
    for symbol in unique:
        neighborhood = neighborhood_subgraph(graph, symbol, depth)
        local_matches = {node.get("id") for node in neighborhood.get("matched", []) if node.get("id")}
        matched_ids.update(local_matches)
        for node in neighborhood.get("nodes", []):
            nid = node.get("id", "")
            if not nid:
                continue
            candidates[nid] = _compact_node(node)
            scores[nid] = max(scores.get(nid, 0), 10 + min(50, int(node.get("degree") or 0)))
            if nid in local_matches:
                scores[nid] = 10_000
            elif node.get("kind") in ("class", "interface", "struct"):
                scores[nid] += 180
        for link in neighborhood.get("links", []):
            key = (link.get("source"), link.get("target"), link.get("label"), link.get("line"))
            all_links[key] = _compact_link(link)
            base = label_score.get(str(link.get("label") or "").lower(), 300)
            for nid in (link.get("source"), link.get("target")):
                if nid in candidates:
                    scores[nid] = max(scores.get(nid, 0), base + min(50, int(candidates[nid].get("degree") or 0)))
        contexts.append({
            "symbol": symbol,
            "matched_ids": sorted(local_matches),
        })
    budget = max(len(matched_ids), max(1, int(max_nodes)))
    ranked_ids = sorted(candidates, key=lambda nid: (-scores.get(nid, 0), nid))
    selected_ids = set(ranked_ids[:budget]) | matched_ids
    selected_nodes = [candidates[nid] for nid in ranked_ids if nid in selected_ids]
    selected_links = [link for link in all_links.values()
                      if link.get("source") in selected_ids and link.get("target") in selected_ids]
    link_budget = max(1, budget * 2)
    selected_links.sort(key=lambda link: (-label_score.get(str(link.get("label") or "").lower(), 300),
                                          str(link.get("source")), str(link.get("target"))))
    omitted_nodes = max(0, len(candidates) - len(selected_nodes))
    omitted_links = max(0, len(selected_links) - link_budget) + sum(
        1 for link in all_links.values()
        if link.get("source") not in selected_ids or link.get("target") not in selected_ids
    )
    selected_links = selected_links[:link_budget]
    for context in contexts:
        context["truncated"] = omitted_nodes > 0 or omitted_links > 0
    result = {
        "symbols": unique,
        "contexts": contexts,
        "nodes": selected_nodes,
        "links": selected_links,
        "budget": {"max_nodes": budget, "max_links": link_budget},
        "omitted": {"nodes": omitted_nodes, "links": omitted_links},
        "planner": "relevance-v1",
        "guidance": "Aristas implementa/hereda/llama son evidencia direccional. No convierta nodos del mismo subsistema en consumidores sin una arista entrante llama/usa.",
    }
    result["estimated_tokens"] = len(json.dumps(result, ensure_ascii=False)) // 4
    return result

def _tokens_avoided(workspace: Path, result: dict, payload_text: str) -> int:
    try:
        files: set = set()

        def collect(nodes):
            for n in nodes:
                nid = n.get("id", "")
                if nid.startswith("file:"):
                    files.add(nid[5:])

        collect(result.get("nodes", []))
        collect(result.get("matched", []))
        for imp in result.get("impacted", []):
            collect([imp.get("node", {})])
        raw_chars = 0
        for rel in files:
            p = workspace / rel
            if p.is_file():
                raw_chars += p.stat().st_size
        return max(0, (raw_chars // 4) - (len(payload_text) // 4))
    except Exception:
        return 0

def neighborhood_subgraph(graph: dict, symbol: str, depth: int = 1) -> dict:
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    nodes_map = {n["id"]: n for n in nodes}
    selector = symbol.strip()
    if "." in selector and "/" not in selector and not selector.lower().endswith((".cs", ".py", ".js", ".ts")):
        container, name = selector.rsplit(".", 1)
        matches = [n for n in nodes if n.get("name", "").lower() == name.lower()
                   and n.get("container", "").lower() == container.lower()]
    else:
        exact = [n for n in nodes if n.get("name", "").lower() == selector.lower()]
        matches = exact or [n for n in nodes if selector.lower() in n.get("name", "").lower()]

    adj: Dict[str, list] = {}
    for l in links:
        s, t = l["source"], l["target"]
        adj.setdefault(s, []).append(t)
        adj.setdefault(t, []).append(s)

    ids: Dict[str, int] = {n["id"]: 0 for n in matches}
    frontier = [(n["id"], 0) for n in matches]
    while frontier:
        nid, d = frontier.pop(0)
        if d >= depth:
            continue
        for nb in adj.get(nid, []):
            if nb in ids:
                continue
            ids[nb] = d + 1
            frontier.append((nb, d + 1))

    sub_nodes = [_prune_node(nodes_map[nid]) for nid in ids]
    sub_links = [l for l in links if l["source"] in ids and l["target"] in ids]
    return {
        "symbol": symbol,
        "depth": depth,
        "matched": [_prune_node(n) for n in matches[:10]],
        "nodes": sub_nodes,
        "links": sub_links,
    }

def blast_radius(graph: dict, symbol: str, depth: int = 2) -> dict:
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    nodes_map = {n["id"]: n for n in nodes}
    selector = symbol.strip()
    if "." in selector and "/" not in selector and not selector.lower().endswith((".cs", ".py", ".js", ".ts")):
        container, name = selector.rsplit(".", 1)
        matches = [n for n in nodes if n.get("name", "").lower() == name.lower()
                   and n.get("container", "").lower() == container.lower()]
    else:
        exact = [n for n in nodes if n.get("name", "").lower() == selector.lower()]
        matches = exact or [n for n in nodes if selector.lower() in n.get("name", "").lower()]

    adj: Dict[str, list] = {}
    edge_map = {}
    for l in links:
        s = l["source"]
        t = l["target"]
        adj.setdefault(s, []).append(t)
        adj.setdefault(t, []).append(s)
        edge_map[(s, t)] = l
        edge_map[(t, s)] = l

    impacted = []
    seen = {n["id"] for n in matches}
    frontier = [(n["id"], 0) for n in matches]
    while frontier:
        nid, d = frontier.pop(0)
        if d >= depth:
            continue
        for nb in adj.get(nid, []):
            if nb in seen:
                continue
            seen.add(nb)
            edge = edge_map.get((nid, nb), {})
            impacted.append({
                "node": nodes_map.get(nb, {"id": nb}),
                "hop": d + 1,
                "via": nodes_map.get(nid, {}).get("name", nid),
                "label": edge.get("label", "conecta"),
                "confidence": edge.get("confidence", "EXTRACTED"),
            })
            frontier.append((nb, d + 1))

    return {
        "symbol": symbol,
        "depth": depth,
        "matched": matches[:10],
        "impacted": impacted,
    }

def run_mcp_server(workspace: Path, tool_profile: str = "full"):
    """
    Stdio Model Context Protocol (MCP) Server for AetherGraph.
    Provides tools for AI agents: graph_neighborhood, graph_blast_radius, graph_search_concepts, graph_register_project.
    """
    parser = ASTParser()
    history = HistoryTracker(workspace)
    intent_contexts: dict[str, dict] = {}

    def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aether-graph-mcp", "version": "0.1.0"}
                }
            }
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "graph_query_intent",
                            "description": "Ruta principal de una sola llamada para flow/bindings/persistence/tests/impact. Devuelve ops filtradas, complete_for y do_not_expand; responde inmediatamente cuando do_not_expand=true.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "request": {"type": "string", "description": "Pregunta o tarea completa"},
                                    "intent": {"type": "string", "enum": ["auto", "flow", "bindings", "persistence", "tests", "impact"]},
                                    "limit": {"type": "integer", "description": "Máximo de entidades; default 10"},
                                    "extends_context_id": {"type": "string", "description": "Contexto previo para devolver sólo evidencia nueva"}
                                },
                                "required": ["request"]
                            }
                        },
                        {
                            "name": "graph_analyze_change",
                            "description": "Primera opción para flujos, bindings, persistencia e impacto. Devuelve targets, contratos, estado y operaciones internas compactas (ops). Responde con esa evidencia; expande sólo si falta un hecho y cita aliases.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "request": {"type": "string", "description": "Issue, requisito o cambio solicitado"},
                                    "limit": {"type": "integer", "description": "Máximo de entidades; default 18"},
                                    "response_mode": {"type": "string", "enum": ["compact", "full"]}
                                },
                                "required": ["request"]
                            }
                        },
                        {
                            "name": "graph_context_bundle",
                            "description": "Obtén evidencia compacta para hasta 10 símbolos en una llamada. Responde directamente si complete=true; expande sólo si falta un hecho.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "symbols": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                                    "depth": {"type": "integer", "description": "Default 1"},
                                    "limit": {"type": "integer", "description": "Presupuesto global de nodos; default 12"},
                                    "response_mode": {"type": "string", "enum": ["compact", "full"], "description": "compact usa aliases evidence-v1 (default)"}
                                },
                                "required": ["symbols"]
                            }
                        },
                        {
                            "name": "graph_neighborhood",
                            "description": "Obtén evidencia estructural de un símbolo. Si complete=true, los ceros de coverage son evidencia negativa suficiente: no busques sinónimos ni amplíes para reconfirmarlos.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Ruta del proyecto"},
                                    "symbol": {"type": "string", "description": "Opcional: nombre de símbolo o archivo para devolver solo su vecindario"},
                                    "depth": {"type": "integer", "description": "Saltos alrededor del símbolo (default 1)"},
                                    "limit": {"type": "integer", "description": "Máximo de nodos; default 24"},
                                    "response_mode": {"type": "string", "enum": ["compact", "full"], "description": "compact (default) reduce tokens; full conserva todos los campos"}
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "graph_blast_radius",
                            "description": "Calcula impacto con evidencia E/I/A. Si complete=true, coverage=0 confirma ausencia de relaciones; no hagas búsquedas adicionales para reconfirmar.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "symbol": {"type": "string", "description": "Nombre de la función o clase"},
                                    "depth": {"type": "integer", "description": "Profundidad máxima de recorrido (default 2)"},
                                    "limit": {"type": "integer", "description": "Máximo de impactos; default 24"},
                                    "response_mode": {"type": "string", "enum": ["compact", "full"]}
                                },
                                "required": ["symbol"]
                            }
                        },
                        {
                            "name": "graph_search_concepts",
                            "description": "Busca nombres, descripciones y operaciones internas (AddScoped, Publish, Skip/Take, etc.). Devuelve coincidencias compactas; usa graph_analyze_change para agrupar un flujo.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Término o concepto semántico a buscar"},
                                    "limit": {"type": "integer", "description": "Máximo de resultados; default 12"},
                                    "response_mode": {"type": "string", "enum": ["compact", "full"]}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "graph_history_search",
                            "description": "Busca en el historial de sesiones y acciones pasadas del agente para recordar eventos o decisiones.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"query": {"type": "string", "description": "Término de búsqueda en el historial"}},
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "graph_history_timeline",
                            "description": "Devuelve la secuencia cronológica de acciones de una sesión previa para contexto completo.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"session_id": {"type": "string", "description": "ID de sesión opcional"}},
                                "required": []
                            }
                        },
                        {
                            "name": "graph_history_get",
                            "description": "Recupera la observación detallada de una acción pasada específica por su ID.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"id": {"type": "integer", "description": "ID de la observación"}},
                                "required": ["id"]
                            }
                        },
                        {
                            "name": "graph_register_project",
                            "description": "Registra autónomamente una ruta de proyecto en AetherGraph.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Ruta absoluta del proyecto"},
                                    "name": {"type": "string", "description": "Nombre del proyecto"}
                                },
                                "required": ["path"]
                            }
                        }
                    ]
                }
            }
            if tool_profile == "intent":
                response["result"]["tools"] = [
                    tool for tool in response["result"]["tools"]
                    if tool["name"] == "graph_query_intent"
                ]
            return response
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name == "graph_query_intent":
                graph = get_workspace_graph(workspace, parser)
                request = str(args.get("request") or "").strip()
                limit = max(4, min(24, int(args.get("limit") or 10)))
                raw = query_intent(graph, request, str(args.get("intent") or "auto"), limit)
                result = evidence_result(raw, max_nodes=limit)
                context_id = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
                previous_id = str(args.get("extends_context_id") or "")
                previous = intent_contexts.get(previous_id)
                if previous:
                    old_entities = previous.get("entities", {})
                    old_relations = {json.dumps(item, ensure_ascii=False) for item in previous.get("relations", [])}
                    result = {
                        "format": "evidence-delta-v1", "extends": previous_id, "context_id": context_id,
                        "files": result.get("files", {}),
                        "entities": {key: value for key, value in result.get("entities", {}).items() if old_entities.get(key) != value},
                        "relations": [item for item in result.get("relations", []) if json.dumps(item, ensure_ascii=False) not in old_relations],
                        "complete_for": result.get("complete_for", []), "missing": result.get("missing", []),
                        "do_not_expand": result.get("do_not_expand", False), "guidance": result.get("guidance"),
                    }
                    result["estimated_tokens"] = len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) // 4
                else:
                    result["context_id"] = context_id
                intent_contexts[context_id] = evidence_result(raw, max_nodes=limit)
                history.log_event("mcp", "query_intent", f"Consulta {raw['intent']} de una ronda", {"request": request[:240], "context_id": context_id, "estimated_tokens": result["estimated_tokens"]})
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}}
            elif name == "graph_analyze_change":
                graph = get_workspace_graph(workspace, parser)
                request = str(args.get("request") or "").strip()
                limit = max(6, min(40, int(args.get("limit") or 18)))
                result = analyze_change(graph, request, limit)
                if args.get("response_mode", "compact") != "full":
                    result = evidence_result(result, max_nodes=limit)
                history.log_event("mcp", "analyze_change", "Análisis de cambio con evidencia", {"request": request[:240], "confidence": result.get("plan", {}).get("confidence")})
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}}
            elif name == "graph_context_bundle":
                graph = get_workspace_graph(workspace, parser)
                symbols = args.get("symbols") or []
                requested_limit = args.get("limit")
                adaptive_limit = int(requested_limit) if requested_limit else min(36, max(12, len(symbols) * 6))
                result = context_bundle(graph, symbols, int(args.get("depth", 1)), adaptive_limit)
                if args.get("response_mode", "compact") != "full":
                    result = evidence_result(result, max_nodes=adaptive_limit)
                history.log_event("mcp", "context_bundle", f"Contexto agrupado para {len(result['symbols'])} símbolos", {"symbols": result["symbols"], "estimated_tokens": result["estimated_tokens"]})
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}}
            elif name == "graph_neighborhood":
                symbol = (args.get("symbol") or "").strip()
                depth = int(args.get("depth", 1))
                limit = int(args.get("limit") or 0)
                response_mode = args.get("response_mode", "compact")
                graph = get_workspace_graph(workspace, parser)
                if symbol:
                    result = neighborhood_subgraph(graph, symbol, depth=depth)
                else:
                    pruned_nodes = [_prune_node(n) for n in graph.get("nodes", [])]
                    if limit > 0:
                        top = sorted(
                            pruned_nodes, key=lambda n: n.get("degree", 0), reverse=True
                        )[:limit]
                        keep = {n["id"] for n in top}
                        for n in top:
                            parts = n["id"].split(":")
                            if len(parts) >= 2 and parts[0] == "file" and "/" in parts[1]:
                                keep.add("dir:" + parts[1].rsplit("/", 1)[0])
                        pruned_nodes = [n for n in pruned_nodes if n["id"] in keep]
                        sub_links = [l for l in graph.get("links", []) if l["source"] in keep and l["target"] in keep]
                    else:
                        sub_links = graph.get("links", [])
                    result = {"nodes": pruned_nodes, "links": sub_links, "limit": limit or None}
                if response_mode != "full":
                    result = evidence_result(result, max_nodes=limit or 24)
                history.log_event("mcp", "neighborhood", f"Escaneo de mapa de código para {workspace.name}", {"nodes": len(result.get("nodes", [])), "tokens_avoided": _tokens_avoided(workspace, result, json.dumps(result))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}
                }
            elif name == "graph_blast_radius":
                symbol = args.get("symbol", "")
                depth = int(args.get("depth", 2))
                graph = get_workspace_graph(workspace, parser)
                result = blast_radius(graph, symbol, depth=depth)
                result["matched"] = [_prune_node(n) for n in result["matched"]]
                for imp in result["impacted"]:
                    imp["node"] = _prune_node(imp["node"])
                impacted_count = len(result["impacted"])
                if args.get("response_mode", "compact") != "full":
                    result = evidence_result(result, max_nodes=int(args.get("limit") or 24))
                history.log_event("mcp", "blast_radius", f"Evaluación de radio de impacto para {symbol}", {"symbol": symbol, "depth": depth, "impacted": impacted_count, "tokens_avoided": _tokens_avoided(workspace, result, json.dumps(result))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}
                }
            elif name == "graph_search_concepts":
                query = args.get("query", "").lower().strip()
                graph = get_workspace_graph(workspace, parser)
                terms = list(dict.fromkeys(term for term in re.findall(r"[\w.]+", query) if len(term) >= 3))[:12]
                ranked = []
                for node in graph.get("nodes", []):
                    name_text = str(node.get("name") or "").lower()
                    details_text = str(node.get("details") or "").lower()
                    operations_text = " ".join(
                        f"{op.get('name', '')} {op.get('text', '')}" for op in node.get("operations", [])
                    ).lower()
                    searchable = f"{name_text} {details_text} {operations_text}"
                    matched_terms = sum(term in searchable for term in terms)
                    if query in searchable or matched_terms:
                        exact_name = any(term == name_text for term in terms)
                        score = (100 if query and query in searchable else 0) + matched_terms * 10 + (30 if exact_name else 0) + min(10, int(node.get("degree") or 0))
                        ranked.append((score, node))
                ranked.sort(key=lambda item: (-item[0], str(item[1].get("name") or ""), str(item[1].get("id") or "")))
                matches = [_prune_node(node) for _, node in ranked]
                result_search = {"query": query, "matches": matches}
                if args.get("response_mode", "compact") != "full":
                    result_search = evidence_result(result_search, max_nodes=int(args.get("limit") or 12), max_links=0)
                history.log_event("mcp", "search_concepts", f"Búsqueda semántica de concepto: {query}", {"query": query, "count": len(matches), "tokens_avoided": _tokens_avoided(workspace, result_search, json.dumps(result_search))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result_search, ensure_ascii=False, separators=(",", ":"))}]}
                }
            elif name == "graph_history_search":

                q = args.get("query", "")
                events = history.search_events(q)
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps({"query": q, "results": events}, indent=2)}]}
                }
            elif name == "graph_history_timeline":
                sid = args.get("session_id")
                timeline = history.get_timeline(sid)
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps({"session_id": sid, "timeline": timeline}, indent=2)}]}
                }
            elif name == "graph_history_get":
                obs_id = args.get("id", 0)
                obs = history.get_observation(obs_id)
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(obs, indent=2)}]}
                }
            elif name == "graph_register_project":
                path_str = args.get("path")
                proj_name = args.get("name")
                import os
                import urllib.request
                daemon_url = os.environ.get("AETHER_DAEMON_URL", "http://127.0.0.1:9210").rstrip("/")
                data = json.dumps({"path": path_str, "name": proj_name, "mode": "agent_discovered"}).encode("utf-8")
                req_obj = urllib.request.Request(f"{daemon_url}/api/projects/register", data=data, headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req_obj, timeout=10) as resp:
                        res = json.loads(resp.read().decode())
                        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}}
                except Exception as e:
                    err = {"ok": False, "error": str(e), "daemon_url": daemon_url}
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(err, indent=2), "isError": True}]}}

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            sys.stderr.write(f"[AetherGraph MCP Error] {e}\n")
