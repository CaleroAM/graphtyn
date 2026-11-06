"""Whether a saved index was built by this parser, and its one-time rebuild when it was not.

A new parser version changes what the graph contains (calls attributed to overloads,
qualified Ruby bases, test blocks), but a saved `index.json` is loaded as it is. When
its `metadata.incremental.cache_version` differs from `PARSER_VERSION`, every graph
answer carries `index_status`, and the index is rebuilt once in the background with
the engine it was built with. A lock in the project store keeps the MCP servers of
several clients from rebuilding the same project at once.

`ast_cloud` indexes are never rebuilt automatically: that engine spends paid tokens.
`GRAPHTYN_AUTO_REINDEX=0` turns the rebuild off; the status is still reported.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .tree_sitter_backend import PARSER_VERSION

AUTO_ENV = "GRAPHTYN_AUTO_REINDEX"
LOCK_NAME = "parser_rebuild.lock"
# A failed rebuild keeps its lock this long, so a broken project is not retried by every call.
LOCK_SECONDS = 3 * 3600
_ENGINES = {"ast_pure": "ast_pure", "onboarding_ast_pure": "ast_pure", "watch_ast_pure": "ast_pure",
            "ast_local_llm": "ast_local_llm"}
_STATUS: dict[str, dict[str, Any] | None] = {}
_STARTED: set[str] = set()


def stale_status(graph: dict[str, Any]) -> dict[str, Any] | None:
    """What the index was built with, when it is not this parser; None when it is current."""
    metadata = graph.get("metadata")
    if not isinstance(metadata, dict):
        return None  # not an index Graphtyn wrote
    built = (metadata.get("incremental") or {}).get("cache_version")
    if built == PARSER_VERSION:
        return None
    return {"stale": True, "built_with": built or "unknown", "current": PARSER_VERSION,
            "engine": metadata.get("indexed_with") or "ast_pure"}


def _store(workspace: Path) -> Path:
    from .storage import data_home, project_store_dir
    return project_store_dir(data_home(), workspace, create=False)


def _auto_rebuild() -> bool:
    return os.environ.get(AUTO_ENV, "1").strip().lower() not in {"0", "off", "false", "no"}


def _start_rebuild(workspace: Path, engine: str) -> bool:
    """Start the rebuild unless another process holds a fresh lock; True when one is running."""
    key = str(workspace)
    if key in _STARTED:
        return True
    lock = _store(workspace) / LOCK_NAME
    try:
        if lock.exists():
            if time.time() - lock.stat().st_mtime < LOCK_SECONDS:
                _STARTED.add(key)
                return True
            lock.unlink()
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, f"{os.getpid()} {engine}\n".encode())
        os.close(descriptor)
        subprocess.Popen([sys.executable, "-m", "graphtyn.core.index_freshness", key, engine],
                         cwd=key, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        return False
    _STARTED.add(key)
    return True


def check(workspace: Path, graph: dict[str, Any]) -> dict[str, Any] | None:
    """Record whether `graph` is current for `workspace`, starting its rebuild when allowed."""
    workspace = Path(workspace).resolve()
    status = stale_status(graph)
    if status:
        engine = _ENGINES.get(str(status["engine"]))
        status["rebuilding"] = bool(engine and _auto_rebuild() and _start_rebuild(workspace, engine))
        if not status["rebuilding"]:
            status["action"] = f"graphtyn reindex --path {workspace}"
    _STATUS[str(workspace)] = status
    return status


def annotate(result: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Add `index_status` and a note to a graph answer built from a stale index."""
    status = _STATUS.get(str(Path(workspace).resolve()))
    if status:
        result["index_status"] = status
        note = (f"The index was built with parser {status['built_with']}, not {status['current']}: "
                + ("it is being rebuilt in the background, so" if status["rebuilding"] else
                   f"run `{status.get('action')}`; until then")
                + " some calls, overrides or test callers may be missing.")
        result["guidance"] = f"{result.get('guidance') or ''} {note}".strip()
    return result


def _rebuild(path: str, engine: str) -> int:
    """Child process: the dashboard's reindex, in this process and this GRAPHTYN_HOME.

    Asking a running dashboard instead could write into its own data home, which a
    client with an isolated home does not read.
    """
    try:
        from ..api.main import _execute_reindex
        result = _execute_reindex({"path": path, "engine": engine})
    except Exception:  # noqa: BLE001 - the lock stays: the next attempt waits LOCK_SECONDS
        return 1
    if result.get("cancelled"):
        return 1
    (_store(Path(path)) / LOCK_NAME).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_rebuild(sys.argv[1], sys.argv[2]))
