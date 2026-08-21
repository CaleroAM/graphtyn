"""Git-aware pull-request and working-tree impact analysis."""

from __future__ import annotations

import subprocess
import re
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


def _diff_details(root: Path, base: str | None, changed: list[str]) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    commands = []
    if base:
        commands.append(("diff", "--no-ext-diff", "--no-color", "--unified=0", f"{base}...HEAD"))
    commands.extend([
        ("diff", "--no-ext-diff", "--no-color", "--unified=0"),
        ("diff", "--cached", "--no-ext-diff", "--no-color", "--unified=0"),
    ])
    for args in commands:
        result = _git(root, *args)
        current = ""
        for line in result.stdout.splitlines():
            if line.startswith("+++ b/"):
                current = line[6:]
                details.setdefault(current, {"ranges": [], "added": [], "removed": []})
            elif current and line.startswith("@@"):
                match = re.search(r"\+(\d+)(?:,(\d+))?", line)
                if match:
                    start = int(match.group(1))
                    count = int(match.group(2) or "1")
                    if count:
                        details[current]["ranges"].append([start, start + count - 1])
            elif current and line.startswith("+") and not line.startswith("+++"):
                details[current]["added"].append(line[1:][:500])
            elif current and line.startswith("-") and not line.startswith("---"):
                details[current]["removed"].append(line[1:][:500])

    for path in changed:
        item = details.setdefault(path, {"ranges": [], "added": [], "removed": []})
        file_path = root / path
        if not item["ranges"] and file_path.is_file() and path not in {
            line[3:].split(" -> ")[-1] for line in _git(root, "status", "--porcelain").stdout.splitlines()
            if not line.startswith("??")
        }:
            try:
                count = sum(1 for _ in file_path.open(encoding="utf-8", errors="ignore"))
                item["ranges"] = [[1, max(1, count)]]
            except OSError:
                pass
        suffix = file_path.suffix.lower()
        changed_text = "\n".join(item["added"] + item["removed"])
        types = []
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".wav", ".mp4", ".prefab", ".unity", ".asset"}:
            types.append("asset")
        if suffix in {".json", ".yaml", ".yml", ".toml", ".xml", ".csproj", ".sln", ".asmdef"}:
            types.append("configuration")
        if suffix in {".md", ".rst", ".txt"}:
            types.append("documentation")
        if re.search(r"\b(class|interface|struct|enum|public|protected|internal|def|func|fn)\b[^\n]*(\(|:)", changed_text):
            types.append("signature")
        if not types:
            types.append("logic")
        item["change_types"] = types
        item.pop("added", None)
        item.pop("removed", None)
    return details


def analyze_impact(root: Path, graph: dict, base: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    changed = _changed_files(root, base)
    nodes = {n.get("id"): n for n in graph.get("nodes", [])}
    diff_details = _diff_details(root, base, changed)
    changed_symbols = []
    symbol_seed_ids: set[str] = set()
    symbols_by_file: dict[str, list[dict]] = {}
    for node in nodes.values():
        if node.get("file") and node.get("line"):
            symbols_by_file.setdefault(node["file"], []).append(node)
    selected_nodes: dict[str, dict] = {}
    for rel_file, detail in diff_details.items():
        file_symbols = symbols_by_file.get(rel_file, [])
        for start, end in detail["ranges"]:
            overlapping = [
                node for node in file_symbols
                if node.get("line", 0) <= end and node.get("end_line", node.get("line", 0)) >= start
            ]
            declarations = [node for node in overlapping if start <= node.get("line", 0) <= end]
            if declarations:
                for node in declarations:
                    selected_nodes[node["id"]] = node
            elif overlapping:
                narrowest = min(overlapping, key=lambda node: node.get("end_line", node["line"]) - node["line"])
                selected_nodes[narrowest["id"]] = narrowest
    for node in selected_nodes.values():
        rel_file = node["file"]
        symbol_seed_ids.add(node["id"])
        changed_symbols.append({
            "id": node["id"], "name": node.get("name"), "kind": node.get("kind"),
            "file": rel_file, "line": node.get("line"), "end_line": node.get("end_line"),
            "change_types": diff_details[rel_file]["change_types"],
        })
    files_with_symbols = {item["file"] for item in changed_symbols}
    changed_ids = symbol_seed_ids | {f"file:{path}" for path in changed if path not in files_with_symbols}
    adjacency: dict[str, list[tuple[str, dict]]] = {}
    for link in graph.get("links", []):
        source, target = link.get("source"), link.get("target")
        label = link.get("label", "")
        if label in {"llama", "usa", "referencia"}:
            adjacency.setdefault(target, []).append((source, link))
        elif label == "contiene":
            adjacency.setdefault(source, []).append((target, link))
        else:
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
    signature_changes = sum("signature" in item["change_types"] for item in changed_symbols)
    score = min(100, len(changed) * 5 + signature_changes * 12 + direct * 3 + max(0, len(impacted) - direct))
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
        "file_changes": diff_details,
        "changed_symbols": sorted(changed_symbols, key=lambda item: (item["file"], item["line"], item["name"])),
        "impacted_nodes": impacted[:250],
        "impacted_count": total_impacted,
        "impacted_truncated": total_impacted > 250,
        "risk": {"level": risk, "score": score, "direct": direct, "transitive": len(impacted) - direct},
        "conflicts": sorted(set(conflicts)),
        "conflict_detection": conflict_note,
    }
