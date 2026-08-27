import os
import sqlite3
import sys
import json
import argparse
import subprocess
import urllib.request
import time
from pathlib import Path

from . import __version__
from .core.ast_parser import ASTParser
from .core.history import HistoryTracker
from .core.benchmark import benchmark_markdown, run_benchmark
from .core.benchmark_protocol import paired_statistics, validate_protocol
from .core.agent_benchmark import compare_agent_runs
from .core.agent_eval import grade_runs
from .core.external_benchmark import score_graphify
from .core.impact import analyze_impact
from .core.change_analyst import analyze_change, query_intent
from .core.overview_report import render_report
from .core.storage import data_home, project_store_dir
from .core.type_evidence import provider_status
from .core.global_graph import default_registry, list_projects, query_global, register_project, remove_project
from .core.work_memory import attach_learning, reflect, save_result
from .core.shared_memory import SharedMemoryStore
from .core.memory_benchmark import build_stability_dataset, run_memory_benchmark
from .core.history_import import (discover_histories, import_histories, ProjectIdentityRegistry,
                                  configured_sources, save_source, import_history_archive,
                                  delete_source, test_source)
from .core.verification import verification_plan, verify_python_edits
from .core.agent_installer import install_agent, install_ci
from .core.answer_validation import validate_answer
from .core.ambiguity_review import ambiguity_queue, apply_decisions, save_decision
from .core.change_report import render_change_report
from .mcp_server import context_bundle, run_mcp_server
from .core.console import configure_utf8_stdio

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
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="graphtyn",
        description="Graphtyn — Zero-Token AST Deterministic + Hybrid RAG Graph for AI Coding Agents"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    setup_p = subparsers.add_parser("setup", help="Detecta y configura Graphtyn sin editar código")
    setup_p.add_argument("--path", default=".")
    setup_p.add_argument("--agent", action="append", default=[])
    setup_p.add_argument("--apply", action="store_true")
    setup_p.add_argument("--no-token", action="store_true")
    setup_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default="intent")
    onboard_p = subparsers.add_parser("onboard", help="Configura agentes, índice, MCP y dashboard en una sola orden")
    onboard_p.add_argument("--path", default=".")
    onboard_p.add_argument("--agent", action="append", default=[])
    onboard_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default="full")
    onboard_p.add_argument("--start-dashboard", action="store_true")
    onboard_p.add_argument("--watch", action="store_true")
    onboard_p.add_argument("--no-token", action="store_true")
    adapter_p = subparsers.add_parser("adapter", help="Gestiona adaptadores de historiales")
    adapter_sub = adapter_p.add_subparsers(dest="adapter_action", required=True)
    adapter_sub.add_parser("list")
    for action in ("install", "validate"):
        item = adapter_sub.add_parser(action); item.add_argument("manifest")
    remove_adapter_p = adapter_sub.add_parser("remove"); remove_adapter_p.add_argument("name")
    service_p = subparsers.add_parser("service", help="Instala y administra el dashboard persistente")
    service_sub = service_p.add_subparsers(dest="service_action", required=True)
    service_install = service_sub.add_parser("install")
    service_install.add_argument("--kind", choices=["auto", "systemd", "windows", "compose"], default="auto")
    service_install.add_argument("--output", default=None); service_install.add_argument("--interval", type=float, default=10)
    service_install.add_argument("--path", default=".")
    service_install.add_argument("--enable", action="store_true", help="Activa el servicio nativo ahora y al iniciar sesión")
    service_install.add_argument("--watch", action="store_true", help="Activa reindexación automática (puede usar CPU en repositorios grandes)")
    for service_action in ("start", "stop", "restart", "status", "uninstall"):
        service_command = service_sub.add_parser(service_action)
        service_command.add_argument("--kind", choices=["auto", "systemd", "windows"], default="auto")
        service_command.add_argument("--unit", default=None, help="Unidad systemd o nombre de tarea de Windows")
    backup_p = subparsers.add_parser("backup", help="Crea o verifica backup de memoria")
    backup_p.add_argument("--output", required=True); backup_p.add_argument("--path", default=".")
    verify_backup_p = subparsers.add_parser("backup-verify"); verify_backup_p.add_argument("backup")
    restore_p = subparsers.add_parser("restore", help="Previsualiza o restaura un backup")
    restore_p.add_argument("backup"); restore_p.add_argument("--apply", action="store_true"); restore_p.add_argument("--path", default=".")
    token_p = subparsers.add_parser("token", help="Rota tokens HTTP por rol/proyecto")
    token_sub = token_p.add_subparsers(dest="token_action", required=True)
    token_rotate = token_sub.add_parser("rotate"); token_rotate.add_argument("--role", choices=["reader", "writer", "admin"], default="admin")
    token_rotate.add_argument("--project", action="append", default=[]); token_rotate.add_argument("--file", default=None)
    token_rotate.add_argument("--keep-existing", action="store_true")
    token_rotate.add_argument("--show-token", action="store_true", help="Muestra el secreto una sola vez (evite logs)")

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
    intent_p.add_argument("--evidence-mode", default="auto", choices=["auto", "compact", "balanced", "precision"], help="Expansión dirigida de fuente")
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

    suite_p = subparsers.add_parser("benchmark-suite", help="Valida una matriz de 30–50 tareas y calcula estadística pareada")
    suite_p.add_argument("--protocol", required=True, help="Manifiesto JSON de la matriz")
    suite_p.add_argument("--results", default=None, help="Resultados JSON opcionales: task_id, variant, tokens, quality")
    suite_p.add_argument("--control", default="no_graph", choices=["no_graph", "competitor"])
    suite_p.add_argument("--output", default=None)

    types_p = subparsers.add_parser("type-status", help="Detecta analizadores de tipos opcionales sin ejecutarlos")
    types_p.add_argument("--path", default=".")

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
    session_p = memory_sub.add_parser("session-start", help="Abre una sesión multiagente compartida")
    session_p.add_argument("--agent", required=True)
    session_p.add_argument("--task", required=True)
    session_p.add_argument("--branch", default=None)
    session_p.add_argument("--base-commit", default=None)
    session_p.add_argument("--capture", action="store_true")
    session_p.add_argument("--path", default=".")
    end_p = memory_sub.add_parser("session-end", help="Cierra una sesión y guarda su handoff")
    end_p.add_argument("--session", required=True)
    end_p.add_argument("--summary", default=None)
    end_p.add_argument("--observed-commit", default=None)
    end_p.add_argument("--path", default=".")
    checkpoint_p = memory_sub.add_parser("checkpoint", help="Registra una decisión o resultado atribuido")
    checkpoint_p.add_argument("--session", required=True)
    checkpoint_p.add_argument("--kind", choices=["episodic", "decision", "fact", "procedure", "outcome", "correction", "handoff"], required=True)
    checkpoint_p.add_argument("--title", required=True)
    checkpoint_p.add_argument("--content", required=True)
    checkpoint_p.add_argument("--scope", choices=["private", "project", "team"], default="project")
    checkpoint_p.add_argument("--files", nargs="*", default=[])
    checkpoint_p.add_argument("--nodes", nargs="*", default=[])
    checkpoint_p.add_argument("--tests", nargs="*", default=[])
    checkpoint_p.add_argument("--path", default=".")
    append_p = memory_sub.add_parser("append", help="Captura un mensaje/evento saneado en una sesión opt-in")
    append_p.add_argument("--session", required=True)
    append_p.add_argument("--role", choices=["user", "assistant", "tool"], required=True)
    append_p.add_argument("--content", required=True)
    append_p.add_argument("--event-type", default=None)
    append_p.add_argument("--path", default=".")
    ingest_p = memory_sub.add_parser("ingest-turn", help="Hook idempotente: captura un turno y genera embeddings de memorias útiles")
    ingest_p.add_argument("--agent", required=True)
    ingest_p.add_argument("--external-session", required=True)
    ingest_p.add_argument("--task", required=True)
    ingest_p.add_argument("--role", choices=["user", "assistant", "tool"], required=True)
    ingest_p.add_argument("--content", required=True)
    ingest_p.add_argument("--branch", default=None)
    ingest_p.add_argument("--event-type", default=None)
    ingest_p.add_argument("--consent", action="store_true", help="Autoriza captura saneada de esta sesión")
    ingest_p.add_argument("--no-compact", action="store_true")
    ingest_p.add_argument("--close", action="store_true")
    ingest_p.add_argument("--provider", choices=["auto", "deterministic", "ollama", "api"], default="auto")
    ingest_p.add_argument("--path", default=".")
    search_p = memory_sub.add_parser("search", help="Busca recuerdos de cualquier sesión del proyecto")
    search_p.add_argument("query")
    search_p.add_argument("--agent", default=None, help="Identidad solicitante; necesaria para memoria private")
    search_p.add_argument("--limit", type=int, default=8)
    search_p.add_argument("--branch", default=None)
    search_p.add_argument("--path", default=".")
    context_p = memory_sub.add_parser("context", help="Genera contexto semántico acotado para otro agente")
    context_p.add_argument("query")
    context_p.add_argument("--agent", default=None)
    context_p.add_argument("--branch", default=None)
    context_p.add_argument("--limit", type=int, default=8)
    context_p.add_argument("--token-budget", type=int, default=1800)
    context_p.add_argument("--neighbor-limit", type=int, default=12)
    context_p.add_argument("--no-graph", action="store_true")
    context_p.add_argument("--path", default=".")
    status_p = memory_sub.add_parser("status", help="Estado del almacén compartido")
    status_p.add_argument("--path", default=".")
    migrate_p = memory_sub.add_parser("migrate", help="Importa historial y outcomes v1 sin duplicar")
    migrate_p.add_argument("--path", default=".")
    reindex_p = memory_sub.add_parser("reindex", help="Actualiza sólo embeddings de memorias modificadas")
    reindex_p.add_argument("--path", default=".")
    evidence_p = memory_sub.add_parser("ingest-evidence", help="Ingiere benchmarks como evidencia verificada y ligada a Git")
    evidence_p.add_argument("--files", nargs="*", default=None,
                            help="Archivos relativos; por defecto BENCHMARKS.md, reportes y summaries/comparisons JSON")
    evidence_p.add_argument("--path", default=".")
    correct_p = memory_sub.add_parser("correct", help="Corrige una memoria conservando procedencia")
    correct_p.add_argument("--memory", required=True)
    correct_p.add_argument("--session", required=True)
    correct_p.add_argument("--title", required=True)
    correct_p.add_argument("--content", required=True)
    correct_p.add_argument("--path", default=".")
    forget_p = memory_sub.add_parser("forget", help="Invalida o elimina físicamente una memoria propia")
    forget_p.add_argument("--memory", required=True)
    forget_p.add_argument("--agent", required=True)
    forget_p.add_argument("--physical", action="store_true")
    forget_p.add_argument("--path", default=".")
    doctor_p = memory_sub.add_parser("doctor", help="Verifica SQLite, FTS, vectores y referencias")
    doctor_p.add_argument("--path", default=".")
    memory_bench_p = memory_sub.add_parser("benchmark", help="Evalúa recall, MRR, atribución, tokens y latencia")
    memory_bench_p.add_argument("--dataset", default="benchmarks/shared_memory_v1.json")
    memory_bench_p.add_argument("--suite", choices=["dataset", "stability"], default="dataset")
    memory_bench_p.add_argument("--output", default=None)
    memory_bench_p.add_argument("--path", default=".")
    compact_p = memory_sub.add_parser("compact", help="Extrae memorias propuestas desde una sesión capturada")
    compact_p.add_argument("--session", required=True)
    compact_p.add_argument("--provider", choices=["auto", "deterministic", "ollama", "api"], default="auto")
    compact_p.add_argument("--path", default=".")
    brain_p = memory_sub.add_parser("brain-init", help="Crea un cerebro (espacio de memoria de agentes)")
    brain_p.add_argument("--brain-path", required=True, help="Carpeta del cerebro (se crea si no existe)")
    brain_p.add_argument("--name", required=True, help="Nombre visible en el dashboard")
    brain_p.add_argument("--agents-dir", default=None,
                         help="Directorio con workspaces de agentes (subcarpetas con IDENTITY.md/SOUL.md) a descubrir en bloque")
    brain_p.add_argument("--agent-workspace", action="append", default=[],
                         help="Workspace de agente individual a vincular (repetible)")
    brain_p.add_argument("--register", action="store_true", help="Registrar el cerebro en el dashboard")
    alias_imp_p = memory_sub.add_parser("alias-import", help="Importa alias de agentes en bloque")
    alias_imp_p.add_argument("--json-file", default=None, help='JSON {"alias":"canonico"}')
    alias_imp_p.add_argument("--pairs", default=None, help="Formato compacto: alias=identidad,otro=identidad")
    alias_imp_p.add_argument("--global-config", action="store_true",
                             help="Escribir también en $GRAPHTYN_HOME/agent-aliases.json (afecta a todos los espacios)")
    alias_imp_p.add_argument("--path", default=".")
    stores_p = memory_sub.add_parser("stores", help="Lista los almacenes de memoria y limpia residuos de pruebas")
    stores_p.add_argument("--home", default=None, help="Raíz de estado (default $GRAPHTYN_HOME o ~/.graphtyn)")
    stores_p.add_argument("--clean-test", action="store_true", help="Elimina almacenes generados por tests")
    bootstrap_p = memory_sub.add_parser("bootstrap", help="Descubre o importa conversaciones anteriores a Graphtyn")
    bootstrap_p.add_argument("--provider", default=None, help="Proveedor/adaptador (admite nombres personalizados)")
    bootstrap_p.add_argument("--source", action="append", default=[], help="Archivo/directorio histórico (repetible)")
    bootstrap_p.add_argument("--apply", action="store_true", help="Importar; sin esta opción sólo previsualiza")
    bootstrap_p.add_argument("--consent", action="store_true", help="Autoriza procesar los historiales seleccionados")
    bootstrap_p.add_argument("--provider-model", choices=["deterministic", "auto", "ollama", "api"], default="deterministic")
    bootstrap_p.add_argument("--output", default=None, help="Guardar plan/reporte JSON")
    bootstrap_p.add_argument("--archive-all", action="store_true",
                             help="Importar toda sesión en un cerebro histórico separado")
    bootstrap_p.add_argument("--path", default=".")
    projects_p = memory_sub.add_parser("projects", help="Lista identidades globales de proyectos y alias")
    projects_p.add_argument("--path", default=".")
    projects_p.add_argument("--alias", action="append", default=[],
                            help="Alias local o ruta remota equivalente al proyecto (repetible)")
    sync_p = memory_sub.add_parser("sync", help="Importa incrementalmente historiales nuevos o modificados")
    sync_p.add_argument("--provider", default=None, help="Proveedor/adaptador")
    sync_p.add_argument("--source", action="append", default=[])
    sync_p.add_argument("--consent", action="store_true", required=True)
    sync_p.add_argument("--provider-model", choices=["deterministic", "auto", "ollama", "api"], default="deterministic")
    sync_p.add_argument("--watch", action="store_true", help="Continuar observando cambios")
    sync_p.add_argument("--interval", type=float, default=5.0)
    sync_p.add_argument("--path", default=".")
    export_p = memory_sub.add_parser("export", help="Exporta memoria saneada sin vectores")
    export_p.add_argument("--output", required=True)
    export_p.add_argument("--include-messages", action="store_true")
    export_p.add_argument("--path", default=".")
    retention_p = memory_sub.add_parser("retention", help="Previsualiza o aplica retención de memorias de baja confianza")
    retention_p.add_argument("--days", type=int, default=90)
    retention_p.add_argument("--statuses", nargs="*", default=None)
    retention_p.add_argument("--apply", action="store_true")
    retention_p.add_argument("--path", default=".")
    sources_p = memory_sub.add_parser("sources", help="Configura historiales en host, Docker o VPS")
    sources_p.add_argument("action", choices=["list", "add", "remove", "test"])
    sources_p.add_argument("--provider", default=None)
    sources_p.add_argument("--source", default=None,
                           help="Ruta local, ssh://, docker:// o ssh+docker://host:contenedor/ruta")
    sources_p.add_argument("--label", default="")

    install_p = subparsers.add_parser("agent-install", help="Instala instrucciones Graphtyn para asistentes")
    install_p.add_argument("platform", choices=["all", "codex", "opencode", "openclaw", "hermes", "claude", "cursor", "gemini", "antigravity", "copilot"])
    install_p.add_argument("--path", default=".")
    install_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default="intent")

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
    mcp_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default="intent", help="intent expone consulta+contexto; memory añade escritura compartida; full conserva todo")

    # serve
    serve_p = subparsers.add_parser("serve", help="Inicia el demonio HTTP local")
    serve_p.add_argument("--reload", action="store_true", help="Habilitar recarga automática en vivo")
    serve_p.add_argument("--watch", action="store_true", help="Reindexa automáticamente proyectos al cambiar archivos")
    serve_p.add_argument("--mcp-token", default=None, help="Activa MCP HTTP con este token Bearer (preferible: GRAPHTYN_MCP_TOKEN)")
    serve_p.add_argument("--host", default="127.0.0.1", help="Host (predeterminado: sólo acceso local)")
    serve_p.add_argument("--port", type=int, default=9210, help="Puerto")
    serve_p.add_argument("--path", default=".", help="Ruta del proyecto")
    serve_p.add_argument("--ssl-certfile", default=None)
    serve_p.add_argument("--ssl-keyfile", default=None)

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

    if args.command == "setup":
        from .core.deployment import detect_environment, apply_setup
        plan = detect_environment(root)
        if args.apply:
            from .core.agent_installer import TARGETS
            agents = args.agent or sorted({row["provider"] for row in plan["sources"]
                                            if row["provider"] in TARGETS})
            print(json.dumps(apply_setup(root, agents=agents, sources=plan["sources"],
                                         create_token=not args.no_token,
                                         tool_profile=args.tool_profile), ensure_ascii=False, indent=2))
        else:
            print(json.dumps({**plan, "dry_run": True, "message": "Repita con --apply"}, ensure_ascii=False, indent=2))
    elif args.command == "onboard":
        from .core.deployment import (DASHBOARD_URL, apply_setup, build_local_index,
            default_service_output, detect_environment, initialize_project,
            manage_user_service, native_service_kind, service_artifact)
        plan = detect_environment(root)
        from .core.agent_installer import TARGETS
        agents = args.agent or sorted({row["provider"] for row in plan["sources"]
                                       if row["provider"] in TARGETS})
        initialized = initialize_project(root)
        configured = apply_setup(root, agents=agents, sources=plan["sources"],
                                 create_token=not args.no_token, tool_profile=args.tool_profile)
        indexed = build_local_index(root)
        service = None
        if args.start_dashboard:
            kind = native_service_kind()
            artifact = service_artifact(root, kind=kind, output=default_service_output(kind),
                                        watch=args.watch)
            service = manage_user_service("enable", kind=kind,
                unit=(artifact.name if kind == "systemd" else None), artifact=artifact)
        result = {"ok": bool(indexed["nodes"]) and (service is None or service["ok"]),
                  "project": str(root), "agents": agents, "tool_profile": args.tool_profile,
                  "initialized": initialized, "setup": configured,
                  "index": {key: indexed[key] for key in ("ok", "nodes", "links", "index")},
                  "dashboard": DASHBOARD_URL, "service": service}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            raise SystemExit(1)
    elif args.command == "adapter":
        from .core.adapters import list_adapters, install_adapter, remove_adapter, validate_manifest
        if args.adapter_action == "list": result = {"ok": True, "adapters": list_adapters()}
        elif args.adapter_action == "install": result = {"ok": True, "adapter": install_adapter(args.manifest)}
        elif args.adapter_action == "validate":
            result = {"ok": True, "adapter": validate_manifest(json.loads(Path(args.manifest).read_text(encoding="utf-8")))}
        else: result = {"ok": True, "removed": remove_adapter(args.name)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "service":
        from .core.deployment import default_service_output, manage_user_service, native_service_kind, service_artifact
        if args.service_action == "install":
            resolved_kind = native_service_kind() if args.kind == "auto" else args.kind
            output_path = Path(args.output).expanduser() if args.output else default_service_output(resolved_kind)
            output = service_artifact(root, kind=resolved_kind, output=output_path, interval=args.interval,
                                      watch=args.watch)
            result = {"ok": True, "kind": resolved_kind, "output": str(output),
                      "dashboard": "http://127.0.0.1:9210"}
            if args.enable:
                if resolved_kind == "compose":
                    parser.error("--enable no aplica a Compose; use docker compose up -d")
                result["activation"] = manage_user_service("enable", kind=resolved_kind,
                    unit=(output.name if resolved_kind == "systemd" else None), artifact=output)
                result["ok"] = result["activation"]["ok"]
            print(json.dumps(result, indent=2))
            if not result["ok"]: raise SystemExit(1)
        else:
            result = manage_user_service(args.service_action, unit=args.unit, kind=args.kind)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result["ok"]: raise SystemExit(1)
    elif args.command == "token":
        from .core.deployment import rotate_token
        result = rotate_token(role=args.role, projects=args.project,
            path=Path(args.file).expanduser() if args.file else None,
            keep_existing=args.keep_existing)
        if not args.show_token: result["token"] = "[stored; use --show-token only in a private terminal]"
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command in {"backup", "backup-verify", "restore"}:
        from .core.memory_admin import backup_memory, verify_backup, restore_memory
        if args.command == "backup": result = backup_memory(root, Path(args.output))
        elif args.command == "backup-verify": result = verify_backup(Path(args.backup))
        else: result = restore_memory(root, Path(args.backup), apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "init":
        from .core.deployment import initialize_project
        initialized = initialize_project(root)
        print(f"✓ Inicializado .graphtyn/ en {root}")
        if initialized["gitignore_added"]:
            print("✓ .graphtyn/ agregado a .gitignore")

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
            from .core.deployment import build_local_index
            indexed = build_local_index(root)
            print(f"✓ Reindexado AST local completado ({args.mode or 'fast'}): {indexed['nodes']} nodos, {indexed['links']} conectores.")
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
        from .core.source_evidence import attach_source_evidence
        result = query_intent(graph, args.request, args.intent, args.limit)
        result = attach_source_evidence(root, result, args.request, args.evidence_mode)
        result = attach_learning(result, root)
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

    elif args.command == "benchmark-suite":
        protocol = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
        result = {"protocol": validate_protocol(protocol)}
        if args.results:
            rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("runs", [])
            result["paired_statistics"] = paired_statistics(rows, control=args.control)
        if args.output:
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "type-status":
        print(json.dumps({"path": str(root), "providers": provider_status(root),
                          "sidecar": str(root / ".graphtyn/type-evidence.json")},
                         ensure_ascii=False, indent=2))

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
        if args.memory_action == "brain-init":
            brain_dir = Path(args.brain_path).expanduser().resolve()
            brain_dir.mkdir(parents=True, exist_ok=True)
            brain = SharedMemoryStore(brain_dir)
            discovered, errors = [], []
            if args.agents_dir:
                scan = brain.discover_agents(args.agents_dir)
                discovered.extend(scan["discovered"]); errors.extend(scan["errors"])
            for ws in args.agent_workspace:
                try:
                    discovered.append(brain.ingest_agent_profile(ws))
                except ValueError as exc:
                    errors.append({"workspace": ws, "error": str(exc)})
            registered_to = None
            if args.register:
                home = Path(os.environ.get("GRAPHTYN_HOME") or Path.home() / ".graphtyn")
                reg_file = home / "registered_projects.json"
                projects = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.is_file() else []
                if not any(p.get("path") == str(brain_dir) for p in projects):
                    projects.append({"id": args.name, "name": args.name,
                                     "path": str(brain_dir), "mode": "single_folder"})
                    reg_file.parent.mkdir(parents=True, exist_ok=True)
                    reg_file.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
                registered_to = str(reg_file)
            result = {"ok": True, "brain": args.name, "path": str(brain_dir),
                      "agents": [{"agent_id": d["agent_id"], "name": d["name"]} for d in discovered],
                      "errors": errors, "registered_to": registered_to}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.memory_action == "alias-import":
            memory = SharedMemoryStore(Path(args.path).expanduser().resolve())
            pairs: dict[str, str] = {}
            if args.json_file:
                raw = Path(args.json_file).expanduser().resolve().read_text(encoding="utf-8")
                pairs.update({str(k): str(v) for k, v in json.loads(raw).items()})
            if args.pairs:
                for chunk in args.pairs.split(","):
                    if "=" in chunk:
                        alias, canonical = chunk.split("=", 1)
                        pairs[alias.strip()] = canonical.strip()
            applied = [memory.set_alias(a, c) | {"alias": a} for a, c in pairs.items()]
            config_written = None
            if args.global_config:
                from .core.shared_memory import config_aliases_file, load_config_aliases
                merged = {**load_config_aliases(), **{a.casefold(): c.casefold() for a, c in pairs.items()}}
                cfg = config_aliases_file()
                cfg.parent.mkdir(parents=True, exist_ok=True)
                cfg.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
                config_written = str(cfg)
            print(json.dumps({"ok": True, "aliases": len(applied), "config_written": config_written},
                             ensure_ascii=False, indent=2))
        elif args.memory_action == "stores":
            home = Path(args.home or os.environ.get("GRAPHTYN_HOME") or Path.home() / ".graphtyn").resolve()
            found = []
            for child in sorted(home.iterdir()) if home.is_dir() else []:
                db = child / "memory-v2.db"
                if not db.is_file():
                    continue
                is_test = child.name.startswith(("test_", "test-"))
                info = {"store": child.name, "path": str(child), "test_artifact": is_test}
                try:
                    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                    info["memories"] = conn.execute(
                        "SELECT COUNT(*) FROM memories WHERE status!='deleted'").fetchone()[0]
                    info["sessions"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                    conn.close()
                except sqlite3.Error as exc:
                    info["error"] = str(exc)
                found.append(info)
            removed = []
            if args.clean_test:
                import shutil
                for item in found:
                    if item["test_artifact"]:
                        shutil.rmtree(item["path"], ignore_errors=True)
                        removed.append(item["path"])
                found = [f for f in found if f["path"] not in removed]
            print(json.dumps({"ok": True, "home": str(home), "stores": found,
                              "removed_test_stores": removed}, ensure_ascii=False, indent=2))
        elif args.memory_action == "bootstrap":
            discovered = discover_histories(args.provider, args.source or None)
            if args.apply:
                importer = import_history_archive if args.archive_all else import_histories
                result = importer(Path(args.path), discovered["sessions"], consent=args.consent,
                                  provider=args.provider_model)
                result["discovery"] = {"count": discovered["count"], "errors": discovered["errors"]}
            else:
                ProjectIdentityRegistry().register(Path(args.path))
                result = {**discovered, "dry_run": True,
                          "message": "Revise el plan y repita con --apply --consent"}
            if args.output:
                output = Path(args.output).expanduser().resolve()
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                result["output"] = str(output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.memory_action == "projects":
            current = ProjectIdentityRegistry().register(Path(args.path), aliases=args.alias)
            print(json.dumps({"ok": True, "current": current,
                              "projects": ProjectIdentityRegistry().list()}, ensure_ascii=False, indent=2))
        elif args.memory_action == "sync":
            def sync_once():
                discovered = discover_histories(args.provider, args.source or None)
                result = import_histories(Path(args.path), discovered["sessions"], consent=args.consent,
                                          provider=args.provider_model)
                result["discovered"] = discovered["count"]
                return result
            if not args.watch:
                print(json.dumps(sync_once(), ensure_ascii=False, indent=2))
            else:
                try:
                    while True:
                        print(json.dumps(sync_once(), ensure_ascii=False), flush=True)
                        time.sleep(max(1.0, args.interval))
                except KeyboardInterrupt:
                    pass
        elif args.memory_action == "sources":
            if args.action == "add":
                if not args.provider or not args.source:
                    raise SystemExit("sources add requiere --provider y --source")
                saved = save_source(args.provider, args.source, label=args.label)
                print(json.dumps({"ok": True, "saved": saved}, ensure_ascii=False, indent=2))
            elif args.action == "remove":
                if not args.provider or not args.source: raise SystemExit("sources remove requiere --provider y --source")
                print(json.dumps({"ok": True, "removed": delete_source(args.provider, args.source)}, indent=2))
            elif args.action == "test":
                if not args.provider or not args.source: raise SystemExit("sources test requiere --provider y --source")
                print(json.dumps(test_source(args.provider, args.source), ensure_ascii=False, indent=2))
            else:
                print(json.dumps({"ok": True, "sources": configured_sources()}, ensure_ascii=False, indent=2))
        elif args.memory_action == "save":
            output = save_result(root, args.question, args.answer, args.nodes, args.outcome, args.files, args.correction)
            print(json.dumps({"ok": True, "saved": str(output)}, ensure_ascii=False))
        elif args.memory_action == "reflect":
            print(json.dumps(reflect(root, args.half_life_days), ensure_ascii=False, indent=2))
        else:
            memory = SharedMemoryStore(root)
            if args.memory_action == "session-start":
                result = memory.start_session(args.agent, args.task, branch=args.branch,
                                              base_commit=args.base_commit, capture_enabled=args.capture)
            elif args.memory_action == "session-end":
                result = memory.end_session(args.session, args.summary, args.observed_commit)
            elif args.memory_action == "checkpoint":
                result = memory.checkpoint(args.session, args.kind, args.title, args.content,
                                           scope=args.scope, files=args.files, node_ids=args.nodes,
                                           tests=args.tests)
            elif args.memory_action == "append":
                result = memory.append_message(args.session, args.role, args.content,
                                               event_type=args.event_type)
            elif args.memory_action == "ingest-turn":
                result = memory.ingest_turn(args.agent, args.external_session, args.task,
                    [{"role": args.role, "content": args.content, "event_type": args.event_type}],
                    consent=args.consent, branch=args.branch, compact=not args.no_compact,
                    close=args.close, provider=args.provider)
            elif args.memory_action == "search":
                result = {"query": args.query, "results": memory.search(
                    args.query, requester_agent=args.agent, limit=args.limit, branch=args.branch)}
            elif args.memory_action == "context":
                result = memory.context(args.query, requester_agent=args.agent, limit=args.limit,
                                        token_budget=args.token_budget, branch=args.branch,
                                        include_graph=not args.no_graph, neighbor_limit=args.neighbor_limit)
            elif args.memory_action == "status":
                result = memory.status()
            elif args.memory_action == "migrate":
                result = memory.migrate_legacy()
            elif args.memory_action == "reindex":
                result = memory.reindex_embeddings()
            elif args.memory_action == "ingest-evidence":
                result = memory.ingest_benchmark_evidence(args.files)
            elif args.memory_action == "correct":
                result = memory.correct(args.memory, args.session, args.title, args.content)
            elif args.memory_action == "forget":
                result = memory.forget(args.memory, requester_agent=args.agent, physical=args.physical)
            elif args.memory_action == "doctor":
                result = memory.doctor()
            elif args.memory_action == "export":
                result = memory.export_snapshot(include_messages=args.include_messages)
                output = Path(args.output).expanduser().resolve()
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                result = {"ok": True, "output": str(output), "memories": len(result["memories"]),
                          "sessions": len(result["sessions"])}
            elif args.memory_action == "retention":
                result = memory.apply_retention(args.days, statuses=args.statuses, dry_run=not args.apply)
            elif args.memory_action == "benchmark":
                dataset = build_stability_dataset() if args.suite == "stability" else json.loads(
                    Path(args.dataset).expanduser().resolve().read_text(encoding="utf-8"))
                output = Path(args.output).expanduser().resolve() if args.output else None
                result = run_memory_benchmark(dataset, output)
            else:
                result = memory.compact_session(args.session, args.provider)
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "agent-install":
        files = install_agent(root, args.platform, tool_profile=args.tool_profile)
        print(json.dumps({"ok": True, "platform": args.platform,
                          "tool_profile": args.tool_profile, "files": files}, ensure_ascii=False, indent=2))

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
        import uvicorn
        if args.watch:
            os.environ["GRAPHTYN_WATCH"] = "1"
            os.environ["GRAPHTYN_WATCH_PATH"] = str(root)
        if args.mcp_token:
            os.environ["GRAPHTYN_MCP_TOKEN"] = args.mcp_token
        os.environ["GRAPHTYN_MCP_PATH"] = str(root)
        scheme = "https" if args.ssl_certfile and args.ssl_keyfile else "http"
        dashboard_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
        print("\n🌌 Graphtyn está listo")
        print(f"   Dashboard: {scheme}://{dashboard_host}:{args.port}")
        print(f"   Proyecto:  {root}")
        print(f"   Servidor:  {args.host}:{args.port} · Recarga={args.reload} · Watch={args.watch}\n", flush=True)
        if args.reload:
            uvicorn.run("graphtyn.api.main:app", host=args.host, port=args.port, reload=True,
                        ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)
        else:
            from .api.main import app
            uvicorn.run(app, host=args.host, port=args.port,
                        ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)

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
