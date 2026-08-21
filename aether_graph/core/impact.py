"""Git-aware pull-request and working-tree impact analysis."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )


def _changed_files(root: Path, base: str | None) -> list[str]:
    files: set[str] = set()
    if base:
        res = _git(root, "diff", "--name-only", "--diff-filter=ACMRD", f"{base}...HEAD")
        if res.returncode == 0:
            files.update(line for line in res.stdout.splitlines() if line)
    for args in (("diff", "--name-only"), ("diff", "--cached", "--name-only")):
        res = _git(root, *args)
        if res.returncode == 0:
            files.update(line for line in res.stdout.splitlines() if line)
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if len(line) > 3:
                files.add(line[3:].split(" -> ")[-1])
    return sorted(path for path in files if not path.startswith(".aether-graph/"))


def analyze_impact(root: Path, graph: dict, base: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    changed = _changed_files(root, base)
    changed_ids = {f"file:{path}" for path in changed}
    nodes = {n.get("id"): n for n in graph.get("nodes", [])}
    adjacency: dict[str, list[tuple[str, dict]]] = {}
    for link in graph.get("links", []):
        source, target = link.get("source"), link.get("target")
        adjacency.setdefault(source, []).append((target, link))
        adjacency.setdefault(target, []).append((source, link))
    impacted = []
    seen = set(changed_ids)
    frontier = [(node_id, 0) for node_id in changed_ids]
    while frontier:
        current, hop = frontier.pop(0)
        if hop >= 2:
            continue
        for neighbor, edge in adjacency.get(current, []):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            impacted.append({
                "node": nodes.get(neighbor, {"id": neighbor, "name": neighbor}),
                "hop": hop + 1,
                "via": current,
                "label": edge.get("label", "conecta"),
                "confidence": edge.get("confidence", "EXTRACTED"),
            })
            frontier.append((neighbor, hop + 1))
    direct = sum(1 for item in impacted if item["hop"] == 1)
    score = min(100, len(changed) * 8 + direct * 3 + max(0, len(impacted) - direct))
    risk = "high" if score >= 60 else "medium" if score >= 25 else "low"
    conflicts: list[str] = []
    conflict_note = "Sin rama base: solo se calculó riesgo sobre dependencias."
    if base:
        merge_base = _git(root, "merge-base", base, "HEAD")
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            simulated = _git(root, "merge-tree", merge_base.stdout.strip(), base, "HEAD")
            lines = simulated.stdout.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("changed in both"):
                    nearby = lines[index:index + 8]
                    candidate = next((part.strip() for part in nearby if part.strip().startswith(("base ", "our  ", "their "))), "")
                    if candidate:
                        conflicts.append(candidate.split()[-1])
            conflict_note = "Conflictos potenciales obtenidos mediante simulación no destructiva de git merge-tree."
        else:
            conflict_note = f"No se pudo resolver la rama base '{base}'."
    impacted.sort(key=lambda item: (item["hop"], -item["node"].get("degree", 0), item["node"].get("name", "")))
    total_impacted = len(impacted)
    return {
        "base": base,
        "changed_files": changed,
        "impacted_nodes": impacted[:250],
        "impacted_count": total_impacted,
        "impacted_truncated": total_impacted > 250,
        "risk": {"level": risk, "score": score, "direct": direct, "transitive": len(impacted) - direct},
        "conflicts": sorted(set(conflicts)),
        "conflict_detection": conflict_note,
    }
