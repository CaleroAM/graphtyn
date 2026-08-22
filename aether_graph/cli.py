import sys
import json
import argparse
import subprocess
import urllib.request
from pathlib import Path

from .core.ast_parser import ASTParser
from .core.history import HistoryTracker
from .core.benchmark import benchmark_markdown, run_benchmark
from .core.agent_benchmark import compare_agent_runs
from .core.impact import analyze_impact
from .mcp_server import run_mcp_server

def bfs_path(graph: dict, start_sym: str, end_sym: str):
    nodes = {n['id']: n for n in graph.get('nodes', [])}
    name_to_id = {}
    for n in graph.get('nodes', []):
        name_to_id[n['name'].lower()] = n['id']

    s_id = name_to_id.get(start_sym.lower())
    e_id = name_to_id.get(end_sym.lower())
    if not s_id or not e_id:
        return None

    adj = {}
    for l in graph.get('links', []):
        src = l['source'] if isinstance(l['source'], str) else l['source']['id']
        tgt = l['target'] if isinstance(l['target'], str) else l['target']['id']
        adj.setdefault(src, []).append(tgt)
        adj.setdefault(tgt, []).append(src)

    queue = [[s_id]]
    visited = {s_id}
    while queue:
        path = queue.pop(0)
        curr = path[-1]
        if curr == e_id:
            return [nodes[nid]['name'] for nid in path]
        for nxt in adj.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(path + [nxt])
    return None

def main():
    parser = argparse.ArgumentParser(
        prog="aether-graph",
        description="AetherGraph — Zero-Token AST Deterministic + Hybrid RAG Graph for AI Coding Agents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # init
    init_p = subparsers.add_parser("init", help="Inicializa .aether-graph/ en el repositorio")
    init_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # build / reindex
    reindex_p = subparsers.add_parser("reindex", help="Reindexa el código con motor AST + IA")
    reindex_p.add_argument("--path", default=".", help="Ruta del proyecto")
    reindex_p.add_argument("--engine", default="ast_local_llm", choices=["ast_local_llm", "ast_cloud", "ast_pure"], help="Motor de IA")

    # query
    query_p = subparsers.add_parser("query", help="Consulta conceptos o símbolos en el grafo")
    query_p.add_argument("query_text", help="Término, símbolo o concepto a consultar")
    query_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # path
    path_p = subparsers.add_parser("path", help="Encuentra la ruta de conexión entre dos símbolos")
    path_p.add_argument("start_symbol", help="Símbolo inicial")
    path_p.add_argument("end_symbol", help="Símbolo destino")
    path_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # explain
    explain_p = subparsers.add_parser("explain", help="Explica el propósito y conexiones de un símbolo")
    explain_p.add_argument("symbol", help="Símbolo a explicar")
    explain_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # diff
    diff_p = subparsers.add_parser("diff", help="Calcula el radio de impacto de los cambios de git (git diff)")
    diff_p.add_argument("--path", default=".", help="Ruta del proyecto")

    pr_p = subparsers.add_parser("pr-impact", help="Analiza riesgo, impacto y conflictos potenciales de una rama o PR")
    pr_p.add_argument("--base", default=None, help="Rama base, por ejemplo main")
    pr_p.add_argument("--path", default=".", help="Ruta del proyecto")
    pr_p.add_argument("--json", action="store_true", help="Salida JSON")

    bench_p = subparsers.add_parser("benchmark", help="Mide rendimiento, validez y recall contra un ground truth")
    bench_p.add_argument("--path", default=".", help="Ruta del proyecto")
    bench_p.add_argument("--ground-truth", default=None, help="Archivo JSON con símbolos esperados")
    bench_p.add_argument("--output", default=None, help="Guarda el resultado JSON")
    bench_p.add_argument("--cache", default=None, help="Ruta opcional del caché estructural")

    agent_bench_p = subparsers.add_parser("agent-benchmark", help="Compara tokens y tiempo de corridas con/sin AetherGraph")
    agent_bench_p.add_argument("--treatment", required=True, help="JSON o lista JSON de corridas con AetherGraph")
    agent_bench_p.add_argument("--baseline", required=True, help="JSON o lista JSON de corridas sin AetherGraph")
    agent_bench_p.add_argument("--output", default=None, help="Guarda el resultado JSON")

    # export-md
    export_p = subparsers.add_parser("export-md", help="Exporta un mapa de arquitectura conciso en Markdown para Agentes de IA")
    export_p.add_argument("--output", default="ARCHITECTURE.md", help="Archivo de salida")
    export_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # timeline
    timeline_p = subparsers.add_parser("timeline", help="Muestra la línea de tiempo del historial de acciones de la IA")
    timeline_p.add_argument("--session-id", default=None, help="ID de sesión opcional")
    timeline_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # mcp
    mcp_p = subparsers.add_parser("mcp", help="Inicia el servidor Model Context Protocol (MCP) por stdio")
    mcp_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # serve
    serve_p = subparsers.add_parser("serve", help="Inicia el demonio HTTP local")
    serve_p.add_argument("--reload", action="store_true", help="Habilitar recarga automática en vivo")
    serve_p.add_argument("--watch", action="store_true", help="Reindexa automáticamente proyectos al cambiar archivos")
    serve_p.add_argument("--mcp-token", default=None, help="Activa MCP HTTP con este token Bearer (preferible: AETHER_MCP_TOKEN)")
    serve_p.add_argument("--host", default="0.0.0.0", help="Host")
    serve_p.add_argument("--port", type=int, default=9210, help="Puerto")
    serve_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # hook
    hook_p = subparsers.add_parser("hook", help="Instala/desinstala el hook post-commit de reindexado incremental")
    hook_p.add_argument("action", choices=["install", "uninstall"], help="install o uninstall")
    hook_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # gitignore
    git_p = subparsers.add_parser("gitignore", help="Configura si el grafo respeta .gitignore (on/off) por proyecto")
    git_p.add_argument("value", choices=["on", "off"], help="on = solo archivos versionados · off = incluir todo")
    git_p.add_argument("--path", default=".", help="Ruta del proyecto")

    args = parser.parse_args()
    root = Path(args.path if hasattr(args, 'path') else ".").resolve()

    if args.command == "init":
        dot_dir = root / ".aether-graph"
        dot_dir.mkdir(exist_ok=True)
        config = {"version": "0.1.0", "name": root.name}
        (dot_dir / "aether.json").write_text(json.dumps(config, indent=2))
        print(f"✓ Inicializado .aether-graph/ en {root}")
        gi = root / ".gitignore"
        try:
            if gi.exists():
                content = gi.read_text(encoding="utf-8")
                if ".aether-graph/" not in content.splitlines():
                    gi.write_text(content + ("" if content.endswith("\n") else "\n") + ".aether-graph/\n", encoding="utf-8")
                    print("✓ .aether-graph/ agregado a .gitignore")
            else:
                gi.write_text(".aether-graph/\n", encoding="utf-8")
                print("✓ .gitignore creado con .aether-graph/")
        except Exception:
            pass

    elif args.command == "reindex":
        data = json.dumps({"path": str(root), "engine": args.engine}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:9210/api/reindex", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode())
                mode = res.get("mode", "full")
                extra = ""
                if mode == "incremental":
                    extra = f" · {res.get('changed_files', 0)} archivos cambiados · {res.get('enriched_files', 0)} archivos con contexto"
                print(f"✓ Reindexado ({args.engine}, modo {mode}){extra}: {res.get('nodes')} nodos, {res.get('links')} conectores.")
        except Exception:
            ast_p = ASTParser()
            graph = ast_p.scan_directory(root)
            print(f"✓ Reindexado AST local completado: {len(graph['nodes'])} nodos, {len(graph['links'])} conectores.")

    elif args.command == "query":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        q = args.query_text.lower()
        matches = [n for n in graph["nodes"] if q in n["name"].lower() or q in n.get("details", "").lower()]
        print(json.dumps({"query": args.query_text, "matches": matches}, indent=2))

    elif args.command == "path":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        found_path = bfs_path(graph, args.start_symbol, args.end_symbol)
        if found_path:
            print(" -> ".join(found_path))
        else:
            print(f"No se encontró ruta entre '{args.start_symbol}' y '{args.end_symbol}'.")

    elif args.command == "explain":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        matches = [n for n in graph["nodes"] if args.symbol.lower() in n["name"].lower()]
        if matches:
            target = matches[0]
            print(f"📌 {target['name']} ({target.get('kind')})")
            print(f"   Detalle: {target.get('details', 'Sin detalle')}")
            print(f"   Conexiones: {target.get('degree', 0)}")
        else:
            print(f"No se encontró el símbolo '{args.symbol}'.")

    elif args.command in ("diff", "pr-impact"):
        graph = ASTParser().scan_directory(root)
        ht = HistoryTracker(root)
        base = args.base if args.command == "pr-impact" else None
        report = analyze_impact(root, graph, base=base)
        try:
            ht.log_event("cli", "pr_impact", f"Análisis de impacto Git en {root.name}", {"path": str(root), "base": base, "risk": report["risk"]})
        except Exception:
            # Analysis must remain read-only and usable on mounted repositories;
            # history persistence is best effort.
            pass
        if getattr(args, "json", False):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif not report["changed_files"]:
            print("✓ No hay archivos modificados en git status.")
        else:
            print(f"🔍 {len(report['changed_files'])} archivos · riesgo {report['risk']['level'].upper()} ({report['risk']['score']}/100)")
            print(f"🎯 {len(report['changed_symbols'])} símbolos realmente modificados")
            for symbol in report["changed_symbols"][:10]:
                print(f"  Δ {symbol['name']} ({symbol['kind']}) · {symbol['file']}:{symbol['line']} · {','.join(symbol['change_types'])}")
            print(f"💥 {len(report['impacted_nodes'])} nodos afectados (directos: {report['risk']['direct']}, transitivos: {report['risk']['transitive']})")
            for item in report["impacted_nodes"][:15]:
                node = item["node"]
                print(f"  • {node.get('name', node.get('id'))} · salto {item['hop']} · {item['confidence']}")
            print(f"⚠ Conflictos potenciales: {len(report['conflicts'])} · {report['conflict_detection']}")

    elif args.command == "benchmark":
        truth = Path(args.ground_truth).resolve() if args.ground_truth else None
        cache = Path(args.cache).resolve() if args.cache else Path.home() / ".aether-graph" / root.name / "benchmark_structural_cache.json"
        result = run_benchmark(root, truth, cache)
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(benchmark_markdown(result), end="")

    elif args.command == "agent-benchmark":
        result = compare_agent_runs(Path(args.treatment), Path(args.baseline))
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "export-md":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        meta = graph.get("metadata", {})
        top_nodes = sorted(graph.get("nodes", []), key=lambda x: x.get("degree", 0), reverse=True)[:10]

        md_lines = [
            f"# 🏗️ Arquitectura del Proyecto: {root.name}",
            f"- **Nodos totales:** {meta.get('total_nodes', len(graph.get('nodes', [])))}",
            f"- **Conexiones totales:** {meta.get('total_links', len(graph.get('links', [])))}",
            "",
            "## 📌 Componentes y Módulos Principales",
        ]
        for n in top_nodes:
            md_lines.append(f"- **{n['name']}** (`{n.get('kind')}`): {n.get('details', '')} [{n.get('degree', 0)} conexiones]")

        out_path = root / args.output
        out_path.write_text("\n".join(md_lines), encoding="utf-8")

        print(f"✓ Mapa de arquitectura exportado exitosamente en: {out_path}")

    elif args.command == "timeline":
        ht = HistoryTracker(root)
        events = ht.get_timeline(args.session_id)
        if not events:
            print("✓ No hay eventos registrados en la línea de tiempo de este proyecto.")
        else:
            print(f"🕒 Línea de tiempo de la sesión ({len(events)} eventos):")
            for ev in events:
                print(f"  [{ev['id']}] {ev['action_type'].upper()} — {ev['summary']}")


    elif args.command == "mcp":
        run_mcp_server(root)

    elif args.command == "serve":
        import os
        import uvicorn
        if args.watch:
            os.environ["AETHER_WATCH"] = "1"
            os.environ["AETHER_WATCH_PATH"] = str(root)
        if args.mcp_token:
            os.environ["AETHER_MCP_TOKEN"] = args.mcp_token
        os.environ["AETHER_MCP_PATH"] = str(root)
        print(f"🚀 Servidor AetherGraph escuchando en http://{args.host}:{args.port} (Hot-Reloading={args.reload}, Watch={args.watch})")
        if args.reload:
            uvicorn.run("aether_graph.api.main:app", host=args.host, port=args.port, reload=True)
        else:
            from .api.main import app
            uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == "gitignore":
        from .api.main import _save_project_config, _load_project_config
        cfg = _save_project_config(root, {"respect_git": args.value == "on"})
        state = "ON (solo archivos versionados)" if cfg["respect_git"] else "OFF (incluye ignorados por .gitignore)"
        print(f"✓ .gitignore por proyecto: {state} para {root}")
        print("  Reindexa para aplicar: aether-graph reindex --path .")

    elif args.command == "hook":
        hook_path = root / ".git" / "hooks" / "post-commit"
        if args.action == "install":
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_script = (
                "#!/bin/sh\n"
                "# AetherGraph: reindexado incremental automatico post-commit (AST + IA local)\n"
                f"( nohup aether-graph reindex --path '{root}' --engine ast_local_llm > /dev/null 2>&1 & ) || true\n"
            )
            hook_path.write_text(hook_script, encoding="utf-8")
            hook_path.chmod(0o755)
            print(f"✓ Hook post-commit instalado en {hook_path}")
            print("  Cada commit lanzará un reindexado incremental en background (solo nodos cambiados).")
        else:
            if hook_path.exists() and "AetherGraph" in hook_path.read_text(encoding="utf-8"):
                hook_path.unlink()
                print(f"✓ Hook post-commit de AetherGraph eliminado")
            else:
                print("✗ No hay hook de AetherGraph instalado en este repositorio.")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
