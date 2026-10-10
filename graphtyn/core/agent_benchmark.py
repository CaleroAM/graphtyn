"""Compare repeatable agent runs exported as Antigravity-style JSON."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from itertools import product
from math import comb, sqrt
from pathlib import Path
from statistics import mean, stdev
from typing import Any


def _load_runs(source: Path | str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(source, list):
        return source
    path = Path(source)
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    usage = [run.get("usage", {}) for run in runs]
    totals = [int(item["total_tokens"]) for item in usage if item.get("total_tokens") is not None]
    durations = [float(run["duration_seconds"]) for run in runs if run.get("duration_seconds") is not None]
    scores = [float(run["quality_score"]) for run in runs if "quality_score" in run]
    adjusted = [float(run.get("adjusted_quality_score", run["quality_score"])) for run in runs if "quality_score" in run]
    factual_errors = [int(run["factual_errors"]) for run in runs if run.get("factual_errors") is not None]
    unsupported_claims = [int(run.get("unsupported_claims", run.get("factual_errors"))) for run in runs
                          if run.get("unsupported_claims", run.get("factual_errors")) is not None]
    tool_calls = [int(run["tool_calls"]) for run in runs if run.get("tool_calls") is not None]
    costs = [float(run["cost_usd"]) for run in runs if run.get("cost_usd") is not None]
    statuses = Counter(str(run.get("status") or "UNKNOWN") for run in runs)
    known_statuses = [str(run["status"]) for run in runs if run.get("status") is not None]

    def ci95(values: list[float]) -> list[float] | None:
        if not values:
            return None
        if len(values) == 1:
            return [round(values[0], 4), round(values[0], 4)]
        margin = 1.96 * stdev(values) / sqrt(len(values))
        return [round(mean(values) - margin, 4), round(mean(values) + margin, 4)]

    result = {
        "runs": len(runs),
        "successful_runs": sum(status == "SUCCESS" for status in known_statuses),
        "success_rate": (round(sum(status == "SUCCESS" for status in known_statuses) / len(known_statuses), 4)
                         if known_statuses else None),
        "statuses": dict(statuses),
        "mean_duration_seconds": round(mean(durations), 3) if durations else None,
        "duration_ci95": ci95(durations),
        "mean_total_tokens": round(mean(totals)) if totals else None,
        "total_tokens_ci95": ci95(totals),
        "mean_input_tokens": (round(mean(int(item["input_tokens"]) for item in usage
                                         if item.get("input_tokens") is not None))
                              if any(item.get("input_tokens") is not None for item in usage) else None),
        "mean_output_tokens": (round(mean(int(item["output_tokens"]) for item in usage
                                          if item.get("output_tokens") is not None))
                               if any(item.get("output_tokens") is not None for item in usage) else None),
        "mean_tool_calls": round(mean(tool_calls), 3) if tool_calls else None,
        "unsupported_claims": sum(unsupported_claims) if unsupported_claims else None,
        "factual_errors": sum(factual_errors) if factual_errors else None,
        "token_source": "provider_reported" if all(item.get("provider_reported") is True for item in usage) else "mixed_or_estimated",
    }
    if costs:
        result["mean_cost_usd"] = round(mean(costs), 6)
        result["cost_source"] = "provider_reported" if all(
            run.get("cost_provider_reported") is True for run in runs if run.get("cost_usd") is not None
        ) else "mixed_or_estimated"
    if scores:
        result["mean_quality_score"] = round(mean(scores), 4)
        result["quality_ci95"] = ci95(scores)
        result["mean_adjusted_quality_score"] = round(mean(adjusted), 4)
    return result


def compare_agent_runs(treatment_path: Path | str | list[dict[str, Any]],
                       baseline_path: Path | str | list[dict[str, Any]]) -> dict[str, Any]:
    treatment_runs = _load_runs(treatment_path)
    baseline_runs = _load_runs(baseline_path)
    treatment = _summary(treatment_runs)
    baseline = _summary(baseline_runs)

    def reduction(metric: str) -> float | None:
        base = baseline.get(metric)
        treat = treatment.get(metric)
        return round((base - treat) / base, 4) if base and treat is not None else None

    def canonical(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def repetition(run: dict[str, Any]) -> Any:
        return run.get("repetition", run.get("repetition_index", run.get("trial", run.get("repeat"))))

    def configuration(run: dict[str, Any]) -> str | None:
        for key in ("experiment_config", "configuration", "config_id"):
            if run.get(key) is not None:
                return canonical(run[key])
        return None

    def build_index(runs: list[dict[str, Any]]) -> tuple[dict[tuple, dict[str, Any]], list[str], list[dict[str, Any]]]:
        prepared = []
        exclusions: list[dict[str, Any]] = []
        missing_rep_counts: Counter = Counter()
        for index, run in enumerate(runs):
            task = str(run.get("task_id") or run.get("task") or "").strip()
            if not task:
                exclusions.append({"index": index, "reason": "missing_task_identifier"})
                continue
            rep = repetition(run)
            seed = run.get("seed")
            config = configuration(run)
            prepared.append((index, task, rep, seed, config, run))
            if rep is None:
                missing_rep_counts[(task, seed, config)] += 1

        grouped: dict[tuple, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for index, task, rep, seed, config, run in prepared:
            if rep is None and missing_rep_counts[(task, seed, config)] > 1:
                exclusions.append({"index": index, "task_id": task,
                                   "reason": "ambiguous_missing_repetition"})
                continue
            grouped[(task, rep, seed, config)].append((index, run))

        result: dict[tuple, dict[str, Any]] = {}
        duplicates: list[str] = []
        for key, entries in grouped.items():
            if len(entries) != 1:
                duplicates.append(str(key))
                exclusions.extend({"index": index, "key": str(key), "reason": "duplicate_pair_key"}
                                  for index, _run in entries)
                continue
            result[key] = entries[0][1]
        return result, duplicates, exclusions

    base_by_key, base_duplicates, baseline_exclusions = build_index(baseline_runs)
    treatment_by_key, treatment_duplicates, treatment_exclusions = build_index(treatment_runs)

    paired = []
    candidate_pairs = []
    incompatible_pairs = []
    unpaired_treatment = [k for k in treatment_by_key if k not in base_by_key]
    unpaired_baseline = [k for k in base_by_key if k not in treatment_by_key]

    condition_fields = {
        "model": ("model",),
        "repository": ("repository", "repo"),
        "revision": ("revision", "commit"),
        "instructions": ("instructions_digest", "instructions"),
        "environment": ("environment_digest_sha256", "environment_digest", "environment"),
        "budget": ("budget", "token_budget"),
        "graphtyn_version": ("graphtyn_version",),
    }

    def first_value(run: dict[str, Any], names: tuple[str, ...]) -> Any:
        return next((run[name] for name in names if run.get(name) is not None), None)

    def numeric_delta(run: dict[str, Any], other: dict[str, Any], getter) -> float | int | None:
        left, right = getter(run), getter(other)
        return left - right if left is not None and right is not None else None

    for key, run in treatment_by_key.items():
        if key in base_by_key:
            other = base_by_key[key]
            run_q = run.get("adjusted_quality_score", run.get("quality_score"))
            other_q = other.get("adjusted_quality_score", other.get("quality_score"))
            q_delta = (float(run_q) - float(other_q)) if (run_q is not None and other_q is not None) else None
            conditions = {}
            mismatches = []
            for label, names in condition_fields.items():
                left, right = first_value(run, names), first_value(other, names)
                same = canonical(left) == canonical(right) if left is not None and right is not None else None
                conditions[f"same_{label}"] = same
                if same is False and label != "graphtyn_version":
                    mismatches.append(label)

            pair = {
                "task_id": key[0],
                "repetition": key[1],
                "seed": key[2],
                "configuration": key[3],
                "token_delta": numeric_delta(
                    run, other,
                    lambda item: (int(item.get("usage", {})["total_tokens"])
                                  if item.get("usage", {}).get("total_tokens") is not None else None),
                ),
                "quality_delta": q_delta,
                "duration_delta": numeric_delta(
                    run, other,
                    lambda item: float(item["duration_seconds"]) if item.get("duration_seconds") is not None else None,
                ),
                "tool_call_delta": numeric_delta(
                    run, other,
                    lambda item: int(item["tool_calls"]) if item.get("tool_calls") is not None else None,
                ),
                "unsupported_claim_delta": numeric_delta(
                    run, other,
                    lambda item: (int(item.get("unsupported_claims", item.get("factual_errors")))
                                  if item.get("unsupported_claims", item.get("factual_errors")) is not None else None),
                ),
                "cost_delta_usd": (float(run.get("cost_usd", 0)) - float(other.get("cost_usd", 0)))
                                  if run.get("cost_usd") is not None and other.get("cost_usd") is not None else None,
                **conditions,
            }
            candidate_pairs.append(pair)
            if mismatches:
                incompatible_pairs.append({"key": str(key), "mismatched_conditions": mismatches})
            else:
                paired.append(pair)

    def task_values(metric: str) -> list[float]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for item in paired:
            if item.get(metric) is not None:
                grouped[item["task_id"]].append(float(item[metric]))
        return [mean(values) for _task, values in sorted(grouped.items())]

    rated_pairs = [p for p in paired if p["quality_delta"] is not None]
    quality_task_deltas = task_values("quality_delta")
    wins = sum(value > 0 for value in quality_task_deltas)
    losses = sum(value < 0 for value in quality_task_deltas)
    decisive = wins + losses
    sign_p = min(1.0, 2 * sum(comb(decisive, k) for k in range(0, min(wins, losses) + 1)) / (2 ** decisive)) if decisive else None

    token_deltas = task_values("token_delta")
    token_mean = mean(token_deltas) if token_deltas else None
    token_ci = None
    token_effect_dz = None
    permutation_p = None
    permutation_method = None

    if token_deltas:
        if len(token_deltas) > 1:
            token_sd = stdev(token_deltas)
            margin = 1.96 * token_sd / sqrt(len(token_deltas))
            token_ci = [round(token_mean - margin, 2), round(token_mean + margin, 2)]
            token_effect_dz = round(token_mean / token_sd, 4) if token_sd else None
        else:
            token_ci = [round(token_mean, 2), round(token_mean, 2)]
        observed = abs(token_mean)

        if len(token_deltas) <= 15:
            permuted = [abs(mean(sign * value for sign, value in zip(signs, token_deltas)))
                        for signs in product((-1, 1), repeat=len(token_deltas))]
            permutation_p = round(sum(value >= observed - 1e-12 for value in permuted) / len(permuted), 6)
            permutation_method = "exact_enumeration"
        else:
            rng = random.Random(42)
            n_samples = 10000
            count_ge = 0
            n_items = len(token_deltas)
            for _ in range(n_samples):
                signs = [rng.choice((-1, 1)) for _ in range(n_items)]
                perm_val = abs(mean(sign * val for sign, val in zip(signs, token_deltas)))
                if perm_val >= observed - 1e-12:
                    count_ge += 1
            permutation_p = round(count_ge / n_samples, 6)
            permutation_method = "monte_carlo_10k"

    valid_q_deltas = quality_task_deltas

    def mean_task_metric(metric: str) -> float | None:
        values = task_values(metric)
        return round(mean(values), 4) if values else None

    def comparability_value(field: str) -> bool | None:
        values = [item.get(field) for item in candidate_pairs if item.get(field) is not None]
        if any(value is False for value in values):
            return False
        return True if values and len(values) == len(candidate_pairs) else None

    result = {
        "schema_version": 2,
        "treatment": treatment,
        "baseline": baseline,
        "reduction": {
            "total_tokens": reduction("mean_total_tokens"),
            "input_tokens": reduction("mean_input_tokens"),
            "duration": reduction("mean_duration_seconds"),
        },
        "paired": {
            "pairs": len(paired),
            "pairs_list": paired,
            "candidate_pairs": len(candidate_pairs),
            "excluded_incompatible_pairs": incompatible_pairs,
            "statistical_unit": "task",
            "task_token_deltas": token_deltas,
            "quality_wins": wins,
            "quality_losses": losses,
            "quality_ties": len(quality_task_deltas) - decisive,
            "unrated_pairs": len(paired) - len(rated_pairs),
            "missing_token_pairs": sum(item["token_delta"] is None for item in paired),
            "two_sided_sign_test_p": round(sign_p, 6) if sign_p is not None else None,
            "mean_token_delta": round(token_mean) if token_mean is not None else None,
            "token_delta_ci95": token_ci,
            "token_effect_size_dz": token_effect_dz,
            "token_permutation_p": permutation_p,
            "token_permutation_method": permutation_method,
            "mean_quality_delta": round(mean(valid_q_deltas), 4) if valid_q_deltas else None,
            "mean_duration_delta": mean_task_metric("duration_delta"),
            "mean_tool_call_delta": mean_task_metric("tool_call_delta"),
            "unsupported_claim_delta": (sum(item["unsupported_claim_delta"] for item in paired
                                              if item["unsupported_claim_delta"] is not None)
                                            if any(item["unsupported_claim_delta"] is not None for item in paired)
                                            else None),
            "mean_cost_delta_usd": mean_task_metric("cost_delta_usd"),
        },
        "comparability": {
            **{field: comparability_value(field) for field in (
                "same_model", "same_repository", "same_revision", "same_instructions",
                "same_environment", "same_budget", "same_graphtyn_version",
            )},
            "note": "null means the exported runs did not provide enough metadata to establish parity.",
            "unpaired_treatment": [str(k) for k in unpaired_treatment],
            "unpaired_baseline": [str(k) for k in unpaired_baseline],
            "treatment_duplicates": treatment_duplicates,
            "baseline_duplicates": base_duplicates,
            "treatment_exclusions": treatment_exclusions,
            "baseline_exclusions": baseline_exclusions,
        },
        "warning": "Los intervalos usan aproximación normal 95%. Use tareas pareadas, ground truth auditable y al menos 5 repeticiones por variante.",
    }
    return result
