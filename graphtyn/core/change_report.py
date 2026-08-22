"""Persistent Markdown report for Git-aware impact analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def render_change_report(root: Path, impact: dict[str, Any]) -> str:
    risk = impact.get("risk", {})
    lines = [f"# GRAPHTYN CHANGE REPORT — {root.name}", "",
             f"- Base: `{impact.get('base') or 'working tree'}`",
             f"- Risk: **{risk.get('level', 'unknown').upper()}** ({risk.get('score', 0)}/100)",
             f"- Changed files: {len(impact.get('changed_files', []))}",
             f"- Changed symbols: {len(impact.get('changed_symbols', []))}",
             f"- Impacted nodes: {impact.get('impacted_count', len(impact.get('impacted_nodes', [])))}", "",
             "## Changed symbols", ""]
    if impact.get("changed_symbols"):
        for item in impact["changed_symbols"][:100]:
            lines.append(f"- `{item.get('name')}` — `{item.get('file')}:{item.get('line')}` ({', '.join(item.get('change_types', []))})")
    else:
        lines.append("- No symbol-level changes detected.")
    lines.extend(["", "## Blast radius", ""])
    for item in impact.get("impacted_nodes", [])[:100]:
        node = item.get("node", {})
        location = node.get("file") or node.get("details") or "unknown"
        lines.append(f"- hop {item.get('hop')} · `{node.get('name', node.get('id'))}` · {item.get('label')} · {item.get('confidence')} · `{location}`")
    if not impact.get("impacted_nodes"):
        lines.append("- No downstream nodes detected.")
    lines.extend(["", "## Recommended verification", ""])
    for item in impact.get("verification_plan", [])[:100]:
        lines.append(f"{item.get('order')}. `{item.get('symbol')}` — {item.get('reason')} ({item.get('file') or 'location unavailable'})")
    if not impact.get("verification_plan"):
        lines.append("- Run the tests closest to each changed file and verify public contracts.")
    lines.extend(["", "## Potential conflicts", ""])
    lines.extend(f"- `{item}`" for item in impact.get("conflicts", []))
    if not impact.get("conflicts"):
        lines.append(f"- None reported. {impact.get('conflict_detection', '')}")
    lines.extend(["", "## Evidence policy", "",
                  "EXTRACTED is parser evidence; INFERRED requires source verification; AMBIGUOUS must not be asserted as fact.", ""])
    return "\n".join(lines)
