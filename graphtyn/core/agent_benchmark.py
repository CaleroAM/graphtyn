"""Compare repeatable agent runs exported as Antigravity-style JSON."""

from __future__ import annotations

import json
from pathlib import Path
from itertools import product
from math import comb, sqrt
from statistics import mean, stdev
from typing import Any


def _load_runs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    usage = [run.get("usage", {}) for run in runs]
    totals = [int(item.get("total_tokens", 0)) for item in usage]
    durations = [float(run.get("duration_seconds", 0)) for run in runs]
    scores = [float(run["quality_score"]) for run in runs if "quality_score" in run]
    adjusted = [float(run.get("adjusted_quality_score", run["quality_score"])) for run in runs if "quality_score" in run]
    factual_errors = [int(run.get("factual_errors", 0)) for run in runs]

    def ci95(values: list[float]) -> list[float] | None:
        if not values:
            return None
        if len(values) == 1:
            return [round(values[0], 4), round(values[0], 4)]
        margin = 1.96 * stdev(values) / sqrt(len(values))
        return [round(mean(values) - margin, 4), round(mean(values) + margin, 4)]

    result = {
        "runs": len(runs),
        "successful_runs": sum(run.get("status") == "SUCCESS" for run in runs),
        "mean_duration_seconds": round(mean(durations), 3),
        "duration_ci95": ci95(durations),
        "mean_total_tokens": round(mean(totals)),
        "total_tokens_ci95": ci95(totals),
        "mean_input_tokens": round(mean(int(item.get("input_tokens", 0)) for item in usage)),
        "mean_output_tokens": round(mean(int(item.get("output_tokens", 0)) for item in usage)),
    }
    if scores:
        result["mean_quality_score"] = round(mean(scores), 4)
        result["quality_ci95"] = ci95(scores)
        result["mean_adjusted_quality_score"] = round(mean(adjusted), 4)
        result["factual_errors"] = sum(factual_errors)
    return result


def compare_agent_runs(treatment_path: Path, baseline_path: Path) -> dict[str, Any]:
    treatment_runs = _load_runs(treatment_path)
    baseline_runs = _load_runs(baseline_path)
    treatment = _summary(treatment_runs)
    baseline = _summary(baseline_runs)

    def reduction(metric: str) -> float | None:
        base = baseline[metric]
        return round((base - treatment[metric]) / base, 4) if base else None

    paired = []
    base_by_task = {run.get("task_id", str(i)): run for i, run in enumerate(baseline_runs)}
    for i, run in enumerate(treatment_runs):
        task = run.get("task_id", str(i))
        if task in base_by_task:
            other = base_by_task[task]
            paired.append({
                "task_id": task,
                "token_delta": int(run.get("usage", {}).get("total_tokens", 0)) - int(other.get("usage", {}).get("total_tokens", 0)),
                "quality_delta": float(run.get("adjusted_quality_score", run.get("quality_score", 0))) - float(other.get("adjusted_quality_score", other.get("quality_score", 0))),
            })
    wins = sum(item["quality_delta"] > 0 for item in paired)
    losses = sum(item["quality_delta"] < 0 for item in paired)
    decisive = wins + losses
    sign_p = min(1.0, 2 * sum(comb(decisive, k) for k in range(0, min(wins, losses) + 1)) / (2 ** decisive)) if decisive else None
    token_deltas = [item["token_delta"] for item in paired]
    token_mean = mean(token_deltas) if token_deltas else None
    token_ci = None
    token_effect_dz = None
    permutation_p = None
    if token_deltas:
        if len(token_deltas) > 1:
            token_sd = stdev(token_deltas)
            margin = 1.96 * token_sd / sqrt(len(token_deltas))
            token_ci = [round(token_mean - margin, 2), round(token_mean + margin, 2)]
            token_effect_dz = round(token_mean / token_sd, 4) if token_sd else None
        else:
            token_ci = [round(token_mean, 2), round(token_mean, 2)]
        observed = abs(token_mean)
        permuted = [abs(mean(sign * value for sign, value in zip(signs, token_deltas)))
                    for signs in product((-1, 1), repeat=len(token_deltas))]
        permutation_p = round(sum(value >= observed - 1e-12 for value in permuted) / len(permuted), 6)
    result = {
        "schema_version": 1,
        "treatment": treatment,
        "baseline": baseline,
        "reduction": {
            "total_tokens": reduction("mean_total_tokens"),
            "input_tokens": reduction("mean_input_tokens"),
            "duration": reduction("mean_duration_seconds"),
        },
        "paired": {
            "pairs": len(paired), "quality_wins": wins, "quality_losses": losses,
            "quality_ties": len(paired) - decisive,
            "two_sided_sign_test_p": round(sign_p, 6) if sign_p is not None else None,
            "mean_token_delta": round(token_mean) if token_mean is not None else None,
            "token_delta_ci95": token_ci,
            "token_effect_size_dz": token_effect_dz,
            "token_permutation_p": permutation_p,
            "mean_quality_delta": round(mean(item["quality_delta"] for item in paired), 4) if paired else None,
        },
        "warning": "Los intervalos usan aproximación normal 95%. Use tareas pareadas, ground truth auditable y al menos 5 repeticiones por variante.",
    }
    return result
