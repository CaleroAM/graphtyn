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
                        }
                    ]
                }
            }
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name == "graph_neighborhood":
                graph = parser.scan_directory(workspace)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(graph, indent=2)}]
                    }
                }
            elif name == "graph_blast_radius":
                symbol = args.get("symbol", "")
                graph = parser.scan_directory(workspace)
                matches = [n for n in graph["nodes"] if symbol.lower() in n["name"].lower()]
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"symbol": symbol, "impacted_nodes": matches}, indent=2)}]
                    }
                }

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
