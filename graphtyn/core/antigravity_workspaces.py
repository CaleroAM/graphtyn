"""Workspaces of Antigravity (AGY) conversations, read from its metadata database.

A memory watcher asks for this map every cycle. Building it reads the whole database and resolves
each recorded workspace to its Git checkout with one ``git`` process per URI: on a real machine,
thousands of processes per cycle for a few hundred distinct paths. The map only changes with the
database and its cache file, so it is kept while their size and mtime stay the same. The Git root of
a path is remembered for a while, because a directory rarely becomes or stops being a checkout.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

GIT_ROOT_TTL = 900.0
_lock = threading.Lock()
_git_roots: dict[str, tuple[float, str]] = {}
_maps: dict[str, tuple[tuple, float, dict[str, str]]] = {}


def git_toplevel(path: Path) -> str:
    """The Git checkout root containing ``path``, or ``path`` itself outside a checkout.

    A workspace may be a subdirectory of its Git project. Normalizing it to that checkout root keeps
    exact project identity checks safe.
    """
    key = str(path)
    now = time.monotonic()
    with _lock:
        cached = _git_roots.get(key)
    if cached and cached[0] > now:
        return cached[1]
    value = key
    try:
        result = subprocess.run(["git", "-C", key, "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=2, check=False)
        if result.returncode == 0 and result.stdout.strip():
            value = str(Path(result.stdout.strip()).resolve())
    except (OSError, subprocess.SubprocessError):
        pass
    with _lock:
        _git_roots[key] = (now + GIT_ROOT_TTL, value)
    return value


def _version(root: Path) -> tuple:
    parts = []
    for name in ("conversation_summaries.db", "conversation_summaries.db-wal", "cache/last_conversations.json"):
        try:
            stat = (root / name).stat()
            parts.append((name, stat.st_size, stat.st_mtime_ns))
        except OSError:
            parts.append((name, None, None))
    return tuple(parts)


def antigravity_workspace_map(source_root: str | Path) -> dict[str, str]:
    """Map AGY transcript UUIDs to their recorded workspace; reused while its sources are unchanged."""
    root = Path(source_root).expanduser()
    if root.is_file():
        root = root.parent
    if root.name == "brain":
        root = root.parent
    key, version, now = str(root), _version(root), time.monotonic()
    with _lock:
        cached = _maps.get(key)
    # The Git roots inside it expire too: rebuild once they could have changed.
    if cached and cached[0] == version and cached[1] > now:
        return copy.deepcopy(cached[2])
    workspaces = _build_workspace_map(root)
    with _lock:
        _maps[key] = (version, now + GIT_ROOT_TTL, copy.deepcopy(workspaces))
    return workspaces


def clear_caches() -> None:
    with _lock:
        _git_roots.clear(); _maps.clear()


def _build_workspace_map(root: Path) -> dict[str, str]:
    """Map AGY transcript UUIDs to their recorded workspace from its metadata DB.

    Antigravity's canonical transcript JSONL omits the workspace. Its adjacent
    conversation_summaries.db carries workspace_uris, so use that metadata to
    route a session without assigning every AGY conversation to one project.
    """
    database = root / "conversation_summaries.db"
    rows = []
    if database.is_file():
        try:
            connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True, timeout=1)
            connection.execute("PRAGMA query_only=ON")
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(conversation_summaries)")}
            if not {"conversation_id", "workspace_uris"}.issubset(columns):
                connection.close()
            else:
                rows = connection.execute(
                    "SELECT conversation_id, workspace_uris FROM conversation_summaries"
                ).fetchall()
                connection.close()
        except sqlite3.Error:
            rows = []

    def decode_workspace(value: str) -> str | None:
        try:
            parsed = urlparse(value)
            if parsed.scheme == "file":
                value = unquote(parsed.path)
                if parsed.netloc and parsed.netloc.casefold() not in {"", "localhost"}:
                    value = f"//{parsed.netloc}{value}"
                elif re.match(r"^/[A-Za-z]:[\\/]", value):
                    # RFC 8089 file URIs encode Windows drives as file:///C:/…;
                    # pathlib on Windows expects C:/…, without the extra slash.
                    value = value[1:]
            path = Path(value).expanduser()
            if not path.is_absolute():
                return None
            normalized = path.resolve()
        except (OSError, RuntimeError, ValueError):
            return None

        return git_toplevel(normalized)

    workspaces: dict[str, str] = {}
    ambiguous_sessions: set[str] = set()

    def associate(session_id: Any, workspace: str | None) -> None:
        if not session_id or not workspace or str(session_id) in ambiguous_sessions:
            return
        key = str(session_id)
        previous = workspaces.get(key)
        if previous and previous != workspace:
            workspaces.pop(key, None)
            ambiguous_sessions.add(key)
        else:
            workspaces[key] = workspace

    for session_id, raw_uris in rows:
        try:
            uris = json.loads(raw_uris) if isinstance(raw_uris, str) else raw_uris
        except (TypeError, ValueError):
            continue
        if isinstance(uris, str):
            uris = [uris]
        if not isinstance(uris, list):
            continue
        candidates = sorted({workspace for uri in uris if isinstance(uri, str)
                             if (workspace := decode_workspace(uri))})
        # Multiple distinct project roots are ambiguous and must stay pending.
        if len(candidates) == 1 and session_id:
            associate(session_id, candidates[0])

    # The AGY CLI's non-interactive sessions may not yet have a row in
    # conversation_summaries.db. Its cache maps each working directory to the
    # latest native conversation id; this safely scopes an active/new session
    # without importing the rest of the user's AGY history.
    latest_file = root / "cache" / "last_conversations.json"
    try:
        latest = json.loads(latest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        latest = {}
    if isinstance(latest, dict):
        for workspace_uri, session_id in latest.items():
            if not isinstance(workspace_uri, str) or not isinstance(session_id, str):
                continue
            associate(session_id, decode_workspace(workspace_uri))
    return workspaces
