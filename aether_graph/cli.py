import sys
import json
import argparse
from pathlib import Path

from .core.ast_parser import ASTParser
from .mcp_server import run_mcp_server

def main():
    parser = argparse.ArgumentParser(
        prog="aether-graph",
        description="AetherGraph — Zero-Token AST Deterministic + Hybrid RAG Graph for AI Coding Agents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # init
    init_parser = subparsers.add_parser("init", help="Inicializa .aether-graph/ en el repositorio actual")
    init_parser.add_argument("--path", default=".", help="Ruta del proyecto")

    # build
    build_parser = subparsers.add_parser("build", help="Construye el índice AST de código")
    build_parser.add_argument("--path", default=".", help="Ruta del proyecto")

    # query
    query_parser = subparsers.add_parser("query", help="Consulta símbolos y relaciones")
    query_parser.add_argument("symbol", help="Símbolo o función a consultar")
    query_parser.add_argument("--path", default=".", help="Ruta del proyecto")

    # mcp
    mcp_parser = subparsers.add_parser("mcp", help="Inicia el servidor Model Context Protocol (MCP) por stdio")
    mcp_parser.add_argument("--path", default=".", help="Ruta del proyecto")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Inicia el demonio HTTP local")
    serve_parser.add_argument("--reload", action="store_true", help="Habilitar recarga automática en vivo (Hot-Reloading)")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host")
    serve_parser.add_argument("--port", type=int, default=9210, help="Puerto")
    serve_parser.add_argument("--path", default=".", help="Ruta del proyecto")

    args = parser.parse_args()
    root = Path(args.path if hasattr(args, 'path') else ".").resolve()

    if args.command == "init":
        dot_dir = root / ".aether-graph"
        dot_dir.mkdir(exist_ok=True)
        config = {
            "version": "0.1.0",
            "name": root.name,
            "ignore": [".git", "venv", "node_modules", "__pycache__"]
        }
        (dot_dir / "aether.json").write_text(json.dumps(config, indent=2))
        print(f"✓ Inicializado .aether-graph/ en {root}")

    elif args.command == "build":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        dot_dir = root / ".aether-graph"
        dot_dir.mkdir(exist_ok=True)
        (dot_dir / "index.json").write_text(json.dumps(graph, indent=2))
        print(f"✓ Índice AetherGraph construido: {len(graph['nodes'])} nodos, {len(graph['links'])} enlaces.")

    elif args.command == "query":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        matches = [n for n in graph["nodes"] if args.symbol.lower() in n["name"].lower()]
        print(json.dumps({"symbol": args.symbol, "matches": matches}, indent=2))

    elif args.command == "mcp":
        run_mcp_server(root)

    elif args.command == "serve":
        import uvicorn
        print(f"🚀 Servidor AetherGraph escuchando en http://{args.host}:{args.port} (Hot-Reloading={args.reload})")
        if args.reload:
            uvicorn.run("aether_graph.api.main:app", host=args.host, port=args.port, reload=True)
        else:
            from .api.main import app
            uvicorn.run(app, host=args.host, port=args.port)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
