#!/usr/bin/env python3
"""Fit the candidate ranking weights of graphtyn/core/ranking_weights.py.

For every dev task of benchmarks/task_bank_2026-10-28 the script records the
features of each retrieval candidate once, then searches weights that maximise
the mean share of rubric facts spelled by the top-K candidates (their name,
signature or operations). The search is coordinate ascent over multiplicative
steps of the current weights, so a fitted weight keeps its sign and a feature
can be switched off (×0). A step is accepted only when it raises the mean and
lowers the objective on no corpus: fitted on 30 tasks without that rule, the
weights gained on dev and lost on the held-out test split. Measure the package coverage of the dev and test
splits with benchmarks/task_bank_2026-10-28/coverage.py before adopting the
printed weights.

usage: GRAPHTYN_HOME=<home with indexes> python tools/learn_ranking_weights.py <dir with indexed corpora>
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "benchmarks" / "task_bank_2026-10-28"
CORPORA = ("redis", "fmt", "rails", "flask")
STEPS = (0.0, 0.5, 0.75, 1.5, 2.0, 3.0)
POOL = 400


def _node_text(node: dict) -> str:
    return " ".join([str(node.get("name") or ""), str(node.get("signature") or ""),
                     *(f"{op.get('name', '')} {op.get('text', '')}" for op in node.get("operations") or [])])


def record(workspace: Path, split: str) -> list[dict]:
    from graphtyn.core.change_analyst import query_intent
    from graphtyn.core.ranking_weights import WEIGHTS, collect_features
    from graphtyn.core.storage import data_home, project_store_dir

    patterns = json.loads((BANK / "split.json").read_text(encoding="utf-8"))[split]
    tasks = []
    for corpus in CORPORA:
        files = [BANK / pattern.format(corpus=corpus) for pattern in patterns]
        files = [path for path in files if path.exists()]
        if not files:
            continue
        graph = json.loads((project_store_dir(data_home(), workspace / corpus) / "index.json").read_text())
        for path in files:
            for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]:
                with collect_features() as collected:
                    query_intent(graph, task["request"], "auto", 10)
                scored = sorted(collected, key=lambda item: -sum(WEIGHTS[k] * v for k, v in item[0].items() if v))
                candidates = []
                for index, (features, node) in enumerate(scored):
                    text = _node_text(node)
                    facts = frozenset(fact["id"] for fact in task["rubric"] if any(term in text for term in fact["any"]))
                    if index < POOL or facts:
                        candidates.append(({k: float(v) for k, v in features.items() if v}, facts,
                                           str(node.get("id") or "")))
                tasks.append({"id": task["id"], "corpus": corpus, "total": len(task["rubric"]),
                              "candidates": candidates})
                print(f"recorded {task['id']}: {len(candidates)} candidates", flush=True)
    return tasks


def objective(tasks: list[dict], weights: dict[str, float], top: int) -> float:
    shares = []
    for task in tasks:
        ranked = sorted(task["candidates"], key=lambda item: (
            -sum(weights[k] * v for k, v in item[0].items()), item[2]))[:top]
        covered = set().union(*(facts for _features, facts, _id in ranked))
        shares.append(len(covered) / task["total"])
    return statistics.fmean(shares)


def fit(tasks: list[dict], weights: dict[str, float], top: int, rounds: int) -> dict[str, float]:
    groups: dict[str, list[dict]] = {}
    for task in tasks:
        groups.setdefault(task["corpus"], []).append(task)
    per_corpus = lambda trial: {corpus: objective(group, trial, top) for corpus, group in groups.items()}
    best = dict(weights)
    best_value, best_groups = objective(tasks, best, top), per_corpus(best)
    print(f"start objective {best_value:.4f} {best_groups}")
    for round_index in range(rounds):
        improved = False
        for name in sorted(best):
            for step in STEPS:
                trial = dict(best, **{name: weights[name] * step if best[name] == 0 else best[name] * step})
                value = objective(tasks, trial, top)
                if value <= best_value + 1e-4:
                    continue
                trial_groups = per_corpus(trial)
                if all(trial_groups[corpus] >= best_groups[corpus] - 1e-9 for corpus in groups):
                    best, best_value, best_groups, improved = trial, value, trial_groups, True
                    print(f"round {round_index} {name} -> {trial[name]:g}: {value:.4f}", flush=True)
        if not improved:
            break
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    from graphtyn.core.ranking_weights import WEIGHTS

    dev = record(args.workspace, "dev")
    fitted = fit(dev, dict(WEIGHTS), args.top, args.rounds)
    test = record(args.workspace, "test2")
    print(f"test2 objective: hand {objective(test, dict(WEIGHTS), args.top):.4f} "
          f"fitted {objective(test, fitted, args.top):.4f}")
    print(json.dumps({name: round(value, 3) for name, value in fitted.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
