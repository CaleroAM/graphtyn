#!/usr/bin/env python3
"""Retrieval regression gate: rubric facts present in graph_query_intent packages.

Indexes pinned public corpora, builds the lean package for every task of
benchmarks/task_bank_2026-10-28 and of the spent validation folders, and compares
the rubric coverage with tools/retrieval_coverage_baseline.json. No agent runs.

The gate fails when mean coverage drops, when a task loses two or more rubric
facts, or when a package claims completeness (do_not_expand=true) while
covering less than half of its rubric and did not before. It also fails when a
corpus's graph loses more than a tenth of its extracted calls, inheritance edges
or typed fields: Java extracted no method call for months and nothing noticed.

A validation's frozen tasks join SPENT only after the validation ran, so a change
is never tuned against tasks still held out.
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
    "redis": ("https://github.com/redis/redis", "f2a17a8dca1566d2a0f078840fffef5661eab4b1"),
    "rails": ("https://github.com/rails/rails", "3f0b675158e8284241bb1213c00375bc1fb9c52f"),
    "gson": ("https://github.com/google/gson", "65df6e5a99747f73d386f3a61d887a0257255e0f"),
    "slim": ("https://github.com/slimphp/Slim", "3675bf6baac66b07032575b7bef4200b60b7974b"),
    "cobra": ("https://github.com/spf13/cobra", "adbc8813901bba65827259daa8e22ff94ec1f30e"),
    "ripgrep": ("https://github.com/BurntSushi/ripgrep", "91f5d22ef48bde459d90a8c7dbeab416e97d0f2b"),
    "express": ("https://github.com/expressjs/express", "43fca52d28a422c8be48fd489cbd4f2d6152bab6"),
    "ky": ("https://github.com/sindresorhus/ky", "3541888878c4d303a8bc2ad61815f4e048f55a5d"),
}
# Corpora kept only for their graph floor, without tasks (none since the final validation).
GRAPH_ONLY: frozenset[str] = frozenset()
# Validation folders whose runs are finished: their tasks are no longer held out.
SPENT = ("intent_impact_2026-11-04", *(f"intent_impact_2026-11-04/set{number}" for number in range(2, 7)),
         "graphify_head_to_head_2026-11-06", "h2h_fix_validation_2026-11-06", "inherited_self_calls_2026-11-06",
         "language_conformance_2026-11-06", "workspace_scope_2026-11-06", "impact_completeness_2026-11-06",
         "final_validation_2026-11-08")
GRAPH_TOLERANCE = 0.10
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
    paths = [BANK / pattern.format(corpus=corpus) for pattern in patterns]
    paths += [ROOT / "benchmarks" / folder / f"{corpus}_tasks.json" for folder in SPENT]
    for path in paths:
        if path.exists():
            for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]:
                tasks.setdefault(task["id"], task)
    return list(tasks.values())


def graph_stats(graph: dict) -> dict[str, int]:
    links = graph.get("links", [])
    return {"extracted_calls": sum(link.get("label") == "llama" and link.get("confidence") == "EXTRACTED" for link in links),
            "inheritance": sum(link.get("label") in ("hereda", "implementa") for link in links),
            "typed_fields": sum(node.get("kind") in ("field", "property") for node in graph.get("nodes", []))}


def measure(corpus_root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    from graphtyn.core.lean_package import lean_payload
    from graphtyn.core.storage import data_home, project_store_dir
    from graphtyn.mcp_server import build_intent_package

    rows: dict[str, dict] = {}
    graphs: dict[str, dict] = {}
    for corpus, (url, commit) in CORPORA.items():
        workspace = corpus_root / corpus
        _checkout(url, commit, workspace)
        subprocess.run([sys.executable, "-m", "graphtyn.cli", "reindex", "--path", str(workspace),
                        "--engine", "ast_pure", "--mode", "fast"], check=True, stdout=subprocess.DEVNULL)
        graph = json.loads((project_store_dir(data_home(), workspace) / "index.json").read_text(encoding="utf-8"))
        graphs[corpus] = graph_stats(graph)
        for task in _tasks(corpus):
            _raw, result, _ = build_intent_package(workspace, graph, task["request"])
            text = json.dumps(lean_payload(result), ensure_ascii=False)
            covered = sum(any(term in text for term in fact["any"]) for fact in task["rubric"])
            rows[task["id"]] = {"covered": covered, "total": len(task["rubric"]),
                                "do_not_expand": bool(result.get("do_not_expand"))}
    return rows, graphs


def compare_graphs(current: dict[str, dict], baseline: dict[str, dict]) -> list[str]:
    failures = []
    for corpus in sorted(set(current) & set(baseline)):
        for stat, value in baseline[corpus].items():
            if value and current[corpus].get(stat, 0) < value * (1 - GRAPH_TOLERANCE):
                failures.append(f"{corpus}: {stat} {current[corpus].get(stat, 0)} (baseline {value})")
    return failures


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
        current, graphs = measure(args.corpus_root or Path(scratch) / "corpora")
    if args.update_baseline:
        BASELINE.write_text(json.dumps({"schema_version": "1.1", "tasks": current, "graphs": graphs},
                                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Baseline actualizado: {BASELINE} ({len(current)} tareas, {len(graphs)} grafos)")
        return 0
    saved = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures = compare(current, saved["tasks"]) + compare_graphs(graphs, saved.get("graphs", {}))
    covered = statistics.fmean(row["covered"] / row["total"] for row in current.values())
    if failures:
        print("Retrieval coverage gate failed:\n- " + "\n- ".join(failures))
        print("Corrige la regresión o, tras una revisión explícita, actualiza el baseline.")
        return 1
    print(f"Retrieval coverage gate passed: {len(current)} tareas en {len(graphs)} corpus, cobertura media {covered:.1%}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
