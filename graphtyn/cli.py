import sys
import json
import argparse
import subprocess
import urllib.request
from pathlib import Path

from . import __version__
from .core.ast_parser import ASTParser
from .core.history import HistoryTracker
from .core.benchmark import benchmark_markdown, run_benchmark
from .core.agent_benchmark import compare_agent_runs
from .core.agent_eval import grade_runs
from .core.external_benchmark import score_graphify
from .core.impact import analyze_impact
from .core.change_analyst import analyze_change, query_intent
from .core.overview_report import render_report
from .core.storage import data_home, project_store_dir
from .core.global_graph import default_registry, list_projects, query_global, register_project, remove_project
from .core.work_memory import attach_learning, reflect, save_result
from .core.verification import verification_plan, verify_python_edits
from .core.agent_installer import install_agent, install_ci
from .core.answer_validation import validate_answer
from .core.ambiguity_review import ambiguity_queue, apply_decisions, save_decision
from .core.change_report import render_change_report
from .mcp_server import context_bundle, run_mcp_server

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
        prog="graphtyn",
        description="Graphtyn — Zero-Token AST Deterministic + Hybrid RAG Graph for AI Coding Agents"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # init
    init_p = subparsers.add_parser("init", help="Inicializa .graphtyn/ en el repositorio")
    init_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # build / reindex
    reindex_p = subparsers.add_parser("reindex", help="Reindexa el código con motor AST + IA")
    reindex_p.add_argument("--path", default=".", help="Ruta del proyecto")
    reindex_p.add_argument("--engine", default="ast_local_llm", choices=["ast_local_llm", "ast_cloud", "ast_pure"], help="Motor de IA")
    reindex_p.add_argument("--mode", default=None, choices=["fast", "balanced", "deep", "verified"], help="Perfil: fast=AST, balanced=IA local incremental, deep=IA completa, verified=deep+verificación")

    # query
    query_p = subparsers.add_parser("query", help="Consulta conceptos o símbolos en el grafo")
    query_p.add_argument("query_text", help="Término, símbolo o concepto a consultar")
    query_p.add_argument("--path", default=".", help="Ruta del proyecto")

    context_p = subparsers.add_parser("context", help="Contexto compacto agrupado para agentes en una sola ronda")
    context_p.add_argument("symbols", nargs="+", help="Hasta 10 símbolos o archivos")
    context_p.add_argument("--depth", type=int, default=1, help="Saltos por símbolo")
    context_p.add_argument("--limit", type=int, default=12, help="Presupuesto global máximo de nodos")
    context_p.add_argument("--path", default=".", help="Ruta del proyecto")

    change_p = subparsers.add_parser("analyze-change", help="Planifica un cambio con evidencia estructural compacta")
    change_p.add_argument("request", help="Issue, requisito o petición de cambio")
    change_p.add_argument("--limit", type=int, default=18, help="Máximo de entidades de evidencia")
    change_p.add_argument("--path", default=".", help="Ruta del proyecto")

    intent_p = subparsers.add_parser("query-intent", help="Contexto de una ronda optimizado por intención")
    intent_p.add_argument("request", help="Pregunta o tarea completa")
    intent_p.add_argument("--intent", default="auto", choices=["auto", "overview", "flow", "bindings", "persistence", "tests", "impact"])
    intent_p.add_argument("--limit", type=int, default=10, help="Máximo de entidades")
    intent_p.add_argument("--path", default=".", help="Ruta del proyecto")

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

    ci_p = subparsers.add_parser("ci-check", help="Check reproducible de impacto para pull requests")
    ci_p.add_argument("--base", default="HEAD~1", help="Rama o revisión base")
    ci_p.add_argument("--max-risk", choices=["low", "medium", "high"], default="high")
    ci_p.add_argument("--output", default=None, help="Resumen Markdown para GitHub/GitLab")
    ci_p.add_argument("--json", action="store_true", help="Salida JSON")
    ci_p.add_argument("--path", default=".", help="Ruta del proyecto")

    verify_p = subparsers.add_parser("verify-edit", help="Verificación diferencial conservadora de cambios Python")
    verify_p.add_argument("--base", default="HEAD", help="Revisión base")
    verify_p.add_argument("--path", default=".", help="Ruta del proyecto")
    verify_p.add_argument("--json", action="store_true", help="Salida JSON")

    validate_p = subparsers.add_parser("validate-answer", help="Audita afirmaciones de una respuesta contra evidencia del grafo")
    validate_p.add_argument("--answer", required=True, help="Texto de la respuesta o @archivo")
    validate_p.add_argument("--path", default=".")

    impact_p = subparsers.add_parser("impact", help="Análisis Git entre base/head con reporte persistente")
    impact_p.add_argument("--base", default="HEAD", help="Revisión o rama base")
    impact_p.add_argument("--head", default=None, help="Revisión head; por defecto HEAD + working tree")
    impact_p.add_argument("--output", default="GRAPHTYN_CHANGE_REPORT.md")
    impact_p.add_argument("--json", action="store_true")
    impact_p.add_argument("--path", default=".")

    review_p = subparsers.add_parser("review", help="Revisa cambios staged o relaciones ambiguas")
    review_p.add_argument("--staged", action="store_true", help="Analiza únicamente el índice staged")
    review_p.add_argument("--ambiguities", action="store_true", help="Lista la cola de relaciones ambiguas")
    review_p.add_argument("--key", default=None, help="Clave de relación ambigua")
    review_p.add_argument("--decision", choices=["accept", "reject", "correct"], default=None)
    review_p.add_argument("--note", default="")
    review_p.add_argument("--path", default=".")

    bench_p = subparsers.add_parser("benchmark", help="Mide rendimiento, validez y recall contra un ground truth")
    bench_p.add_argument("--path", default=".", help="Ruta del proyecto")
    bench_p.add_argument("--ground-truth", default=None, help="Archivo JSON con símbolos esperados")
    bench_p.add_argument("--output", default=None, help="Guarda el resultado JSON")
    bench_p.add_argument("--cache", default=None, help="Ruta opcional del caché estructural")

    agent_bench_p = subparsers.add_parser("agent-benchmark", help="Compara tokens y tiempo de corridas con/sin Graphtyn")
    agent_bench_p.add_argument("--treatment", required=True, help="JSON o lista JSON de corridas con Graphtyn")
    agent_bench_p.add_argument("--baseline", required=True, help="JSON o lista JSON de corridas sin Graphtyn")
    agent_bench_p.add_argument("--output", default=None, help="Guarda el resultado JSON")

    grade_p = subparsers.add_parser("agent-grade", help="Puntúa respuestas contra hechos atómicos auditables")
    grade_p.add_argument("--runs", required=True, help="JSON de respuestas con task_id")
    grade_p.add_argument("--tasks", required=True, help="JSON de tareas y key facts")
    grade_p.add_argument("--output", default=None, help="Guarda las corridas puntuadas")

    external_p = subparsers.add_parser("benchmark-graphify", help="Puntúa un graph.json de Graphify con el mismo ground truth")
    external_p.add_argument("--graph", required=True, help="graphify-out/graph.json")
    external_p.add_argument("--ground-truth", required=True, help="Ground truth Graphtyn")
    external_p.add_argument("--output", default=None, help="Guarda resultado JSON")

    # export-md
    export_p = subparsers.add_parser("export-md", help="Exporta un mapa de arquitectura conciso en Markdown para Agentes de IA")
    export_p.add_argument("--output", default="ARCHITECTURE.md", help="Archivo de salida")
    export_p.add_argument("--path", default=".", help="Ruta del proyecto")

    report_p = subparsers.add_parser("report", help="Genera GRAPHTYN_REPORT.md con propósito, arquitectura, flujos, riesgos y métricas")
    report_p.add_argument("--output", default="GRAPHTYN_REPORT.md", help="Archivo de salida")
    report_p.add_argument("--graphify-report", default=None, help="GRAPH_REPORT.md opcional para comparar tokens")
    report_p.add_argument("--path", default=".", help="Ruta del proyecto")

    global_p = subparsers.add_parser("global", help="Grafo global entre repositorios")
    global_sub = global_p.add_subparsers(dest="global_action", required=True)
    for action in ("add", "remove", "list", "query", "path"):
        item = global_sub.add_parser(action)
        item.add_argument("--registry", default=None, help="Ruta alternativa del registro global")
        if action == "add":
            item.add_argument("--path", default=".")
            item.add_argument("--as", dest="tag", required=True)
        elif action == "remove":
            item.add_argument("tag")
        elif action == "query":
            item.add_argument("query_text")
            item.add_argument("--limit", type=int, default=20)

    memory_p = subparsers.add_parser("memory", help="Memoria de resultados del agente")
    memory_sub = memory_p.add_subparsers(dest="memory_action", required=True)
    save_p = memory_sub.add_parser("save")
    save_p.add_argument("--question", required=True)
    save_p.add_argument("--answer", required=True)
    save_p.add_argument("--nodes", nargs="+", required=True)
    save_p.add_argument("--files", nargs="*", default=[])
    save_p.add_argument("--outcome", choices=["useful", "dead_end", "corrected"], required=True)
    save_p.add_argument("--correction", default=None)
    save_p.add_argument("--path", default=".")
    reflect_p = memory_sub.add_parser("reflect")
    reflect_p.add_argument("--half-life-days", type=float, default=30.0)
    reflect_p.add_argument("--path", default=".")

    install_p = subparsers.add_parser("agent-install", help="Instala instrucciones Graphtyn para asistentes")
    install_p.add_argument("platform", choices=["all", "codex", "opencode", "claude", "cursor", "gemini", "copilot"])
    install_p.add_argument("--path", default=".")

    ci_install_p = subparsers.add_parser("ci-install", help="Instala check de impacto para GitHub o GitLab")
    ci_install_p.add_argument("platform", choices=["github", "gitlab"])
    ci_install_p.add_argument("--max-risk", choices=["low", "medium", "high"], default="high")
    ci_install_p.add_argument("--path", default=".")

    # timeline
    timeline_p = subparsers.add_parser("timeline", help="Muestra la línea de tiempo del historial de acciones de la IA")
    timeline_p.add_argument("--session-id", default=None, help="ID de sesión opcional")
    timeline_p.add_argument("--path", default=".", help="Ruta del proyecto")

    # mcp
    mcp_p = subparsers.add_parser("mcp", help="Inicia el servidor Model Context Protocol (MCP) por stdio")
    mcp_p.add_argument("--path", default=".", help="Ruta del proyecto")
    mcp_p.add_argument("--tool-profile", choices=["intent", "full"], default="intent", help="intent expone una sola tool y reduce tokens; full conserva catálogo legado")

    # serve
    serve_p = subparsers.add_parser("serve", help="Inicia el demonio HTTP local")
    serve_p.add_argument("--reload", action="store_true", help="Habilitar recarga automática en vivo")
    serve_p.add_argument("--watch", action="store_true", help="Reindexa automáticamente proyectos al cambiar archivos")
    serve_p.add_argument("--mcp-token", default=None, help="Activa MCP HTTP con este token Bearer (preferible: GRAPHTYN_MCP_TOKEN)")
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
        dot_dir = root / ".graphtyn"
        dot_dir.mkdir(exist_ok=True)
        config = {"version": "0.5.0", "name": root.name}
        (dot_dir / "graphtyn.json").write_text(json.dumps(config, indent=2))
        print(f"✓ Inicializado .graphtyn/ en {root}")
        gi = root / ".gitignore"
        try:
            if gi.exists():
                content = gi.read_text(encoding="utf-8")
                if ".graphtyn/" not in content.splitlines():
                    gi.write_text(content + ("" if content.endswith("\n") else "\n") + ".graphtyn/\n", encoding="utf-8")
                    print("✓ .graphtyn/ agregado a .gitignore")
            else:
                gi.write_text(".graphtyn/\n", encoding="utf-8")
                print("✓ .gitignore creado con .graphtyn/")
        except Exception:
            pass

    elif args.command == "reindex":
        profiles = {"fast": "ast_pure", "balanced": "ast_local_llm", "deep": "ast_cloud", "verified": "ast_cloud"}
        if args.mode:
            args.engine = profiles[args.mode]
        data = json.dumps({"path": str(root), "engine": args.engine,
                           "full": args.mode in {"deep", "verified"}}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:9210/api/reindex", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode())
                mode = res.get("mode", "full")
                extra = ""
                if mode == "incremental":
                    extra = f" · {res.get('changed_files', 0)} archivos cambiados · {res.get('enriched_files', 0)} archivos con contexto"
                print(f"✓ Reindexado ({args.engine}, modo {args.mode or mode}){extra}: {res.get('nodes')} nodos, {res.get('links')} conectores.")
        except Exception:
            ast_p = ASTParser()
            graph = ast_p.scan_directory(root)
            print(f"✓ Reindexado AST local completado ({args.mode or 'fast'}): {len(graph['nodes'])} nodos, {len(graph['links'])} conectores.")
        if args.mode == "verified":
            print(json.dumps(verify_python_edits(root), ensure_ascii=False))

    elif args.command == "query":
        ast_p = ASTParser()
        graph = ast_p.scan_directory(root)
        q = args.query_text.lower()
        matches = [n for n in graph["nodes"] if q in n["name"].lower() or q in n.get("details", "").lower()]
        print(json.dumps({"query": args.query_text, "matches": matches}, indent=2))

    elif args.command == "query-intent":
        graph = ASTParser().scan_directory(root, respect_git=True)
        result = attach_learning(query_intent(graph, args.request, args.intent, args.limit), root)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "analyze-change":
        graph = ASTParser().scan_directory(root, respect_git=True)
        result = analyze_change(graph, args.request, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "context":
        # CLI context is also the recovery path when an agent daemon has a
        # stale MCP catalog/index, so build from current sources here.
        graph = ASTParser().scan_directory(root, respect_git=True)
        result = context_bundle(graph, args.symbols[:10], args.depth, args.limit)
        print(json.dumps(result, ensure_ascii=False))

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

    elif args.command == "ci-check":
        graph = ASTParser().scan_directory(root, respect_git=True)
        report = analyze_impact(root, graph, base=args.base)
        report["verification_plan"] = verification_plan(report)
        levels = {"low": 0, "medium": 1, "high": 2}
        passed = levels[report["risk"]["level"]] <= levels[args.max_risk]
        result = {"ok": passed, "policy": {"max_risk": args.max_risk}, **report}
        markdown = (f"## Graphtyn PR check\n\n"
                    f"- Result: {'PASS' if passed else 'FAIL'}\n- Risk: **{report['risk']['level']}** ({report['risk']['score']}/100)\n"
                    f"- Changed files: {len(report['changed_files'])}\n- Changed symbols: {len(report['changed_symbols'])}\n"
                    f"- Impacted nodes: {report['impacted_count']}\n- Potential conflicts: {len(report['conflicts'])}\n")
        if args.output:
            Path(args.output).write_text(markdown, encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown, end="" if not args.json else "\n")
        if not passed:
            raise SystemExit(2)

    elif args.command == "verify-edit":
        result = verify_python_edits(root, args.base)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "validate-answer":
        graph = apply_decisions(ASTParser().scan_directory(root, respect_git=True), root)
        answer = Path(args.answer[1:]).read_text(encoding="utf-8") if args.answer.startswith("@") else args.answer
        print(json.dumps(validate_answer(graph, answer), ensure_ascii=False, indent=2))

    elif args.command == "impact":
        if args.head and args.head != "HEAD":
            raise SystemExit("--head distinto de HEAD aún no se aplica al working tree; checkout esa revisión o use HEAD")
        graph = apply_decisions(ASTParser().scan_directory(root, respect_git=True), root)
        result = analyze_impact(root, graph, base=args.base)
        result["verification_plan"] = verification_plan(result)
        output = (root / args.output).resolve()
        try:
            output.relative_to(root)
        except ValueError:
            raise SystemExit("El reporte debe escribirse dentro del proyecto")
        output.write_text(render_change_report(root, result), encoding="utf-8")
        result["report"] = str(output)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"✓ Reporte diferencial: {output}\n")

    elif args.command == "review":
        graph = ASTParser().scan_directory(root, respect_git=True)
        if args.key and args.decision:
            saved = save_decision(root, args.key, args.decision, args.note)
            print(json.dumps({"ok": True, "key": args.key, "review": saved}, ensure_ascii=False, indent=2))
        elif args.ambiguities:
            print(json.dumps(ambiguity_queue(graph, root), ensure_ascii=False, indent=2))
        else:
            result = analyze_impact(root, graph, base=None, staged_only=args.staged)
            result["verification_plan"] = verification_plan(result)
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "benchmark":
        truth = Path(args.ground_truth).resolve() if args.ground_truth else None
        cache = Path(args.cache).resolve() if args.cache else project_store_dir(data_home(), root) / "benchmark_structural_cache.json"
        result = run_benchmark(root, truth, cache)
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(benchmark_markdown(result), end="")

    elif args.command == "agent-benchmark":
        result = compare_agent_runs(Path(args.treatment), Path(args.baseline))
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "agent-grade":
        result = grade_runs(Path(args.runs), Path(args.tasks))
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "benchmark-graphify":
        result = score_graphify(Path(args.graph), Path(args.ground_truth))
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

    elif args.command == "report":
        graph = ASTParser().scan_directory(root, respect_git=True)
        comparison = Path(args.graphify_report).resolve() if args.graphify_report else None
        report, metrics = render_report(root, graph, comparison)
        out_path = (root / args.output).resolve()
        try:
            out_path.relative_to(root)
        except ValueError:
            raise SystemExit("El reporte debe escribirse dentro del proyecto")
        out_path.write_text(report, encoding="utf-8")
        print(f"✓ Reporte Graphtyn generado en: {out_path}")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))

    elif args.command == "global":
        registry = Path(args.registry).expanduser().resolve() if args.registry else default_registry()
        if args.global_action == "add":
            project = Path(args.path).resolve()
            data = register_project(ASTParser().scan_directory(project, respect_git=True), project, args.tag, registry)
            print(json.dumps({"ok": True, "tag": args.tag, "registry": str(registry), "project": data["projects"][args.tag]}, ensure_ascii=False, indent=2))
        elif args.global_action == "remove":
            remove_project(args.tag, registry)
            print(json.dumps({"ok": True, "removed": args.tag, "registry": str(registry)}))
        elif args.global_action == "list":
            print(json.dumps({"registry": str(registry), "projects": list_projects(registry)}, ensure_ascii=False, indent=2))
        elif args.global_action == "path":
            print(str(registry))
        else:
            print(json.dumps(query_global(args.query_text, registry, args.limit), ensure_ascii=False, indent=2))

    elif args.command == "memory":
        if args.memory_action == "save":
            output = save_result(root, args.question, args.answer, args.nodes, args.outcome, args.files, args.correction)
            print(json.dumps({"ok": True, "saved": str(output)}, ensure_ascii=False))
        else:
            print(json.dumps(reflect(root, args.half_life_days), ensure_ascii=False, indent=2))

    elif args.command == "agent-install":
        files = install_agent(root, args.platform)
        print(json.dumps({"ok": True, "platform": args.platform, "files": files}, ensure_ascii=False, indent=2))

    elif args.command == "ci-install":
        output = install_ci(root, args.platform, args.max_risk)
        print(json.dumps({"ok": True, "platform": args.platform, "file": str(output)}, ensure_ascii=False, indent=2))

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
        run_mcp_server(root, args.tool_profile)

    elif args.command == "serve":
        import os
        import uvicorn
        if args.watch:
            os.environ["GRAPHTYN_WATCH"] = "1"
            os.environ["GRAPHTYN_WATCH_PATH"] = str(root)
        if args.mcp_token:
            os.environ["GRAPHTYN_MCP_TOKEN"] = args.mcp_token
        os.environ["GRAPHTYN_MCP_PATH"] = str(root)
        print(f"🚀 Servidor Graphtyn escuchando en http://{args.host}:{args.port} (Hot-Reloading={args.reload}, Watch={args.watch})")
        if args.reload:
            uvicorn.run("graphtyn.api.main:app", host=args.host, port=args.port, reload=True)
        else:
            from .api.main import app
            uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == "gitignore":
        from .api.main import _save_project_config, _load_project_config
        cfg = _save_project_config(root, {"respect_git": args.value == "on"})
        state = "ON (solo archivos versionados)" if cfg["respect_git"] else "OFF (incluye ignorados por .gitignore)"
        print(f"✓ .gitignore por proyecto: {state} para {root}")
        print("  Reindexa para aplicar: graphtyn reindex --path .")

    elif args.command == "hook":
        hook_path = root / ".git" / "hooks" / "post-commit"
        if args.action == "install":
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_script = (
                "#!/bin/sh\n"
                "# Graphtyn: reindexado incremental automatico post-commit (AST + IA local)\n"
                f"( nohup graphtyn reindex --path '{root}' --engine ast_local_llm > /dev/null 2>&1 & ) || true\n"
            )
            hook_path.write_text(hook_script, encoding="utf-8")
            hook_path.chmod(0o755)
            print(f"✓ Hook post-commit instalado en {hook_path}")
            print("  Cada commit lanzará un reindexado incremental en background (solo nodos cambiados).")
        else:
            if hook_path.exists() and "Graphtyn" in hook_path.read_text(encoding="utf-8"):
                hook_path.unlink()
                print(f"✓ Hook post-commit de Graphtyn eliminado")
            else:
                print("✗ No hay hook de Graphtyn instalado en este repositorio.")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
