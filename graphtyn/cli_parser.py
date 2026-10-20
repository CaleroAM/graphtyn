"""Argument parser construction for the Graphtyn CLI."""

from __future__ import annotations

import argparse

from . import __version__


def _add_setup_commands(subparsers: argparse._SubParsersAction) -> None:
    setup_p = subparsers.add_parser("setup", help="Detecta y configura Graphtyn sin editar código")
    setup_p.add_argument("--path", default=".")
    setup_p.add_argument("--agent", action="append", default=[])
    setup_p.add_argument("--apply", action="store_true")
    setup_p.add_argument("--no-token", action="store_true")
    setup_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default=None,
                         help="Perfil MCP; si se omite conserva el existente o usa full con memoria activa")
    setup_p.add_argument("--memory", choices=["ask", "on", "off"], default="ask",
                         help="Memoria conversacional: preguntar, activar o desactivar")
    setup_p.add_argument("--memory-watch", action="store_true",
                         help="Iniciar y verificar el sincronizador continuo al activar memoria")
    setup_p.add_argument("--import-history", action="store_true",
                         help="Importar historial anterior (requiere --consent-history)")
    setup_p.add_argument("--consent-history", action="store_true",
                         help="Confirma que autorizas leer e importar conversaciones históricas")
    harness_p = subparsers.add_parser("harness", help="Detecta y conecta memorias de agentes")
    harness_sub = harness_p.add_subparsers(dest="harness_name", required=True)
    openclaw_p = harness_sub.add_parser("openclaw", help="Integración nativa con OpenClaw")
    openclaw_sub = openclaw_p.add_subparsers(dest="openclaw_action", required=True)
    discover_oc = openclaw_sub.add_parser("discover", help="Detecta OpenClaw local o en un destino SSH explícito")
    discover_oc.add_argument("--config", default=None)
    discover_oc.add_argument("--ssh-target", default=None, help="Host explícito usuario@host; no se escanea la red")
    discover_oc.add_argument("--data-root", default=None, help="Directorio de datos OpenClaw remoto")
    discover_oc.add_argument("--ssh-config", default=None,
                             help="Archivo SSH alternativo; también se guarda para la captura continua")
    connect_oc = openclaw_sub.add_parser("connect", help="Registra agentes aislados y activa captura nueva")
    connect_oc.add_argument("--installation", default=None)
    connect_oc.add_argument("--config", default=None)
    connect_oc.add_argument("--ssh-target", default=None)
    connect_oc.add_argument("--data-root", default=None)
    connect_oc.add_argument("--ssh-config", default=None,
                            help="Archivo SSH alternativo; se guarda para la captura continua")
    connect_oc.add_argument("--parent", action="append", default=[], metavar="HIJO=PADRE",
                            help="Confirma una relación padre/subagente; repetible")
    connect_oc.add_argument("--independent", action="append", default=[], metavar="AGENTE",
                            help="Confirma un cerebro independiente; repetible")
    connect_oc.add_argument("--brain", action="append", default=[], metavar="AGENTE=RUTA",
                            help="Asigna explícitamente un almacén privado a un agente")
    connect_oc.add_argument("--import-history", action="store_true",
                            help="Importa historiales anteriores; sin esto sólo captura conversaciones nuevas")
    connect_oc.add_argument("--mcp-url", default=None,
                            help="URL /mcp accesible desde OpenClaw; también puede venir de GRAPHTYN_MCP_URL")
    connect_oc.add_argument("--no-watch", action="store_true", help="No activa captura automática")
    connect_oc.add_argument("--interval", type=float, default=300)
    relate_oc = openclaw_sub.add_parser("relate", help="Confirma o separa una relación de agentes")
    relate_oc.add_argument("--installation", required=True)
    relate_oc.add_argument("--child", required=True)
    relate_oc.add_argument("--parent", default=None)
    relate_oc.add_argument("--independent", action="store_true")
    relate_oc.add_argument("--confirm", action="store_true", help="Confirma que la relación es correcta")
    memory_policy_oc = openclaw_sub.add_parser(
        "memory-policy", help="Activa o desactiva la memoria de un agente sólo en esta instalación")
    memory_policy_oc.add_argument("--installation", required=True)
    memory_policy_oc.add_argument("--agent", required=True)
    memory_policy_oc.add_argument("--state", choices=["enabled", "disabled"], required=True)
    memory_policy_oc.add_argument("--reason", default="operator policy")
    openclaw_sub.add_parser("list", help="Muestra instalaciones y relaciones registradas")
    onboard_p = subparsers.add_parser("onboard", help="Configura agentes, índice, MCP y dashboard en una sola orden")
    onboard_p.add_argument("--path", default=".")
    onboard_p.add_argument("--agent", action="append", default=[])
    onboard_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default="full")
    onboard_p.add_argument("--start-dashboard", action="store_true")
    onboard_p.add_argument("--watch", action="store_true")
    onboard_p.add_argument("--no-token", action="store_true")
    onboard_p.add_argument("--no-harness-auto", action="store_true",
                           help="No detectar ni conectar OpenClaw durante el onboarding")
    onboard_p.add_argument("--harness-installation", default=None,
                           help="Elegir una instalación OpenClaw cuando se detecten varias")


def _add_admin_commands(subparsers: argparse._SubParsersAction) -> None:
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
    service_install.add_argument("--host", default="127.0.0.1", help="Interfaz de escucha; fuera de loopback requiere --tokens-file")
    service_install.add_argument("--port", type=int, default=9210)
    service_install.add_argument("--tokens-file", default=None, help="Archivo JSON de tokens HTTP")
    service_install.add_argument("--embed-model", default=None, help="Modelo local de embeddings de Ollama")
    service_install.add_argument("--ollama-host", default=None, help="URL local de Ollama")
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


def _add_graph_commands(subparsers: argparse._SubParsersAction) -> None:
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
    intent_p.add_argument("--response-mode", default="compact", choices=["compact", "full"], help="Salida compacta con aliases (predeterminado) o estructura interna completa")
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


def _add_benchmark_commands(subparsers: argparse._SubParsersAction) -> None:
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


def _add_memory_capture_commands(memory_sub: argparse._SubParsersAction) -> None:
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
    stream_p = memory_sub.add_parser("stream", help="Importación JSONL por lotes con cursor persistente")
    stream_p.add_argument("source")
    stream_p.add_argument("--path", required=True)
    stream_p.add_argument("--agent", required=True)
    stream_p.add_argument("--provider", required=True)
    stream_p.add_argument("--external-session", required=True)
    stream_p.add_argument("--consent", action="store_true")
    stream_p.add_argument("--select-project", action="store_true")
    stream_p.add_argument("--watch", action="store_true")


def _add_memory_knowledge_commands(memory_sub: argparse._SubParsersAction) -> None:
    for action in ("entities", "entity", "topics", "topic", "window", "topic-update", "node", "relation-candidates", "relation-review", "topics-enrich"):
        topic_p = memory_sub.add_parser(action)
        topic_p.add_argument("--path", default=".")
        topic_p.add_argument("--agent", default="cli")
        if action == "entities":
            topic_p.add_argument("query", nargs="?", default="")
            topic_p.add_argument("--kind", default=None)
            topic_p.add_argument("--limit", type=int, default=50)
            topic_p.add_argument("--offset", type=int, default=0)
        elif action == "entity":
            topic_p.add_argument("entity_id")
            topic_p.add_argument("--limit", type=int, default=50)
        elif action == "topics":
            topic_p.add_argument("query", nargs="?", default="")
            topic_p.add_argument("--state", default=None)
            topic_p.add_argument("--session", default=None)
            topic_p.add_argument("--limit", type=int, default=20)
            topic_p.add_argument("--offset", type=int, default=0)
        elif action == "window":
            topic_p.add_argument("message_id")
            topic_p.add_argument("--before", type=int, default=10)
            topic_p.add_argument("--after", type=int, default=10)
            topic_p.add_argument("--token-budget", type=int, default=3000)
        elif action == "node":
            topic_p.add_argument("reference")
            topic_p.add_argument("--limit", type=int, default=20)
        elif action == "relation-candidates":
            topic_p.add_argument("--status", default="pending")
            topic_p.add_argument("--limit", type=int, default=50)
        elif action == "relation-review":
            topic_p.add_argument("relation_id")
            topic_p.add_argument("--status", choices=["accepted", "rejected"], required=True)
            topic_p.add_argument("--reason", required=True)
        elif action == "topics-enrich":
            topic_p.add_argument("--session", default=None)
            topic_p.add_argument("--provider", choices=["auto", "ollama", "deterministic", "api"], default="auto")
            topic_p.add_argument("--force", action="store_true", help="Reprocesa explícitamente aunque la fuente no haya cambiado")
            topic_p.add_argument("--retry-failed", action="store_true", help="Reintenta sólo temas con enriquecimiento fallido")
        else:
            topic_p.add_argument("topic_id")
            if action == "topic-update":
                topic_p.add_argument("--reason", required=True)
                topic_p.add_argument("--state", default=None)
                topic_p.add_argument("--title", default=None)
                topic_p.add_argument("--verification", default=None)
                topic_p.add_argument("--message-ids", nargs="*", default=[])
                topic_p.add_argument("--merge-into", default=None)
                topic_p.add_argument("--split-episode", default=None)
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
    context_p.add_argument("--mode", choices=["semantic", "continuity"], default="semantic",
                           help="continuity incluye las últimas actualizaciones atribuidas")
    context_p.add_argument("--activity-limit", type=int, default=3)
    context_p.add_argument("--neighbor-limit", type=int, default=12)
    context_p.add_argument("--no-graph", action="store_true")
    context_p.add_argument("--path", default=".")
    status_p = memory_sub.add_parser("status", help="Estado del almacén compartido")
    status_p.add_argument("--path", default=".")
    migrate_p = memory_sub.add_parser("migrate", help="Importa historial y outcomes v1 sin duplicar")
    migrate_p.add_argument("--path", default=".")
    reindex_p = memory_sub.add_parser("reindex", help="Actualiza sólo embeddings de memorias modificadas")
    reindex_p.add_argument("--path", default=".")
    evidence_p = memory_sub.add_parser("ingest-evidence", help="Ingiere informes y verifica métricas sólo con ejecución enlazada")
    evidence_p.add_argument("--files", nargs="*", default=None,
                            help="Archivos relativos; por defecto BENCHMARKS.md, reportes y summaries/comparisons JSON")
    evidence_p.add_argument("--path", default=".")
    evidence_status_p = memory_sub.add_parser("evidence-status", help="Muestra vigencia, ejecución y dependencias de la evidencia importada")
    evidence_status_p.add_argument("--memory", default=None, help="ID opcional de una evidencia")
    evidence_status_p.add_argument("--agent", default="cli")
    evidence_status_p.add_argument("--limit", type=int, default=100)
    evidence_status_p.add_argument("--path", default=".")


def _add_memory_evidence_commands(memory_sub: argparse._SubParsersAction) -> None:
    run_local_p = memory_sub.add_parser("run-local", help="Ejecuta una verificación local y registra procedencia")
    run_local_p.add_argument("--test", action="append", default=[], help="Archivo de prueba vinculado (repetible)")
    run_local_p.add_argument("--data", action="append", default=[], help="Archivo de datos vinculado (repetible)")
    run_local_p.add_argument("--dependency", action="append", default=[], help="Dependencia vinculada (repetible)")
    run_local_p.add_argument("--timeout", type=float, default=60.0)
    run_local_p.add_argument("--executor", default="cli/local")
    run_local_p.add_argument("--path", default=".")
    run_local_p.add_argument("run_command", nargs=argparse.REMAINDER,
                             help="Comando y argumentos; puede anteponer --")
    migrate_evidence_p = memory_sub.add_parser(
        "migrate-evidence", help="Previsualiza o aplica degradación de evidencia histórica sin procedencia"
    )
    migrate_evidence_p.add_argument("--apply", action="store_true")
    migrate_evidence_p.add_argument("--path", default=".")
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
    doctor_p = memory_sub.add_parser("doctor", help="Diagnostica almacenamiento, captura, consulta y conexión MCP")
    doctor_p.add_argument("--path", default=".")
    memory_bench_p = memory_sub.add_parser("benchmark", help="Evalúa recall, MRR, atribución, tokens y latencia")
    memory_bench_p.add_argument("--dataset", default="benchmarks/shared_memory_v1.json")
    memory_bench_p.add_argument("--suite", choices=["dataset", "stability", "scale"], default="dataset")
    memory_bench_p.add_argument("--records", type=int, choices=[1000, 10000, 50000], default=1000,
                                help="Registros para --suite scale; ejecute 50k en hardware objetivo")
    memory_bench_p.add_argument("--repetitions", type=int, default=1,
                                help="Repeticiones pareadas normal/degradada para --suite scale")
    memory_bench_p.add_argument("--query-count", type=int, default=90,
                                help="Consultas positivas deterministas para --suite scale")
    memory_bench_p.add_argument("--query-profile", choices=["synthetic", "mixed"], default="synthetic",
                                help="Perfil de consultas para --suite scale: identificadores o mezcla realista")
    memory_bench_p.add_argument("--output", default=None)
    memory_bench_p.add_argument("--path", default=".")
    project_eval_p = memory_sub.add_parser(
        "project-evaluation", help="Evalúa evidencia, procedencia y abstención en el proyecto actual"
    )
    project_eval_p.add_argument("--output", default=None,
                                help="Guarda el resultado reproducible en JSON")
    project_eval_p.add_argument("--path", default=".")
    compact_p = memory_sub.add_parser("compact", help="Extrae memorias propuestas desde una sesión capturada")
    compact_p.add_argument("--session", required=True)
    compact_p.add_argument("--provider", choices=["auto", "deterministic", "ollama", "api"], default="auto")
    compact_p.add_argument("--path", default=".")
    brain_p = memory_sub.add_parser("brain-init", help="Crea un cerebro (espacio de memoria de agentes)")
    brain_p.add_argument("--brain-path", required=True, help="Carpeta del cerebro (se crea si no existe)")
    brain_p.add_argument("--name", required=True, help="Nombre visible en el dashboard")
    brain_p.add_argument("--agent-id", action="append", default=[],
                         help="Identidad propietaria del cerebro (repetible para alias explícitos)")
    brain_p.add_argument("--agents-dir", default=None,
                         help="Directorio con workspaces de agentes (subcarpetas con IDENTITY.md/SOUL.md) a descubrir en bloque")
    brain_p.add_argument("--agent-workspace", action="append", default=[],
                         help="Workspace de agente individual a vincular (repetible)")
    brain_p.add_argument("--register", action="store_true", help="Registrar el cerebro en el dashboard")
    consolidate_p = memory_sub.add_parser("consolidate", help="Migra un legado a un cerebro activo por agente")
    consolidate_p.add_argument("--source", required=True, help="Ruta del archivo de memoria marcado LEGADO")
    consolidate_p.add_argument("--target", required=True, help="Ruta del cerebro activo del agente")
    consolidate_p.add_argument("--agent-id", required=True, help="Identidad canónica exacta, por ejemplo openclaw/nexus")
    consolidate_p.add_argument("--apply", action="store_true", help="Ejecutar la migración; por defecto sólo previsualiza")
    consolidate_p.add_argument("--consent", action="store_true", help="Autoriza la copia al cerebro activo")
    consolidate_p.add_argument("--batch-size", type=int, default=100, help="Mensajes/recuerdos entre guardados de progreso")
    scope_p = memory_sub.add_parser("scope", help="Consulta o administra la política de propietarios de un espacio")
    scope_p.add_argument("action", choices=["show", "set"])
    scope_p.add_argument("--path", required=True, help="Ruta del proyecto o cerebro registrado")
    scope_p.add_argument("--space-type", choices=["project", "agent_brain", "container"], default=None)
    scope_p.add_argument("--agent-id", action="append", default=[],
                         help="Identidad canónica autorizada (repetible)")
    scope_ids = scope_p.add_mutually_exclusive_group()
    scope_ids.add_argument("--replace-agent-ids", action="store_true",
                           help="Reemplaza la lista completa con los --agent-id proporcionados")
    scope_ids.add_argument("--clear-agent-ids", action="store_true",
                           help="Elimina explícitamente todos los propietarios autorizados")
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
    bootstrap_p.add_argument("--session", action="append", default=[],
                             help="ID de conversación exacto (repetible; limita la importación)")
    bootstrap_p.add_argument("--apply", action="store_true", help="Importar; sin esta opción sólo previsualiza")
    bootstrap_p.add_argument("--consent", action="store_true", help="Autoriza procesar los historiales seleccionados")
    bootstrap_p.add_argument("--provider-model", choices=["deterministic", "auto", "ollama", "api"], default="deterministic")
    bootstrap_p.add_argument("--output", default=None, help="Guardar plan/reporte JSON")
    bootstrap_p.add_argument("--archive-all", action="store_true",
                             help="Importar toda sesión en un cerebro histórico separado")
    bootstrap_p.add_argument("--path", default=".")
    bootstrap_p.add_argument("--agent-id", default=None,
                             help="Identidad propietaria; evita importar sesiones de otro agente")


def _add_memory_registry_commands(memory_sub: argparse._SubParsersAction) -> None:
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
    sync_p.add_argument("--all-spaces", action="store_true", help="Sincronizar todos los espacios registrados con fuente asociada")
    sync_p.add_argument("--installation", default=None,
                        help="Sincronizar todos los cerebros privados de una instalación de harness")
    sync_p.add_argument("--interval", type=float, default=5.0)
    sync_p.add_argument("--path", default=".")
    sync_p.add_argument("--agent-id", default=None,
                        help="Identidad propietaria de la fuente (requerida para una raíz compartida)")
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
    sources_p.add_argument("--workspace", default=None, help="Cerebro/proyecto al que pertenece la fuente")
    sources_p.add_argument("--agent-id", default=None, help="Identidad estable del agente que produce la fuente")
    agents_p = memory_sub.add_parser("agents", help="Lista o registra identidades de agentes")
    agents_p.add_argument("action", choices=["list", "register"])
    agents_p.add_argument("--id", dest="agent_id", default=None)
    agents_p.add_argument("--name", default=None)
    agents_p.add_argument("--provider", default=None)
    agents_p.add_argument("--path", dest="agent_path", action="append", default=[])
    agents_p.add_argument("--description", default="")



def _add_memory_commands(subparsers: argparse._SubParsersAction) -> None:
    memory_p = subparsers.add_parser("memory", help="Memoria de resultados del agente")
    memory_sub = memory_p.add_subparsers(dest="memory_action", required=True)
    _add_memory_capture_commands(memory_sub)
    _add_memory_knowledge_commands(memory_sub)
    _add_memory_evidence_commands(memory_sub)
    _add_memory_registry_commands(memory_sub)


def _add_integration_commands(subparsers: argparse._SubParsersAction) -> None:
    install_p = subparsers.add_parser("agent-install", help="Configura el MCP de Graphtyn para un proyecto; el ejecutable es global")
    install_p.add_argument("platform", choices=["all", "codex", "opencode", "openclaw", "hermes", "claude", "cursor", "gemini", "antigravity", "copilot"])
    install_p.add_argument("--path", default=".")
    install_p.add_argument("--tool-profile", choices=["intent", "memory", "full"], default=None,
                           help="Perfil MCP; si se omite conserva el existente")

    integrations_p = subparsers.add_parser("integrations", help="Consulta o retira conexiones MCP por proyecto")
    integrations_sub = integrations_p.add_subparsers(dest="integration_action", required=True)
    integrations_status = integrations_sub.add_parser("status", help="Muestra identidad y estado MCP del proyecto")
    integrations_status.add_argument("--path", default=".")
    integrations_verify = integrations_sub.add_parser("verify", help="Prueba el handshake MCP y las herramientas del proyecto")
    integrations_verify.add_argument("--path", default=".")
    integrations_remove = integrations_sub.add_parser("remove", help="Retira sólo entradas MCP administradas por Graphtyn")
    integrations_remove.add_argument("--path", default=".")
    integrations_remove.add_argument("--agent", action="append", default=[],
                                     help="Cliente que se desconecta (repetible; sin opción elimina todos los configurados)")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graphtyn",
        description="Graphtyn — Grafo semántico de código para agentes de IA",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")
    _add_setup_commands(subparsers)
    _add_admin_commands(subparsers)
    _add_graph_commands(subparsers)
    _add_benchmark_commands(subparsers)
    _add_memory_commands(subparsers)
    _add_integration_commands(subparsers)
    return parser
