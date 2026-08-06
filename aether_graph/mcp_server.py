import json
import sys
from pathlib import Path
from typing import Dict, Any

from .core.ast_parser import ASTParser

def run_mcp_server(workspace: Path):
    """
    Stdio Model Context Protocol (MCP) Server for AetherGraph.
    Provides tools for AI agents: graph_neighborhood, graph_who_calls, graph_blast_radius.
    """
    parser = ASTParser()

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
                            "description": "Obtiene el mapa de código determinista (archivos y símbolos) alrededor del proyecto sin consumir tokens de LLM.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"path": {"type": "string", "description": "Ruta del proyecto"}},
                                "required": []
                            }
                        },
                        {
                            "name": "graph_blast_radius",
                            "description": "Calcula el radio de impacto de modificar un símbolo o archivo en el proyecto.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"symbol": {"type": "string", "description": "Nombre de la función o clase"}},
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
                            "name": "graph_register_project",
                            "description": "Registra autónomamente una ruta de proyecto en AetherGraph (Opción 3: Registro por Agente).",
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
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(graph, indent=2)}]
                    }
                }
            elif name == "graph_blast_radius":
                symbol = args.get("symbol", "")
                graph = get_workspace_graph(workspace, parser)
                matches = [n for n in graph["nodes"] if symbol.lower() in n["name"].lower()]
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"symbol": symbol, "impacted_nodes": matches}, indent=2)}]
                    }
                }
                        elif name == "graph_search_concepts":
                query = args.get("query", "").lower()
                graph = get_workspace_graph(workspace, parser)
                matches = [
                    n for n in graph.get("nodes", [])
                    if query in n.get("name", "").lower() or query in n.get("details", "").lower()
                ]
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"query": query, "matches": matches}, indent=2)}]
                    }
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
