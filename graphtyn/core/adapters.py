"""Manifest-based history adapters; built-ins and third parties share one catalog."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
from .storage import data_home

BUILTIN_ADAPTERS = {
    name: {"name": name, "format": "auto", "extensions": ["json", "jsonl", "db", "sqlite", "sqlite3"],
           "builtin": True, "version": 1}
    for name in ("openclaw", "hermes", "codex", "antigravity", "opencode", "claude")
}

def adapter_dir() -> Path:
    return data_home() / "adapters"

def validate_manifest(value: dict[str, Any]) -> dict[str, Any]:
    name = str(value.get("name") or "").strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", name):
        raise ValueError("name de adaptador inválido")
    fmt = str(value.get("format") or "auto").casefold()
    if fmt not in {"auto", "json", "jsonl", "sqlite"}: raise ValueError("format no soportado")
    extensions = [str(item).lstrip(".").casefold() for item in value.get("extensions", [])]
    if not extensions: extensions = [fmt] if fmt != "auto" else ["json", "jsonl", "db"]
    if any(not re.fullmatch(r"[a-z0-9]{1,12}", item) for item in extensions):
        raise ValueError("extensión inválida")
    return {"name": name, "format": fmt, "extensions": sorted(set(extensions)),
            "version": int(value.get("version") or 1), "builtin": False,
            "description": str(value.get("description") or "")[:300]}

def install_adapter(manifest: str | Path) -> dict[str, Any]:
    path = Path(manifest).expanduser().resolve()
    value = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
    target = adapter_dir() / f"{value['name']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    target.chmod(0o600)
    return {**value, "path": str(target)}

def list_adapters() -> list[dict[str, Any]]:
    values = dict(BUILTIN_ADAPTERS)
    for path in adapter_dir().glob("*.json") if adapter_dir().exists() else []:
        try:
            item = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
            item["path"] = str(path); values[item["name"]] = item
        except (OSError, ValueError, TypeError): pass
    return [values[key] for key in sorted(values)]

def remove_adapter(name: str) -> bool:
    if name.casefold() in BUILTIN_ADAPTERS: raise ValueError("un adaptador integrado no se elimina")
    target = adapter_dir() / f"{name.casefold()}.json"
    existed = target.exists(); target.unlink(missing_ok=True); return existed

