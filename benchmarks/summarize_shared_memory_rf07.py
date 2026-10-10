#!/usr/bin/env python3
"""Validate RF07 scale artifacts and build a compact cross-scale summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
from pathlib import Path
from typing import Any


SCALES = (1_000, 10_000, 50_000)
CROSS_SCALE_THRESHOLDS = {
    "latency_p95_growth_max": 5.0,
    "initial_throughput_retention_min": 0.50,
    "incremental_throughput_retention_min": 0.50,
    "database_bytes_per_record_growth_max": 1.50,
}

SOURCE_FILES = (
    "graphtyn/core/memory_scale_benchmark.py",
    "graphtyn/core/memory_retrieval.py",
    "graphtyn/core/shared_memory.py",
)


def _median(runs: list[dict[str, Any]], section: str, metric: str) -> float:
    return round(statistics.median(float(run[section][metric]) for run in runs), 4)


def _load(directory: Path) -> dict[int, dict[str, Any]]:
    artifacts = {scale: json.loads((directory / f"scale_{scale}.json").read_text(encoding="utf-8"))
                 for scale in SCALES}
    for scale, artifact in artifacts.items():
        if artifact.get("protocol") != "graphtyn-shared-memory-rf07-v1":
            raise ValueError(f"protocolo inesperado en {scale}")
        if artifact.get("dataset", {}).get("records") != scale:
            raise ValueError(f"escala incoherente en {scale}")
    return artifacts


def _source_revision() -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, text=True,
                                capture_output=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], check=True, text=True,
                                capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError):
        commit, status = None, ""
    files = {}
    for name in SOURCE_FILES:
        path = Path(name)
        if path.is_file():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"commit": commit, "dirty": bool(status),
            "status_sha256": hashlib.sha256(status.encode()).hexdigest(), "files": files}


def summarize(directory: Path) -> dict[str, Any]:
    artifacts = _load(directory)
    scales: dict[str, Any] = {}
    for size, artifact in artifacts.items():
        runs = artifact["runs"]
        scales[str(size)] = {
            "ok": artifact["ok"], "repetitions": artifact["repetitions"],
            "queries_per_mode_per_repetition": artifact["dataset"]["queries"],
            "normal": artifact["summary"]["normal"],
            "degraded_without_embeddings": artifact["summary"]["degraded_without_embeddings"],
            "initial_index_seconds_median": _median(runs, "indexing", "seconds"),
            "initial_records_per_second_median": _median(runs, "indexing", "records_per_second"),
            "incremental_records_median": _median(runs, "incremental", "records"),
            "incremental_seconds_median": _median(runs, "incremental", "seconds"),
            "incremental_records_per_second_median": _median(runs, "incremental", "records_per_second"),
            "database_bytes_median": round(statistics.median(run["database_bytes"] for run in runs)),
            "peak_rss_bytes_max": max(run["peak_rss_bytes"] for run in runs),
            "peak_rss_fraction_max": max(run["peak_rss_fraction"] for run in runs),
            "isolation_violations": sum(run["isolation_violations"] for run in runs),
            "failed_guardrails": sum(not check["passed"] for run in runs
                for mode in ("normal", "degraded_without_embeddings")
                for check in run[mode]["guardrails"].values()),
        }
    first, last = scales["1000"], scales["50000"]
    normal_growth = last["normal"]["latency_ms_p95"] / first["normal"]["latency_ms_p95"]
    degraded_growth = (last["degraded_without_embeddings"]["latency_ms_p95"] /
                       first["degraded_without_embeddings"]["latency_ms_p95"])
    initial_retention = (last["initial_records_per_second_median"] /
                         first["initial_records_per_second_median"])
    incremental_retention = (last["incremental_records_per_second_median"] /
                             first["incremental_records_per_second_median"])
    bytes_per_record = {size: values["database_bytes_median"] / int(size)
                        for size, values in scales.items()}
    database_growth = max(bytes_per_record.values()) / min(bytes_per_record.values())
    checks = {
        "all_scale_guardrails": all(value["ok"] and value["failed_guardrails"] == 0 for value in scales.values()),
        "five_repetitions_each": all(value["repetitions"] == 5 for value in scales.values()),
        "latency_p95_growth": max(normal_growth, degraded_growth) <= CROSS_SCALE_THRESHOLDS["latency_p95_growth_max"],
        "initial_throughput_retention": initial_retention >= CROSS_SCALE_THRESHOLDS["initial_throughput_retention_min"],
        "incremental_throughput_retention": incremental_retention >= CROSS_SCALE_THRESHOLDS["incremental_throughput_retention_min"],
        "database_bytes_per_record_growth": database_growth <= CROSS_SCALE_THRESHOLDS["database_bytes_per_record_growth_max"],
    }
    return {"ok": all(checks.values()), "protocol": "graphtyn-rf07-cross-scale-v1",
            "thresholds": CROSS_SCALE_THRESHOLDS, "checks": checks,
            "growth": {"normal_latency_p95_1000_to_50000": round(normal_growth, 4),
                       "degraded_latency_p95_1000_to_50000": round(degraded_growth, 4),
                       "initial_throughput_retention": round(initial_retention, 4),
                       "incremental_throughput_retention": round(incremental_retention, 4),
                       "database_bytes_per_record_growth": round(database_growth, 4)},
            "environment": artifacts[1_000]["environment"], "source_revision": _source_revision(),
            "scales": scales}


def _report(summary: dict[str, Any]) -> str:
    rows = []
    for size, value in summary["scales"].items():
        normal, degraded = value["normal"], value["degraded_without_embeddings"]
        rows.append(f"| {int(size):,} | {normal['recall_at_5']:.2f} | {normal['latency_ms_p95']:.3f} | "
                    f"{degraded['latency_ms_p95']:.3f} | {value['initial_records_per_second_median']:.2f} | "
                    f"{value['incremental_records_per_second_median']:.2f} | "
                    f"{value['database_bytes_median'] / 1_000_000:.2f} | "
                    f"{value['peak_rss_bytes_max'] / 1_000_000:.2f} | {value['isolation_violations']} |")
    status = "APROBADO" if summary["ok"] else "NO APROBADO"
    return "\n".join([
        "# RF07 — benchmark de memoria compartida (2026-10-09)", "", f"**Resultado:** {status}", "",
        "Cinco repeticiones independientes por escala, con 90 consultas positivas y 10 negativas por modo y repetición.",
        "Cada repetición mide carga inicial, actualización incremental, recuperación normal, degradación sin embeddings y aislamiento.", "",
        "| Registros | Recall@5 | p95 normal ms | p95 degradado ms | Carga reg/s | Incremental reg/s | SQLite MB | RSS pico MB | Fugas |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|", *rows, "",
        "## Crecimiento 1k → 50k", "", *[f"- `{key}`: {value}" for key, value in summary["growth"].items()], "",
        "## Veredicto", "", *[f"- {'✓' if passed else '✗'} `{name}`" for name, passed in summary["checks"].items()], "",
        f"Commit base: `{summary['source_revision']['commit']}`; worktree con cambios: `{summary['source_revision']['dirty']}`.", "",
        "Los tiempos de carga corresponden al fixture transaccional controlado del benchmark; no representan la latencia de llamadas individuales a `checkpoint`.",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    summary = summarize(args.directory)
    (args.directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.directory / "REPORT.md").write_text(_report(summary), encoding="utf-8")
    print(json.dumps({"ok": summary["ok"], "checks": summary["checks"]}))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
