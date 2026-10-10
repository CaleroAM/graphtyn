"""Execution handlers for the ``graphtyn memory`` CLI family."""

from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import threading
import time
from pathlib import Path

from .core.history_import import (
    ProjectIdentityRegistry, configured_sources, delete_source, discover_histories,
    import_histories, import_history_archive, save_source, sync_memory_workspace, test_source,
)
from .core.memory_benchmark import (
    build_scale_dataset, build_stability_dataset, run_memory_benchmark,
)
from .core.memory_scale_benchmark import run_scale_benchmark
from .core.project_evaluation import evaluate_project
from .core.shared_memory import (
    MemoryStoreConflictError, SharedMemoryStore, existing_store_db,
)
from .core.storage import atomic_write_json, data_home
from .core.work_memory import reflect, save_result

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

def _memory_brain_init(args, root: Path, parser) -> None:
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

def _memory_consolidate(args, root: Path, parser) -> None:
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

def _memory_scope(args, root: Path, parser) -> None:
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

def _memory_alias_import(args, root: Path, parser) -> None:
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

def _memory_stores(args, root: Path, parser) -> None:
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

def _memory_bootstrap(args, root: Path, parser) -> None:
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

def _memory_projects(args, root: Path, parser) -> None:
    from .core.project_integrations import ensure_project_identity
    current = ensure_project_identity(Path(args.path), aliases=args.alias)
    print(json.dumps({"ok": True, "current": current,
                      "projects": ProjectIdentityRegistry().list()}, ensure_ascii=False, indent=2))

def _memory_sources(args, root: Path, parser) -> None:
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

def _memory_agents(args, root: Path, parser) -> None:
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

def _memory_save(args, root: Path, parser) -> None:
    output = save_result(root, args.question, args.answer, args.nodes, args.outcome, args.files, args.correction)
    print(json.dumps({"ok": True, "saved": str(output)}, ensure_ascii=False))

def _memory_reflect(args, root: Path, parser) -> None:
    print(json.dumps(reflect(root, args.half_life_days), ensure_ascii=False, indent=2))

def _memory_store_action(args, root: Path, parser) -> None:
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
    elif args.memory_action == "evidence-status":
        result = memory.evidence_status(args.memory, requester_agent=args.agent, limit=args.limit)
    elif args.memory_action == "run-local":
        command = list(args.run_command)
        if command[:1] == ["--"]:
            command = command[1:]
        if not command:
            raise SystemExit("memory run-local requiere un comando después de --")
        result = memory.run_local_execution(
            command, timeout=args.timeout, executor=args.executor,
            test_files=args.test, data_files=args.data,
            declared_dependencies=args.dependency,
        )
    elif args.memory_action == "migrate-evidence":
        result = memory.migrate_evidence_provenance(preview=not args.apply)
    elif args.memory_action == "correct":
        result = memory.correct(args.memory, args.session, args.title, args.content)
    elif args.memory_action == "forget":
        result = memory.forget(args.memory, requester_agent=args.agent, physical=args.physical)
    elif args.memory_action == "doctor":
        result = memory.project_doctor()
    elif args.memory_action == "export":
        result = memory.export_snapshot(include_messages=args.include_messages)
        output = Path(args.output).expanduser().resolve()
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {"ok": True, "output": str(output), "memories": len(result["memories"]),
                  "sessions": len(result["sessions"])}
    elif args.memory_action == "retention":
        result = memory.apply_retention(args.days, statuses=args.statuses, dry_run=not args.apply)
    elif args.memory_action == "benchmark":
        dataset = (build_stability_dataset() if args.suite == "stability" else
                   build_scale_dataset(args.records, args.query_count, args.query_profile) if args.suite == "scale" else
                   json.loads(Path(args.dataset).expanduser().resolve().read_text(encoding="utf-8")))
        output = Path(args.output).expanduser().resolve() if args.output else None
        result = (run_scale_benchmark(dataset, repetitions=args.repetitions, output=output)
                  if args.suite == "scale" else run_memory_benchmark(dataset, output))
    elif args.memory_action == "project-evaluation":
        output = Path(args.output).expanduser().resolve() if args.output else None
        result = evaluate_project(root, output=output)
    else:
        result = memory.compact_session(args.session, args.provider)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def _discover_all_space_targets():
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

def _memory_sync_targets(args):
    from .core.openclaw_integration import paths_for_installation
    if args.installation:
        return [Path(item).expanduser().resolve()
                for item in paths_for_installation(args.installation)]
    if args.all_spaces:
        return _discover_all_space_targets()[0]
    return [Path(args.path).expanduser().resolve()]

def _memory_sync_path(args, path: Path):
    return sync_memory_workspace(path, provider=args.provider,
        source=args.source or None, provider_model=args.provider_model,
        agent_id=args.agent_id)

def _memory_sync_once(args):
    if args.installation:
        results = []
        for path in _memory_sync_targets(args):
            try:
                results.append(_memory_sync_path(args, path))
            except MemoryStoreConflictError as exc:
                results.append({"ok": False, "path": str(path),
                                "code": "memory_store_conflict", "error": str(exc)})
        return {"ok": all(item.get("ok", False) for item in results),
                "spaces": results, "space_count": len(results),
                "failed_spaces": sum(not item.get("ok", False) for item in results)}
    if args.all_spaces:
        paths, conflicts = _discover_all_space_targets()
        results = [{"ok": False, **item} for item in conflicts]
        for path in paths:
            try:
                results.append(_memory_sync_path(args, path))
            except MemoryStoreConflictError as exc:
                results.append({"ok": False, "path": str(path),
                                "code": "memory_store_conflict", "error": str(exc)})
        return {"ok": all(item.get("ok", False) for item in results),
                "spaces": results, "space_count": len(results),
                "failed_spaces": sum(not item.get("ok", False) for item in results)}
    return _memory_sync_path(args, Path(args.path).expanduser().resolve())

def _watch_memory_sync(args) -> None:
    watcher_id = f"cli-sync:{os.getpid()}"
    interval = max(1.0, float(args.interval))

    def update_watchers(status, error="", cycle_result=None):
        for path in _memory_sync_targets(args):
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
        for path in _memory_sync_targets(args):
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
            heartbeat_stop = threading.Event()

            def keep_heartbeat():
                while not heartbeat_stop.wait(min(10.0, interval)):
                    try:
                        update_watchers("processing")
                    except (OSError, RuntimeError, sqlite3.Error):
                        # The synchronization cycle owns the useful
                        # work; a transient heartbeat lock must not
                        # terminate the watcher.
                        continue

            heartbeat = threading.Thread(
                target=keep_heartbeat, name="graphtyn-sync-heartbeat", daemon=True)
            heartbeat.start()
            try:
                result = _memory_sync_once(args)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                result = {"ok": False, "error": error}
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=1)
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

def _memory_sync(args, root: Path, parser) -> None:
    if args.watch:
        _watch_memory_sync(args)
    else:
        print(json.dumps(_memory_sync_once(args), ensure_ascii=False, indent=2))

def _handle_memory_command(args, root: Path, parser) -> None:
    handlers = {
        "brain-init": _memory_brain_init, "consolidate": _memory_consolidate,
        "scope": _memory_scope, "alias-import": _memory_alias_import,
        "stores": _memory_stores, "bootstrap": _memory_bootstrap,
        "projects": _memory_projects, "sync": _memory_sync,
        "sources": _memory_sources, "agents": _memory_agents,
        "save": _memory_save, "reflect": _memory_reflect,
    }
    handlers.get(args.memory_action, _memory_store_action)(args, root, parser)
