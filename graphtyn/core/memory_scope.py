"""Resolve the explicit identity scope of a Graphtyn memory space."""
from __future__ import annotations

import json
from pathlib import Path
from .storage import data_home


def resolve_memory_scope(workspace: str | Path, *, registrations=None, sources=None) -> dict:
    root = Path(workspace).expanduser().resolve()
    project_file = data_home() / "registered_projects.json"
    source_file = data_home() / "history-sources.json"
    if registrations is None:
        try:
            rows = json.loads(project_file.read_text(encoding="utf-8"))
            registrations = rows if isinstance(rows, list) else []
        except (OSError, ValueError, TypeError, RuntimeError):
            registrations = []
    registration = next((row for row in registrations if isinstance(row, dict) and
                         row.get("path") and Path(str(row["path"])).expanduser().resolve() == root), None)
    if sources is None:
        try:
            payload = json.loads(source_file.read_text(encoding="utf-8"))
            rows = payload.get("sources", []) if isinstance(payload, dict) else payload
            sources = rows if isinstance(rows, list) else []
        except (OSError, ValueError, TypeError, RuntimeError):
            sources = []
    associated_sources = []
    for row in sources:
        if not isinstance(row, dict) or not row.get("enabled", True):
            continue
        associated = row.get("project_path") or row.get("workspace")
        if associated and Path(str(associated)).expanduser().resolve() == root:
            associated_sources.append(row)

    explicit_type = str((registration or {}).get("space_type") or "").strip().casefold()
    space_type = explicit_type if explicit_type in {"project", "agent_brain", "container"} else (
        "project")
    owners = {str(value).strip().casefold() for value in (registration or {}).get("agent_ids", [])
              if str(value).strip()}
    # Source attribution identifies who produced a conversation; it does not
    # turn a shared project into a private agent brain. Only agent-brain
    # stores inherit owners from their linked sources.
    if space_type == "agent_brain":
        owners.update(str(row.get("agent_id") or row.get("agent") or "").strip().casefold()
                      for row in associated_sources if str(row.get("agent_id") or row.get("agent") or "").strip())
    restricted = space_type == "agent_brain" or bool((registration or {}).get("agent_ids"))
    return {"workspace": str(root), "space_type": space_type, "agent_ids": sorted(owners),
            "restricted": restricted, "configured": bool(owners),
            "source_count": len(associated_sources), "registered": registration is not None}
