"""Portable polling watcher for incremental Graphtyn refreshes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .ast_parser import ASTParser, VALID_EXTS


_IGNORED_PARTS = {
    "vendor", "venv", ".venv", "node_modules", "__pycache__", "Library",
    "Logs", "Temp", "obj", "bin", "dist", "build", ".git", ".idea", "Captures", ".vs",
}


class ProjectWatcher:
    def __init__(self, root: Path, index_dir: Path, interval: float = 1.0):
        self.root = root.resolve()
        self.index_dir = index_dir
        self.interval = max(0.25, interval)
        self.manifest_path = index_dir / "watch_manifest.json"
        self.cache_path = index_dir / "structural_cache.json"
        self.index_path = index_dir / "index.json"
        self.version = 0
        self.last_event: dict[str, Any] = {}
        self.last_error = ""
        self.running = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._manifest = self._load_manifest()

    def _respect_git(self) -> bool:
        try:
            cfg = json.loads((self.index_dir / "config.json").read_text(encoding="utf-8"))
            return bool(cfg.get("respect_git", True))
        except (OSError, ValueError, TypeError):
            return True

    def _eligible_files(self) -> list[Path]:
        if self._respect_git() and (self.root / ".git").exists():
            try:
                result = subprocess.run(
                    ["git", "ls-files", "-z"], cwd=self.root, capture_output=True, timeout=30
                )
                if result.returncode == 0:
                    paths = []
                    for raw in result.stdout.split(b"\0"):
                        if not raw:
                            continue
                        rel = raw.decode("utf-8", errors="replace")
                        path = self.root / rel
                        if path.is_file() and path.suffix.lower() in VALID_EXTS:
                            paths.append(path)
                    return paths
            except (OSError, subprocess.SubprocessError):
                pass
        return [
            path for path in self.root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in VALID_EXTS
            and not any(part.startswith(".") or part in _IGNORED_PARTS for part in path.relative_to(self.root).parts)
        ]

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return data.get("files", {}) if data.get("version") == 1 else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _snapshot(self) -> dict[str, dict[str, Any]]:
        snapshot = {}
        for path in self._eligible_files():
            try:
                stat = path.stat()
                rel = path.relative_to(self.root).as_posix()
                previous = self._manifest.get(rel, {})
                if previous.get("size") == stat.st_size and previous.get("mtime_ns") == stat.st_mtime_ns:
                    digest = previous.get("sha256", "")
                else:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                snapshot[rel] = {"sha256": digest, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            except OSError:
                continue
        return snapshot

    def _save_manifest(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"version": 1, "files": self._manifest}, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.manifest_path)

    def _refresh(self, changed: set[str], removed: set[str]) -> None:
        from ..api.enrich import _enrich_with_ai

        previous = None
        if self.index_path.exists():
            try:
                previous = json.loads(self.index_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        graph = ASTParser().scan_directory(
            self.root, respect_git=self._respect_git(), cache_path=self.cache_path
        )
        graph.setdefault("metadata", {}).update({
            "indexed_with": "watch_ast_pure",
            "status": "ok",
            "path": str(self.root),
            "respect_git": self._respect_git(),
            "reindex_mode": "incremental_watch",
            "changed_files": len(changed),
            "removed_files": len(removed),
        })
        graph = _enrich_with_ai(graph, "ast_pure", self.root, prev=previous, changed=changed | removed)
        temp = self.index_path.with_suffix(".tmp")
        temp.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        temp.replace(self.index_path)

    def scan_once(self, refresh: bool = True) -> dict[str, Any] | None:
        current = self._snapshot()
        previous_manifest = self._manifest
        old_keys, new_keys = set(previous_manifest), set(current)
        created = new_keys - old_keys
        removed = old_keys - new_keys
        modified = {
            key for key in old_keys & new_keys
            if previous_manifest[key].get("sha256") != current[key].get("sha256")
        }
        changed = created | modified
        if not changed and not removed:
            return None
        if refresh:
            self._refresh(changed, removed)
        # Commit the manifest only after a successful refresh. A transient
        # parser/write error must be retried on the next polling cycle.
        self._manifest = current
        self._save_manifest()
        self.version += 1
        self.last_event = {
            "version": self.version,
            "path": str(self.root),
            "created": sorted(created),
            "modified": sorted(modified),
            "removed": sorted(removed),
            "timestamp": time.time(),
        }
        return self.last_event

    def _run(self) -> None:
        self.running = True
        if not self._manifest:
            self._manifest = self._snapshot()
            self._save_manifest()
        while not self._stop.wait(self.interval):
            try:
                self.scan_once(refresh=True)
                self.last_error = ""
            except Exception as exc:
                self.last_error = str(exc)
        self.running = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"graphtyn-watch-{self.root.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def status(self) -> dict[str, Any]:
        return {
            "path": str(self.root), "running": self.running, "version": self.version,
            "last_event": self.last_event, "error": self.last_error,
        }


class WatchManager:
    def __init__(self):
        self._watchers: dict[str, ProjectWatcher] = {}
        self._lock = threading.Lock()

    def ensure(self, root: Path, index_dir: Path) -> ProjectWatcher:
        key = str(root.resolve())
        with self._lock:
            watcher = self._watchers.get(key)
            if watcher is None:
                interval = float(os.environ.get("GRAPHTYN_WATCH_INTERVAL", "1.0"))
                watcher = ProjectWatcher(root, index_dir, interval=interval)
                self._watchers[key] = watcher
            watcher.start()
            return watcher

    def stop_all(self) -> None:
        for watcher in list(self._watchers.values()):
            watcher.stop()

    def statuses(self) -> list[dict[str, Any]]:
        return [watcher.status() for watcher in self._watchers.values()]
