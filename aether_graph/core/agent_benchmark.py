"""Compare repeatable agent runs exported as Antigravity-style JSON."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any


def _load_runs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    usage = [run.get("usage", {}) for run in runs]
    return {
        "runs": len(runs),
        "successful_runs": sum(run.get("status") == "SUCCESS" for run in runs),
        "mean_duration_seconds": round(mean(float(run.get("duration_seconds", 0)) for run in runs), 3),
        "mean_total_tokens": round(mean(int(item.get("total_tokens", 0)) for item in usage)),
        "mean_input_tokens": round(mean(int(item.get("input_tokens", 0)) for item in usage)),
        "mean_output_tokens": round(mean(int(item.get("output_tokens", 0)) for item in usage)),
    }


def compare_agent_runs(treatment_path: Path, baseline_path: Path) -> dict[str, Any]:
    treatment = _summary(_load_runs(treatment_path))
    baseline = _summary(_load_runs(baseline_path))

    def reduction(metric: str) -> float | None:
        base = baseline[metric]
        return round((base - treatment[metric]) / base, 4) if base else None

    return {
        "schema_version": 1,
        "treatment": treatment,
        "baseline": baseline,
        "reduction": {
            "total_tokens": reduction("mean_total_tokens"),
            "input_tokens": reduction("mean_input_tokens"),
            "duration": reduction("mean_duration_seconds"),
        },
        "warning": "Una sola corrida es orientativa; use al menos 5 repeticiones por variante. La calidad debe evaluarse con un ground truth separado.",
    }
