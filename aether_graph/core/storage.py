"""Collision-safe per-project storage locations."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
from pathlib import Path

def project_store_dir(base: Path, project: Path, migrate_legacy: bool = True, create: bool = True) -> Path:
    resolved = project.resolve()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", resolved.name) or "project"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:10]
    target = Path(base) / f"{slug}-{digest}"
    if target.exists():
        return target
    legacy = Path(base) / resolved.name
    if migrate_legacy and legacy.is_dir():
        try:
            index = json.loads((legacy / "index.json").read_text(encoding="utf-8"))
            indexed_path = Path(str((index.get("metadata") or {}).get("path") or "")).resolve()
            if indexed_path == resolved:
                shutil.copytree(legacy, target)
                return target
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target
