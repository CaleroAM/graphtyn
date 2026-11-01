#!/usr/bin/env python3
"""Run agent sessions that compare Graphtyn flow policies on one split of the task bank.

Each variant is either `none` (no Graphtyn) or a flow policy (GRAPHTYN_FLOW_POLICY,
`KEY=VALUE,...`; empty for the defaults). For every policy the script writes a
small executable into <runs-root>/bin/ that sets the policy and starts the
Graphtyn CLI, so MCP servers and prompt hooks launched by the clients use it.

Layout: <runs-root>/rep<N>/<variant>/<corpus>/<task id lowercased>/<client>/runs/<run_id>/,
graded by analyze_variants.py with one run root per repetition. Cells that
already hold a complete session are skipped; a failed session is copied to
<runs-root>/failed_attempts/ before it is retried, up to --attempts times.

usage: python run_variants.py test4 --variant none --variant current= \\
           --variant previous=CHAIN_SHARE=0,OUTLINE_LIMIT=0 --repetitions 3 \\
           [--runs-root DIR] [--repos-root DIR] [--parallel claude=3,codex=2]

--runs-root and --repos-root default to $GRAPHTYN_BENCH_RUNS and $GRAPHTYN_BENCH_REPOS.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HARNESS = ROOT / "benchmarks" / "run_three_client_mcp_comparison.py"
CORPORA = ("redis", "fmt", "rails", "flask", "lua", "jq", "sinatra")
MODELS = {"claude": "claude-sonnet-5-5", "codex": "gpt-5.6-luna"}
WRAPPER = '''#!{python}
"""Graphtyn CLI under the '{name}' flow policy (benchmark only)."""
import os
import sys
os.environ["GRAPHTYN_FLOW_POLICY"] = {policy!r}
from graphtyn.cli import main
sys.exit(main())
'''


def policy_executable(bin_dir: Path, name: str, policy: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / f"graphtyn-{name}"
    path.write_text(WRAPPER.format(python=sys.executable, name=name, policy=policy), encoding="utf-8")
    path.chmod(0o755)
    return path


def complete(run_dir: Path) -> bool:
    summary = run_dir / "summary.json"
    return summary.exists() and json.loads(summary.read_text()).get("session_status") == "complete"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("split")
    parser.add_argument("--variant", action="append", required=True, help="none, or NAME=POLICY")
    parser.add_argument("--client", action="append", choices=sorted(MODELS))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--runs-root", type=Path, default=os.environ.get("GRAPHTYN_BENCH_RUNS"))
    parser.add_argument("--repos-root", type=Path, default=os.environ.get("GRAPHTYN_BENCH_REPOS"))
    parser.add_argument("--parallel", default="claude=3,codex=2")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not args.runs_root or not args.repos_root:
        parser.error("--runs-root and --repos-root (or GRAPHTYN_BENCH_RUNS/GRAPHTYN_BENCH_REPOS) are required")
    clients = args.client or sorted(MODELS)
    executables = {}
    for spec in args.variant:
        name, _, policy = spec.partition("=")
        executables[name] = None if name == "none" else policy_executable(args.runs_root / "bin", name, policy)
    tasks = [(corpus, task) for corpus in CORPORA if (HERE / args.split / f"{corpus}_tasks.json").exists()
             for task in json.loads((HERE / args.split / f"{corpus}_tasks.json").read_text())["tasks"]]
    cells = [(rep, name, client, corpus, task) for rep in range(1, args.repetitions + 1)
             for name in executables for client in clients for corpus, task in tasks]

    def run(cell) -> str:
        rep, name, client, corpus, task = cell
        output = args.runs_root / f"rep{rep}" / name / corpus / task["id"].lower() / client
        run_dir = output / "runs" / f"{client}_{task['id']}_{'baseline' if name == 'none' else 'graphtyn_hook'}"
        if args.repetitions > 1:
            run_dir = run_dir.with_name(f"{run_dir.name}_r{rep}")
        for attempt in range(1, args.attempts + 1):
            if complete(run_dir):
                return f"{rep} {name} {client} {task['id']} complete"
            if run_dir.exists():
                kept = args.runs_root / "failed_attempts" / f"attempt{attempt}" / run_dir.relative_to(args.runs_root)
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(run_dir, kept, dirs_exist_ok=True)
                shutil.rmtree(run_dir)
            command = [sys.executable, str(HARNESS), "--protocol", str(HERE / args.split / f"{task['id'].lower()}_protocol.json"),
                       "--tasks", str(HERE / args.split / f"{corpus}_tasks.json"), "--repo", str(args.repos_root / corpus),
                       "--output-dir", str(output), "--model", f"{client}={MODELS[client]}", "--client", client,
                       "--arms", "baseline" if name == "none" else "graphtyn_hook",
                       "--repetitions", str(args.repetitions), "--repetition", str(rep),
                       "--timeout", str(args.timeout), "--stop-rule", "targeted", "--execute"]
            if executables[name]:
                command += ["--graphtyn-executable", str(executables[name])]
            subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        return f"{rep} {name} {client} {task['id']} {'complete' if complete(run_dir) else 'FAILED'}"

    limits = dict(item.split("=") for item in args.parallel.split(","))
    pools = {client: ThreadPoolExecutor(int(limits.get(client, 1))) for client in clients}
    futures = [pools[cell[2]].submit(run, cell) for cell in cells]
    for future in futures:
        print(future.result(), flush=True)
    for pool in pools.values():
        pool.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
