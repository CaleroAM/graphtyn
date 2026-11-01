"""Triage several open branches: conflicts, shared symbols and merge order.

Each branch is compared with its merge base. Changed line ranges on the base
side are mapped onto the indexed graph, so symbols refer to the indexed
revision (normally the base branch). Pairs are checked for textual conflicts
with a non-destructive `git merge-tree --write-tree`, for symbols both branches
edit, and for semantic coupling, where one branch edits a symbol and the other
edits one of its callers. Nothing in the working tree or index is modified.
"""
from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path
from typing import Any

from .impact import _git

_CONSUMER_LABELS = {"llama", "usa", "referencia", "implementa", "hereda", "crea", "invoca ruta"}


def _base_ranges(root: Path, merge_base: str, branch: str) -> dict[str, list[tuple[int, int]]]:
    """Changed ranges per file, on the merge-base side of the diff."""
    diff = _git(root, "diff", "--no-ext-diff", "--no-color", "--unified=0", merge_base, branch)
    ranges: dict[str, list[tuple[int, int]]] = {}
    current = None
    for line in diff.stdout.splitlines():
        if line.startswith("--- "):
            current = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("+++ ") and current is None and line.startswith("+++ b/"):
            current = line[6:]  # file added on the branch
            ranges.setdefault(current, [])
        elif current and line.startswith("@@"):
            match = re.search(r"-(\d+)(?:,(\d+))?", line)
            if match:
                start, count = int(match.group(1)), int(match.group(2) or "1")
                # A pure insertion (count 0) sits between base lines start and start+1.
                ranges.setdefault(current, []).append((start, start + max(count, 1) - 1))
    return ranges


def branch_changes(root: Path, graph: dict[str, Any], base: str, branch: str) -> dict[str, Any]:
    merge_base = _git(root, "merge-base", base, branch)
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        return {"branch": branch, "error": f"no se pudo calcular merge-base con {base}"}
    merge_base_sha = merge_base.stdout.strip()
    ranges = _base_ranges(root, merge_base_sha, branch)
    by_file: dict[str, list[dict[str, Any]]] = {}
    for node in graph.get("nodes", []):
        if node.get("file") and node.get("line") and node.get("kind") not in {"file", "module"}:
            by_file.setdefault(str(node["file"]), []).append(node)
    symbols: dict[str, dict[str, Any]] = {}
    for path, spans in ranges.items():
        for start, end in spans:
            overlapping = [node for node in by_file.get(path, [])
                           if int(node["line"]) <= end and int(node.get("end_line") or node["line"]) >= start]
            if overlapping:
                narrowest = min(overlapping, key=lambda node: int(node.get("end_line") or node["line"]) - int(node["line"]))
                symbols[str(narrowest["id"])] = narrowest
    consumers: dict[str, set[str]] = {}
    for link in graph.get("links", []):
        if str(link.get("label") or "") in _CONSUMER_LABELS and str(link.get("target")) in symbols:
            consumers.setdefault(str(link["target"]), set()).add(str(link.get("source")))
    return {
        "branch": branch, "merge_base": merge_base_sha, "files": sorted(ranges),
        "symbols": {node_id: {"name": node.get("name"), "file": node.get("file"), "line": node.get("line")}
                    for node_id, node in symbols.items()},
        "consumers": {node_id: sorted(ids) for node_id, ids in consumers.items()},
    }


def _textual_conflicts(root: Path, left: str, right: str) -> list[str]:
    result = _git(root, "merge-tree", "--write-tree", "--no-messages", "--name-only", left, right)
    if result.returncode == 0:
        return []
    # Exit status 1 lists the result tree followed by conflicted paths.
    return [line for line in result.stdout.splitlines()[1:] if line.strip()]


def triage(root: str | Path, graph: dict[str, Any], base: str, branches: list[str]) -> dict[str, Any]:
    root = Path(root).resolve()
    changes = [branch_changes(root, graph, base, branch) for branch in dict.fromkeys(branches)]
    valid = [item for item in changes if "error" not in item]
    pairs, depends_on = [], {item["branch"]: set() for item in valid}
    for left, right in combinations(valid, 2):
        shared_files = sorted(set(left["files"]) & set(right["files"]))
        shared_symbols = sorted(left["symbols"][key]["name"] for key in set(left["symbols"]) & set(right["symbols"]))
        coupling = []
        for provider, consumer in ((left, right), (right, left)):
            for symbol_id, callers in provider["consumers"].items():
                touched = set(callers) & set(consumer["symbols"])
                if touched and symbol_id not in consumer["symbols"]:
                    coupling.append({"changed_by": provider["branch"], "symbol": provider["symbols"][symbol_id]["name"],
                                     "callers_changed_by": consumer["branch"],
                                     "callers": sorted(consumer["symbols"][item]["name"] for item in touched)})
                    depends_on[consumer["branch"]].add(provider["branch"])
        conflicts = _textual_conflicts(root, left["branch"], right["branch"]) if shared_files else []
        risk = "high" if conflicts else "medium" if shared_symbols or coupling else "low" if shared_files else "none"
        pairs.append({"branches": [left["branch"], right["branch"]], "risk": risk,
                      "textual_conflicts": conflicts, "shared_files": shared_files,
                      "shared_symbols": shared_symbols, "semantic_coupling": coupling})
    exposure = {item["branch"]: sum(len(callers) for callers in item["consumers"].values()) for item in valid}
    conflict_count = {item["branch"]: 0 for item in valid}
    for pair in pairs:
        for branch in pair["branches"]:
            conflict_count[branch] += len(pair["textual_conflicts"])
    # Providers before the branches whose callers depend on them; among ready
    # branches, fewer conflicts and a smaller blast radius go first.
    order, pending = [], set(depends_on)
    while pending:
        ready = [branch for branch in pending if not (depends_on[branch] & pending)] or list(pending)
        chosen = min(ready, key=lambda branch: (conflict_count[branch], exposure[branch], branch))
        order.append(chosen)
        pending.remove(chosen)
    return {"base": base, "branches": changes, "pairs": pairs, "merge_order": order,
            "note": "Símbolos mapeados sobre la revisión indexada; los conflictos se simulan con git merge-tree sin modificar el árbol."}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [f"# Triaje de ramas frente a `{result['base']}`", ""]
    for item in result["branches"]:
        if "error" in item:
            lines.append(f"- **{item['branch']}**: {item['error']}")
            continue
        names = ", ".join(f"`{value['name']}`" for value in list(item["symbols"].values())[:6]) or "sin símbolos indexados"
        lines.append(f"- **{item['branch']}**: {len(item['files'])} archivos; símbolos: {names}")
    lines += ["", "## Pares"]
    for pair in sorted(result["pairs"], key=lambda item: ["high", "medium", "low", "none"].index(item["risk"])):
        detail = []
        if pair["textual_conflicts"]:
            detail.append("conflictos: " + ", ".join(f"`{path}`" for path in pair["textual_conflicts"]))
        if pair["shared_symbols"]:
            detail.append("símbolos compartidos: " + ", ".join(f"`{name}`" for name in pair["shared_symbols"]))
        for item in pair["semantic_coupling"]:
            detail.append(f"`{item['changed_by']}` cambia `{item['symbol']}` y `{item['callers_changed_by']}` "
                          f"modifica sus llamadores ({', '.join(item['callers'])})")
        lines.append(f"- {' ↔ '.join(pair['branches'])} — **{pair['risk']}**" + (": " + "; ".join(detail) if detail else ""))
    lines += ["", "## Orden de merge sugerido", *[f"{index}. `{branch}`" for index, branch in enumerate(result["merge_order"], 1)],
              "", f"_{result['note']}_"]
    return "\n".join(lines) + "\n"
