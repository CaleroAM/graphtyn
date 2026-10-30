"""Retry failed agent sessions of the test3 variant comparison with bounded parallelism."""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path("/home/calero/Documentos/docker/graphtyn-benchmark-runs-test3-2026-10-29")
B = Path("benchmarks/task_bank_2026-10-28")
S = Path(sys.argv[1])
EXE = {"none": ".venv/bin/graphtyn", "current": str(S / "bin/graphtyn-previous"), "BCD": ".venv/bin/graphtyn"}
MODEL = {"claude": "claude-sonnet-5-5", "codex": "gpt-5.6-luna"}
corpus_of = {t["id"]: c for c in ("redis", "rails", "flask", "lua") for t in json.loads((B / "test3" / f"{c}_tasks.json").read_text())["tasks"]}
data = json.loads((B / "agent_variants_test3.json").read_text())
done = {(r["repetition"], r["variant"], r["client"], r["task_id"]) for r in data["runs"] if r["session_status"] == "complete"}
failed_dirs = {(r["repetition"], r["variant"], r["client"], r["task_id"]): r["raw_directory"] for r in data["runs"]
               if r["session_status"] != "complete" and r["variant"] in EXE}
expected = {(rep, variant, client, task) for rep in (1, 2, 3) for variant in EXE for client in MODEL for task in corpus_of}
todo = sorted(expected - done)
import shutil
for item in todo:
    src = Path(failed_dirs.get(item, "/nonexistent"))
    if src.exists():
        dst = ROOT / "failed_attempts" / f"retry{len(sys.argv)}" / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src)
print(len(todo), "to retry", flush=True)
def run(item):
    rep, variant, client, task = item
    corpus = corpus_of[task]
    root = ROOT if rep == 1 else ROOT / f"rep{rep}"
    cmd = [".venv/bin/python", "benchmarks/run_three_client_mcp_comparison.py",
           "--protocol", str(B / "test3" / f"{task.lower()}_protocol.json"), "--tasks", str(B / "test3" / f"{corpus}_tasks.json"),
           "--repo", f"/home/calero/Documentos/docker/graphtyn-benchmark-repos-2026-10-20/{corpus}",
           "--output-dir", str(root / variant / corpus / task.lower() / client), "--model", f"{client}={MODEL[client]}",
           "--client", client, "--arms", "baseline" if variant == "none" else "graphtyn_hook",
           "--repetitions", str(rep), "--repetition", str(rep), "--graphtyn-executable", EXE[variant],
           "--timeout", "600", "--stop-rule", "targeted", "--execute"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(rep, variant, client, task, "rc", proc.returncode, proc.stderr.strip().splitlines()[-1:] if proc.returncode else "", flush=True)
with ThreadPoolExecutor(3) as claude_pool, ThreadPoolExecutor(2) as codex_pool:
    for item in todo:
        (claude_pool if item[2] == "claude" else codex_pool).submit(run, item)
