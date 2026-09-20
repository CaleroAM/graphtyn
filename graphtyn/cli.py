import os
import sqlite3
import sys
import json
import argparse
import subprocess
import urllib.request
import time
import re
import signal
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
from .core.storage import data_home, project_store_dir, atomic_write_json
from .core.type_evidence import provider_status
from .core.global_graph import default_registry, list_projects, query_global, register_project, remove_project
from .core.work_memory import attach_learning, reflect, save_result
from .core.shared_memory import (SharedMemoryStore, MemoryStoreConflictError,
                                 existing_store_db)
from .core.memory_benchmark import build_stability_dataset, run_memory_benchmark
from .core.history_import import (discover_histories, import_histories, ProjectIdentityRegistry,
                                  configured_sources, save_source, import_history_archive,
                                  delete_source, test_source, sync_memory_workspace)
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


def _install_openclaw_capture_service(installation_id: str, interval: float = 300) -> dict:
    """Enable the per-install OpenClaw history watcher under systemd --user."""
    if not re.fullmatch(r"openclaw-[a-f0-9]{16}", installation_id):
        return {"ok": False, "active": False, "error": "id de instalación inválido"}
    suffix = installation_id.removeprefix("openclaw-")
    unit_name = f"graphtyn-openclaw-{suffix}.service"
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    home = str(data_home().resolve()).replace("\\", "\\\\").replace('"', '\\"')
    ssh_config = os.environ.get("GRAPHTYN_SSH_CONFIG", "").strip()
    ssh_config_env = []
    if ssh_config:
        escaped_ssh_config = str(Path(ssh_config).expanduser().resolve())
        if "\n" in escaped_ssh_config or "\r" in escaped_ssh_config:
            return {"ok": False, "active": False, "error": "la ruta GRAPHTYN_SSH_CONFIG no puede contener saltos de línea"}
        escaped_ssh_config = escaped_ssh_config.replace("\\", "\\\\").replace('"', '\\"')
        ssh_config_env = [f'Environment="GRAPHTYN_SSH_CONFIG={escaped_ssh_config}"']
    # Keep the venv symlink path: resolving it may escape into a system Python
    # that does not have Graphtyn installed (common with Nix).
    python = str(Path(sys.executable)).replace("\\", "\\\\").replace('"', '\\"')
    interval = max(30, min(3600, int(interval)))
    content = "\n".join([
        "[Unit]", "Description=Graphtyn OpenClaw conversation capture",
        "After=network-online.target", "Wants=network-online.target", "",
        "[Service]", "Type=simple", "Restart=on-failure", "RestartSec=15",
        f'Environment="GRAPHTYN_HOME={home}"',
        *ssh_config_env,
        f'ExecStart="{python}" -m graphtyn.cli memory sync --installation {installation_id} '
        f'--watch --interval {interval} --consent', "", "[Install]",
        "WantedBy=default.target", "",
    ])
    unit_path = unit_dir / unit_name
    unit_path.write_text(content, encoding="utf-8")
    try:
        unit_path.chmod(0o600)
    except OSError:
        pass
    try:
        reload_result = subprocess.run(["systemctl", "--user", "daemon-reload"],
            capture_output=True, text=True, timeout=20)
        if reload_result.returncode:
            return {"ok": False, "active": False, "unit": str(unit_path),
                    "error": (reload_result.stderr or reload_result.stdout).strip()[-500:]}
        enabled = subprocess.run(["systemctl", "--user", "enable", "--now", unit_name],
            capture_output=True, text=True, timeout=30)
        if enabled.returncode:
            return {"ok": False, "active": False, "unit": str(unit_path),
                    "error": (enabled.stderr or enabled.stdout).strip()[-500:]}
        restarted = subprocess.run(["systemctl", "--user", "restart", unit_name],
            capture_output=True, text=True, timeout=30)
        if restarted.returncode:
            return {"ok": False, "active": False, "unit": str(unit_path),
                    "error": (restarted.stderr or restarted.stdout).strip()[-500:]}
        active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit_name],
            capture_output=True, text=True, timeout=10).returncode == 0
        return {"ok": enabled.returncode == 0 and active, "active": active,
                "unit": str(unit_path), "error": "" if active else
                (restarted.stderr or restarted.stdout).strip()[-500:]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "active": False, "unit": str(unit_path), "error": str(exc)}


def _sync_cycle_space_summary(result: dict) -> dict:
    """Keep durable sync telemetry useful without storing transcript contents."""
    imported = result.get("import") if isinstance(result.get("import"), dict) else {}
    exclusions = list(result.get("excluded") or []) + list(imported.get("excluded") or [])
    reasons: dict[str, int] = {}
    for item in exclusions:
        reason = str(item.get("reason") or "unspecified") if isinstance(item, dict) else "unspecified"
        reasons[reason[:80]] = reasons.get(reason[:80], 0) + 1
    errors = list(result.get("errors") or imported.get("errors") or [])
    topic = result.get("topic_processing") if isinstance(result.get("topic_processing"), dict) else {}
    return {
        "ok": bool(result.get("ok", not errors)) and not errors,
        "discovered": int(result.get("discovered") or 0),
        "imported": len(imported.get("imported") or []),
        "reused": len(imported.get("reused") or []),
        "ambiguous": len(imported.get("ambiguous") or []),
        "excluded": len(exclusions),
        "exclusion_reasons": dict(sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "error_count": len(errors) + (1 if result.get("error") and not errors else 0),
        "topic_sessions": int(topic.get("sessions") or 0),
        "topic_messages": int(topic.get("messages") or 0),
    }


def _sync_cycle_log_summary(result: dict) -> dict:
    spaces = result.get("spaces") if isinstance(result.get("spaces"), list) else [result]
    summaries = []
    reason_totals: dict[str, int] = {}
    for item in spaces:
        if not isinstance(item, dict):
            continue
        summary = _sync_cycle_space_summary(item)
        for reason, count in summary["exclusion_reasons"].items():
            reason_totals[reason] = reason_totals.get(reason, 0) + count
        raw_path = str(item.get("path") or "")
        summaries.append({"space": Path(raw_path).name if raw_path else "unknown", **summary})
    totals = {key: sum(int(row.get(key) or 0) for row in summaries)
              for key in ("discovered", "imported", "reused", "ambiguous", "excluded", "error_count")}
    return {
        "event": "memory_sync_cycle",
        "ok": bool(result.get("ok", True)) and all(row["ok"] for row in summaries),
        "space_count": len(summaries),
        "failed_spaces": sum(not row["ok"] for row in summaries),
        **totals,
        "exclusion_reasons": dict(sorted(reason_totals.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "by_space": summaries[:20],
    }


def _project_sync_watcher(root: Path) -> dict | None:
    """Return the live persisted watcher for a project, if one exists."""
    if existing_store_db(root) is None:
        return None
    try:
        status = SharedMemoryStore(root).status()
    except (OSError, RuntimeError, sqlite3.Error, ValueError):
        return None
    return next((item for item in status.get("sync_watchers", [])
                 if isinstance(item, dict) and item.get("active")), None)


def _start_project_memory_watch(root: Path, *, interval: float = 5) -> dict:
    """Start one detached project watcher and verify its first heartbeat."""
    root = Path(root).expanduser().resolve()
    existing = _project_sync_watcher(root)
    if existing:
        return {"ok": True, "active": True, "started": False,
                "pid": existing.get("pid"), "watcher_id": existing.get("watcher_id"),
                "reason": "already_active"}

    state_dir = root / ".graphtyn"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "memory-sync-watch.log"
    command = [sys.executable, "-m", "graphtyn.cli", "memory", "sync",
               "--path", str(root), "--watch", "--interval", str(max(1.0, float(interval))),
               "--consent"]
    try:
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=str(root), stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, close_fds=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "active": False, "started": False,
                "log": str(log_path), "error": str(exc)}

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        watcher = _project_sync_watcher(root)
        if watcher:
            return {"ok": True, "active": True, "started": True,
                    "pid": watcher.get("pid") or process.pid,
                    "watcher_id": watcher.get("watcher_id"), "log": str(log_path)}
        if process.poll() is not None:
            break
        time.sleep(0.1)
    try:
        detail = log_path.read_text(encoding="utf-8")[-1200:]
    except OSError:
        detail = ""
    return {"ok": False, "active": False, "started": False, "pid": process.pid,
            "log": str(log_path), "error": "El watcher terminó antes de registrar heartbeat",
            "detail": detail}


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
    stream_p = memory_sub.add_parser("stream", help="Importación JSONL por lotes con cursor persistente")
    stream_p.add_argument("source")
    stream_p.add_argument("--path", required=True)
    stream_p.add_argument("--agent", required=True)
    stream_p.add_argument("--provider", required=True)
    stream_p.add_argument("--external-session", required=True)
    stream_p.add_argument("--consent", action="store_true")
    stream_p.add_argument("--select-project", action="store_true")
    stream_p.add_argument("--watch", action="store_true")
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

    install_p = subparsers.add_parser("agent-install", help="Instala instrucciones Graphtyn para asistentes")
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

    args = parser.parse_args()
    root = Path(args.path if hasattr(args, 'path') else ".").resolve()

    if args.command == "harness":
        from .core.openclaw_integration import (connect_openclaw, discover_openclaw,
            configure_openclaw_mcp, list_installations, set_parent, paths_for_installation,
            set_agent_memory_enabled)

        def parse_pairs(values, option):
            result = {}
            for value in values:
                if "=" not in value:
                    parser.error(f"{option} espera AGENTE=VALOR")
                key, val = value.split("=", 1)
                if not key.strip() or not val.strip() or key.strip() in result:
                    parser.error(f"par {option} inválido o duplicado: {value}")
                result[key.strip()] = val.strip()
            return result

        if args.harness_name != "openclaw":
            parser.error(f"harness no soportado: {args.harness_name}")
        if getattr(args, "ssh_config", None):
            ssh_config_path = Path(args.ssh_config).expanduser()
            if not ssh_config_path.is_file():
                parser.error(f"el archivo SSH no existe o no es un archivo: {ssh_config_path}")
            os.environ["GRAPHTYN_SSH_CONFIG"] = str(ssh_config_path.resolve())
        if args.openclaw_action == "discover":
            result = {"ok": True, "installations": discover_openclaw(args.config,
                ssh_target=args.ssh_target, data_root=args.data_root)}
        elif args.openclaw_action == "list":
            result = {"ok": True, "installations": list_installations()}
        elif args.openclaw_action == "relate":
            if args.independent and args.parent:
                parser.error("use --parent o --independent, no ambos")
            if not args.independent and not args.parent:
                parser.error("indique --parent ID o --independent")
            result = {"ok": True, "agent": set_parent(args.installation, args.child,
                None if args.independent else args.parent, confirm=args.confirm)}
        elif args.openclaw_action == "memory-policy":
            result = set_agent_memory_enabled(args.installation, args.agent,
                args.state == "enabled", reason=args.reason)
        elif args.openclaw_action == "connect":
            detected = discover_openclaw(args.config, ssh_target=args.ssh_target,
                                         data_root=args.data_root)
            usable = [item for item in detected if item.get("ok")]
            if args.installation:
                chosen = next((item for item in usable if item.get("id") == args.installation), None)
                if chosen is None:
                    parser.error(f"instalación no accesible o desconocida: {args.installation}")
            elif len(usable) == 1:
                chosen = usable[0]
            elif not usable:
                parser.error("no se detectó OpenClaw; especifique --config o --ssh-target y --data-root")
            else:
                parser.error("hay varias instalaciones; indique --installation " +
                             ", ".join(item["id"] for item in usable))
            installation = connect_openclaw(chosen,
                parents=parse_pairs(args.parent, "--parent"),
                independent=set(args.independent),
                brain_paths=parse_pairs(args.brain, "--brain"),
                import_history=args.import_history)
            mcp_configuration = configure_openclaw_mcp(chosen, mcp_url=args.mcp_url)
            historical = None
            if args.import_history:
                by_path = {}
                for agent in installation["agents"]:
                    by_path.setdefault(agent["brain_path"], agent["agent_id"])
                historical = [sync_memory_workspace(Path(path), provider="openclaw",
                    provider_model="deterministic", agent_id=by_path.get(path))
                    for path in paths_for_installation(installation["id"])]
            capture = ({"ok": True, "active": False, "enabled": False}
                       if args.no_watch else _install_openclaw_capture_service(
                           installation["id"], args.interval))
            result = {"ok": bool((capture["ok"] or args.no_watch) and mcp_configuration["ok"]),
                      "installation": installation, "historical_import": historical,
                      "capture": capture, "mcp": mcp_configuration,
                      "capture_mode": "historical_and_continuous" if args.import_history else
                                      "new_and_modified_sessions_only",
                      "note": ("Las relaciones no especificadas quedan privadas y pendientes de confirmar."
                               " MCP publica recuerdos entre cerebros sólo con memory_agent_publish.")}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok", True):
            raise SystemExit(1)
    elif args.command == "setup":
        from .core.deployment import detect_environment, apply_setup
        plan = detect_environment(root)
        if args.apply:
            if args.import_history and not args.consent_history:
                raise SystemExit("La importación histórica requiere --consent-history explícito")
            if args.consent_history and not args.import_history:
                raise SystemExit("--consent-history sólo se usa junto con --import-history")
            from .core.agent_installer import TARGETS
            agents = args.agent or sorted({row["provider"] for row in plan["sources"]
                                            if row["provider"] in TARGETS})
            memory_choice = args.memory
            if memory_choice == "ask" and sys.stdin.isatty():
                answer = input("¿Activar memoria conversacional para este proyecto? [s/N]: ").strip().casefold()
                memory_choice = "on" if answer in {"s", "si", "sí", "y", "yes"} else "off"
            if (args.import_history or args.memory_watch) and memory_choice != "on":
                raise SystemExit("--import-history y --memory-watch requieren --memory on")
            configured = apply_setup(root, agents=agents, sources=plan["sources"],
                                     create_token=not args.no_token, tool_profile=args.tool_profile,
                                     memory_enabled=memory_choice == "on", memory_agents=agents)
            configured["memory"] = {"enabled": memory_choice == "on", "choice": memory_choice,
                                     "historical_imported": False,
                                     "continuous_capture_active": False}
            if memory_choice == "on":
                if args.import_history:
                    discovered_rows = []
                    discovery_errors = []
                    for provider in sorted({row["provider"] for row in plan["sources"]}):
                        found = discover_histories(provider,
                            [row["source"] for row in plan["sources"] if row["provider"] == provider])
                        discovered_rows.extend(found["sessions"]); discovery_errors.extend(found["errors"])
                    discovered = {"sessions": discovered_rows, "errors": discovery_errors,
                                  "count": len(discovered_rows)}
                    imported = import_histories(root, discovered["sessions"], consent=True,
                                                provider="deterministic")
                    configured["memory"].update({"historical_imported": True,
                                                   "discovered": discovered["count"],
                                                   "imported": len(imported.get("imported", [])),
                                                   "reused": len(imported.get("reused", [])),
                                                   "ambiguous": len(imported.get("ambiguous", [])),
                                                   "errors": discovery_errors})
                if args.memory_watch:
                    watch = _start_project_memory_watch(root, interval=5)
                    configured["memory"].update({
                        "watch_command": f"graphtyn memory sync --path {root} --watch --interval 5 --consent",
                        "watch_started": bool(watch.get("active")),
                        "watch": watch,
                        "continuous_capture_active": bool(watch.get("active")),
                        "watch_note": ("Captura continua activa y verificada."
                                       if watch.get("active") else
                                       "No se pudo verificar el heartbeat del watcher.")})
                    from .core.agent_installer import update_agent_manifest
                    update_agent_manifest(root, capture_configured=bool(watch.get("active")),
                                          capture=watch)
                    from .core.project_integrations import project_integration_status
                    configured["integrations"] = project_integration_status(root)
                    configured["ok"] = bool(configured.get("ok") and watch.get("ok"))
            configured["tool_profile"] = configured.get("tool_profile") or args.tool_profile
            print(json.dumps(configured, ensure_ascii=False, indent=2))
            if not configured.get("ok", True):
                raise SystemExit(1)
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
        harness_auto = {"status": "disabled", "ok": True}
        if not args.no_harness_auto:
            from .core.openclaw_integration import (connect_openclaw, configure_openclaw_mcp,
                                                     discover_openclaw)
            try:
                discovered = [item for item in discover_openclaw() if item.get("ok")]
                if args.harness_installation:
                    chosen = next((item for item in discovered
                                   if item.get("id") == args.harness_installation), None)
                    if chosen is None:
                        harness_auto = {"status": "selection_invalid", "ok": False,
                                        "requested": args.harness_installation,
                                        "candidates": [item.get("id") for item in discovered]}
                elif len(discovered) == 1:
                    chosen = discovered[0]
                elif len(discovered) > 1:
                    chosen = None
                    harness_auto = {"status": "selection_required", "ok": True,
                                    "candidates": [{"id": item.get("id"), "target": item.get("target"),
                                                    "version": item.get("version")}
                                                   for item in discovered]}
                else:
                    chosen = None
                    harness_auto = {"status": "no_openclaw_detected", "ok": True}
                if chosen:
                    installation = connect_openclaw(chosen, import_history=False)
                    mcp = configure_openclaw_mcp(chosen)
                    capture = _install_openclaw_capture_service(installation["id"], 300)
                    pending = sum(agent.get("relation_status") in {"pending", "proposed"}
                                  for agent in installation.get("agents", []))
                    harness_auto = {
                        "status": ("configured_restart_required" if mcp.get("ok") and
                                   mcp.get("changed") and capture.get("active") else
                                   "connected" if mcp.get("ok") and capture.get("active") else
                                   "capture_active_mcp_pending" if capture.get("active") else
                                   "capture_pending"),
                        "ok": bool(capture.get("ok")), "installation_id": installation["id"],
                        "agent_count": len(installation.get("agents", [])),
                        "relationships_pending_review": pending,
                        "capture": capture, "mcp": mcp,
                        "gateway_restart_required": bool(mcp.get("changed")),
                        "history_imported": False,
                    }
            except Exception as exc:
                harness_auto = {"status": "error", "ok": False, "error": str(exc)}
        result = {"ok": bool(indexed["nodes"]) and (service is None or service["ok"]),
                  "project": str(root), "agents": agents, "tool_profile": args.tool_profile,
                  "initialized": initialized, "setup": configured,
                  "index": {key: indexed[key] for key in ("ok", "nodes", "links", "index")},
                  "dashboard": DASHBOARD_URL, "service": service,
                  "harness_auto_connect": harness_auto}
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
                existing = next((p for p in projects
                                 if str(Path(str(p.get("path") or "")).expanduser().resolve()) == str(brain_dir)), None)
                configured_agents = sorted({str(value).strip().casefold()
                                            for value in args.agent_id if str(value).strip()})
                if existing is None:
                    projects.append({"id": args.name, "name": args.name,
                                     "path": str(brain_dir), "mode": "single_folder",
                                     "space_type": "agent_brain", "agent_ids": configured_agents})
                else:
                    existing.update({"space_type": "agent_brain", "agent_ids": configured_agents
                                     if args.agent_id else existing.get("agent_ids", [])})
                atomic_write_json(reg_file, projects)
                registered_to = str(reg_file)
            result = {"ok": True, "brain": args.name, "path": str(brain_dir),
                      "agent_ids": [str(value).strip().casefold() for value in args.agent_id if str(value).strip()],
                      "agents": [{"agent_id": d["agent_id"], "name": d["name"]} for d in discovered],
                      "errors": errors, "registered_to": registered_to}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.memory_action == "consolidate":
            from .core.memory_consolidation import consolidate_legacy_brain, preview_legacy_consolidation
            source_path = Path(args.source).expanduser().resolve()
            target_path = Path(args.target).expanduser().resolve()
            registry_path = data_home() / "registered_projects.json"
            try:
                registrations = json.loads(registry_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                registrations = []
            registrations = registrations if isinstance(registrations, list) else []
            source_row = next((row for row in registrations if isinstance(row, dict) and row.get("path")
                               and Path(str(row["path"])).expanduser().resolve() == source_path), None)
            target_row = next((row for row in registrations if isinstance(row, dict) and row.get("path")
                               and Path(str(row["path"])).expanduser().resolve() == target_path), None)
            agent_id = args.agent_id.strip().casefold()
            if not source_row or not source_row.get("legacy"):
                parser.error("--source debe estar registrado explícitamente como archivo LEGADO")
            if (not target_row or target_row.get("legacy")
                    or target_row.get("space_type") != "agent_brain"
                    or agent_id not in {str(value).strip().casefold() for value in target_row.get("agent_ids", [])}):
                parser.error("--target debe ser el cerebro activo registrado del agent_id exacto")
            archive_id = str(source_row.get("id") or source_path.name)
            if args.apply and not args.consent:
                parser.error("--apply requiere --consent")
            if args.apply:
                result = consolidate_legacy_brain(source_path, target_path, agent_id=agent_id,
                    archive_id=archive_id, consent=True, batch_size=args.batch_size)
            else:
                result = preview_legacy_consolidation(source_path, target_path, agent_id, archive_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result.get("ok", True):
                raise SystemExit(1)
        elif args.memory_action == "scope":
            target = Path(args.path).expanduser().resolve()
            registry = data_home() / "registered_projects.json"
            try:
                rows = json.loads(registry.read_text(encoding="utf-8")) if registry.is_file() else []
            except (OSError, ValueError) as exc:
                raise SystemExit(f"No se pudo leer el registro de espacios: {exc}")
            if not isinstance(rows, list):
                raise SystemExit("El registro registered_projects.json debe contener una lista")
            current = next((row for row in rows if isinstance(row, dict) and row.get("path") and
                            Path(str(row["path"])).expanduser().resolve() == target), None)
            if args.action == "show":
                if current is None:
                    print(json.dumps({"ok": True, "registered": False, "path": str(target),
                                      "message": "El espacio no tiene política registrada"},
                                     ensure_ascii=False, indent=2))
                else:
                    raw_ids = current.get("agent_ids") or []
                    agent_ids = raw_ids if isinstance(raw_ids, list) else []
                    print(json.dumps({"ok": True, "registered": True, "id": current.get("id"),
                                      "name": current.get("name"), "path": str(target),
                                      "space_type": current.get("space_type") or "project",
                                      "agent_ids": sorted({str(value).strip().casefold() for value in agent_ids
                                                           if str(value).strip()})},
                                     ensure_ascii=False, indent=2))
            else:
                if not target.is_dir():
                    raise SystemExit(f"El espacio debe existir y ser un directorio: {target}")
                if current is None and args.space_type is None:
                    raise SystemExit("Un espacio nuevo requiere --space-type para registrar su alcance")
                supplied = [str(value).strip().casefold() for value in args.agent_id if str(value).strip()]
                if any(not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]{0,127}", value) for value in supplied):
                    raise SystemExit("agent-id inválido; use la identidad canónica registrada")
                raw_ids = (current or {}).get("agent_ids") or []
                existing_ids = raw_ids if isinstance(raw_ids, list) else []
                if args.clear_agent_ids:
                    owners = []
                elif args.replace_agent_ids:
                    owners = sorted(set(supplied))
                else:
                    owners = sorted({str(value).strip().casefold() for value in existing_ids
                                     if str(value).strip()} | set(supplied))
                if current is None:
                    current = {"id": target.name, "name": target.name, "path": str(target),
                               "mode": "single_folder"}
                    rows.append(current)
                current.update({"path": str(target), "space_type": args.space_type or
                                current.get("space_type") or "project", "agent_ids": owners})
                atomic_write_json(registry, rows)
                print(json.dumps({"ok": True, "registered": True, "path": str(target),
                                  "space_type": current["space_type"], "agent_ids": owners,
                                  "registry": str(registry)}, ensure_ascii=False, indent=2))
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
            discovered = discover_histories(args.provider, args.source or None,
                                            project_path=None if args.source else Path(args.path),
                                            agent_id=args.agent_id)
            if args.session:
                wanted = {str(value).strip() for value in args.session}
                discovered["sessions"] = [row for row in discovered["sessions"]
                                           if any(value in str(row.get("external_session_id") or "")
                                                  or value in str(row.get("source") or "") for value in wanted)]
                discovered["count"] = len(discovered["sessions"])
                for selected in discovered["sessions"]: selected["explicit_project_selection"] = True
            if args.apply:
                importer = import_history_archive if args.archive_all else import_histories
                result = importer(Path(args.path), discovered["sessions"], consent=args.consent,
                                  provider=args.provider_model)
                result["discovery"] = {"count": discovered["count"], "errors": discovered["errors"]}
            else:
                result = {**discovered, "dry_run": True,
                          "message": "Revise el plan y repita con --apply --consent"}
            if args.output:
                output = Path(args.output).expanduser().resolve()
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                result["output"] = str(output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.memory_action == "projects":
            from .core.project_integrations import ensure_project_identity
            current = ensure_project_identity(Path(args.path), aliases=args.alias)
            print(json.dumps({"ok": True, "current": current,
                              "projects": ProjectIdentityRegistry().list()}, ensure_ascii=False, indent=2))
        elif args.memory_action == "sync":
            from .core.openclaw_integration import paths_for_installation

            def discover_all_space_targets():
                candidates: list[Path] = []
                conflicts: list[dict[str, str]] = []
                for project in ProjectIdentityRegistry().list():
                    if not isinstance(project, dict) or project.get("legacy"):
                        continue
                    for raw in project.get("paths", []):
                        try:
                            candidates.append(Path(str(raw)).expanduser().resolve())
                        except (OSError, RuntimeError, ValueError) as exc:
                            conflicts.append({"ok": False, "path": str(raw),
                                              "code": "invalid_memory_path", "error": str(exc)})

                registry = data_home() / "registered_projects.json"
                try:
                    registrations = json.loads(registry.read_text(encoding="utf-8")) if registry.is_file() else []
                except (OSError, ValueError) as exc:
                    registrations = []
                    conflicts.append({"ok": False, "path": str(registry),
                                      "code": "memory_registry_error", "error": str(exc)})
                if not isinstance(registrations, list):
                    registrations = []
                    conflicts.append({"ok": False, "path": str(registry),
                                      "code": "memory_registry_error",
                                      "error": "registered_projects.json debe contener una lista"})
                for row in registrations:
                    if not isinstance(row, dict) or not row.get("path") or row.get("legacy") or                             row.get("mode") == "master_folder":
                        continue
                    try:
                        candidates.append(Path(str(row["path"])).expanduser().resolve())
                    except (OSError, RuntimeError, ValueError) as exc:
                        conflicts.append({"ok": False, "path": str(row.get("path") or ""),
                                          "code": "invalid_memory_path", "error": str(exc)})

                associated: set[Path] = set()
                for row in configured_sources():
                    raw = row.get("project_path")
                    if not raw:
                        continue
                    try:
                        associated.add(Path(str(raw)).expanduser().resolve())
                    except (OSError, RuntimeError, ValueError) as exc:
                        conflicts.append({"ok": False, "path": str(raw),
                                          "code": "invalid_memory_path", "error": str(exc)})
                candidates.extend(associated)

                targets: list[Path] = []
                for path in dict.fromkeys(candidates):
                    if not path.is_dir():
                        continue
                    try:
                        has_store = bool(existing_store_db(path))
                    except MemoryStoreConflictError as exc:
                        conflicts.append({"ok": False, "path": str(path),
                                          "code": "memory_store_conflict", "error": str(exc)})
                        continue
                    if path in associated or has_store:
                        targets.append(path)
                return targets, conflicts

            def sync_targets():
                if args.installation:
                    return [Path(item).expanduser().resolve()
                            for item in paths_for_installation(args.installation)]
                if args.all_spaces:
                    return discover_all_space_targets()[0]
                return [Path(args.path).expanduser().resolve()]

            def sync_path(path: Path):
                return sync_memory_workspace(path, provider=args.provider,
                    source=args.source or None, provider_model=args.provider_model,
                    agent_id=args.agent_id)

            def sync_once():
                if args.installation:
                    results = []
                    for path in sync_targets():
                        try:
                            results.append(sync_path(path))
                        except MemoryStoreConflictError as exc:
                            results.append({"ok": False, "path": str(path),
                                            "code": "memory_store_conflict", "error": str(exc)})
                    return {"ok": all(item.get("ok", False) for item in results),
                            "spaces": results, "space_count": len(results),
                            "failed_spaces": sum(not item.get("ok", False) for item in results)}
                if args.all_spaces:
                    paths, conflicts = discover_all_space_targets()
                    results = [{"ok": False, **item} for item in conflicts]
                    for path in paths:
                        try:
                            results.append(sync_path(path))
                        except MemoryStoreConflictError as exc:
                            results.append({"ok": False, "path": str(path),
                                            "code": "memory_store_conflict", "error": str(exc)})
                    return {"ok": all(item.get("ok", False) for item in results),
                            "spaces": results, "space_count": len(results),
                            "failed_spaces": sum(not item.get("ok", False) for item in results)}
                return sync_path(Path(args.path).expanduser().resolve())

            if not args.watch:
                print(json.dumps(sync_once(), ensure_ascii=False, indent=2))
            else:
                watcher_id = f"cli-sync:{os.getpid()}"
                interval = max(1.0, float(args.interval))

                def update_watchers(status, error="", cycle_result=None):
                    for path in sync_targets():
                        SharedMemoryStore(path).update_sync_watcher(
                            watcher_id, status, interval=interval, error=error,
                            cycle_result=cycle_result)

                def record_cycle(result):
                    spaces = result.get("spaces") if isinstance(result.get("spaces"), list) else [result]
                    by_path = {}
                    for item in spaces:
                        if not isinstance(item, dict) or not item.get("path"):
                            continue
                        try:
                            by_path[str(Path(item["path"]).expanduser().resolve())] = item
                        except (OSError, RuntimeError, ValueError):
                            continue
                    for path in sync_targets():
                        item = by_path.get(str(path.resolve()))
                        if item is None:
                            item = ({**result, "path": str(path)} if result.get("error") else
                                    {"path": str(path), "ok": False,
                                     "error": "No se produjo resultado para este almacén"})
                        summary = _sync_cycle_space_summary(item)
                        failed = not summary["ok"]
                        SharedMemoryStore(path).update_sync_watcher(
                            watcher_id, "error" if failed else "watching", interval=interval,
                            error=(f"{summary['error_count']} errores en el último ciclo" if failed else ""),
                            cycle_result=summary)

                def stop_watcher(_signum, _frame):
                    raise KeyboardInterrupt

                previous_sigterm = signal.signal(signal.SIGTERM, stop_watcher)
                try:
                    while True:
                        update_watchers("processing")
                        try:
                            result = sync_once()
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                            result = {"ok": False, "error": error}
                        record_cycle(result)
                        print(json.dumps(_sync_cycle_log_summary(result),
                                         ensure_ascii=False, separators=(",", ":")), flush=True)
                        time.sleep(interval)
                except KeyboardInterrupt:
                    pass
                finally:
                    try:
                        update_watchers("stopped")
                    finally:
                        signal.signal(signal.SIGTERM, previous_sigterm)
        elif args.memory_action == "sources":
            if args.action == "add":
                if not args.provider or not args.source:
                    raise SystemExit("sources add requiere --provider y --source")
                saved = save_source(args.provider, args.source, label=args.label, project_path=args.workspace,
                                    agent_id=args.agent_id)
                print(json.dumps({"ok": True, "saved": saved}, ensure_ascii=False, indent=2))
            elif args.action == "remove":
                if not args.provider or not args.source: raise SystemExit("sources remove requiere --provider y --source")
                print(json.dumps({"ok": True, "removed": delete_source(args.provider, args.source)}, indent=2))
            elif args.action == "test":
                if not args.provider or not args.source: raise SystemExit("sources test requiere --provider y --source")
                print(json.dumps(test_source(args.provider, args.source), ensure_ascii=False, indent=2))
            else:
                print(json.dumps({"ok": True, "sources": configured_sources()}, ensure_ascii=False, indent=2))
        elif args.memory_action == "agents":
            registry = data_home() / "registered_agents.json"
            try:
                payload = json.loads(registry.read_text(encoding="utf-8"))
                rows = payload.get("agents", []) if isinstance(payload, dict) else payload
            except (OSError, ValueError, TypeError):
                rows = []
            if args.action == "list":
                print(json.dumps({"ok": True, "agents": rows}, ensure_ascii=False, indent=2))
            else:
                aid = str(args.agent_id or "").strip().casefold()
                if not aid:
                    raise SystemExit("agents register requiere --id")
                if not all(ch.isalnum() or ch in "._:/-" for ch in aid) or not aid[0].isalnum():
                    raise SystemExit("id de agente inválido")
                entry = {"id": aid, "name": args.name or aid, "provider": args.provider or "",
                         "description": args.description[:500],
                         "paths": [str(Path(value).expanduser().resolve()) for value in args.agent_path if str(value).strip()]}
                existing = next((row for row in rows if str(row.get("id") or "").casefold() == aid), None)
                if existing is None: rows.append(entry)
                else: existing.update(entry)
                registry.parent.mkdir(parents=True, exist_ok=True)
                registry.write_text(json.dumps({"version": 1, "agents": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
                try: registry.chmod(0o600)
                except OSError: pass
                print(json.dumps({"ok": True, "agent": entry}, ensure_ascii=False, indent=2))
        elif args.memory_action == "save":
            output = save_result(root, args.question, args.answer, args.nodes, args.outcome, args.files, args.correction)
            print(json.dumps({"ok": True, "saved": str(output)}, ensure_ascii=False))
        elif args.memory_action == "reflect":
            print(json.dumps(reflect(root, args.half_life_days), ensure_ascii=False, indent=2))
        else:
            memory = SharedMemoryStore(root)
            write_actions = {"session-start", "session-end", "checkpoint", "append", "ingest-turn",
                "stream", "relation-review", "topics-enrich", "topic-update", "correct", "forget",
                "compact", "migrate", "reindex", "ingest-evidence", "retention"}
            if args.memory_action in write_actions:
                from .core.openclaw_integration import assert_agent_memory_enabled
                actor = getattr(args, "agent", None)
                if args.memory_action in {"session-end", "checkpoint", "append", "compact", "correct"}:
                    session = memory.get_session(str(getattr(args, "session", "") or ""))
                    actor = (session or {}).get("agent_id") or actor
                assert_agent_memory_enabled(root, actor)
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
            elif args.memory_action == "stream":
                from .core.history_stream import ingest_jsonl, watch_jsonl
                stream_operation = watch_jsonl if args.watch else ingest_jsonl
                result = stream_operation(memory, args.source, provider=args.provider, agent_id=args.agent,
                    external_session_id=args.external_session, consent=args.consent,
                    explicit_project_selection=args.select_project)
            elif args.memory_action == "entities":
                result = memory.entities(args.query, requester_agent=args.agent, kind=args.kind,
                    limit=args.limit, offset=args.offset)
            elif args.memory_action == "entity":
                result = memory.entity(args.entity_id, requester_agent=args.agent, limit=args.limit)
            elif args.memory_action == "topics":
                result = memory.topics(args.query, requester_agent=args.agent, state=args.state,
                    session_id=args.session, limit=args.limit, offset=args.offset)
            elif args.memory_action == "topic":
                result = memory.topic(args.topic_id, requester_agent=args.agent)
            elif args.memory_action == "window":
                result = memory.message_window(args.message_id, requester_agent=args.agent,
                    before=args.before, after=args.after, token_budget=args.token_budget)
            elif args.memory_action == "node":
                result = memory.resolve_node_reference(args.reference, requester_agent=args.agent, limit=args.limit)
            elif args.memory_action == "relation-candidates":
                result = memory.relation_candidates(requester_agent=args.agent, status=args.status, limit=args.limit)
            elif args.memory_action == "relation-review":
                result = memory.relation_review(args.relation_id, status=args.status, actor=args.agent, reason=args.reason)
            elif args.memory_action == "topics-enrich":
                result = memory.enrich_topics(args.session, provider=args.provider, force=args.force,
                                              retry_failed=args.retry_failed)
            elif args.memory_action == "topic-update":
                result = memory.topic_update(args.topic_id, requester_agent=args.agent, reason=args.reason,
                    state=args.state, title=args.title, verification=args.verification,
                    message_ids=args.message_ids, merge_into=args.merge_into, split_episode=args.split_episode)
            elif args.memory_action == "context":
                result = memory.context(args.query, requester_agent=args.agent, limit=args.limit,
                                        token_budget=args.token_budget, branch=args.branch,
                                        mode=args.mode, activity_limit=args.activity_limit,
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
        from .core.agent_installer import resolve_tool_profile
        from .core.project_integrations import project_integration_status
        profile = resolve_tool_profile(root, args.tool_profile)
        files = install_agent(root, args.platform, tool_profile=profile)
        status = project_integration_status(root)
        print(json.dumps({"ok": True, "platform": args.platform,
                          "project_id": status.get("project_id"), "mcp_server": status.get("mcp_server"),
                          "integrations": status.get("clients", []),
                          "tool_profile": profile, "files": files}, ensure_ascii=False, indent=2))

    elif args.command == "integrations":
        from .core.project_integrations import (project_integration_status, remove_project_integrations,
                                                verify_project_mcp)
        if args.integration_action == "status":
            result = {"ok": True, **project_integration_status(Path(args.path))}
        elif args.integration_action == "verify":
            result = verify_project_mcp(Path(args.path))
        else:
            current = project_integration_status(Path(args.path))
            clients = args.agent or [str(item.get("platform")) for item in current.get("clients", [])
                                     if item.get("status") in {"configured", "command_unavailable"}]
            result = remove_project_integrations(Path(args.path), clients)
            result["project_id"] = current.get("project_id")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok", True):
            raise SystemExit(1)

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
