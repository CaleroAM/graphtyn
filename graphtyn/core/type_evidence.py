"""Optional compiler/LSP evidence ingestion.

Providers write a small, portable JSON sidecar. Graphtyn never executes a
project compiler implicitly; CI or the developer controls that step.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


PROVIDERS = {
    ".cs": ("roslyn", "dotnet"),
    ".ts": ("typescript-language-service", "tsc"),
    ".tsx": ("typescript-language-service", "tsc"),
    ".py": ("pyright", "pyright"),
    ".php": ("phpstan", "phpstan"),
}


def provider_status(root: Path) -> list[dict[str, Any]]:
    suffixes = {path.suffix.lower() for path in root.rglob("*") if path.is_file()}
    result = []
    for suffix, (provider, executable) in PROVIDERS.items():
        if suffix in suffixes and not any(item["provider"] == provider for item in result):
            result.append({"provider": provider, "executable": executable,
                           "available": shutil.which(executable) is not None})
    return result


def apply_type_evidence(graph: dict[str, Any], root: Path) -> dict[str, Any]:
    """Merge `.graphtyn/type-evidence.json` relations as high-confidence facts."""
    sidecar = root / ".graphtyn" / "type-evidence.json"
    applied = 0
    rejected = 0
    nodes = {node.get("id") for node in graph.get("nodes", [])}
    if sidecar.exists():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        for item in payload.get("relations", []):
            source, target = item.get("source"), item.get("target")
            if source not in nodes or target not in nodes or not item.get("label"):
                rejected += 1
                continue
            graph.setdefault("links", []).append({
                "source": source, "target": target, "label": item["label"],
                "confidence": "TYPED", "file": item.get("file"), "line": item.get("line"),
                "evidence": item.get("evidence", "compiler/type-service evidence"),
                "resolution": {"strategy": item.get("provider", "type-sidecar"), "candidates": 1},
            })
            applied += 1
    graph.setdefault("metadata", {})["type_analysis"] = {
        "providers": provider_status(root), "sidecar": str(sidecar.relative_to(root)),
        "typed_relations": applied, "rejected_relations": rejected,
        "execution": "explicit; Graphtyn does not run project analyzers automatically",
    }
    return graph
