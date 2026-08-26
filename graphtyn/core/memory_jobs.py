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

    def _write(self, job: dict[str, Any]) -> None:
        job["updated_at"] = time.time()
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            target = self._path(job["id"])
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(target)

    def get(self, job_id: str) -> dict[str, Any]:
        try: return json.loads(self._path(job_id).read_text(encoding="utf-8"))
        except FileNotFoundError: raise ValueError("job no encontrado")

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.root.is_dir(): return []
        jobs = []
        for path in sorted(self.root.glob("job_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try: jobs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError): continue
        return jobs

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["status"] in {"completed", "failed"}: return job
        self._cancelled.add(job_id)
        job["status"] = "cancelled"
        self._write(job)
        return job

    def run(self, job_id: str, operation: Callable[[Callable[[int, str], bool]], Any]) -> None:
        def worker():
            job = self.get(job_id)
            job["status"], job["progress"] = "running", 1
            self._write(job)

            def update(percent: int, message: str = "") -> bool:
                if job_id in self._cancelled: return False
                current = self.get(job_id)
                current["progress"] = max(0, min(99, int(percent)))
                current["message"] = message
                self._write(current)
                return True
            try:
                result = operation(update)
                job = self.get(job_id)
                if job["status"] != "cancelled":
                    job.update(status="completed", progress=100, result=result)
                    self._write(job)
            except Exception as exc:
                job = self.get(job_id)
                job.update(status="failed", error=str(exc))
                self._write(job)
        threading.Thread(target=worker, name=f"graphtyn-{job_id}", daemon=True).start()


memory_jobs = MemoryJobManager()
