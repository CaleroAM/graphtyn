"""Verified, bounded-memory backup/restore and schema inspection for shared memory."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

from .shared_memory import (SharedMemoryStore, _resolve_store_path,
                            exclusive_store_access)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_zip_member(bundle: zipfile.ZipFile, name: str) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with bundle.open(name) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk); size += len(chunk)
    return digest.hexdigest(), size


def backup_memory(workspace: Path, output: Path) -> dict:
    store = SharedMemoryStore(workspace)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="graphtyn-backup-") as temp:
        copy = Path(temp) / "memory-v2.db"
        with store._connect() as source:
            target = sqlite3.connect(copy)
            try:
                source.backup(target)
            finally:
                target.close()
        digest = _sha256_file(copy)
        resolved = workspace.resolve()
        manifest = {"schema": "graphtyn-memory-backup-v1", "workspace": resolved.name,
                    "workspace_id": hashlib.sha256(str(resolved).encode()).hexdigest()[:16],
                    "created_at": time.time(), "database_sha256": digest}
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(copy, "memory-v2.db")
            bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    output.chmod(0o600)
    return {"ok": True, "source": str(store.db_path.resolve()), "output": str(output), **manifest}


def verify_backup(path: Path) -> dict:
    with zipfile.ZipFile(path.expanduser().resolve()) as bundle:
        if set(bundle.namelist()) != {"memory-v2.db", "manifest.json"}:
            raise ValueError("contenido de backup inesperado")
        manifest = json.loads(bundle.read("manifest.json"))
        digest, size = _hash_zip_member(bundle, "memory-v2.db")
    valid = digest == manifest.get("database_sha256")
    return {"ok": valid, "manifest": manifest, "size": size}


def restore_memory(workspace: Path, backup: Path, *, apply: bool = False) -> dict:
    check = verify_backup(backup)
    if not check["ok"]:
        raise ValueError("checksum de backup inválido")
    db_path = _resolve_store_path(workspace, create=False)
    if not apply:
        return {**check, "dry_run": True, "target": str(db_path)}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    safety = db_path.with_suffix(f".before-restore-{int(time.time())}.db")
    with tempfile.TemporaryDirectory(prefix="graphtyn-restore-") as temp:
        incoming = Path(temp) / "memory-v2.db"
        with zipfile.ZipFile(backup.expanduser().resolve()) as bundle, bundle.open("memory-v2.db") as source:
            with incoming.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
        if _sha256_file(incoming) != check["manifest"].get("database_sha256"):
            raise ValueError("checksum de backup inválido")
        with closing(sqlite3.connect(incoming)) as source:
            integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError("la base de datos del backup no supera integrity_check")
        with exclusive_store_access(db_path):
            if db_path.is_file():
                safety_tmp = safety.with_suffix(safety.suffix + ".tmp")
                with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(safety_tmp)) as target:
                    source.backup(target)
                os.replace(safety_tmp, safety)
                safety.chmod(0o600)
            with closing(sqlite3.connect(incoming)) as source, closing(sqlite3.connect(db_path)) as target:
                source.backup(target)
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError("la base restaurada no supera integrity_check")
        db_path.chmod(0o600)
    # Force normal migration checks once the exclusive restore lease is released.
    SharedMemoryStore(workspace)
    return {**check, "dry_run": False, "target": str(db_path),
            "safety_copy": str(safety) if safety.exists() else None,
            "integrity_check": "ok"}
