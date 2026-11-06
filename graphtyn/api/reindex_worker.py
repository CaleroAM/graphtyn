"""Run one dashboard reindex job in its own process.

A large project keeps a scan busy for many minutes. Inside the web server process it
competed for the interpreter with every request, and status polls timed out. The job
file is the only shared state: the worker updates progress and result there, and a
cancellation written there by the server is seen between stages.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Any, Callable

# Tests patch the scan in-process, so they run jobs in a thread instead.
WORKER_ENV = "GRAPHTYN_REINDEX_WORKER"
_TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def start(job_id: str, payload: dict[str, Any], jobs: Any, run_job: Callable[[str, dict], None]) -> None:
    if os.environ.get(WORKER_ENV, "process").strip().lower() == "thread":
        threading.Thread(target=run_job, args=(job_id, payload), name=f"graphtyn-{job_id}", daemon=True).start()
        return
    process = subprocess.Popen([sys.executable, "-m", "graphtyn.api.reindex_worker", job_id],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    threading.Thread(target=watch, args=(process, job_id, jobs), name=f"graphtyn-{job_id}-watch", daemon=True).start()


def watch(process: subprocess.Popen, job_id: str, jobs: Any) -> None:
    """Fail a job whose process died before writing a final state."""
    _out, err = process.communicate()
    try:
        job = jobs.get(job_id)
    except ValueError:
        return
    if job.get("status") not in _TERMINAL:
        detail = (err or b"").decode("utf-8", errors="replace").strip()[-500:]
        jobs.update(job_id, status="failed", message="La reindexación falló",
                    error=f"El proceso de reindexado terminó con código {process.returncode}: {detail}".strip(": "))


def main(job_id: str) -> int:
    from . import main as api
    job = api.reindex_jobs.get(job_id)
    api._run_reindex_job(job_id, job["payload"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
