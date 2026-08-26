"""Validation and statistics for multi-repository paired agent benchmarks."""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter
from typing import Any


REQUIRED_VARIANTS = {"graphtyn", "competitor", "no_graph"}


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    tasks = protocol.get("tasks", [])
    ids = [str(task.get("id") or "") for task in tasks]
    technologies = Counter(str(task.get("technology") or "unknown") for task in tasks)
    repositories = Counter(str(task.get("repository") or "unknown") for task in tasks)
    repository_metadata = {str(item.get("id") or ""): item for item in protocol.get("repositories", [])}
    errors = []
    if not 30 <= len(tasks) <= 50:
        errors.append("task count must be between 30 and 50")
    if len(set(ids)) != len(ids) or any(not task_id for task_id in ids):
        errors.append("task ids must be non-empty and unique")
    if len(technologies) < 5:
        errors.append("at least five technologies are required")
    if len(repositories) < 5:
        errors.append("at least five repositories are required")
    for repository in repositories:
        metadata = repository_metadata.get(repository, {})
        if not metadata.get("source") or not metadata.get("revision"):
            errors.append(f"{repository}: immutable source and revision required")
    for task in tasks:
        if not task.get("prompt") or len(task.get("facts", [])) < 3:
            errors.append(f"{task.get('id')}: prompt and >=3 atomic facts required")
    variants = set(protocol.get("variants", []))
    if variants != REQUIRED_VARIANTS:
        errors.append("variants must be graphtyn, competitor and no_graph")
    return {"ok": not errors, "tasks": len(tasks), "technologies": dict(technologies),
            "repositories": dict(repositories), "planned_runs": len(tasks) * len(variants), "errors": errors}


def paired_statistics(rows: list[dict[str, Any]], treatment: str = "graphtyn",
                      control: str = "no_graph", bootstrap_samples: int = 5000,
                      seed: int = 20260822) -> dict[str, Any]:
    by_task: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_task.setdefault(str(row["task_id"]), {})[str(row["variant"])] = row
    pairs = [(items[treatment], items[control]) for items in by_task.values()
             if treatment in items and control in items]
    deltas = [float(left["tokens"]) - float(right["tokens"]) for left, right in pairs]
    quality = [float(left.get("quality", 0)) - float(right.get("quality", 0)) for left, right in pairs]
    if not deltas:
        return {"ok": False, "error": "no paired rows"}
    mean = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    boot = sorted(sum(rng.choice(deltas) for _ in deltas) / len(deltas) for _ in range(bootstrap_samples))
    lo, hi = boot[int(0.025 * len(boot))], boot[min(len(boot) - 1, int(0.975 * len(boot)))]
    # Exact sign-flip permutation for small n; deterministic Monte Carlo above 20.
    if len(deltas) <= 20:
        permutations = [abs(sum(sign * value for sign, value in zip(signs, deltas)) / len(deltas))
                        for signs in itertools.product((-1, 1), repeat=len(deltas))]
        p_value = sum(value >= abs(mean) for value in permutations) / len(permutations)
    else:
        permutations = [abs(sum((1 if rng.random() > .5 else -1) * value for value in deltas) / len(deltas))
                        for _ in range(10000)]
        p_value = sum(value >= abs(mean) for value in permutations) / len(permutations)
    control_tokens = sum(float(right["tokens"]) for _, right in pairs)
    treatment_tokens = sum(float(left["tokens"]) for left, _ in pairs)
    return {"ok": True, "pairs": len(pairs), "mean_token_delta": round(mean, 3),
            "token_delta_ci95": [round(lo, 3), round(hi, 3)],
            "token_reduction": round(1 - treatment_tokens / control_tokens, 4) if control_tokens else None,
            "quality_delta": round(sum(quality) / len(quality), 4),
            "sign_flip_p": round(p_value, 6),
            "effect_dz": round(mean / (math.sqrt(sum((x - mean) ** 2 for x in deltas) / max(1, len(deltas) - 1)) or 1), 4)}
