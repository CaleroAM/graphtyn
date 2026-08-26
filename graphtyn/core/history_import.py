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
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .shared_memory import SharedMemoryStore
from .storage import data_home


BUILTIN_PROVIDERS = {"openclaw", "hermes", "codex", "antigravity", "opencode", "claude"}
_ROLE_ALIASES = {"human": "user", "user": "user", "assistant": "assistant", "ai": "assistant",
                 "tool": "tool", "function": "tool"}
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
    return {
        "openclaw": [home / ".openclaw" / "agents"],
        "hermes": [home / ".hermes", home / ".config" / "hermes"],
        "codex": [home / ".codex" / "sessions"],
        "antigravity": [home / ".agy", home / ".config" / "antigravity"],
        "opencode": [home / ".local" / "share" / "opencode"],
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
            result.append({"provider": provider, "source": source, "label": str(row.get("label") or "")})
    return result


def save_source(provider: str, source: str, *, label: str = "", path: Path | None = None) -> dict[str, Any]:
    """Persist a host/container/VPS history source with restrictive permissions."""
    provider, source = provider.strip().casefold(), source.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", provider): raise ValueError("proveedor inválido")
    if not source or "\x00" in source: raise ValueError("fuente inválida")
    target = path or sources_config_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = configured_sources(target)
    item = {"provider": provider, "source": source, "label": label.strip(), "enabled": True}
    rows = [row for row in rows if not (row["provider"] == item["provider"] and row["source"] == item["source"])]
    rows.append(item)
    target.write_text(json.dumps({"version": 1, "sources": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(target, 0o600)
    return item


def delete_source(provider: str, source: str, *, path: Path | None = None) -> bool:
    target = path or sources_config_file(); rows = configured_sources(target)
    kept = [row for row in rows if not (row["provider"] == provider.casefold() and row["source"] == source)]
    changed = len(kept) != len(rows)
    if changed:
        target.write_text(json.dumps({"version": 1, "sources": kept}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(target, 0o600)
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
    if parsed.scheme == "ssh": command = ["ssh", "-o", "BatchMode=yes", ssh_target, *tar_args]
    elif parsed.scheme == "docker": command = ["docker", "exec", container, *tar_args]
    else: command = ["ssh", "-o", "BatchMode=yes", ssh_target, "docker", "exec", container, *tar_args]
    with archive.open("wb") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, timeout=600)
    if result.returncode:
        temp.cleanup()
        raise OSError(f"no se pudo copiar la fuente remota: {result.stderr.decode(errors='replace').strip()[:300]}")
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(destination, filter="data")
    archive.unlink(missing_ok=True)
    copied = destination / Path(remote_path).name
    return copied, temp, raw.rstrip("/")


def _walk_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for key in ("messages", "history", "conversation", "turns", "events", "items", "payload", "message", "data"):
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
    value = record.get("content", record.get("text", record.get("message", record.get("body", ""))))
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str): parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str): parts.append(item["text"])
        value = "\n".join(parts)
    if isinstance(value, dict):
        value = value.get("text") or value.get("content") or ""
    return str(value or "").strip()


def _role(record: dict[str, Any]) -> str | None:
    raw = record.get("role") or record.get("author") or record.get("sender") or record.get("type")
    if isinstance(raw, dict): raw = raw.get("role") or raw.get("name")
    return _ROLE_ALIASES.get(str(raw or "").casefold())


def parse_history_database(path: Path, provider: str, agent_hint: str | None = None) -> list[HistoricalSession]:
    """Read common role/content/session columns without modifying an agent DB."""
    uri = f"file:{path.resolve()}?mode=ro"
    grouped: dict[str, dict[str, Any]] = {}
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
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
    return [HistoricalSession(provider, f"{provider}/{agent}", sid,
        str(group.get("title") or next((m["content"] for m in group["messages"] if m["role"] == "user"), "Historical session"))[:180],
        group["messages"], str(path), min(group["timestamps"], default=None), group["workspace"], group.get("branch"))
        for sid, group in grouped.items() if group["messages"]]


def _workspace(record: dict[str, Any]) -> str | None:
    for key in ("cwd", "workspace", "workspaceDir", "project_path", "workdir", "directory"):
        value = record.get(key)
        if isinstance(value, str) and value.strip(): return value.strip()
    metadata = record.get("metadata") or record.get("context")
    return _workspace(metadata) if isinstance(metadata, dict) and metadata and metadata is not record else None


def parse_history_file(path: Path, provider: str, agent_hint: str | None = None) -> list[HistoricalSession]:
    """Parse JSON/JSONL histories defensively; unknown records are ignored."""
    try:
        if path.suffix.casefold() == ".jsonl":
            values = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                      if line.strip().startswith(("{", "["))]
        else:
            loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            values = loaded if isinstance(loaded, list) else [loaded]
    except (OSError, ValueError, TypeError):
        return []
    grouped: dict[str, dict[str, Any]] = {}
    file_workspace = next((_workspace(value) for value in values
                           if isinstance(value, dict) and _workspace(value)), None)
    file_session = next((value.get("sessionId") or value.get("session_id") or value.get("conversation_id")
                         for value in values if isinstance(value, dict) and
                         (value.get("sessionId") or value.get("session_id") or value.get("conversation_id"))), None)
    for root in values:
        root_session = ((root.get("sessionId") or root.get("session_id") or root.get("conversation_id"))
                        if isinstance(root, dict) else None) or file_session
        root_workspace = (_workspace(root) if isinstance(root, dict) else None) or file_workspace
        for record in _walk_records(root):
            role, content = _role(record), _content(record)
            if not role or not content: continue
            sid = str(record.get("sessionId") or record.get("session_id") or record.get("conversation_id")
                      or root_session or path.stem)
            group = grouped.setdefault(sid, {"messages": [], "workspace": root_workspace, "timestamps": []})
            group["messages"].append({"role": role, "content": content,
                                      "metadata": {"historical_source": str(path)}})
            group["workspace"] = group["workspace"] or _workspace(record)
            stamp = record.get("timestamp") or record.get("created_at") or record.get("createdAt")
            if isinstance(stamp, (int, float)): group["timestamps"].append(float(stamp) / (1000 if stamp > 1e11 else 1))
            elif isinstance(stamp, str):
                try: group["timestamps"].append(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
                except ValueError: pass
    agent = agent_hint or (path.parent.parent.name if provider == "openclaw" and path.parent.name == "sessions" else provider)
    sessions = []
    for sid, group in grouped.items():
        if not group["messages"]: continue
        first_user = next((m["content"] for m in group["messages"] if m["role"] == "user"), "Historical session")
        sessions.append(HistoricalSession(provider, f"{provider}/{agent}", sid, first_user[:180],
            group["messages"], str(path), min(group["timestamps"], default=None), group["workspace"]))
    return sessions


def discover_histories(provider: str | None = None, sources: list[str] | None = None) -> dict[str, Any]:
    configured = configured_sources()
    from .adapters import list_adapters
    known = {row["name"] for row in list_adapters()}
    providers = [provider.casefold()] if provider else sorted(known | {row["provider"] for row in configured})
    found, errors = [], []
    for name in providers:
        roots = sources if sources else [row["source"] for row in configured if row["provider"] == name]
        if not roots: roots = default_sources().get(name, [])
        for source in roots:
            temp = None
            try:
                root, temp, source_label = _materialize_source(source)
                if not root.exists(): continue
                files = ([root] if root.is_file() else [p for p in root.rglob("*.jsonl") if ".trajectory." not in p.name]
                         + list(root.rglob("*.json"))
                         + list(root.rglob("*.db")) + list(root.rglob("*.sqlite")) + list(root.rglob("*.sqlite3")))
                for path in files:
                    parser = parse_history_database if path.suffix.casefold() in {".db", ".sqlite", ".sqlite3"} else parse_history_file
                    for session in parser(path, name):
                        if str(source).startswith(("ssh://", "docker://", "ssh+docker://")):
                            try: session.source = f"{source_label}/{path.relative_to(root).as_posix()}"
                            except ValueError: session.source = source_label
                        found.append({**asdict(session), "fingerprint": session.fingerprint,
                                      "message_count": len(session.messages)})
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
    return {"ok": not errors, "sessions": found, "count": len(found), "projects": projects, "errors": errors}


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
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
                     provider: str = "deterministic", dry_run: bool = False) -> dict[str, Any]:
    if not consent: raise PermissionError("la importación histórica requiere consentimiento explícito")
    root = Path(workspace).expanduser().resolve()
    registry = ProjectIdentityRegistry()
    project = registry.register(root)
    selected, ambiguous = [], []
    for raw in sessions:
        workspace_hint = str(raw.get("workspace") or "").strip()
        hinted = registry.resolve(workspace_hint)
        if hinted and hinted["id"] != project["id"]:
            ambiguous.append({"session": raw.get("external_session_id"), "workspace": workspace_hint,
                              "suggested_project": hinted["canonical_name"]})
            continue
        if workspace_hint and not hinted:
            hint_name = Path(workspace_hint).name.casefold()
            current_names = {project["canonical_name"].casefold(), *(a.casefold() for a in project.get("aliases", []))}
            if hint_name not in current_names:
                ambiguous.append({"session": raw.get("external_session_id"), "workspace": workspace_hint,
                                  "suggested_project": Path(workspace_hint).name, "reason": "proyecto no registrado"})
                continue
        selected.append(raw)
    if dry_run:
        return {"ok": True, "dry_run": True, "project": project, "selected": len(selected),
                "ambiguous": ambiguous, "sessions": selected}
    store, imported, reused, errors = SharedMemoryStore(root), [], [], []
    for raw in selected:
        try:
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
            external_id = f"historical:{raw.get('external_session_id') or raw.get('fingerprint')}"
            session_id = "ses_ext_" + hashlib.sha256(f"{agent_id}\0{external_id}".encode()).hexdigest()[:24]
            existing_pairs = {(message.get("role"), message.get("content"))
                              for message in store.list_messages(session_id, limit=1000)}
            historical_messages = []
            for message in list(raw.get("messages") or []):
                if (message.get("role"), message.get("content")) in existing_pairs:
                    continue
                historical_messages.append({**message, "metadata": {**(message.get("metadata") or {}),
                    "capture_mode": "historical_import", "occurred_at": occurred_at,
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
                reopen_closed=True)
            imported.append({"source": raw.get("source"), "session_id": result["session_id"],
                             "external_session_id": raw.get("external_session_id")})
            with store._connect() as conn:
                conn.execute("INSERT OR IGNORE INTO legacy_imports(source_key,memory_id,imported_at) VALUES(?,?,?)",
                             (source_key, result["session_id"], time.time()))
                conn.execute("UPDATE sessions SET started_at=?,ended_at=? WHERE id=?",
                             (occurred_at, occurred_at, result["session_id"]))
                conn.execute("UPDATE messages SET created_at=? WHERE session_id=?", (occurred_at, result["session_id"]))
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
            "ambiguous": ambiguous, "errors": errors}


def import_history_archive(workspace: str | Path, sessions: list[dict[str, Any]], *, consent: bool,
                           provider: str = "deterministic", dry_run: bool = False) -> dict[str, Any]:
    """Import every discovered session into an explicit cross-project archive.

    Original workspace hints remain provenance metadata, but cannot accidentally
    route a transcript into the archive's own project identity rules.
    """
    prepared = []
    for raw in sessions:
        item = {**raw, "workspace": None}
        original_workspace = raw.get("workspace")
        item["messages"] = [{**message, "metadata": {**(message.get("metadata") or {}),
            "original_workspace": original_workspace, "archive_import": True}}
            for message in list(raw.get("messages") or [])]
        prepared.append(item)
    result = import_histories(workspace, prepared, consent=consent, provider=provider, dry_run=dry_run)
    result["archive"] = True
    result["source_projects"] = sorted({str(row.get("workspace")) for row in sessions if row.get("workspace")})
    return result
