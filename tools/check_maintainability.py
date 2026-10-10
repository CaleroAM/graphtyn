#!/usr/bin/env python3
"""Reject new structural hotspots while allowing existing debt to shrink."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_LIMITS = {"module": 1200, "class": 800, "function": 120}


@dataclass(frozen=True)
class Metric:
    key: str
    kind: str
    lines: int
    path: str
    line: int


class DefinitionVisitor(ast.NodeVisitor):
    """Collect qualified definitions without counting nested bodies twice."""

    def __init__(self, path: str):
        self.path = path
        self.scope: list[str] = []
        self.metrics: list[Metric] = []

    def _visit_definition(self, node: ast.AST, kind: str, name: str) -> None:
        qualified = ".".join([*self.scope, name])
        self.metrics.append(Metric(
            key=f"{self.path}::{qualified}",
            kind=kind,
            lines=int(node.end_lineno) - int(node.lineno) + 1,
            path=self.path,
            line=int(node.lineno),
        ))
        self.scope.append(name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._visit_definition(node, "class", node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_definition(node, "function", node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_definition(node, "function", node.name)


def collect_metrics(project_root: Path) -> list[Metric]:
    metrics: list[Metric] = []
    package_root = project_root / "graphtyn"
    for source_path in sorted(package_root.rglob("*.py")):
        relative = source_path.relative_to(project_root).as_posix()
        source = source_path.read_text(encoding="utf-8")
        metrics.append(Metric(
            key=relative,
            kind="module",
            lines=len(source.splitlines()),
            path=relative,
            line=1,
        ))
        visitor = DefinitionVisitor(relative)
        visitor.visit(ast.parse(source, filename=relative))
        metrics.extend(visitor.metrics)
    return metrics


def current_hotspots(metrics: Iterable[Metric]) -> list[Metric]:
    return [metric for metric in metrics if metric.lines > DEFAULT_LIMITS[metric.kind]]


def load_baseline(path: Path) -> dict[str, dict[str, int | str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("limits") != DEFAULT_LIMITS:
        raise ValueError(f"Los límites de {path} no coinciden con el verificador")
    return {item["key"]: item for item in data.get("hotspots", [])}


def violations(metrics: Iterable[Metric], baseline: dict[str, dict[str, int | str]]) -> list[str]:
    failures: list[str] = []
    for metric in current_hotspots(metrics):
        accepted = baseline.get(metric.key)
        if accepted is None:
            failures.append(
                f"nuevo {metric.kind} sobredimensionado: {metric.path}:{metric.line} "
                f"{metric.key.split('::')[-1]} ({metric.lines} > {DEFAULT_LIMITS[metric.kind]})"
            )
            continue
        maximum = int(accepted["max_lines"])
        if metric.kind != accepted.get("kind"):
            failures.append(f"tipo de hotspot cambió: {metric.key}")
        elif metric.lines > maximum:
            failures.append(
                f"hotspot creció: {metric.path}:{metric.line} "
                f"{metric.key.split('::')[-1]} ({metric.lines} > baseline {maximum})"
            )
    return failures


def write_baseline(path: Path, metrics: Iterable[Metric]) -> None:
    hotspots = [
        {**asdict(metric), "max_lines": metric.lines}
        for metric in current_hotspots(metrics)
    ]
    for item in hotspots:
        item.pop("lines")
        item.pop("path")
        item.pop("line")
    payload = {
        "schema_version": 1,
        "description": "Deuda heredada: puede reducirse o eliminarse, pero no crecer.",
        "limits": DEFAULT_LIMITS,
        "hotspots": hotspots,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    baseline_path = args.baseline or root / "tools" / "maintainability_baseline.json"
    metrics = collect_metrics(root)
    if args.update_baseline:
        write_baseline(baseline_path, metrics)
        print(f"Baseline actualizado: {baseline_path}")
        return 0
    failures = violations(metrics, load_baseline(baseline_path))
    if failures:
        print("Maintainability gate failed:")
        for failure in failures:
            print(f"- {failure}")
        print("Extrae responsabilidades o, tras una revisión explícita, actualiza el baseline.")
        return 1
    print(
        f"Maintainability gate passed: {len(current_hotspots(metrics))} hotspots heredados "
        "sin crecimiento."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
