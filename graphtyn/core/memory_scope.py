"""Resolve the explicit identity scope of a Graphtyn memory space."""
from __future__ import annotations

import json
from pathlib import Path
from .storage import data_home


def resolve_memory_scope(workspace: str | Path) -> dict:
    root = Path(workspace).expanduser().resolve()
    project_file = data_home() / "registered_projects.json"
    source_file = data_home() / "history-sources.json"
    registration = None
    sources: list[dict] = []
    try:
        rows = json.loads(project_file.read_text(encoding="utf-8"))
        if isinstance(rows, list):
            registration = next((row for row in rows if isinstance(row, dict) and
                                 Path(str(row.get("path") or "")).expanduser().resolve() == root), None)
    except (OSError, ValueError, TypeError, RuntimeError):
        pass
    try:
        payload = json.loads(source_file.read_text(encoding="utf-8"))
        rows = payload.get("sources", []) if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or not row.get("enabled", True):
                    continue
                associated = row.get("project_path") or row.get("workspace")
                if associated and Path(str(associated)).expanduser().resolve() == root:
                    sources.append(row)
    except (OSError, ValueError, TypeError, RuntimeError):
        pass

    explicit_type = str((registration or {}).get("space_type") or "").strip().casefold()
    space_type = explicit_type if explicit_type in {"project", "agent_brain", "container"} else (
        "project")
    owners = {str(value).strip().casefold() for value in (registration or {}).get("agent_ids", [])
              if str(value).strip()}
    owners.update(str(row.get("agent_id") or row.get("agent") or "").strip().casefold()
                  for row in sources if str(row.get("agent_id") or row.get("agent") or "").strip())
    restricted = space_type == "agent_brain" or bool(sources)
    return {"workspace": str(root), "space_type": space_type, "agent_ids": sorted(owners),
            "restricted": restricted, "configured": bool(owners),
            "source_count": len(sources), "registered": registration is not None}
