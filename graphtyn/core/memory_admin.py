"""Verified backup/restore and schema inspection for shared memory."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from .shared_memory import SharedMemoryStore

def backup_memory(workspace: Path, output: Path) -> dict:
    store = SharedMemoryStore(workspace); output = output.expanduser().resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="graphtyn-backup-") as temp:
        copy = Path(temp) / "memory-v2.db"
        source = sqlite3.connect(store.db_path); target = sqlite3.connect(copy); source.backup(target); target.close(); source.close()
        digest = hashlib.sha256(copy.read_bytes()).hexdigest()
        manifest = {"schema": "graphtyn-memory-backup-v1", "workspace": str(workspace.resolve()),
                    "created_at": time.time(), "database_sha256": digest}
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(copy, "memory-v2.db"); bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    output.chmod(0o600); return {"ok": True, "output": str(output), **manifest}

def verify_backup(path: Path) -> dict:
    with zipfile.ZipFile(path.expanduser().resolve()) as bundle:
        names = set(bundle.namelist())
        if names != {"memory-v2.db", "manifest.json"}: raise ValueError("contenido de backup inesperado")
        manifest = json.loads(bundle.read("manifest.json")); raw = bundle.read("memory-v2.db")
    valid = hashlib.sha256(raw).hexdigest() == manifest.get("database_sha256")
    return {"ok": valid, "manifest": manifest, "size": len(raw)}

def restore_memory(workspace: Path, backup: Path, *, apply: bool = False) -> dict:
    check = verify_backup(backup)
    if not check["ok"]: raise ValueError("checksum de backup inválido")
    store = SharedMemoryStore(workspace)
    if not apply: return {**check, "dry_run": True, "target": str(store.db_path)}
    safety = store.db_path.with_suffix(f".before-restore-{int(time.time())}.db")
    if store.db_path.exists(): safety.write_bytes(store.db_path.read_bytes()); safety.chmod(0o600)
    with zipfile.ZipFile(backup.expanduser().resolve()) as bundle:
        raw = bundle.read("memory-v2.db")
    temp = store.db_path.with_suffix(".restore.tmp"); temp.write_bytes(raw); temp.chmod(0o600); os.replace(temp, store.db_path)
    return {**check, "dry_run": False, "target": str(store.db_path), "safety_copy": str(safety)}
