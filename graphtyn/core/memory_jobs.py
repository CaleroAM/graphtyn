"""Persistent background jobs for historical discovery and imports."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .storage import data_home


class MemoryJobManager:
    def __init__(self, root: Path | None = None):
        self.root = root or data_home() / "memory-jobs"
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()

    def _path(self, job_id: str) -> Path:
        if not job_id.startswith("job_") or not job_id[4:].isalnum(): raise ValueError("job_id inválido")
        return self.root / f"{job_id}.json"

    def create(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        job = {"id": f"job_{uuid.uuid4().hex}", "kind": kind, "status": "pending", "progress": 0,
               "created_at": time.time(), "updated_at": time.time(), "payload": payload,
               "result": None, "error": None}
        self._write(job)
        return job

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        """Atomically update and return one persisted job."""
        job = self.get(job_id)
        job.update(changes)
        self._write(job)
        return job

    def _write(self, job: dict[str, Any]) -> None:
        job["updated_at"] = time.time()
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            target = self._path(job["id"])
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(target)

    def get(self, job_id: str) -> dict[str, Any]:
        # Windows can reject reads while the worker is replacing the target
        # file. Share the writer lock with _write so polling never observes a
        # transient access error during an atomic update.
        with self._lock:
            try: return json.loads(self._path(job_id).read_text(encoding="utf-8"))
            except FileNotFoundError: raise ValueError("job no encontrado")

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if not self.root.is_dir(): return []
            jobs = []
            for path in sorted(self.root.glob("job_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
                try: jobs.append(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError): continue
            return jobs

    def find_active(self, kind: str, key: str, value: str) -> dict[str, Any] | None:
        for job in self.list(limit=500):
            if job.get("kind") != kind or job.get("status") not in {"pending", "running", "cancelling"}:
                continue
            payload = job.get("payload") or {}
            if str(payload.get(key) or "") == value:
                return job
        return None

    def reconcile(self, kind: str | None = None) -> int:
        """Mark jobs abandoned by a previous process as interrupted."""
        count = 0
        for job in self.list(limit=1000):
            if kind and job.get("kind") != kind:
                continue
            if job.get("status") not in {"pending", "running", "cancelling"}:
                continue
            job.update(status="interrupted", error="El proceso terminó antes de completar el trabajo",
                       message="Interrumpido por reinicio")
            self._write(job)
            count += 1
        return count

    def prune(self, *, max_age_seconds: float = 7 * 86400, max_jobs: int = 200) -> int:
        """Remove only terminal jobs beyond the configured retention window."""
        terminal = {"completed", "failed", "cancelled", "interrupted"}
        now = time.time()
        removed = 0
        with self._lock:
            if not self.root.is_dir():
                return 0
            paths = sorted(self.root.glob("job_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for index, path in enumerate(paths):
                try:
                    job = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                expired = now - float(job.get("updated_at") or path.stat().st_mtime) > max_age_seconds
                over_limit = index >= max(1, int(max_jobs))
                if job.get("status") in terminal and (expired or over_limit):
                    try:
                        path.unlink()
                        removed += 1
                    except FileNotFoundError:
                        pass
        return removed

    def is_cancelled(self, job_id: str) -> bool:
        if job_id in self._cancelled:
            return True
        try:
            return bool(self.get(job_id).get("cancel_requested"))
        except ValueError:
            return True

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}: return job
        self._cancelled.add(job_id)
        job["cancel_requested"] = True
        job["status"] = "cancelling"
        job["message"] = "Cancelación solicitada; se aplicará entre etapas"
        self._write(job)
        return job

    def run(self, job_id: str, operation: Callable[[Callable[[int, str], bool]], Any]) -> None:
        def worker():
            job = self.get(job_id)
            job["status"], job["progress"] = "running", 1
            self._write(job)

            def update(percent: int, message: str = "") -> bool:
                if self.is_cancelled(job_id): return False
                current = self.get(job_id)
                current["progress"] = max(0, min(99, int(percent)))
                current["message"] = message
                self._write(current)
                return True
            try:
                result = operation(update)
                job = self.get(job_id)
                if self.is_cancelled(job_id) or (isinstance(result, dict) and result.get("cancelled")):
                    job.update(status="cancelled", result=result,
                               message="Cancelado entre etapas")
                    self._write(job)
                elif job["status"] != "cancelled":
                    job.update(status="completed", progress=100, result=result)
                    self._write(job)
            except Exception as exc:
                job = self.get(job_id)
                job.update(status="failed", error=str(exc))
                self._write(job)
        threading.Thread(target=worker, name=f"graphtyn-{job_id}", daemon=True).start()


memory_jobs = MemoryJobManager()
