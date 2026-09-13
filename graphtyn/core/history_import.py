"""Historical conversation discovery/import for external coding agents.

Adapters intentionally emit one small neutral schema. SharedMemoryStore remains
the only component allowed to sanitize, persist, compact and embed content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import tarfile
import threading
import time
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .shared_memory import SharedMemoryStore
from .ssh import ssh_command
from .storage import data_home, atomic_write_json


BUILTIN_PROVIDERS = {"openclaw", "hermes", "codex", "antigravity", "opencode", "claude"}
_ROLE_ALIASES = {"human": "user", "user": "user", "assistant": "assistant", "ai": "assistant",
                 "tool": "tool", "function": "tool"}
_AGY_USER = {"USER_EXPLICIT", "USER_INPUT"}
_AGY_ASSISTANT = {"MODEL", "ASSISTANT", "AGENT"}
_PROJECT_PATH_RE = re.compile(r"(?:cwd|workspace|project|workdir|directory|path)\s*[:=]\s*([^\n]+)", re.I)


@dataclass
class HistoricalSession:
    provider: str
    agent_id: str
    external_session_id: str
    task: str
    messages: list[dict[str, Any]]
    source: str
    occurred_at: float | None = None
    workspace: str | None = None
    branch: str | None = None
    updated_at: float | None = None

    @property
    def fingerprint(self) -> str:
        # Temporary extraction paths and adapter metadata must not change the
        # identity of an otherwise identical conversation.
        messages = [{"role": row.get("role"), "content": row.get("content"),
                     "event_type": row.get("event_type")} for row in self.messages]
        payload = json.dumps({"provider": self.provider, "agent": self.agent_id,
                              "session": self.external_session_id, "messages": messages},
                             ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def default_sources() -> dict[str, list[Path]]:
    home = Path.home()
    opencode_root = home / ".local" / "share" / "opencode"
    # Prefer the canonical database when present: scanning the entire OpenCode
    # directory also walks caches and unrelated JSON files on every sync.
    opencode_db = next((candidate for candidate in (
        opencode_root / "opencode-stable.db", opencode_root / "opencode.db")
        if candidate.is_file()), opencode_root)
    openclaw_roots = [
        Path(os.environ.get("OPENCLAW_STATE_DIR", "")).expanduser() if os.environ.get("OPENCLAW_STATE_DIR") else None,
        Path(os.environ.get("OPENCLAW_HOME", "")).expanduser() if os.environ.get("OPENCLAW_HOME") else None,
        home / ".openclaw",
        home / ".config" / "openclaw",
    ]
    config_path = os.environ.get("OPENCLAW_CONFIG_PATH", "").strip()
    if config_path:
        openclaw_roots.insert(0, Path(config_path).expanduser().parent)
    openclaw_sources: list[Path] = []
    for root in openclaw_roots:
        if root is None:
            continue
        candidate = root / "agents" if root.name != "agents" else root
        if candidate not in openclaw_sources:
            openclaw_sources.append(candidate)
    return {
        "openclaw": openclaw_sources,
        "hermes": [home / ".hermes", home / ".config" / "hermes"],
        "codex": [home / ".codex" / "sessions"],
        "antigravity": [home / ".agy", home / ".config" / "antigravity",
                        home / ".gemini" / "antigravity-cli",
                        home / ".gemini" / "antigravity-cli" / "brain"],
        "opencode": [opencode_db],
        "claude": [home / ".claude" / "projects"],
    }


def sources_config_file() -> Path:
    return data_home() / "history-sources.json"


def configured_sources(path: Path | None = None) -> list[dict[str, Any]]:
    """Load deployment-specific sources without assuming where an agent runs."""
    target = path or sources_config_file()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        rows = payload.get("sources", []) if isinstance(payload, dict) else payload
    except (OSError, ValueError):
        return []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict): continue
        provider, source = str(row.get("provider") or "").strip().casefold(), str(row.get("source") or "").strip()
        if provider and source and row.get("enabled", True):
            item = {"provider": provider, "source": source, "label": str(row.get("label") or "")}
            agent_id = str(row.get("agent_id") or row.get("agent") or "").strip().casefold()
            if agent_id:
                item["agent_id"] = agent_id
            # A source may belong to one brain/project.  Older entries without
            # this field remain visible but are intentionally not auto-routed.
            project_path = str(row.get("project_path") or row.get("workspace") or "").strip()
            if project_path:
                item["project_path"] = project_path
            if isinstance(row.get("capture_from"), (int, float)):
                item["capture_from"] = float(row["capture_from"])
            result.append(item)
    return result


def save_source(provider: str, source: str, *, label: str = "", project_path: str | Path | None = None,
                agent_id: str | None = None,
                capture_from: float | None = None,
                path: Path | None = None) -> dict[str, Any]:
    """Persist a host/container/VPS history source with restrictive permissions."""
    provider, source = provider.strip().casefold(), source.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", provider): raise ValueError("proveedor inválido")
    if not source or "\x00" in source: raise ValueError("fuente inválida")
    parsed = urlparse(source) if "://" in source else None
    if parsed and parsed.password: raise ValueError("no incluya contraseñas en la URL; use SSH keys o secretos externos")
    safe_label, _ = SharedMemoryStore._sanitize(label.strip(), 200)
    target = path or sources_config_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = configured_sources(target)
    associated = str(project_path or "").strip()
    if associated:
        associated = str(Path(associated).expanduser().resolve())
    item = {"provider": provider, "source": source, "label": safe_label, "enabled": True}
    normalized_agent = str(agent_id or "").strip().casefold()
    if normalized_agent:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]{1,127}", normalized_agent):
            raise ValueError("identidad de agente inválida")
        item["agent_id"] = normalized_agent
    if associated:
        item["project_path"] = associated
    if capture_from is not None:
        item["capture_from"] = float(capture_from)
    else:
        old = next((row for row in rows if row.get("provider") == provider and row.get("source") == source), None)
        if old and isinstance(old.get("capture_from"), (int, float)):
            item["capture_from"] = float(old["capture_from"])
    # A physical transcript source has one owner. Re-saving it for a brain
    # moves the association instead of leaving an unscoped duplicate behind.
    rows = [row for row in rows if not (row["provider"] == item["provider"] and row["source"] == item["source"])]
    rows.append(item)
    atomic_write_json(target, {"version": 1, "sources": rows})
    return item


def delete_source(provider: str, source: str, *, path: Path | None = None) -> bool:
    target = path or sources_config_file(); rows = configured_sources(target)
    kept = [row for row in rows if not (row["provider"] == provider.casefold() and row["source"] == source)]
    changed = len(kept) != len(rows)
    if changed:
        atomic_write_json(target, {"version": 1, "sources": kept})
    return changed


def test_source(provider: str, source: str) -> dict[str, Any]:
    result = discover_histories(provider, [source])
    return {"ok": not result["errors"], "provider": provider, "source": source,
            "sessions": result["count"], "messages": sum(row["message_count"] for row in result["sessions"]),
            "projects": len(result["projects"]), "errors": result["errors"]}


def _materialize_source(source: str | Path) -> tuple[Path, tempfile.TemporaryDirectory | None, str]:
    """Resolve local, Docker, SSH, or SSH+Docker history without mutating it."""
    raw = str(source)
    if not raw.startswith(("ssh://", "docker://", "ssh+docker://")):
        return Path(raw).expanduser(), None, raw
    parsed = urlparse(raw)
    remote_path = unquote(parsed.path)
    if not re.fullmatch(r"/[A-Za-z0-9_./ -]+", remote_path) or ".." in Path(remote_path).parts:
        raise ValueError("ruta de fuente inválida")
    ssh_target = parsed.username + "@" + parsed.hostname if parsed.username and parsed.hostname else (parsed.hostname or "")
    if ssh_target and not re.fullmatch(r"[A-Za-z0-9_.@-]+", ssh_target): raise ValueError("host SSH inválido")
    container = ""
    if parsed.scheme == "docker": container = parsed.netloc
    elif parsed.scheme == "ssh+docker":
        parts = parsed.netloc.rsplit("@", 1)
        host_part = parts[-1]
        if ":" not in host_part: raise ValueError("use ssh+docker://usuario@host/contenedor/ruta")
        host, container = host_part.split(":", 1)
        ssh_target = ((parts[0] + "@") if len(parts) == 2 else "") + host
    if container and not re.fullmatch(r"[A-Za-z0-9_.-]+", container): raise ValueError("contenedor inválido")
    temp = tempfile.TemporaryDirectory(prefix="graphtyn-history-")
    destination = Path(temp.name)
    archive = destination / "history.tar.gz"
    tar_args = ["tar", "-C", str(Path(remote_path).parent), "--exclude=*.trajectory.jsonl",
                "--exclude=*.png", "--exclude=*.jpg", "--exclude=*.log", "-czf", "-", Path(remote_path).name]
    if parsed.scheme == "ssh": command = [*ssh_command(ssh_target), *tar_args]
    elif parsed.scheme == "docker": command = ["docker", "exec", container, *tar_args]
    else: command = [*ssh_command(ssh_target), "docker", "exec", container, *tar_args]
    with archive.open("wb") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, timeout=600)
    if result.returncode:
        temp.cleanup()
        detail, _ = SharedMemoryStore._sanitize(result.stderr.decode(errors="replace").strip()[:300], 300)
        raise OSError(f"no se pudo copiar la fuente remota: {detail}")
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(destination, filter="data")
    archive.unlink(missing_ok=True)
    copied = destination / Path(remote_path).name
    return copied, temp, raw.rstrip("/")


def _walk_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for key in ("messages", "history", "conversation", "turns", "events", "items", "item", "payload", "message", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        yield from _walk_records(item)
            elif isinstance(nested, dict) and nested is not value:
                yield from _walk_records(nested)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _content(record: dict[str, Any]) -> str:
    value = record.get("content", record.get("text", record.get("message", record.get("body", record.get("output", "")))))
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str): parts.append(item)
            elif isinstance(item, dict) and item.get("type") not in {"thinking", "reasoning", "analysis"} and isinstance(item.get("text"), str): parts.append(item["text"])
        value = "\n".join(parts)
    if isinstance(value, dict):
        value = value.get("text") or value.get("content") or ""
    return str(value or "").strip()


def _role(record: dict[str, Any]) -> str | None:
    channel = str(record.get("channel") or record.get("type") or "").casefold()
    if channel in {"analysis", "reasoning", "thinking", "system", "developer"}:
        return None
    source = str(record.get("source") or "").upper()
    record_type = str(record.get("type") or "").upper()
    if record.get("tool_call_id") or record.get("toolUseId") or record_type in {"TOOL_RESULT", "FUNCTION_CALL_OUTPUT", "TOOL", "TOOL_RESPONSE"}:
        return "tool"
    if source in _AGY_USER or record_type in _AGY_USER: return "user"
    if source in _AGY_ASSISTANT and record_type == "PLANNER_RESPONSE" and record.get("content"):
        return "assistant"
    if source in _AGY_ASSISTANT and record_type == "GENERIC":
        # GENERIC is also used for tool/planner dumps. Only explicitly authored
        # natural-language responses qualify as assistant evidence.
        if any(record.get(k) for k in ("tool", "toolName", "tool_name", "toolResult", "tool_result", "toolResults")):
            return "tool"
        if str(record.get("content") or "").startswith("Created At:"):
            if "File Path:" in str(record.get("content")):
                return None  # Technical file copies are not conversational evidence.
            return "tool"
        if str(record.get("role") or "").casefold() != "assistant":
            return None
    if source in _AGY_ASSISTANT and record_type in {"GENERIC", "TEXT", "MESSAGE", "ASSISTANT", "AGENT"}: return "assistant"
    if record_type in {"USERMESSAGE", "USER_MESSAGE"}: return "user"
    if record_type in {"AGENTMESSAGE", "AGENT_MESSAGE", "ASSISTANTMESSAGE", "ASSISTANT_MESSAGE"}: return "assistant"
    raw = record.get("role") or record.get("author") or record.get("sender") or record.get("type")
    if isinstance(raw, dict): raw = raw.get("role") or raw.get("name")
    return _ROLE_ALIASES.get(str(raw or "").casefold())


def parse_history_database(path: Path, provider: str, agent_hint: str | None = None,
                           session_ids: set[str] | None = None) -> list[HistoricalSession]:
    """Read common role/content/session columns without modifying an agent DB."""
    uri = f"file:{path.resolve()}?mode=ro"
    grouped: dict[str, dict[str, Any]] = {}
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]

        # Current OpenCode stores role/timing metadata and text parts as JSON
        # blobs instead of the flat role/content columns handled below.
        if provider.casefold() == "opencode" and {"session", "message", "part"}.issubset(tables):
            session_columns = {row[1] for row in conn.execute("PRAGMA table_info(session)")}
            message_columns = {row[1] for row in conn.execute("PRAGMA table_info(message)")}
            part_columns = {row[1] for row in conn.execute("PRAGMA table_info(part)")}
            if {"id", "session_id", "data"}.issubset(message_columns) and \
                    {"message_id", "data"}.issubset(part_columns):
                requested_sessions = {str(value) for value in session_ids or set()}
                scoped = bool(requested_sessions)
                session_fields = [name for name in ("id", "directory", "title", "time_created", "time_updated")
                                  if name in session_columns]
                session_sql = f"SELECT {','.join(session_fields)} FROM session"
                session_args: list[str] = []
                if scoped:
                    marks = ",".join("?" for _ in requested_sessions)
                    session_sql += f" WHERE id IN ({marks})"
                    session_args.extend(sorted(requested_sessions))
                session_rows = {str(row["id"]): dict(row) for row in conn.execute(
                    session_sql, session_args) if "id" in session_fields}
                parts_by_message: dict[str, list[dict[str, Any]]] = {}
                part_order = "time_created,rowid" if "time_created" in part_columns else "rowid"
                part_sql = "SELECT id,message_id,data FROM part"
                part_args: list[str] = []
                if scoped and "session_id" in part_columns:
                    marks = ",".join("?" for _ in requested_sessions)
                    part_sql += f" WHERE session_id IN ({marks})"
                    part_args.extend(sorted(requested_sessions))
                part_sql += f" ORDER BY {part_order}"
                for row in conn.execute(part_sql, part_args):
                    try:
                        part = json.loads(row["data"])
                    except (TypeError, ValueError):
                        continue
                    # Tool output and reasoning are not user-facing conversation
                    # text. Only authored text parts enter project memory.
                    if not isinstance(part, dict) or part.get("type") != "text":
                        continue
                    text = str(part.get("text") or "").strip()
                    if not text:
                        continue
                    parts_by_message.setdefault(str(row["message_id"]), []).append(
                        {"id": str(row["id"]), "text": text})

                grouped_opencode: dict[str, dict[str, Any]] = {}
                message_order = "session_id,time_created,rowid" if "time_created" in message_columns else "session_id,rowid"
                message_fields = [name for name in ("id", "session_id", "time_created", "data")
                                  if name in message_columns]
                message_sql = f"SELECT {','.join(message_fields)} FROM message"
                message_args: list[str] = []
                if scoped:
                    marks = ",".join("?" for _ in requested_sessions)
                    message_sql += f" WHERE session_id IN ({marks})"
                    message_args.extend(sorted(requested_sessions))
                message_sql += f" ORDER BY {message_order}"
                for row in conn.execute(message_sql, message_args):
                    try:
                        message_data = json.loads(row["data"])
                    except (TypeError, ValueError):
                        continue
                    role = _ROLE_ALIASES.get(str(message_data.get("role") or "").casefold()) \
                        if isinstance(message_data, dict) else None
                    if role not in {"user", "assistant"}:
                        continue
                    message_id = str(row["id"])
                    text_parts = parts_by_message.get(message_id) or []
                    content = "\n".join(part["text"] for part in text_parts).strip()
                    if not content:
                        continue
                    session_id = str(row["session_id"])
                    meta = session_rows.get(session_id, {})
                    stamp = row["time_created"] if "time_created" in message_fields else None
                    try:
                        occurred_at = float(stamp) if stamp is not None else None
                        if occurred_at is not None and occurred_at > 1e11:
                            occurred_at /= 1000
                    except (TypeError, ValueError):
                        occurred_at = None
                    entry = grouped_opencode.setdefault(session_id, {
                        "messages": [], "times": [], "title": meta.get("title"),
                        "workspace": meta.get("directory"),
                    })
                    if occurred_at is not None:
                        entry["times"].append(occurred_at)
                    entry["messages"].append({"role": role, "content": content, "metadata": {
                        "historical_source": str(path), "provider": provider,
                        "source_message_id": message_id,
                        "source_part_ids": [part["id"] for part in text_parts],
                        "occurred_at": occurred_at,
                    }})

                result = []
                for session_id, entry in grouped_opencode.items():
                    meta = session_rows.get(session_id, {})
                    start = meta.get("time_created")
                    updated = meta.get("time_updated")
                    try:
                        start = float(start) if start is not None else min(entry["times"], default=None)
                        if start is not None and start > 1e11: start /= 1000
                    except (TypeError, ValueError):
                        start = min(entry["times"], default=None)
                    try:
                        updated = float(updated) if updated is not None else max(entry["times"], default=start)
                        if updated is not None and updated > 1e11: updated /= 1000
                    except (TypeError, ValueError):
                        updated = max(entry["times"], default=start)
                    title = str(entry.get("title") or next(
                        (item["content"] for item in entry["messages"] if item["role"] == "user"),
                        "OpenCode conversation"))[:180]
                    result.append(HistoricalSession(
                        provider, agent_hint or "opencode", session_id, title,
                        entry["messages"], str(path), start, entry.get("workspace"), None, updated))
                conn.close()
                return result

        # OpenClaw 2026 stores the canonical transcript as JSON events rather
        # than a role/content table.  The FTS table is only a derived index and
        # omits stable message IDs, so prefer transcript_events when present.
        # This keeps imports incremental across the SQLite migration and
        # preserves user/assistant/tool attribution from the nested message.
        openclaw_events = provider.casefold() == "openclaw" and "transcript_events" in tables
        if openclaw_events:
            session_meta: dict[str, dict[str, Any]] = {}
            if "session_windows" in tables:
                for row in conn.execute("SELECT session_id,session_key,display_name,agent_harness_id,started_at FROM session_windows"):
                    session_meta[str(row["session_id"])] = dict(row)
            for row in conn.execute("SELECT session_id,seq,event_json,created_at FROM transcript_events ORDER BY created_at,seq"):
                try:
                    root = json.loads(row["event_json"])
                except (TypeError, ValueError):
                    continue
                if not isinstance(root, dict):
                    continue
                sid = str(row["session_id"])
                meta = session_meta.get(sid, {})
                group = grouped.setdefault(sid, {"messages": [], "timestamps": [],
                    "workspace": None, "branch": None, "title": meta.get("display_name")})
                for child_index, record in enumerate(_walk_records(root)):
                    role, content = _role(record), _content(record)
                    if role not in {"user", "assistant", "tool"} or not content:
                        continue
                    native_id = (record.get("id") or record.get("messageId") or record.get("message_id")
                                 or root.get("id") or root.get("eventId") or root.get("event_id"))
                    source_id = str(native_id or f"{sid}:{row['seq']}:{child_index}")
                    stamp = record.get("timestamp") or record.get("created_at") or record.get("createdAt")
                    if isinstance(stamp, str):
                        try: stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                        except ValueError: stamp = None
                    if isinstance(stamp, (int, float)):
                        stamp = float(stamp) / (1000 if stamp > 1e11 else 1)
                    else:
                        stamp = float(row["created_at"] or 0) / (1000 if row["created_at"] > 1e11 else 1)
                    group["messages"].append({"role": role, "content": content,
                        "metadata": {"historical_source": str(path), "source_message_id": source_id,
                                     "provider": provider, "table": "transcript_events",
                                     "source_sequence": [int(row["seq"]), child_index],
                                     "occurred_at": stamp}})
                    group["timestamps"].append(stamp)
                    group["title"] = group["title"] or (content[:180] if role == "user" else None)
            conn.close()
            agent = agent_hint or provider
            parts = path.parts
            if provider.casefold() == "openclaw" and "agents" in parts:
                index = parts.index("agents")
                if index + 1 < len(parts) and parts[index + 1] not in {"agent", "sessions"}:
                    agent = parts[index + 1]
            canonical_agent = agent if "/" in str(agent) else f"{provider}/{agent}"
            return [HistoricalSession(provider, canonical_agent, sid,
                str(group.get("title") or next((m["content"] for m in group["messages"] if m["role"] == "user"), "Historical session"))[:180],
                group["messages"], str(path), min(group["timestamps"], default=None), group["workspace"], group.get("branch"),
                max(group["timestamps"], default=None))
                for sid, group in grouped.items() if group["messages"]]

        session_meta: dict[str, dict[str, Any]] = {}
        if "sessions" in tables:
            session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
            wanted = [c for c in ("id", "cwd", "git_repo_root", "git_branch", "started_at", "title") if c in session_columns]
            if "id" in wanted:
                session_meta = {str(row["id"]): dict(row)
                                for row in conn.execute(f"SELECT {','.join(wanted)} FROM sessions")}
        for table in tables:
            if not re.fullmatch(r"[A-Za-z0-9_]+", table): continue
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            role_col = next((c for c in ("role", "author", "sender") if c in columns), None)
            content_col = next((c for c in ("content", "text", "message", "body") if c in columns), None)
            if not role_col or not content_col: continue
            session_col = next((c for c in ("session_id", "sessionId", "conversation_id", "thread_id") if c in columns), None)
            time_col = next((c for c in ("created_at", "timestamp", "createdAt") if c in columns), None)
            workspace_col = next((c for c in ("workspace", "cwd", "project_path", "workdir") if c in columns), None)
            selected = [role_col, content_col] + [c for c in (session_col, time_col, workspace_col) if c]
            for row in conn.execute(f"SELECT {','.join(selected)} FROM {table}"):
                role = _ROLE_ALIASES.get(str(row[role_col] or "").casefold())
                content = str(row[content_col] or "").strip()
                if not role or not content: continue
                sid = str(row[session_col] if session_col else path.stem)
                meta = session_meta.get(sid, {})
                group = grouped.setdefault(sid, {"messages": [], "timestamps": [],
                    "workspace": meta.get("git_repo_root") or meta.get("cwd"),
                    "branch": meta.get("git_branch"), "title": meta.get("title")})
                group["messages"].append({"role": role, "content": content,
                                          "metadata": {"historical_source": str(path), "table": table}})
                stamp = row[time_col] if time_col else meta.get("started_at")
                if isinstance(stamp, (int, float)):
                    group["timestamps"].append(float(stamp) / (1000 if stamp > 1e11 else 1))
                elif isinstance(stamp, str):
                    try: group["timestamps"].append(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
                    except ValueError: pass
                if workspace_col and row[workspace_col]: group["workspace"] = str(row[workspace_col])
        conn.close()
    except sqlite3.Error:
        return []
    agent = agent_hint or (path.parent.name if path.parent.parent.name == "profiles" else provider)
    canonical_agent = agent if "/" in str(agent) else f"{provider}/{agent}"
    return [HistoricalSession(provider, canonical_agent, sid,
        str(group.get("title") or next((m["content"] for m in group["messages"] if m["role"] == "user"), "Historical session"))[:180],
        group["messages"], str(path), min(group["timestamps"], default=None), group["workspace"], group.get("branch"),
        max(group["timestamps"], default=None))
        for sid, group in grouped.items() if group["messages"]]


def _workspace(record: dict[str, Any]) -> str | None:
    for key in ("cwd", "workspace", "workspaceDir", "project_path", "workdir", "directory"):
        value = record.get(key)
        if isinstance(value, str) and value.strip(): return value.strip()
    metadata = record.get("metadata") or record.get("context")
    return _workspace(metadata) if isinstance(metadata, dict) and metadata and metadata is not record else None


def parse_history_file(path: Path, provider: str, agent_hint: str | None = None) -> list[HistoricalSession]:
    """Parse JSON/JSONL histories defensively; unknown records are ignored."""
    values: Iterable[Any]
    try:
        if path.suffix.casefold() == ".jsonl":
            def records() -> Iterable[Any]:
                # Never materialize an entire transcript. Oversized records are
                # usually world-state/tool payloads and are intentionally skipped.
                with path.open("r", encoding="utf-8", errors="replace") as stream:
                    while True:
                        line = stream.readline(8 * 1024 * 1024 + 1)
                        if not line: break
                        if len(line) > 8 * 1024 * 1024 and not line.endswith("\n"):
                            while line and not line.endswith("\n"):
                                line = stream.readline(8 * 1024 * 1024 + 1)
                            continue
                        if line.lstrip().startswith(("{", "[")):
                            try: yield json.loads(line)
                            except (ValueError, TypeError): continue
            values = records()
        else:
            loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            values = loaded if isinstance(loaded, list) else [loaded]
    except (OSError, ValueError, TypeError):
        return []
    grouped: dict[str, dict[str, Any]] = {}
    file_workspace = None
    file_session = None
    if provider == "antigravity":
        file_session = next((part for part in path.parts
                             if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27,}", part, re.I)), None)
    # A single-pass stream cannot pre-scan metadata; records update these values
    # as they arrive and messages inherit the latest known context.
    for record_index, root in enumerate(values):
        if provider == "codex" and isinstance(root, dict) and root.get("type") in {"event_msg", "world_state", "turn_context", "compacted"}:
            continue
        root_session = ((root.get("sessionId") or root.get("session_id") or root.get("conversation_id"))
                        if isinstance(root, dict) else None) or file_session
        root_workspace = (_workspace(root) if isinstance(root, dict) else None) or file_workspace
        if isinstance(root, dict):
            file_session = file_session or root_session
            file_workspace = file_workspace or root_workspace
        for child_index, record in enumerate(_walk_records(root)):
            role, content = _role(record), _content(record)
            if role not in {"user", "assistant", "tool"} or not content: continue
            sid = str(record.get("sessionId") or record.get("session_id") or record.get("conversation_id")
                      or root_session or path.stem)
            group = grouped.setdefault(sid, {"messages": [], "workspace": root_workspace, "timestamps": []})
            native_id = record.get("id") or record.get("uuid") or record.get("message_id") or (str(record["step_index"]) if "step_index" in record else None)
            source_id = str(native_id or f"{sid}:{record_index}:{child_index}")
            metadata = {"historical_source": str(path), "source_message_id": source_id,
                        "provider": provider, "source_sequence": [record_index, child_index]}
            stamp = record.get("timestamp") or record.get("created_at") or record.get("createdAt")
            if isinstance(stamp, str):
                try: stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                except ValueError: stamp = None
            if isinstance(stamp, (float, int)):
                metadata["occurred_at"] = float(stamp) / (1000 if stamp > 1e11 else 1)
            group["messages"].append({"role": role, "content": content, "metadata": metadata})
            group["workspace"] = group["workspace"] or _workspace(record)
            stamp = record.get("timestamp") or record.get("created_at") or record.get("createdAt")
            if isinstance(stamp, (int, float)): group["timestamps"].append(float(stamp) / (1000 if stamp > 1e11 else 1))
            elif isinstance(stamp, str):
                try: group["timestamps"].append(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
                except ValueError: pass
    agent = agent_hint or (path.parent.parent.name if provider == "openclaw" and path.parent.name == "sessions" else provider)
    if provider == "antigravity":
        agent = agent_hint or "agy"
    sessions = []
    for sid, group in grouped.items():
        if not group["messages"]: continue
        first_user = next((m["content"] for m in group["messages"] if m["role"] == "user"), "Historical session")
        canonical_agent = agent if "/" in str(agent) else f"{provider}/{agent}"
        try:
            file_updated_at = path.stat().st_mtime
        except OSError:
            file_updated_at = None
        sessions.append(HistoricalSession(provider, canonical_agent, sid, first_user[:180],
            group["messages"], str(path), min(group["timestamps"], default=None), group["workspace"],
            updated_at=max(group["timestamps"], default=file_updated_at)))
    return sessions


def _same_project_path(left: str | Path | None, right: str | Path | None) -> bool:
    if not left or not right:
        return False
    try:
        return Path(str(left)).expanduser().resolve() == Path(str(right)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return str(left).rstrip("/").casefold() == str(right).rstrip("/").casefold()


def _source_matches_root(path: str | Path, roots: set[str]) -> bool:
    """Match a discovered file to its configured file or containing directory."""
    try:
        candidate = Path(path).expanduser().resolve()
        for raw in roots:
            root = Path(raw).expanduser().resolve()
            if candidate == root or root.is_dir() and root in candidate.parents:
                return True
    except (OSError, RuntimeError, ValueError):
        return str(path) in roots
    return False


def _contained_path(root: Path, value: str | Path, base: Path) -> Path | None:
    """Resolve a pointer only inside its explicitly selected history tree."""
    raw = Path(str(value)).expanduser()
    candidates = [raw] if raw.is_absolute() else [base / raw, root / raw]
    # Runtime paths may have been written inside a container. Map only the
    # suffix below its known OpenClaw ``agents`` root into the selected source.
    if raw.is_absolute() and "agents" in raw.parts:
        index = len(raw.parts) - 1 - tuple(reversed(raw.parts)).index("agents")
        suffix = raw.parts[index + 1:]
        if suffix:
            candidates.append(root.joinpath(*suffix))
    if raw.is_absolute() and root.name in raw.parts:
        index = len(raw.parts) - 1 - tuple(reversed(raw.parts)).index(root.name)
        suffix = raw.parts[index + 1:]
        if suffix:
            candidates.append(root.joinpath(*suffix))
    resolved_root = root.resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _openclaw_pointer_transcripts(root: Path, pointer_files: Iterable[Path]) -> tuple[list[Path], list[dict[str, str]]]:
    """Follow OpenClaw trajectory pointers to canonical chat transcripts only.

    Trace events are inspected as metadata; their prompt, model, and tool payloads
    are never emitted to the history importer.
    """
    transcripts: list[Path] = []
    warnings: list[dict[str, str]] = []
    for pointer in pointer_files:
        try:
            pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            warnings.append({"source": str(pointer), "warning": "puntero de trayectoria ilegible"})
            continue
        if not isinstance(pointer_data, dict):
            continue
        runtime_value = pointer_data.get("runtimeFile")
        trace = _contained_path(root, runtime_value, pointer.parent) if runtime_value else None
        if not trace or ".trajectory." not in trace.name:
            warnings.append({"source": str(pointer), "warning": "trace apuntado ausente o fuera de la fuente seleccionada"})
            continue
        try:
            with trace.open("r", encoding="utf-8", errors="replace") as stream:
                for line_number, line in enumerate(stream, 1):
                    if len(line) > 1024 * 1024:
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_name = event.get("type") or event.get("event") or event.get("name")
                    if event_name != "session.started":
                        continue
                    data = event.get("data")
                    session_file = data.get("sessionFile") if isinstance(data, dict) else None
                    if not isinstance(session_file, str) or not session_file.strip():
                        continue
                    transcript = _contained_path(root, session_file, trace.parent)
                    if transcript and transcript.suffix.casefold() == ".jsonl":
                        transcripts.append(transcript)
                    else:
                        warnings.append({"source": str(pointer),
                                         "warning": f"transcripción canónica no disponible (evento {line_number})"})
        except OSError:
            warnings.append({"source": str(pointer), "warning": "no se pudo leer el trace apuntado"})
    return list(dict.fromkeys(transcripts)), warnings


def _agent_id_matches(expected: str | None, observed: str | None) -> bool:
    """Match a configured owner without collapsing identities across providers."""
    wanted = str(expected or "").strip().casefold()
    actual = str(observed or "").strip().casefold()
    if not wanted or not actual:
        return False
    return bool(wanted and wanted == actual)


def discover_histories(provider: str | None = None, sources: list[str] | None = None,
                       project_path: str | Path | None = None,
                       agent_id: str | None = None) -> dict[str, Any]:
    configured = configured_sources()
    from .adapters import list_adapters
    known = {row["name"] for row in list_adapters()}
    providers = [provider.casefold()] if provider else sorted(known | {row["provider"] for row in configured})
    found, errors, excluded, warnings = [], [], [], []
    for name in providers:
        source_owners: dict[str, str] = {}
        source_baselines: dict[str, float] = {}
        if sources:
            roots = sources
            associated_sources = set(roots)
            if agent_id:
                source_owners.update({str(root): str(agent_id).strip().casefold() for root in roots})
        elif project_path:
            # Per-space synchronization only consumes explicitly associated
            # sources. OpenCode is the exception: its database stores many
            # projects, and each session carries a workspace path. Scan the
            # local database and rely on exact path routing below.
            selected = [row for row in configured if row["provider"] == name and
                        _same_project_path(row.get("project_path"), project_path)]
            roots = [row["source"] for row in selected]
            associated_sources = set(roots)
            source_owners.update({row["source"]: str(row.get("agent_id") or agent_id or "").strip().casefold()
                                  for row in selected if row.get("agent_id") or agent_id})
            source_baselines.update({row["source"]: float(row["capture_from"])
                                     for row in selected if isinstance(row.get("capture_from"), (int, float))})
            if not roots and name == "opencode":
                roots = [str(value) for value in default_sources().get(name, [])]
        else:
            roots = [row["source"] for row in configured if row["provider"] == name]
            associated_sources = set()
            source_baselines.update({row["source"]: float(row["capture_from"])
                                     for row in configured if row["provider"] == name
                                     and isinstance(row.get("capture_from"), (int, float))})
            if not roots: roots = default_sources().get(name, [])
        for source in roots:
            temp = None
            try:
                root, temp, source_label = _materialize_source(source)
                if not root.exists(): continue
                scan_root = root if root.is_dir() else root.parent
                if root.is_file():
                    files = [root]
                elif name == "antigravity":
                    # transcript.jsonl is the canonical AGY source. Other files
                    # are compacted copies, planner/tool logs or UI metadata.
                    files = [p for p in root.rglob("transcript.jsonl")
                             if ".system_generated" in p.parts and "logs" in p.parts]
                else:
                    files = ([p for p in root.rglob("*.jsonl") if ".trajectory." not in p.name]
                             + list(root.rglob("*.json"))
                             + list(root.rglob("*.db")) + list(root.rglob("*.sqlite")) + list(root.rglob("*.sqlite3")))
                if name == "openclaw":
                    pointer_files = ([root] if root.is_file() and "trajectory-path" in root.name
                                     else list(scan_root.rglob("*trajectory-path.json")))
                    pointer_files = [p for p in pointer_files if p.is_file()]
                    transcripts, pointer_warnings = _openclaw_pointer_transcripts(scan_root, pointer_files)
                    warnings.extend(pointer_warnings)
                    # Pointer JSON and trajectory traces are technical metadata,
                    # never candidate chat histories. Only canonical transcripts
                    # resolved within the explicitly selected source are parsed.
                    files = [p for p in files if "trajectory-path" not in p.name]
                    files.extend(transcripts)
                files = list(dict.fromkeys(files))
                # Agent distributions often bundle prompts and skill fixtures that
                # happen to use role/content fields. They are not conversations.
                ignored_parts = {"skills", "templates", "examples", "fixtures", "node_modules", ".git"}
                files = [path for path in files if not ignored_parts.intersection(
                    part.casefold() for part in path.relative_to(scan_root).parts[:-1])]
                for path in files:
                    if path.suffix.casefold() == ".jsonl" and not temp:
                        from .history_stream import preview_jsonl
                        preview = preview_jsonl(path, name)
                        for item in preview["sessions"]:
                            owner = source_owners.get(str(source)) or source_owners.get(str(path))
                            if owner and not _agent_id_matches(owner, item.get("agent_id")):
                                excluded.append({"source": str(source), "session": item.get("external_session_id"),
                                                 "agent_id": item.get("agent_id"), "expected_agent_id": owner})
                                continue
                            baseline = source_baselines.get(str(source), source_baselines.get(str(path)))
                            if baseline is not None and float(item.get("updated_at") or item.get("occurred_at") or 0) <= baseline:
                                excluded.append({"source": str(source), "session": item.get("external_session_id"),
                                                 "reason": "before_capture_baseline"})
                                continue
                            if project_path and _source_matches_root(path, associated_sources):
                                item["explicit_project_selection"] = True
                            found.append(item)
                        if preview["errors"]:
                            errors.append({"source": str(path), "error": f"{preview['errors']} registros JSON inválidos"})
                        continue
                    parser = parse_history_database if path.suffix.casefold() in {".db", ".sqlite", ".sqlite3"} else parse_history_file
                    owner_hint = source_owners.get(str(source)) or source_owners.get(str(path))
                    for session in parser(path, name, owner_hint):
                        if str(source).startswith(("ssh://", "docker://", "ssh+docker://")):
                            try: session.source = f"{source_label}/{path.relative_to(root).as_posix()}"
                            except ValueError: session.source = source_label
                        item = {**asdict(session), "fingerprint": session.fingerprint,
                                "message_count": len(session.messages)}
                        owner = source_owners.get(str(source)) or source_owners.get(str(path))
                        if owner and not _agent_id_matches(owner, item.get("agent_id")):
                            excluded.append({"source": str(source), "session": item.get("external_session_id"),
                                             "agent_id": item.get("agent_id"), "expected_agent_id": owner})
                            continue
                        baseline = source_baselines.get(str(source), source_baselines.get(str(path)))
                        if baseline is not None and float(item.get("updated_at") or item.get("occurred_at") or 0) <= baseline:
                            excluded.append({"source": str(source), "session": item.get("external_session_id"),
                                             "reason": "before_capture_baseline"})
                            continue
                        if project_path and _source_matches_root(source, associated_sources):
                            item["explicit_project_selection"] = True
                        found.append(item)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append({"source": str(source), "error": str(exc)})
            finally:
                if temp: temp.cleanup()
    found.sort(key=lambda item: (item.get("occurred_at") or 0, item["provider"], item["external_session_id"]))
    project_counts: dict[str, int] = {}
    for item in found:
        hint = str(item.get("workspace") or "").strip()
        if hint: project_counts[hint] = project_counts.get(hint, 0) + 1
    projects = [{"workspace": workspace, "name": Path(workspace).name, "sessions": count,
                 "confidence": 1.0 if Path(workspace).is_absolute() else .7}
                for workspace, count in sorted(project_counts.items(), key=lambda pair: (-pair[1], pair[0]))]
    return {"ok": not errors, "sessions": found, "count": len(found), "projects": projects,
            "errors": errors, "warnings": warnings,
            "excluded": excluded, "excluded_count": len(excluded)}


def sync_memory_workspace(workspace: str | Path, *, provider: str | None = None,
                          source: list[str] | None = None, provider_model: str = "auto",
                          enrich: bool = True, force: bool = False, agent_id: str | None = None,
                          progress=None) -> dict[str, Any]:
    """Synchronize one explicitly associated memory space incrementally.

    Discovery, idempotent import and topic enrichment share this entry point so
    CLI, REST and the background watcher cannot drift apart.
    """
    root = Path(workspace).expanduser().resolve()
    memory_scope = SharedMemoryStore(root).memory_scope()
    authorized_agents = memory_scope["agent_ids"] if memory_scope["restricted"] else None
    discovered = discover_histories(provider, source or None, project_path=None if source else root,
                                    agent_id=agent_id)
    # A source supplied directly is an explicit user selection for this space.
    if source:
        for item in discovered["sessions"]:
            item["explicit_project_selection"] = True
    if progress:
        progress(20, f"{discovered['count']} sesiones descubiertas")
    imported = import_histories(root, discovered["sessions"], consent=True, provider=provider_model,
                                background_enrich=False, agent_ids=authorized_agents)
    result: dict[str, Any] = {"ok": bool(imported.get("ok", True)), "path": str(root),
                              "discovered": discovered["count"], "import": imported,
                              "warnings": list(discovered.get("warnings") or []),
                              "excluded": discovered.get("excluded") or [],
                              "excluded_count": int(discovered.get("excluded_count") or 0),
                              "errors": list(discovered.get("errors") or [])}
    result["errors"].extend(imported.get("errors") or [])
    # A brain may already contain captured sessions from MCP before a source
    # was configured. Advance their thematic cursors too, so synchronization
    # reports coverage for the whole space rather than only newly imported data.
    store = SharedMemoryStore(root)
    processed_sessions, processed_messages = 0, 0
    with store._connect() as db:
        existing_sessions = [row[0] for row in db.execute("SELECT id FROM sessions ORDER BY started_at,id")]
    for session_id in existing_sessions:
        try:
            topic_result = store.process_topics(session_id)
            processed_sessions += 1
            processed_messages += int(topic_result.get("processed") or 0)
        except PermissionError:
            continue
    result["topic_processing"] = {"sessions": processed_sessions, "messages": processed_messages}
    if enrich:
        if progress:
            progress(45, "Enriqueciendo temas nuevos o modificados")
        enrichment_agents = [str(agent_id).strip().casefold()] if agent_id else []
        if not source and not enrichment_agents:
            enrichment_agents = sorted({str(item.get("agent_id") or "").strip().casefold()
                                        for item in discovered.get("sessions") or [] if item.get("agent_id")})
            if not enrichment_agents:
                enrichment_agents = sorted({str(row.get("agent_id") or "").strip().casefold()
                                            for row in configured_sources()
                                            if row.get("agent_id") and _same_project_path(row.get("project_path"), root)})
        enrichment = store.enrich_topics(None, provider=provider_model,
                                         force=force, progress=progress,
                                         agent_ids=enrichment_agents or None)
        result["enrichment"] = enrichment
    result["ok"] = not result["errors"] and bool(imported.get("ok", True))
    return result


class ProjectIdentityRegistry:
    """Global, portable project identity map used by historical imports."""
    def __init__(self, path: Path | None = None):
        self.path = path or data_home() / "project-identities.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {"version": 1, "projects": []}

    def register(self, workspace: str | Path, aliases: list[str] | None = None) -> dict[str, Any]:
        root = Path(workspace).expanduser().resolve()
        remote = ""
        try:
            import subprocess
            remote = subprocess.run(["git", "-C", str(root), "config", "--get", "remote.origin.url"],
                                    capture_output=True, text=True, timeout=3).stdout.strip()
        except Exception: pass
        key = hashlib.sha256((remote or str(root)).casefold().encode()).hexdigest()[:20]
        with self._lock:
            data = self._read()
            item = next((p for p in data["projects"] if p["id"] == key or remote and p.get("remote") == remote), None)
            if not item:
                item = {"id": key, "canonical_name": root.name, "aliases": [], "paths": [], "remote": remote,
                        "created_at": time.time(), "updated_at": time.time()}
                data["projects"].append(item)
            item["paths"] = sorted(set(item.get("paths", [])) | {str(root)})
            item["aliases"] = sorted(set(item.get("aliases", [])) | set(aliases or []) | {root.name})
            item["updated_at"] = time.time()
            atomic_write_json(self.path, data)
        return item

    def resolve(self, hint: str | None) -> dict[str, Any] | None:
        if not hint: return None
        value = str(Path(hint).expanduser()) if any(mark in hint for mark in ("/", "\\", "~")) else hint
        folded = value.casefold()
        candidates = []
        for item in self._read()["projects"]:
            exact = any(folded == str(v).casefold() for v in [item.get("canonical_name"), item.get("remote"),
                                                               *item.get("aliases", []), *item.get("paths", [])])
            partial = any(str(v).casefold() in folded or folded in str(v).casefold()
                          for v in [item.get("canonical_name"), *item.get("aliases", [])] if v)
            if exact or partial: candidates.append((1.0 if exact else .7, item))
        return max(candidates, key=lambda pair: pair[0])[1] if candidates else None

    def list(self) -> list[dict[str, Any]]:
        return self._read()["projects"]


def import_histories(workspace: str | Path, sessions: list[dict[str, Any]], *, consent: bool,
                     provider: str = "deterministic", dry_run: bool = False,
                     background_enrich: bool = True,
                     agent_ids: list[str] | None = None) -> dict[str, Any]:
    if not consent: raise PermissionError("la importación histórica requiere consentimiento explícito")
    root = Path(workspace).expanduser().resolve()
    policy = SharedMemoryStore(root).memory_scope()
    if agent_ids is None and policy["restricted"]:
        agent_ids = policy["agent_ids"]
    registry = ProjectIdentityRegistry()
    project = registry.register(root)
    selected, ambiguous, excluded = [], [], []
    authorized_agents = sorted({str(value).strip().casefold() for value in (agent_ids or [])
                                if str(value).strip()})
    for raw in sessions:
        raw_agent = str(raw.get("agent_id") or "").strip().casefold()
        try:
            from .openclaw_integration import assert_agent_memory_enabled
            assert_agent_memory_enabled(root, raw_agent)
        except PermissionError as exc:
            excluded.append({"session": raw.get("external_session_id"),
                             "agent_id": raw.get("agent_id"),
                             "reason": str(exc)})
            continue
        if (policy["restricted"] and not authorized_agents) or (
                authorized_agents and not any(_agent_id_matches(owner, raw_agent) for owner in authorized_agents)):
            excluded.append({"session": raw.get("external_session_id"), "agent_id": raw.get("agent_id"),
                             "expected_agent_ids": authorized_agents,
                             "reason": "identidad de agente fuera del espacio de memoria"})
            continue
        workspace_hint = str(raw.get("workspace") or "").strip()
        if workspace_hint:
            # A filesystem path is strong project evidence only when it points
            # to a registered path. Matching just Path.name can silently mix
            # separate checkouts that happen to share a folder name.
            path_hint = (workspace_hint.startswith("~") or Path(workspace_hint).is_absolute()
                         or PurePosixPath(workspace_hint).is_absolute()
                         or PureWindowsPath(workspace_hint).is_absolute())
            if path_hint:
                try:
                    normalized_hint = str(Path(workspace_hint).expanduser().resolve())
                except (OSError, RuntimeError, ValueError):
                    normalized_hint = ""
                matched = next((item for item in registry.list()
                                if normalized_hint and normalized_hint in {
                                    str(Path(value).expanduser().resolve())
                                    for value in item.get("paths", [])}), None)
                if not matched or matched["id"] != project["id"]:
                    windows_hint = PureWindowsPath(workspace_hint)
                    suggested = windows_hint.name if windows_hint.is_absolute() else PurePosixPath(workspace_hint).name
                    ambiguous.append({"session": raw.get("external_session_id"), "workspace": workspace_hint,
                                      "suggested_project": (matched or {}).get("canonical_name") or suggested,
                                      "reason": "ruta de proyecto no coincide exactamente"})
                    continue
            else:
                hinted = registry.resolve(workspace_hint)
                if hinted and hinted["id"] != project["id"]:
                    ambiguous.append({"session": raw.get("external_session_id"), "workspace": workspace_hint,
                                      "suggested_project": hinted["canonical_name"]})
                    continue
                if not hinted:
                    current_names = {project["canonical_name"].casefold(),
                                     *(a.casefold() for a in project.get("aliases", []))}
                    if workspace_hint.casefold() not in current_names:
                        ambiguous.append({"session": raw.get("external_session_id"), "workspace": workspace_hint,
                                          "suggested_project": workspace_hint, "reason": "proyecto no registrado"})
                        continue
        if not workspace_hint and not raw.get("explicit_project_selection"):
            ambiguous.append({"session": raw.get("external_session_id"), "reason": "sin metadatos de proyecto ni selección explícita"})
            continue
        selected.append(raw)
    if dry_run:
        return {"ok": True, "dry_run": True, "project": project, "selected": len(selected),
                "ambiguous": ambiguous, "excluded": excluded, "sessions": selected}
    store, imported, reused, errors = SharedMemoryStore(root), [], [], []
    for raw in selected:
        try:
            if raw.get("streaming_source"):
                from .history_stream import ingest_jsonl
                result = ingest_jsonl(store, raw["source"], provider=raw["provider"],
                    external_session_id=raw["external_session_id"], agent_id=raw["agent_id"],
                    consent=True, explicit_project_selection=True)
                (imported if result["processed_this_run"] else reused).append({"source": raw["source"], "session_id": result["session_id"],
                    "external_session_id": raw["external_session_id"], "progress": result})
                continue
            source_key = "external-history:" + str(raw.get("fingerprint") or hashlib.sha256(
                json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
            with store._connect() as conn:
                previous = conn.execute("SELECT memory_id FROM legacy_imports WHERE source_key=?", (source_key,)).fetchone()
            if previous:
                reused.append({"source": raw.get("source"), "session_id": previous["memory_id"],
                               "external_session_id": raw.get("external_session_id")})
                continue
            occurred_at = float(raw.get("occurred_at") or time.time())
            agent_id = str(raw.get("agent_id") or raw.get("provider") or "unknown").strip().casefold()
            external_id = str(raw.get("external_session_id") or raw.get("fingerprint"))
            session_id = "ses_ext_" + hashlib.sha256(f"{agent_id}\0{external_id}".encode()).hexdigest()[:24]
            historical_messages = []
            for index, message in enumerate(raw.get("messages") or []):
                metadata = message.get("metadata") or {}
                historical_messages.append({**message, "metadata": {**metadata,
                    "source_message_id": metadata.get("source_message_id") or f"{raw.get('external_session_id')}:{index}",
                    "capture_mode": "historical_import", "occurred_at": metadata.get("occurred_at", occurred_at),
                    "provider": raw.get("provider"), "historical_source": raw.get("source")}})
            if not historical_messages and store.get_session(session_id):
                reused.append({"source": raw.get("source"), "session_id": session_id,
                               "external_session_id": raw.get("external_session_id")})
                with store._connect() as conn:
                    conn.execute("INSERT OR IGNORE INTO legacy_imports(source_key,memory_id,imported_at) VALUES(?,?,?)",
                                 (source_key, session_id, time.time()))
                continue
            result = store.ingest_turn(agent_id, external_id,
                str(raw.get("task") or "Historical conversation"), historical_messages,
                consent=True, branch=raw.get("branch"), compact=True, close=True, provider=provider,
                reopen_closed=True, background_enrich=background_enrich)
            imported.append({"source": raw.get("source"), "session_id": result["session_id"],
                             "external_session_id": raw.get("external_session_id")})
            with store._connect() as conn:
                conn.execute("INSERT OR IGNORE INTO legacy_imports(source_key,memory_id,imported_at) VALUES(?,?,?)",
                             (source_key, result["session_id"], time.time()))
                conn.execute("UPDATE sessions SET started_at=?,ended_at=? WHERE id=?",
                             (occurred_at, occurred_at, result["session_id"]))
                rows = conn.execute("SELECT id,metadata_json FROM memories WHERE session_id=?",
                                    (result["session_id"],)).fetchall()
                for row in rows:
                    metadata = json.loads(row["metadata_json"] or "{}")
                    metadata.update({"capture_mode": "historical_import", "occurred_at": occurred_at,
                                     "historical_source": raw.get("source"), "provider": raw.get("provider")})
                    conn.execute("UPDATE memories SET metadata_json=?,created_at=?,updated_at=? WHERE id=?",
                                 (json.dumps(metadata, ensure_ascii=False), occurred_at, occurred_at, row["id"]))
        except Exception as exc:
            errors.append({"source": raw.get("source"), "session": raw.get("external_session_id"), "error": str(exc)})
    return {"ok": not errors, "project": project, "selected": len(selected), "imported": imported, "reused": reused,
            "ambiguous": ambiguous, "excluded": excluded, "errors": errors}


def import_history_archive(workspace: str | Path, sessions: list[dict[str, Any]], *, consent: bool,
                           provider: str = "deterministic", dry_run: bool = False) -> dict[str, Any]:
    """Import every discovered session into an explicit cross-project archive.

    Original workspace hints remain provenance metadata, but cannot accidentally
    route a transcript into the archive's own project identity rules.
    """
    prepared = []
    for raw in sessions:
        item = {**raw, "workspace": None, "explicit_project_selection": True}
        original_workspace = raw.get("workspace")
        item["messages"] = [{**message, "metadata": {**(message.get("metadata") or {}),
            "original_workspace": original_workspace, "archive_import": True}}
            for message in list(raw.get("messages") or [])]
        prepared.append(item)
    result = import_histories(workspace, prepared, consent=consent, provider=provider, dry_run=dry_run)
    result["archive"] = True
    result["source_projects"] = sorted({str(row.get("workspace")) for row in sessions if row.get("workspace")})
    return result
