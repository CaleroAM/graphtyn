"""Safe, resumable transfer of one agent's legacy brain into its active brain.

Legacy stores remain untouched.  The destination receives consented sessions,
messages and memories with historical provenance; a SQLite online backup of
both stores is kept before the first write.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from .memory_scope import resolve_memory_scope
from .shared_memory import CAPTURE_ROLES, SharedMemoryStore, _resolve_store_path, existing_store_db
from .storage import atomic_write_json, secure_private_file


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _archive_key(archive_id: str, agent_id: str, kind: str,
                 session_id: str = "", record_id: str = "", digest: str = "") -> str:
    return "legacy-brain:" + _digest([archive_id, agent_id, kind, session_id, record_id, digest])


def _readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()), safe='/:')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _memory_paths(source_path: str | Path, target_path: str | Path, agent_id: str):
    source = Path(source_path).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()
    agent = str(agent_id or "").strip().casefold()
    if not agent or not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]{1,127}", agent):
        raise ValueError("agent_id debe ser la identidad canónica completa")
    if source == target:
        raise ValueError("el archivo histórico y el cerebro activo deben ser espacios distintos")
    policy = resolve_memory_scope(target)
    if policy["space_type"] != "agent_brain" or not policy["restricted"]:
        raise ValueError("el destino debe estar registrado como cerebro de agente")
    if agent not in set(policy["agent_ids"]):
        raise PermissionError("el agente no es propietario explícito del cerebro de destino")
    source_db = existing_store_db(source)
    if not source_db:
        raise FileNotFoundError("el archivo histórico no contiene memory-v2.db")
    target_db = existing_store_db(target)
    return source, target, source_db, target_db, agent


def _summarize_db(db_path: Path, agent_id: str) -> dict:
    with closing(_readonly(db_path)) as db:
        tables = _tables(db)
        required = {"sessions", "messages", "memories"}
        if not required.issubset(tables):
            raise ValueError("el archivo legado no usa un esquema de memoria compatible")
        sessions = int(db.execute("""SELECT COUNT(*) FROM sessions s
            WHERE lower(s.agent_id)=? AND s.status!='quarantined' AND (s.capture_enabled=1 OR EXISTS
              (SELECT 1 FROM memories m WHERE m.session_id=s.id AND lower(m.agent_id)=?
               AND m.status NOT IN ('deleted','quarantined')))""",
            (agent_id, agent_id)).fetchone()[0])
        conversation_sessions = int(db.execute("""SELECT COUNT(*) FROM sessions
            WHERE lower(agent_id)=? AND status!='quarantined' AND capture_enabled=1""",
            (agent_id,)).fetchone()[0])
        memory_only_sessions = max(0, sessions - conversation_sessions)
        excluded_sessions = int(db.execute("""SELECT COUNT(*) FROM sessions s
            WHERE lower(s.agent_id)=? AND (s.status='quarantined' OR (s.capture_enabled=0 AND NOT EXISTS
              (SELECT 1 FROM memories m WHERE m.session_id=s.id AND lower(m.agent_id)=?
               AND m.status NOT IN ('deleted','quarantined'))))""",
            (agent_id, agent_id)).fetchone()[0])
        messages = int(db.execute("""SELECT COALESCE(SUM((SELECT COUNT(*) FROM messages m
            WHERE m.session_id=s.id AND lower(m.agent_id)=? AND m.role IN ('user','assistant','tool'))),0)
            FROM sessions s WHERE lower(s.agent_id)=? AND s.status!='quarantined' AND s.capture_enabled=1""",
            (agent_id, agent_id)).fetchone()[0])
        excluded_messages = int(db.execute("""SELECT COALESCE(SUM((SELECT COUNT(*) FROM messages m
            WHERE m.session_id=s.id AND m.role NOT IN ('user','assistant','tool'))),0)
            FROM sessions s WHERE lower(s.agent_id)=? AND s.status!='quarantined' AND s.capture_enabled=1""",
            (agent_id,)).fetchone()[0])
        memories = int(db.execute("""SELECT COALESCE(SUM((SELECT COUNT(*) FROM memories m
            WHERE m.session_id=s.id AND lower(m.agent_id)=?
              AND m.status NOT IN ('deleted','quarantined'))),0)
            FROM sessions s WHERE lower(s.agent_id)=? AND s.status!='quarantined'""",
            (agent_id, agent_id)).fetchone()[0])
        topics = 0
        relations = reviews = 0
        if "topic_episodes" in tables and "topics" in tables:
            topics = int(db.execute("""SELECT COUNT(DISTINCT e.topic_id) FROM topic_episodes e
                JOIN sessions s ON s.id=e.session_id WHERE lower(e.agent_id)=?
                AND lower(s.agent_id)=? AND s.status!='quarantined' AND s.capture_enabled=1""",
                (agent_id, agent_id)).fetchone()[0])
            if "topic_relations" in tables:
                relations = int(db.execute("""SELECT COUNT(*) FROM topic_relations r
                    WHERE EXISTS (SELECT 1 FROM topic_episodes e JOIN sessions s ON s.id=e.session_id
                        WHERE e.topic_id=r.source_topic_id AND lower(e.agent_id)=? AND lower(s.agent_id)=?
                          AND s.status!='quarantined' AND s.capture_enabled=1)
                      AND EXISTS (SELECT 1 FROM topic_episodes e JOIN sessions s ON s.id=e.session_id
                        WHERE e.topic_id=r.target_topic_id AND lower(e.agent_id)=? AND lower(s.agent_id)=?
                          AND s.status!='quarantined' AND s.capture_enabled=1)""",
                    (agent_id, agent_id, agent_id, agent_id)).fetchone()[0])
            if "topic_relation_reviews" in tables:
                reviews = int(db.execute("""SELECT COUNT(*) FROM topic_relation_reviews r
                    WHERE EXISTS (SELECT 1 FROM topic_episodes e JOIN sessions s ON s.id=e.session_id
                        WHERE e.topic_id=r.source_topic_id AND lower(e.agent_id)=? AND lower(s.agent_id)=?
                          AND s.status!='quarantined' AND s.capture_enabled=1)
                      AND EXISTS (SELECT 1 FROM topic_episodes e JOIN sessions s ON s.id=e.session_id
                        WHERE e.topic_id=r.target_topic_id AND lower(e.agent_id)=? AND lower(s.agent_id)=?
                          AND s.status!='quarantined' AND s.capture_enabled=1)""",
                    (agent_id, agent_id, agent_id, agent_id)).fetchone()[0])
    return {"sessions": sessions, "conversation_sessions": conversation_sessions,
            "memory_only_sessions": memory_only_sessions, "messages": messages, "memories": memories,
            "topics": topics, "relations": relations, "reviews": reviews,
            "excluded_sessions": excluded_sessions,
            "excluded_messages": excluded_messages}


def preview_legacy_consolidation(source_path: str | Path, target_path: str | Path,
                                 agent_id: str, archive_id: str) -> dict:
    """Read-only estimate; requires an exact active-brain owner mapping."""
    archive = str(archive_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", archive):
        raise ValueError("archive_id inválido")
    source, target, source_db, target_db, agent = _memory_paths(source_path, target_path, agent_id)
    incoming = _summarize_db(source_db, agent)
    already = {"sessions": 0, "messages": 0, "memories": 0, "topics": 0,
               "relations": 0, "reviews": 0}
    if target_db:
        with closing(_readonly(target_db)) as db:
            if "legacy_consolidation_items" in _tables(db):
                rows = db.execute("""SELECT record_kind,COUNT(*) FROM legacy_consolidation_items
                    WHERE archive_id=? AND agent_id=? GROUP BY record_kind""", (archive, agent)).fetchall()
                counts = {str(row[0]): int(row[1]) for row in rows}
                already.update({key: counts.get(value, 0) for key, value in
                                (("sessions", "session"), ("messages", "message"),
                                 ("memories", "memory"), ("topics", "topic"))})
                already["relations"] = counts.get("topic_relation", 0) + counts.get("topic_relation_memory", 0)
                already["reviews"] = counts.get("topic_relation_review", 0) + counts.get("topic_relation_review_memory", 0)
    return {"ok": True, "dry_run": True, "archive_id": archive, "agent_id": agent,
            "source": str(source), "source_db": str(source_db), "target": str(target),
            "target_db": str(target_db) if target_db else None, "eligible": incoming,
            "already_imported": already,
            "will_import": {key: max(0, value - already.get(key, 0))
                            for key, value in incoming.items()
                            if key in {"sessions", "messages", "memories", "topics", "relations", "reviews"}},
            "preservation": ["transcripciones y recuerdos mantienen fecha y agente",
                             "temas actuales se recalculan desde sus mensajes",
                             "estado histórico del tema se conserva como recuerdo histórico",
                             "mensajes sin consentimiento se excluyen; recuerdos explícitos de sesiones sin transcript sí se preservan",
                             "sesiones en cuarentena se excluyen"],
            "source_unchanged": True}


def _snapshot(db_path: Path, output_dir: Path, label: str) -> tuple[str, str]:
    """Create a verified SQLite online backup without opening the source writable."""
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        output_dir.chmod(0o700)
    except OSError:
        pass
    temp_path = output_dir / f".{label}.{uuid.uuid4().hex}.tmp.db"
    uri = f"file:{quote(str(db_path.resolve()), safe='/:')}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as source:
            with closing(sqlite3.connect(temp_path)) as target:
                source.backup(target, pages=256, sleep=0.01)
                check = target.execute("PRAGMA integrity_check").fetchone()[0]
                if check != "ok":
                    raise RuntimeError(f"la copia SQLite no supera integrity_check: {check}")
        digest = hashlib.sha256()
        with temp_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        sha = digest.hexdigest()
        destination = output_dir / f"{label}-{sha[:16]}.db"
        if destination.exists():
            temp_path.unlink()
        else:
            os.replace(temp_path, destination)
        try:
            secure_private_file(destination)
        except OSError:
            destination.chmod(0o600)
        atomic_write_json(destination.with_suffix(".db.json"),
                          {"format": "sqlite-online-backup-v1", "sha256": sha,
                           "bytes": destination.stat().st_size, "created_at": time.time(),
                           "source_name": db_path.name})
        return str(destination), sha
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _ledger_get(store: SharedMemoryStore, key: str) -> str | None:
    with store._connect() as db:
        row = db.execute("SELECT target_id FROM legacy_consolidation_items WHERE source_key=?",
                         (key,)).fetchone()
    return str(row[0]) if row else None


def _ledger_record(store: SharedMemoryStore, *, key: str, run_id: str, archive_id: str,
                   agent_id: str, kind: str, session_id: str = "", record_id: str = "",
                   digest: str = "", target_id: str) -> None:
    with store._connect() as db:
        db.execute("""INSERT OR IGNORE INTO legacy_consolidation_items
            (source_key,run_id,archive_id,agent_id,record_kind,source_session_id,
             source_record_id,source_digest,target_id,imported_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (key, run_id, archive_id, agent_id, kind, session_id, record_id,
             digest, target_id, time.time()))


def _target_session_id(store: SharedMemoryStore, archive_id: str, agent_id: str,
                       source_session_id: str) -> str | None:
    key = _archive_key(archive_id, agent_id, "session", source_session_id)
    return _ledger_get(store, key)


def _decode(store: SharedMemoryStore, value: str) -> str:
    decoded = store._unprotect(str(value or ""))
    if str(value or "").startswith("enc:v1:") and decoded.startswith("[encrypted:"):
        raise ValueError("el legado está cifrado con otra clave; configura la clave original antes de migrar")
    return decoded


def _parse_json(value: str, default):
    try:
        result = json.loads(value or "")
        return result if isinstance(result, type(default)) else default
    except (TypeError, ValueError):
        return default


def _message_digest(row: sqlite3.Row) -> str:
    return _digest([row["role"], row["content"], row["event_type"],
                    row["metadata_json"], row["created_at"]])


def _memory_digest(row: sqlite3.Row) -> str:
    return _digest([row["kind"], row["scope"], row["status"], row["title"], row["content"],
                    row["files_json"], row["node_ids_json"], row["tests_json"],
                    row["metadata_json"], row["supersedes_id"], row["updated_at"]])


def consolidate_legacy_brain(source_path: str | Path, target_path: str | Path, *,
                             agent_id: str, archive_id: str, consent: bool,
                             dry_run: bool = False, batch_size: int = 100,
                             progress=None) -> dict:
    """Consolidate one explicit agent from a legacy store into its active brain.

    Re-running resumes from a per-record ledger in the destination.  The legacy
    database is only read, and its verified online backup is retained there.
    """
    if not consent and not dry_run:
        raise PermissionError("la consolidación requiere consentimiento explícito")
    preview = preview_legacy_consolidation(source_path, target_path, agent_id, archive_id)
    if dry_run:
        return preview
    if not preview["eligible"]["sessions"]:
        return {**preview, "dry_run": False, "imported": {"sessions": 0, "messages": 0,
                "memories": 0, "topics": 0}, "message": "No hay sesiones autorizadas para migrar."}

    source_root, target_root = Path(preview["source"]), Path(preview["target"])
    source_db, target_db = Path(preview["source_db"]), Path(preview["target_db"]) if preview["target_db"] else None
    archive = preview["archive_id"]
    agent = preview["agent_id"]
    dest_hint = target_db or _resolve_store_path(target_root, create=False)
    backup_dir = dest_hint.parent / "legacy-backups"
    safe_archive = re.sub(r"[^A-Za-z0-9._-]+", "_", archive)[:60] or "archive"
    safe_agent = hashlib.sha256(agent.encode()).hexdigest()[:10]
    source_backup, source_sha = _snapshot(source_db, backup_dir,
                                          f"{safe_archive}-{safe_agent}-source")
    target_backup = ""
    if target_db:
        target_backup, _ = _snapshot(target_db, backup_dir,
                                     f"{safe_archive}-{safe_agent}-target-before")

    # Import from the stable snapshot, so later source changes cannot shift the
    # cursor beneath an in-progress or resumed migration.
    with closing(_readonly(Path(source_backup))) as source:
        snapshot_summary = _summarize_db(Path(source_backup), agent)
        destination = SharedMemoryStore(target_root)
        policy = destination.memory_scope()
        if policy["space_type"] != "agent_brain" or agent not in set(policy["agent_ids"]):
            raise PermissionError("la política del cerebro activo cambió antes de importar")

        now, run_id = time.time(), f"mig_{uuid.uuid4().hex}"
        with destination._connect() as db:
            db.execute("UPDATE legacy_consolidation_runs SET status='interrupted',updated_at=? WHERE status='running' AND archive_id=? AND agent_id=?",
                       (now, archive, agent))
            db.execute("""INSERT INTO legacy_consolidation_runs
                (id,archive_id,archive_path,source_db,target_path,agent_id,status,
                 source_backup,target_backup,report_json,started_at,updated_at)
                VALUES(?,?,?,?,?,?,'running',?,?, '{}',?,?)""",
                (run_id, archive, str(source_root), str(source_db), str(target_root), agent,
                 source_backup, target_backup, now, now))

        totals = {"sessions": 0, "messages": 0, "memories": 0, "topics": 0,
                  "events": 0, "relations": 0, "reviews": 0, "provenance": 0,
                  "skipped_messages": 0, "skipped_memories": 0,
                  "errors": []}
        processed = 0
        batch_size = max(1, min(1000, int(batch_size)))

        def report(status="running"):
            with destination._connect() as db:
                db.execute("UPDATE legacy_consolidation_runs SET status=?,report_json=?,updated_at=? WHERE id=?",
                           (status, _json(totals), time.time(), run_id))

        session_rows = source.execute("""SELECT * FROM sessions s WHERE lower(s.agent_id)=?
            AND s.status!='quarantined' AND (s.capture_enabled=1 OR EXISTS
              (SELECT 1 FROM memories m WHERE m.session_id=s.id AND lower(m.agent_id)=?
               AND m.status NOT IN ('deleted','quarantined'))) ORDER BY s.started_at,s.id""", (agent, agent))
        for source_session in session_rows:
            source_sid = str(source_session["id"])
            task = str(source_session["task"] or "Historial histórico")
            session_key = _archive_key(archive, agent, "session", source_sid)
            target_sid = _ledger_get(destination, session_key)
            if not target_sid:
                external_id = f"legacy:{archive}:{source_sid}"
                session = destination.ensure_external_session(agent, external_id, task,
                                                               consent=True, branch=source_session["branch"],
                                                               reopen_closed=True)
                target_sid = session["id"]
                started = float(source_session["started_at"] or now)
                ended = source_session["ended_at"]
                with destination._connect() as db:
                    db.execute("""UPDATE sessions SET task=?,branch=?,base_commit=?,worktree=?,
                        capture_enabled=1,started_at=?,ended_at=?,status='closed' WHERE id=?""",
                        (task, source_session["branch"], source_session["base_commit"],
                         str(target_root), started, float(ended) if ended is not None else started,
                         target_sid))
                    destination._audit(db, "legacy_session_consolidated", agent, target_sid, None,
                                       {"archive_id": archive, "source_session_id": source_sid,
                                        "capture_mode": "historical_import", "source_sha256": source_sha})
                _ledger_record(destination, key=session_key, run_id=run_id, archive_id=archive,
                               agent_id=agent, kind="session", session_id=source_sid,
                               record_id=source_sid, target_id=target_sid)
                totals["sessions"] += 1

            source_messages = source.execute("""SELECT * FROM messages WHERE session_id=?
                AND lower(agent_id)=? ORDER BY created_at,rowid""", (source_sid, agent)) if source_session["capture_enabled"] else []
            for message in source_messages:
                role = str(message["role"] or "").casefold()
                if role not in CAPTURE_ROLES:
                    totals["skipped_messages"] += 1
                    continue
                digest = _message_digest(message)
                old_message_id = str(message["id"])
                message_key = _archive_key(archive, agent, "message", source_sid,
                                            old_message_id, digest)
                if _ledger_get(destination, message_key):
                    continue
                metadata = _parse_json(message["metadata_json"], {})
                occurred = float(message["created_at"] or source_session["started_at"] or now)
                metadata.update({"source_message_id": f"legacy:{archive}:{old_message_id}:{digest[:12]}",
                                "legacy_source_message_id": old_message_id,
                                "legacy_source_session_id": source_sid,
                                "legacy_archive_id": archive,
                                "capture_mode": "historical_import", "occurred_at": occurred,
                                "historical_source": f"legacy-archive:{archive}"})
                try:
                    copied = destination.append_message(target_sid, role, _decode(destination, message["content"]),
                        event_type=message["event_type"], metadata=metadata)
                    _ledger_record(destination, key=message_key, run_id=run_id, archive_id=archive,
                                   agent_id=agent, kind="message", session_id=source_sid,
                                   record_id=old_message_id, digest=digest, target_id=copied["id"])
                    totals["messages"] += 1
                except Exception as exc:
                    totals["errors"].append({"kind": "message", "source_id": old_message_id,
                                             "session_id": source_sid, "error": str(exc)[:300]})
                processed += 1
                if processed % batch_size == 0:
                    report()
                    percent = min(90, int(processed * 80 /
                                  max(1, snapshot_summary["messages"] + snapshot_summary["memories"])))
                    if progress and progress(percent,
                            f"Importados {totals['messages']} mensajes y {totals['memories']} recuerdos") is False:
                        report("paused")
                        return {**preview, "dry_run": False, "paused": True, "run_id": run_id,
                                "imported": totals, "source_backup": source_backup,
                                "target_backup": target_backup}

            if "memories" in _tables(source):
                memories = source.execute("""SELECT * FROM memories WHERE session_id=? AND lower(agent_id)=?
                    AND status NOT IN ('deleted','quarantined') ORDER BY created_at,id""", (source_sid, agent))
                for memory in memories:
                    old_memory_id = str(memory["id"])
                    digest = _memory_digest(memory)
                    memory_key = _archive_key(archive, agent, "memory", source_sid,
                                              old_memory_id, digest)
                    if _ledger_get(destination, memory_key):
                        continue
                    metadata = _parse_json(memory["metadata_json"], {})
                    legacy_status = str(memory["status"] or "observed")
                    status = "observed" if legacy_status == "verified" else legacy_status
                    if status not in {"proposed", "observed", "contested", "superseded"}:
                        status = "observed"
                    original_title = _decode(destination, memory["title"])
                    original_content = _decode(destination, memory["content"])
                    source_ref = ""
                    if "memory_node_references" in _tables(source):
                        ref = source.execute("SELECT reference FROM memory_node_references WHERE node_id=?",
                                              (old_memory_id,)).fetchone()
                        source_ref = str(ref[0]) if ref else ""
                    metadata.update({"capture_mode": "historical_import", "legacy_archive_id": archive,
                                     "legacy_memory_id": old_memory_id,
                                     "legacy_status": legacy_status,
                                     "legacy_scope": str(memory["scope"] or ""),
                                     "legacy_node_reference": source_ref,
                                     "occurred_at": float(memory["created_at"] or now),
                                     "historical_source": f"legacy-archive:{archive}"})
                    old_sources = metadata.get("source_message_ids") or []
                    mapped_sources = []
                    for old_msg_id in old_sources if isinstance(old_sources, list) else []:
                        old_msg = source.execute("SELECT * FROM messages WHERE id=? AND lower(agent_id)=?",
                                                 (str(old_msg_id), agent)).fetchone()
                        if not old_msg:
                            continue
                        msg_key = _archive_key(archive, agent, "message", str(old_msg["session_id"]),
                                               str(old_msg["id"]), _message_digest(old_msg))
                        target_msg = _ledger_get(destination, msg_key)
                        if target_msg:
                            mapped_sources.append(target_msg)
                    metadata["source_message_ids"] = sorted(set(mapped_sources))
                    supersedes = None
                    if memory["supersedes_id"]:
                        with destination._connect() as db:
                            parent = db.execute("""SELECT target_id FROM legacy_consolidation_items
                                WHERE archive_id=? AND agent_id=? AND record_kind='memory'
                                  AND source_record_id=? ORDER BY imported_at LIMIT 1""",
                                (archive, agent, str(memory["supersedes_id"]))).fetchone()
                        supersedes = parent[0] if parent else None
                        metadata["legacy_supersedes_id"] = str(memory["supersedes_id"])
                    source_kind = str(memory["kind"])
                    target_kind = source_kind if source_kind in {"episodic", "decision", "fact",
                        "procedure", "outcome", "correction", "handoff", "profile"} else "fact"
                    if target_kind != source_kind:
                        metadata["legacy_kind"] = source_kind
                    try:
                        copied = destination.checkpoint(target_sid, target_kind,
                            f"[Histórico] {original_title}"[:500], original_content,
                            scope="private", status=status, confidence=float(memory["confidence"] or .5),
                            files=_parse_json(memory["files_json"], []),
                            node_ids=_parse_json(memory["node_ids_json"], []),
                            tests=_parse_json(memory["tests_json"], []),
                            observed_commit=memory["observed_commit"], metadata=metadata,
                            supersedes_id=supersedes)
                        _ledger_record(destination, key=memory_key, run_id=run_id, archive_id=archive,
                                       agent_id=agent, kind="memory", session_id=source_sid,
                                       record_id=old_memory_id, digest=digest, target_id=copied["id"])
                        totals["memories"] += 1
                    except Exception as exc:
                        totals["errors"].append({"kind": "memory", "source_id": old_memory_id,
                                                 "session_id": source_sid, "error": str(exc)[:300]})
                    processed += 1
                    if processed % batch_size == 0:
                        report()
                        percent = min(90, int(processed * 80 /
                                      max(1, snapshot_summary["messages"] + snapshot_summary["memories"])))
                        if progress and progress(percent,
                                f"Importados {totals['messages']} mensajes y {totals['memories']} recuerdos") is False:
                            report("paused")
                            return {**preview, "dry_run": False, "paused": True, "run_id": run_id,
                                    "imported": totals, "source_backup": source_backup,
                                    "target_backup": target_backup}

            # Topic extraction in the destination creates current, queryable
            # episodes from the imported message windows.
            target_row = destination.get_session(target_sid)
            if target_row and source_session["capture_enabled"] and source.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id=?", (source_sid,)).fetchone()[0]:
                try:
                    destination.process_topics(target_sid)
                except Exception as exc:
                    totals["errors"].append({"kind": "topic_processing", "session_id": source_sid,
                                             "error": str(exc)[:300]})

        # Preserve multi-session memory provenance. Each reference is remapped
        # to the destination's message/session IDs; source IDs remain in the
        # memory's historical metadata for audit.
        if "memory_provenance" in _tables(source):
            provenance_rows = source.execute("""SELECT p.* FROM memory_provenance p
                JOIN memories m ON m.id=p.memory_id WHERE lower(p.agent_id)=?
                  AND lower(m.agent_id)=? AND m.status NOT IN ('deleted','quarantined')
                ORDER BY p.observed_at,p.memory_id,p.session_id""", (agent, agent))
            for provenance in provenance_rows:
                old_memory = source.execute("SELECT * FROM memories WHERE id=? AND lower(agent_id)=?",
                                            (provenance["memory_id"], agent)).fetchone()
                if not old_memory:
                    continue
                digest = _memory_digest(old_memory)
                memory_key = _archive_key(archive, agent, "memory", str(old_memory["session_id"]),
                                          str(old_memory["id"]), digest)
                target_memory = _ledger_get(destination, memory_key)
                target_provenance_session = _target_session_id(destination, archive, agent,
                                                               str(provenance["session_id"]))
                if not target_memory or not target_provenance_session:
                    continue
                old_ids = _parse_json(provenance["source_message_ids_json"], [])
                mapped_ids = []
                for old_message_id in old_ids if isinstance(old_ids, list) else []:
                    old_message = source.execute("SELECT * FROM messages WHERE id=? AND lower(agent_id)=?",
                                                 (str(old_message_id), agent)).fetchone()
                    if not old_message:
                        continue
                    message_key = _archive_key(archive, agent, "message",
                        str(old_message["session_id"]), str(old_message["id"]), _message_digest(old_message))
                    mapped_id = _ledger_get(destination, message_key)
                    if mapped_id:
                        mapped_ids.append(mapped_id)
                prov_digest = _digest([target_memory, target_provenance_session, sorted(set(mapped_ids))])
                prov_key = _archive_key(archive, agent, "provenance", str(provenance["session_id"]),
                                        str(provenance["memory_id"]), prov_digest)
                if _ledger_get(destination, prov_key):
                    continue
                with destination._connect() as db:
                    db.execute("""INSERT OR IGNORE INTO memory_provenance
                        (memory_id,session_id,agent_id,source_message_ids_json,observed_at)
                        VALUES(?,?,?,?,?)""",
                        (target_memory, target_provenance_session, agent, _json(sorted(set(mapped_ids))),
                         float(provenance["observed_at"] or now)))
                _ledger_record(destination, key=prov_key, run_id=run_id, archive_id=archive,
                               agent_id=agent, kind="provenance", session_id=str(provenance["session_id"]),
                               record_id=str(provenance["memory_id"]), digest=prov_digest,
                               target_id=target_memory)
                totals["provenance"] += 1

        # Retain the former topic title, state, verification and event history
        # as explicitly historical memories. The live topic graph above is
        # rebuilt from messages, avoiding stale source IDs in the active graph.
        if {"topics", "topic_episodes"}.issubset(_tables(source)):
            topic_rows = source.execute("""SELECT DISTINCT t.* FROM topics t
                JOIN topic_episodes e ON e.topic_id=t.id JOIN sessions s ON s.id=e.session_id
                WHERE lower(e.agent_id)=? AND lower(s.agent_id)=? AND s.status!='quarantined'
                  AND s.capture_enabled=1 ORDER BY t.created_at,t.id""", (agent, agent))
            for topic in topic_rows:
                topic_id = str(topic["id"])
                topic_key = _archive_key(archive, agent, "topic", "", topic_id,
                                         _digest([topic["title"], topic["summary"], topic["state"], topic["verification"]]))
                latest = source.execute("""SELECT e.session_id FROM topic_episodes e
                    JOIN sessions s ON s.id=e.session_id WHERE e.topic_id=? AND lower(e.agent_id)=?
                      AND s.status!='quarantined' AND s.capture_enabled=1
                    ORDER BY e.created_at DESC,e.id DESC LIMIT 1""", (topic_id, agent)).fetchone()
                target_topic_session = _target_session_id(destination, archive, agent,
                                                          str(latest[0])) if latest else None
                if not target_topic_session:
                    continue
                title = _decode(destination, topic["title"])
                summary = _decode(destination, topic["summary"])
                body = (f"Resumen histórico: {summary}\nEstado al archivar: {topic['state']}\n"
                        f"Verificación al archivar: {topic['verification']}\n"
                        f"Categoría: {topic['category']}\nReferencia de origen: {topic_id}")
                metadata = {"capture_mode": "historical_import", "legacy_archive_id": archive,
                            "legacy_topic_id": topic_id, "legacy_topic_state": topic["state"],
                            "legacy_topic_verification": topic["verification"],
                            "occurred_at": float(topic["updated_at"] or topic["created_at"] or now),
                            "historical_source": f"legacy-archive:{archive}"}
                if not _ledger_get(destination, topic_key):
                    try:
                        copied = destination.checkpoint(target_topic_session, "episodic",
                            f"[Tema histórico] {title}"[:500], body[:48000], scope="private",
                            status="observed", confidence=.7, metadata=metadata)
                        _ledger_record(destination, key=topic_key, run_id=run_id, archive_id=archive,
                                       agent_id=agent, kind="topic", record_id=topic_id,
                                       digest=topic_key.rsplit(":", 1)[-1], target_id=copied["id"])
                        totals["topics"] += 1
                    except Exception as exc:
                        totals["errors"].append({"kind": "topic", "source_id": topic_id,
                                                 "error": str(exc)[:300]})
                        continue

                # Map an archived topic to a live destination topic only when
                # all its imported source messages identify exactly one node.
                topic_node_key = _archive_key(archive, agent, "topic_node", "", topic_id)
                if not _ledger_get(destination, topic_node_key) and "topic_messages" in _tables(source):
                    mapped_topics = set()
                    for source_message in source.execute("""SELECT m.* FROM topic_messages tm
                        JOIN topic_episodes e ON e.id=tm.episode_id
                        JOIN messages m ON m.id=tm.message_id AND m.agent_id=e.agent_id
                        WHERE e.topic_id=? AND lower(e.agent_id)=?""", (topic_id, agent)):
                        message_key = _archive_key(archive, agent, "message",
                            str(source_message["session_id"]), str(source_message["id"]),
                            _message_digest(source_message))
                        target_message_id = _ledger_get(destination, message_key)
                        if not target_message_id:
                            continue
                        with destination._connect() as db:
                            topic_ids = db.execute("""SELECT DISTINCT e.topic_id FROM topic_messages tm
                                JOIN topic_episodes e ON e.id=tm.episode_id WHERE tm.message_id=?""",
                                (target_message_id,)).fetchall()
                        mapped_topics.update(str(row[0]) for row in topic_ids)
                    if len(mapped_topics) == 1:
                        target_topic_id = next(iter(mapped_topics))
                        _ledger_record(destination, key=topic_node_key, run_id=run_id,
                            archive_id=archive, agent_id=agent, kind="topic_node",
                            record_id=topic_id, target_id=target_topic_id)
                if "topic_events" in _tables(source):
                    for event in source.execute("""SELECT id,actor,action,details_json,created_at
                        FROM topic_events WHERE topic_id=? ORDER BY created_at,id""", (topic_id,)):
                        event_id = str(event["id"])
                        event_digest = _digest([event["actor"], event["action"],
                                                event["details_json"], event["created_at"]])
                        event_key = _archive_key(archive, agent, "topic_event", topic_id,
                                                 event_id, event_digest)
                        if _ledger_get(destination, event_key):
                            continue
                        event_details = _parse_json(event["details_json"], {})
                        content = (f"Asunto relacionado: {title}\nAcción: {event['action']}\n"
                                   f"Actor: {event['actor']}\nDetalles: {_json(event_details)}")
                        try:
                            event_memory = destination.checkpoint(target_topic_session, "episodic",
                                f"[Evento histórico] {str(event['action'])[:300]} · {title}"[:500],
                                content[:48000], scope="private", status="observed", confidence=.6,
                                metadata={"capture_mode": "historical_import", "legacy_archive_id": archive,
                                          "legacy_topic_id": topic_id, "legacy_topic_event_id": event_id,
                                          "legacy_actor": event["actor"],
                                          "occurred_at": float(event["created_at"] or now),
                                          "historical_source": f"legacy-archive:{archive}"})
                            _ledger_record(destination, key=event_key, run_id=run_id, archive_id=archive,
                                           agent_id=agent, kind="topic_event", session_id="",
                                           record_id=event_id, digest=event_digest,
                                           target_id=event_memory["id"])
                            totals["events"] += 1
                        except Exception as exc:
                            totals["errors"].append({"kind": "topic_event", "source_id": event_id,
                                                     "topic_id": topic_id, "error": str(exc)[:300]})

        def agent_topic_session(source_topic_id: str) -> str | None:
            if "topic_episodes" not in _tables(source):
                return None
            row = source.execute("""SELECT e.session_id FROM topic_episodes e
                JOIN sessions s ON s.id=e.session_id WHERE e.topic_id=? AND lower(e.agent_id)=?
                  AND lower(s.agent_id)=? AND s.status!='quarantined' AND s.capture_enabled=1
                ORDER BY e.created_at DESC,e.id DESC LIMIT 1""",
                (source_topic_id, agent, agent)).fetchone()
            return (_target_session_id(destination, archive, agent, str(row[0])) if row else None)

        def mapped_topic_node(source_topic_id: str) -> str | None:
            with destination._connect() as db:
                rows = db.execute("""SELECT DISTINCT target_id FROM legacy_consolidation_items
                    WHERE archive_id=? AND agent_id=? AND record_kind='topic_node'
                      AND source_record_id=?""", (archive, agent, source_topic_id)).fetchall()
            return str(rows[0][0]) if len(rows) == 1 else None

        def save_unmapped_relation(*, kind: str, key: str, record_id: str, source_topic_id: str,
                                   target_topic_id: str, relation: str, confidence: str,
                                   reason: str, historical_status: str = "") -> str:
            anchor = agent_topic_session(source_topic_id) or agent_topic_session(target_topic_id)
            if not anchor:
                return ""
            source_topic = source.execute("SELECT title FROM topics WHERE id=?", (source_topic_id,)).fetchone() if "topics" in _tables(source) else None
            target_topic = source.execute("SELECT title FROM topics WHERE id=?", (target_topic_id,)).fetchone() if "topics" in _tables(source) else None
            source_title = _decode(destination, source_topic[0]) if source_topic else source_topic_id
            target_title = _decode(destination, target_topic[0]) if target_topic else target_topic_id
            title = f"[Relación histórica pendiente] {source_title} · {relation} · {target_title}"[:500]
            content = (f"Asunto origen: {source_title}\nRelación registrada: {relation}\n"
                       f"Asunto relacionado: {target_title}\nConfianza histórica: {confidence}\n"
                       f"Estado de revisión histórico: {historical_status or 'sin revisión'}\n"
                       f"Motivo: {reason or 'sin motivo registrado'}")
            memory = destination.checkpoint(anchor, "episodic", title, content[:48000],
                scope="private", status="observed", confidence=.6,
                metadata={"capture_mode": "historical_import", "legacy_archive_id": archive,
                          "legacy_topic_relation": {"source_topic_id": source_topic_id,
                              "target_topic_id": target_topic_id, "relation": relation,
                              "confidence": confidence, "review_status": historical_status,
                              "mapping_ambiguous": True},
                          "historical_source": f"legacy-archive:{archive}"})
            _ledger_record(destination, key=key, run_id=run_id, archive_id=archive,
                           agent_id=agent, kind=kind, record_id=record_id,
                           target_id=memory["id"])
            return memory["id"]

        if "topic_relations" in _tables(source) and "topics" in _tables(source):
            for relation_row in source.execute("SELECT * FROM topic_relations ORDER BY created_at,source_topic_id,target_topic_id,relation"):
                source_topic_id, target_topic_id = str(relation_row["source_topic_id"]), str(relation_row["target_topic_id"])
                # Relations in the old shared graph are carried only when both
                # ends have episodes belonging to this exact agent.
                source_session = agent_topic_session(source_topic_id)
                target_session = agent_topic_session(target_topic_id)
                if not source_session or not target_session or source_topic_id == target_topic_id:
                    continue
                relation, confidence = str(relation_row["relation"]), str(relation_row["confidence"])
                digest = _digest([source_topic_id, target_topic_id, relation, confidence,
                                  relation_row["reason"], relation_row["source_message_id"],
                                  relation_row["created_at"]])
                record_id = f"{source_topic_id}:{relation}:{target_topic_id}"
                key = _archive_key(archive, agent, "topic_relation", source_topic_id,
                                   record_id, digest)
                if _ledger_get(destination, key):
                    continue
                mapped_source, mapped_target = mapped_topic_node(source_topic_id), mapped_topic_node(target_topic_id)
                if mapped_source and mapped_target and mapped_source != mapped_target:
                    source_message_id = None
                    if relation_row["source_message_id"]:
                        old_message = source.execute("SELECT * FROM messages WHERE id=? AND lower(agent_id)=?",
                            (str(relation_row["source_message_id"]), agent)).fetchone()
                        if old_message:
                            message_key = _archive_key(archive, agent, "message",
                                str(old_message["session_id"]), str(old_message["id"]),
                                _message_digest(old_message))
                            source_message_id = _ledger_get(destination, message_key)
                    with destination._connect() as db:
                        db.execute("""INSERT INTO topic_relations
                            (source_topic_id,target_topic_id,relation,confidence,reason,source_message_id,created_at)
                            VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_topic_id,target_topic_id,relation)
                            DO UPDATE SET confidence=CASE WHEN excluded.confidence='REVIEWED'
                                THEN 'REVIEWED' ELSE topic_relations.confidence END,
                                reason=CASE WHEN excluded.confidence='REVIEWED'
                                THEN excluded.reason ELSE topic_relations.reason END""",
                            (mapped_source, mapped_target, relation, confidence,
                             str(relation_row["reason"] or ""), source_message_id,
                             float(relation_row["created_at"] or now)))
                    imported_id = f"{mapped_source}:{relation}:{mapped_target}"
                else:
                    imported_id = save_unmapped_relation(kind="topic_relation_memory", key=key,
                        record_id=record_id, source_topic_id=source_topic_id,
                        target_topic_id=target_topic_id, relation=relation,
                        confidence=confidence, reason=str(relation_row["reason"] or ""))
                    if not imported_id:
                        continue
                if mapped_source and mapped_target and mapped_source != mapped_target:
                    _ledger_record(destination, key=key, run_id=run_id, archive_id=archive,
                                   agent_id=agent, kind="topic_relation", record_id=record_id,
                                   digest=digest, target_id=imported_id)
                totals["relations"] += 1

        if "topic_relation_reviews" in _tables(source) and "topics" in _tables(source):
            for review in source.execute("SELECT * FROM topic_relation_reviews ORDER BY created_at,id"):
                source_topic_id, target_topic_id = str(review["source_topic_id"]), str(review["target_topic_id"])
                if not agent_topic_session(source_topic_id) or not agent_topic_session(target_topic_id):
                    continue
                relation = str(review["relation"])
                review_status = str(review["status"])
                digest = _digest([source_topic_id, target_topic_id, relation, review_status,
                                  review["reason"], review["evidence_json"], review["actor"],
                                  review["created_at"], review["updated_at"]])
                review_id = str(review["id"])
                key = _archive_key(archive, agent, "topic_relation_review",
                                   source_topic_id, review_id, digest)
                if _ledger_get(destination, key):
                    continue
                mapped_source, mapped_target = mapped_topic_node(source_topic_id), mapped_topic_node(target_topic_id)
                if mapped_source and mapped_target and mapped_source != mapped_target:
                    historical_evidence = _parse_json(review["evidence_json"], {})
                    if not isinstance(historical_evidence, dict):
                        historical_evidence = {"legacy_evidence": historical_evidence}
                    historical_evidence["legacy_archive_id"] = archive
                    historical_evidence["legacy_review_id"] = review_id
                    new_review_id = "rel_hist_" + _digest([archive, agent, review_id])[:24]
                    with destination._connect() as db:
                        db.execute("""INSERT INTO topic_relation_reviews
                            (id,source_topic_id,target_topic_id,relation,status,reason,evidence_json,actor,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_topic_id,target_topic_id,relation)
                            DO UPDATE SET status=excluded.status,reason=excluded.reason,
                                evidence_json=excluded.evidence_json,actor=excluded.actor,
                                updated_at=excluded.updated_at
                            WHERE topic_relation_reviews.status='pending'""",
                            (new_review_id, mapped_source, mapped_target, relation, review_status,
                             str(review["reason"] or ""), _json(historical_evidence),
                             f"historical:{review['actor'] or 'unknown'}",
                             float(review["created_at"] or now), float(review["updated_at"] or now)))
                        if review_status == "accepted":
                            db.execute("""INSERT INTO topic_relations
                                (source_topic_id,target_topic_id,relation,confidence,reason,source_message_id,created_at)
                                VALUES(?,?,?,'REVIEWED',?,NULL,?)
                                ON CONFLICT(source_topic_id,target_topic_id,relation)
                                DO UPDATE SET confidence='REVIEWED',reason=excluded.reason""",
                                (mapped_source, mapped_target, relation, str(review["reason"] or ""),
                                 float(review["updated_at"] or now)))
                    target_review = new_review_id
                else:
                    target_review = save_unmapped_relation(kind="topic_relation_review_memory", key=key,
                        record_id=review_id, source_topic_id=source_topic_id,
                        target_topic_id=target_topic_id, relation=relation,
                        confidence="historical_review", reason=str(review["reason"] or ""),
                        historical_status=review_status)
                    if not target_review:
                        continue
                if mapped_source and mapped_target and mapped_source != mapped_target:
                    _ledger_record(destination, key=key, run_id=run_id, archive_id=archive,
                                   agent_id=agent, kind="topic_relation_review",
                                   session_id="", record_id=review_id, digest=digest,
                                   target_id=target_review)
                totals["reviews"] += 1

        status = "completed" if not totals["errors"] else "partial"
        report(status)
        if progress:
            progress(100, "Migración histórica finalizada" if status == "completed"
                     else "Migración parcial; se puede reanudar")
        return {**preview, "dry_run": False, "ok": status == "completed",
                "status": status, "run_id": run_id, "imported": totals,
                "source_backup": source_backup, "target_backup": target_backup,
                "source_sha256": source_sha,
                "source_unchanged": True, "resumable": True}
