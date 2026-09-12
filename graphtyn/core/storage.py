"""Collision-safe per-project storage locations."""
from __future__ import annotations
import hashlib
import getpass
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_GENERIC_ROOT_NAMES = {
    "documents", "documentos", "desktop", "escritorio", "downloads", "descargas",
    "projects", "proyectos", "work", "workspace", "code", "dev", "repos", "repositorios"
}


def unsafe_project_root(project: str | Path) -> str | None:
    """Return a reason when a path is a user/container root, not a repository."""
    path = Path(project).expanduser().resolve()
    if path == Path.home().resolve():
        return "la carpeta personal no se puede registrar como proyecto"
    if path.name.casefold() in _GENERIC_ROOT_NAMES and not (path / ".git").exists():
        return "la carpeta contenedora/general no se puede registrar como proyecto"
    return None


def data_home() -> Path:
    """Central Graphtyn state root, overridable for containers and CI."""
    configured = os.environ.get("GRAPHTYN_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".graphtyn"


def secure_private_file(path: Path) -> None:
    """Restrict a state file to the current user on POSIX or Windows ACLs."""
    target = Path(path)
    if os.name != "nt":
        target.chmod(0o600)
        return
    username = os.environ.get("USERNAME") or getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    account = f"{domain}\\{username}" if domain else username
    result = subprocess.run(["icacls", str(target), "/inheritance:r", "/grant:r", f"{account}:(F)"],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise PermissionError(f"no se pudo restringir ACL de {target}: {result.stderr.strip()}")


def atomic_write_json(path: Path, value: object, *, mode: int = 0o600) -> None:
    """Replace a JSON state file atomically and keep it private."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, mode)
        os.replace(temporary, target)
        secure_private_file(target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass

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
