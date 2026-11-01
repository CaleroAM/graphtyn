#!/usr/bin/env python3
"""Retrieval regression gate: rubric facts present in graph_query_intent packages.

Indexes small pinned corpora (fmt and Flask), builds the lean package for every
task of benchmarks/task_bank_2026-10-28 on those corpora and compares the
rubric coverage with tools/retrieval_coverage_baseline.json. No agent runs.

The gate fails when mean coverage drops, when a task loses two or more rubric
facts, or when a package claims completeness (do_not_expand=true) while
covering less than half of its rubric and did not before.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "benchmarks" / "task_bank_2026-10-28"
BASELINE = ROOT / "tools" / "retrieval_coverage_baseline.json"
CORPORA = {
    "fmt": ("https://github.com/fmtlib/fmt", "0fc31633e7d53ac895ae0a688b83b7d44f0b0c1f"),
    "flask": ("https://github.com/pallets/flask", "d086db856be187255b8ec61ef409357393020f32"),
}
MEAN_TOLERANCE = 0.01
TASK_TOLERANCE = 1


def _checkout(url: str, commit: str, destination: Path) -> None:
    if (destination / ".git").is_dir():
        current = subprocess.run(["git", "-C", str(destination), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        if current == commit:
            return
        raise SystemExit(f"{destination} is at {current}, expected {commit}")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"{destination} exists but is not a git checkout; refusing to touch it")
    destination.mkdir(parents=True, exist_ok=True)
    for command in (["git", "init", "-q"], ["git", "remote", "add", "origin", url],
                    ["git", "fetch", "-q", "--depth", "1", "origin", commit], ["git", "checkout", "-q", "FETCH_HEAD"]):
        subprocess.run(command, cwd=destination, check=True)


def _tasks(corpus: str) -> list[dict]:
    split = json.loads((BANK / "split.json").read_text(encoding="utf-8"))
    patterns = dict.fromkeys(pattern for paths in split.values() if isinstance(paths, list) for pattern in paths)
    tasks: dict[str, dict] = {}
    for pattern in patterns:
        path = BANK / pattern.format(corpus=corpus)
        if path.exists():
            for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]:
                tasks.setdefault(task["id"], task)
    return list(tasks.values())


def measure(corpus_root: Path) -> dict[str, dict]:
    from graphtyn.core.lean_package import lean_payload
    from graphtyn.core.storage import data_home, project_store_dir
    from graphtyn.mcp_server import build_intent_package

    rows: dict[str, dict] = {}
    for corpus, (url, commit) in CORPORA.items():
        workspace = corpus_root / corpus
        _checkout(url, commit, workspace)
        subprocess.run([sys.executable, "-m", "graphtyn.cli", "reindex", "--path", str(workspace),
                        "--engine", "ast_pure", "--mode", "fast"], check=True, stdout=subprocess.DEVNULL)
        graph = json.loads((project_store_dir(data_home(), workspace) / "index.json").read_text(encoding="utf-8"))
        for task in _tasks(corpus):
            _raw, result, _ = build_intent_package(workspace, graph, task["request"])
            text = json.dumps(lean_payload(result), ensure_ascii=False)
            covered = sum(any(term in text for term in fact["any"]) for fact in task["rubric"])
            rows[task["id"]] = {"covered": covered, "total": len(task["rubric"]),
                                "do_not_expand": bool(result.get("do_not_expand"))}
    return rows


def _false_complete(row: dict) -> bool:
    return row["do_not_expand"] and row["covered"] / row["total"] < 0.5


def compare(current: dict[str, dict], baseline: dict[str, dict]) -> list[str]:
    failures = []
    shared = sorted(set(current) & set(baseline))
    mean = lambda rows: statistics.fmean(rows[task]["covered"] / rows[task]["total"] for task in shared)
    if shared and mean(current) < mean(baseline) - MEAN_TOLERANCE:
        failures.append(f"mean coverage {mean(current):.1%} < baseline {mean(baseline):.1%}")
    for task in shared:
        lost = baseline[task]["covered"] - current[task]["covered"]
        if lost > TASK_TOLERANCE:
            failures.append(f"{task}: {current[task]['covered']}/{current[task]['total']} "
                            f"(baseline {baseline[task]['covered']})")
        if _false_complete(current[task]) and not _false_complete(baseline[task]):
            failures.append(f"{task}: claims completeness with {current[task]['covered']}/{current[task]['total']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, help="reuse pinned checkouts across runs")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="graphtyn-coverage-") as scratch:
        os.environ["GRAPHTYN_HOME"] = str(Path(scratch) / "home")
        current = measure(args.corpus_root or Path(scratch) / "corpora")
    if args.update_baseline:
        BASELINE.write_text(json.dumps({"schema_version": "1.0", "tasks": current}, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"Baseline actualizado: {BASELINE} ({len(current)} tareas)")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["tasks"]
    failures = compare(current, baseline)
    covered = statistics.fmean(row["covered"] / row["total"] for row in current.values())
    if failures:
        print("Retrieval coverage gate failed:\n- " + "\n- ".join(failures))
        print("Corrige la regresión o, tras una revisión explícita, actualiza el baseline.")
        return 1
    print(f"Retrieval coverage gate passed: {len(current)} tareas, cobertura media {covered:.1%}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
