import time

from graphtyn.api import main as api_main
from graphtyn.api import reindex_worker
from graphtyn.core.memory_jobs import MemoryJobManager


def _wait(jobs, job_id, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        job = jobs.get(job_id)
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"} or time.monotonic() > deadline:
            return job
        time.sleep(0.1)


def test_a_reindex_job_runs_in_its_own_process_and_reports_through_the_job_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def charge():\n    return 1\n\n\ndef pay():\n    return charge()\n", encoding="utf-8")
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    monkeypatch.setenv(reindex_worker.WORKER_ENV, "process")
    jobs = MemoryJobManager(home / "reindex-jobs")
    monkeypatch.setattr(api_main, "reindex_jobs", jobs)
    payload = {"path": str(project), "engine": "ast_pure"}
    job = jobs.create("reindex", payload)

    api_main._start_reindex_worker(job["id"], payload)
    done = _wait(jobs, job["id"])

    assert done["status"] == "completed", done
    assert done["result"]["nodes"] >= 2 and (home / next(p.name for p in home.iterdir() if p.name.startswith("project")) / "index.json").is_file()


def test_a_worker_that_dies_marks_its_job_failed(tmp_path, monkeypatch):
    import subprocess
    import sys

    jobs = MemoryJobManager(tmp_path / "reindex-jobs")
    monkeypatch.setattr(api_main, "reindex_jobs", jobs)
    job = jobs.create("reindex", {"path": str(tmp_path), "engine": "ast_pure"})
    process = subprocess.Popen([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    reindex_worker.watch(process, job["id"], jobs)

    failed = jobs.get(job["id"])
    assert failed["status"] == "failed" and "código 3" in failed["error"] and "boom" in failed["error"]
