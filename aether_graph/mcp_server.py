import json
import sys
from pathlib import Path
from typing import Dict, Any

from .core.ast_parser import ASTParser
from .core.history import HistoryTracker

def _cached_index_dir(workspace: Path) -> Path:
    d = Path.home() / ".aether-graph" / workspace.name
    d.mkdir(parents=True, exist_ok=True)
    return d

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
    matches = [n for n in nodes if symbol.lower() in n.get("name", "").lower()]

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
    matches = [n for n in nodes if symbol.lower() in n.get("name", "").lower()]

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

def run_mcp_server(workspace: Path):
    """
    Stdio Model Context Protocol (MCP) Server for AetherGraph.
    Provides tools for AI agents: graph_neighborhood, graph_blast_radius, graph_search_concepts, graph_register_project.
    """
    parser = ASTParser()
    history = HistoryTracker(workspace)

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
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "graph_neighborhood",
                            "description": "Obtiene el mapa de código determinista y explicaciones semánticas del proyecto sin consumir tokens. Con 'symbol' devuelve solo el subgrafo alrededor de ese símbolo o archivo (más compacto).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Ruta del proyecto"},
                                    "symbol": {"type": "string", "description": "Opcional: nombre de símbolo o archivo para devolver solo su vecindario"},
                                    "depth": {"type": "integer", "description": "Saltos alrededor del símbolo (default 1)"},
                                    "limit": {"type": "integer", "description": "Opcional: máximo de nodos (por degree) cuando no se usa 'symbol'"}
                                },
                                "required": []
                            }
                        },
                        {
                            "name": "graph_blast_radius",
                            "description": "Calcula el radio de impacto de modificar un símbolo o archivo: recorre el grafo por aristas con su confianza (EXTRACTED/INFERRED) y devuelve los nodos afectados por salto (hop).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "symbol": {"type": "string", "description": "Nombre de la función o clase"},
                                    "depth": {"type": "integer", "description": "Profundidad máxima de recorrido (default 2)"}
                                },
                                "required": ["symbol"]
                            }
                        },
                        {
                            "name": "graph_search_concepts",
                            "description": "Busca conceptos semánticos o palabras clave en las descripciones explicativas del código.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"query": {"type": "string", "description": "Término o concepto semántico a buscar"}},
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
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name == "graph_neighborhood":
                symbol = (args.get("symbol") or "").strip()
                depth = int(args.get("depth", 1))
                limit = int(args.get("limit") or 0)
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
                history.log_event("mcp", "neighborhood", f"Escaneo de mapa de código para {workspace.name}", {"nodes": len(result.get("nodes", [])), "tokens_avoided": _tokens_avoided(workspace, result, json.dumps(result))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
                }
            elif name == "graph_blast_radius":
                symbol = args.get("symbol", "")
                depth = int(args.get("depth", 2))
                graph = get_workspace_graph(workspace, parser)
                result = blast_radius(graph, symbol, depth=depth)
                result["matched"] = [_prune_node(n) for n in result["matched"]]
                for imp in result["impacted"]:
                    imp["node"] = _prune_node(imp["node"])
                history.log_event("mcp", "blast_radius", f"Evaluación de radio de impacto para {symbol}", {"symbol": symbol, "depth": depth, "impacted": len(result["impacted"]), "tokens_avoided": _tokens_avoided(workspace, result, json.dumps(result))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
                }
            elif name == "graph_search_concepts":
                query = args.get("query", "").lower()
                graph = get_workspace_graph(workspace, parser)
                matches = [
                    _prune_node(n) for n in graph.get("nodes", [])
                    if query in n.get("name", "").lower() or query in n.get("details", "").lower()
                ]
                result_search = {"query": query, "matches": matches}
                history.log_event("mcp", "search_concepts", f"Búsqueda semántica de concepto: {query}", {"query": query, "count": len(matches), "tokens_avoided": _tokens_avoided(workspace, result_search, json.dumps(result_search))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result_search, indent=2)}]}
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

