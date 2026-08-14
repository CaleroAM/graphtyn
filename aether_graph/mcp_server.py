import json
import sys
from pathlib import Path
from typing import Dict, Any

from .core.ast_parser import ASTParser
from .core.history import HistoryTracker

def get_workspace_graph(workspace: Path, parser: ASTParser) -> dict:
    from .api.main import _index_dir
    try:
        dot_dir = _index_dir(workspace)
        cached = dot_dir / "index.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
    except Exception:
        pass
    return parser.scan_directory(workspace)

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
                            "description": "Obtiene el mapa de código determinista y explicaciones semánticas del proyecto sin consumir tokens.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"path": {"type": "string", "description": "Ruta del proyecto"}},
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
                graph = get_workspace_graph(workspace, parser)
                history.log_event("mcp", "neighborhood", f"Escaneo de mapa de código para {workspace.name}", {"nodes": len(graph.get("nodes", []))})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(graph, indent=2)}]}
                }
            elif name == "graph_blast_radius":
                symbol = args.get("symbol", "")
                depth = int(args.get("depth", 2))
                graph = get_workspace_graph(workspace, parser)
                result = blast_radius(graph, symbol, depth=depth)
                history.log_event("mcp", "blast_radius", f"Evaluación de radio de impacto para {symbol}", {"symbol": symbol, "depth": depth, "impacted": len(result["impacted"])})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
                }
            elif name == "graph_search_concepts":
                query = args.get("query", "").lower()
                graph = get_workspace_graph(workspace, parser)
                matches = [
                    n for n in graph.get("nodes", [])
                    if query in n.get("name", "").lower() or query in n.get("details", "").lower()
                ]
                history.log_event("mcp", "search_concepts", f"Búsqueda semántica de concepto: {query}", {"query": query, "count": len(matches)})
                return {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps({"query": query, "matches": matches}, indent=2)}]}
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
                import urllib.request
                data = json.dumps({"path": path_str, "name": proj_name, "mode": "agent_discovered"}).encode("utf-8")
                req_obj = urllib.request.Request("http://127.0.0.1:9210/api/projects/register", data=data, headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req_obj) as resp:
                        res = json.loads(resp.read().decode())
                        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}}
                except Exception as e:
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)})}]}}

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

