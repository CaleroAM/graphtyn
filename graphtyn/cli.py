import os
import sqlite3
import sys
import json
import subprocess
import urllib.request
import time
import re
from pathlib import Path

from .cli_parser import build_parser
from .cli_memory import _handle_memory_command
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
from .core.work_memory import attach_learning
from .core.shared_memory import SharedMemoryStore, existing_store_db
from .core.history_import import discover_histories, import_histories, sync_memory_workspace
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




# Memory command handlers stay separate from CLI parsing and top-level dispatch.
























# Top-level command handlers keep main focused on parsing and dispatch.

def _command_harness(args, root: Path, parser) -> None:
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

def _command_setup(args, root: Path, parser) -> None:
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

def _command_onboard(args, root: Path, parser) -> None:
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

def _command_adapter(args, root: Path, parser) -> None:
    from .core.adapters import list_adapters, install_adapter, remove_adapter, validate_manifest
    if args.adapter_action == "list": result = {"ok": True, "adapters": list_adapters()}
    elif args.adapter_action == "install": result = {"ok": True, "adapter": install_adapter(args.manifest)}
    elif args.adapter_action == "validate":
        result = {"ok": True, "adapter": validate_manifest(json.loads(Path(args.manifest).read_text(encoding="utf-8")))}
    else: result = {"ok": True, "removed": remove_adapter(args.name)}
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_service(args, root: Path, parser) -> None:
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

def _command_token(args, root: Path, parser) -> None:
    from .core.deployment import rotate_token
    result = rotate_token(role=args.role, projects=args.project,
        path=Path(args.file).expanduser() if args.file else None,
        keep_existing=args.keep_existing)
    if not args.show_token: result["token"] = "[stored; use --show-token only in a private terminal]"
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_restore(args, root: Path, parser) -> None:
    from .core.memory_admin import backup_memory, verify_backup, restore_memory
    if args.command == "backup": result = backup_memory(root, Path(args.output))
    elif args.command == "backup-verify": result = verify_backup(Path(args.backup))
    else: result = restore_memory(root, Path(args.backup), apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_init(args, root: Path, parser) -> None:
    from .core.deployment import initialize_project
    initialized = initialize_project(root)
    print(f"✓ Inicializado .graphtyn/ en {root}")
    if initialized["gitignore_added"]:
        print("✓ .graphtyn/ agregado a .gitignore")

def _command_reindex(args, root: Path, parser) -> None:
    profiles = {"fast": "ast_pure", "balanced": "ast_local_llm", "deep": "ast_cloud", "verified": "ast_cloud"}
    if args.mode:
        args.engine = profiles[args.mode]
    data = json.dumps({"path": str(root), "engine": args.engine,
                       "full": args.mode in {"deep", "verified"}}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:9210/api/reindex", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
    except Exception:
        from .core.deployment import build_local_index
        indexed = build_local_index(root)
        print(f"✓ Reindexado AST local completado ({args.mode or 'fast'}): {indexed['nodes']} nodos, {indexed['links']} conectores.")
    else:
        job_id = res.get("id")
        if job_id:
            while res.get("status") not in {"completed", "failed", "cancelled"}:
                time.sleep(0.5)
                status_req = urllib.request.Request(
                    f"http://127.0.0.1:9210/api/reindex/{job_id}")
                try:
                    with urllib.request.urlopen(status_req, timeout=15) as resp:
                        res = json.loads(resp.read().decode())
                except Exception as exc:
                    raise SystemExit(f"No se pudo consultar el trabajo {job_id}: {exc}")
            if res.get("status") != "completed":
                raise SystemExit(f"Reindexación {res.get('status')}: {res.get('error') or res.get('message')}")
            res = res.get("result") or {}
        mode = res.get("mode", "full")
        extra = ""
        if mode == "incremental":
            extra = f" · {res.get('changed_files', 0)} archivos cambiados · {res.get('enriched_files', 0)} archivos con contexto"
        print(f"✓ Reindexado ({args.engine}, modo {args.mode or mode}){extra}: {res.get('nodes')} nodos, {res.get('links')} conectores.")
    if args.mode == "verified":
        print(json.dumps(verify_python_edits(root), ensure_ascii=False))

def _command_query(args, root: Path, parser) -> None:
    ast_p = ASTParser()
    graph = ast_p.scan_directory(root)
    q = args.query_text.lower()
    matches = [n for n in graph["nodes"] if q in n["name"].lower() or q in n.get("details", "").lower()]
    print(json.dumps({"query": args.query_text, "matches": matches}, indent=2))

def _command_query_intent(args, root: Path, parser) -> None:
    graph = ASTParser().scan_directory(root, respect_git=True)
    from .core.source_evidence import attach_source_evidence
    result = query_intent(graph, args.request, args.intent, args.limit)
    result = attach_source_evidence(root, result, args.request, args.evidence_mode)
    result = attach_learning(result, root)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_analyze_change(args, root: Path, parser) -> None:
    graph = ASTParser().scan_directory(root, respect_git=True)
    result = analyze_change(graph, args.request, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_context(args, root: Path, parser) -> None:
    graph = ASTParser().scan_directory(root, respect_git=True)
    result = context_bundle(graph, args.symbols[:10], args.depth, args.limit)
    print(json.dumps(result, ensure_ascii=False))

def _command_path(args, root: Path, parser) -> None:
    ast_p = ASTParser()
    graph = ast_p.scan_directory(root)
    found_path = bfs_path(graph, args.start_symbol, args.end_symbol)
    if found_path:
        print(" -> ".join(found_path))
    else:
        print(f"No se encontró ruta entre '{args.start_symbol}' y '{args.end_symbol}'.")

def _command_explain(args, root: Path, parser) -> None:
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

def _command_diff(args, root: Path, parser) -> None:
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

def _command_ci_check(args, root: Path, parser) -> None:
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

def _command_verify_edit(args, root: Path, parser) -> None:
    result = verify_python_edits(root, args.base)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_validate_answer(args, root: Path, parser) -> None:
    graph = apply_decisions(ASTParser().scan_directory(root, respect_git=True), root)
    answer = Path(args.answer[1:]).read_text(encoding="utf-8") if args.answer.startswith("@") else args.answer
    print(json.dumps(validate_answer(graph, answer, project_root=root), ensure_ascii=False, indent=2))

def _command_impact(args, root: Path, parser) -> None:
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

def _command_review(args, root: Path, parser) -> None:
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

def _command_benchmark(args, root: Path, parser) -> None:
    truth = Path(args.ground_truth).resolve() if args.ground_truth else None
    cache = Path(args.cache).resolve() if args.cache else project_store_dir(data_home(), root) / "benchmark_structural_cache.json"
    result = run_benchmark(root, truth, cache)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(benchmark_markdown(result), end="")

def _command_agent_benchmark(args, root: Path, parser) -> None:
    result = compare_agent_runs(Path(args.treatment), Path(args.baseline))
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_benchmark_suite(args, root: Path, parser) -> None:
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

def _command_type_status(args, root: Path, parser) -> None:
    print(json.dumps({"path": str(root), "providers": provider_status(root),
                      "sidecar": str(root / ".graphtyn/type-evidence.json")},
                     ensure_ascii=False, indent=2))

def _command_agent_grade(args, root: Path, parser) -> None:
    result = grade_runs(Path(args.runs), Path(args.tasks))
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_benchmark_graphify(args, root: Path, parser) -> None:
    result = score_graphify(Path(args.graph), Path(args.ground_truth))
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _command_export_md(args, root: Path, parser) -> None:
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

def _command_report(args, root: Path, parser) -> None:
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

def _command_global(args, root: Path, parser) -> None:
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

def _command_memory(args, root: Path, parser) -> None:
    _handle_memory_command(args, root, parser)

def _command_agent_install(args, root: Path, parser) -> None:
    from .core.agent_installer import resolve_tool_profile
    from .core.project_integrations import project_integration_status
    profile = resolve_tool_profile(root, args.tool_profile)
    files = install_agent(root, args.platform, tool_profile=profile)
    status = project_integration_status(root)
    print(json.dumps({"ok": True, "platform": args.platform,
                      "project_id": status.get("project_id"), "mcp_server": status.get("mcp_server"),
                      "integrations": status.get("clients", []),
                      "runtime": status.get("runtime", {}),
                      "tool_profile": profile, "files": files}, ensure_ascii=False, indent=2))

def _command_integrations(args, root: Path, parser) -> None:
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

def _command_ci_install(args, root: Path, parser) -> None:
    output = install_ci(root, args.platform, args.max_risk)
    print(json.dumps({"ok": True, "platform": args.platform, "file": str(output)}, ensure_ascii=False, indent=2))

def _command_timeline(args, root: Path, parser) -> None:
    ht = HistoryTracker(root)
    events = ht.get_timeline(args.session_id)
    if not events:
        print("✓ No hay eventos registrados en la línea de tiempo de este proyecto.")
    else:
        print(f"🕒 Línea de tiempo de la sesión ({len(events)} eventos):")
        for ev in events:
            print(f"  [{ev['id']}] {ev['action_type'].upper()} — {ev['summary']}")

def _command_mcp(args, root: Path, parser) -> None:
    run_mcp_server(root, args.tool_profile)

def _command_serve(args, root: Path, parser) -> None:
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

def _command_gitignore(args, root: Path, parser) -> None:
    from .api.main import _save_project_config, _load_project_config
    cfg = _save_project_config(root, {"respect_git": args.value == "on"})
    state = "ON (solo archivos versionados)" if cfg["respect_git"] else "OFF (incluye ignorados por .gitignore)"
    print(f"✓ .gitignore por proyecto: {state} para {root}")
    print("  Reindexa para aplicar: graphtyn reindex --path .")

def _command_hook(args, root: Path, parser) -> None:
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

def main():
    configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.path if hasattr(args, "path") else ".").resolve()
    handlers = {
        'harness': _command_harness,
        'setup': _command_setup,
        'onboard': _command_onboard,
        'adapter': _command_adapter,
        'service': _command_service,
        'token': _command_token,
        'restore': _command_restore,
        'backup': _command_restore,
        'backup-verify': _command_restore,
        'init': _command_init,
        'reindex': _command_reindex,
        'query': _command_query,
        'query-intent': _command_query_intent,
        'analyze-change': _command_analyze_change,
        'context': _command_context,
        'path': _command_path,
        'explain': _command_explain,
        'diff': _command_diff,
        'pr-impact': _command_diff,
        'ci-check': _command_ci_check,
        'verify-edit': _command_verify_edit,
        'validate-answer': _command_validate_answer,
        'impact': _command_impact,
        'review': _command_review,
        'benchmark': _command_benchmark,
        'agent-benchmark': _command_agent_benchmark,
        'benchmark-suite': _command_benchmark_suite,
        'type-status': _command_type_status,
        'agent-grade': _command_agent_grade,
        'benchmark-graphify': _command_benchmark_graphify,
        'export-md': _command_export_md,
        'report': _command_report,
        'global': _command_global,
        'memory': _command_memory,
        'agent-install': _command_agent_install,
        'integrations': _command_integrations,
        'ci-install': _command_ci_install,
        'timeline': _command_timeline,
        'mcp': _command_mcp,
        'serve': _command_serve,
        'gitignore': _command_gitignore,
        'hook': _command_hook,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return
    handler(args, root, parser)

if __name__ == "__main__":
    main()
