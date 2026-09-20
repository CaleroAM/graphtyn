"""Project identity and project-scoped MCP configuration for coding clients."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib


SUPPORTED_CONFIGS = {
    "codex": ".codex/config.toml",
    "opencode": "opencode.json",
    "claude": ".mcp.json",
    "cursor": ".cursor/mcp.json",
    "antigravity": ".agents/mcp_config.json",
}
_MANAGED_START = "# BEGIN GRAPHTYN MCP PROJECT "
_MANAGED_END = "# END GRAPHTYN MCP PROJECT"


def _read_metadata(root: Path) -> dict[str, Any]:
    path = root / ".graphtyn" / "graphtyn.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "name": root.name}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} debe contener un objeto JSON")
    return value


def _registered_identity(root: Path) -> dict[str, Any]:
    """Read an exact project identity without registering or mutating it."""
    from .storage import data_home

    try:
        registry = json.loads((data_home() / "project-identities.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    for item in registry.get("projects", []) if isinstance(registry, dict) else []:
        if not isinstance(item, dict):
            continue
        for value in item.get("paths", []):
            try:
                if Path(str(value)).expanduser().resolve() == root:
                    return item
            except (OSError, RuntimeError, ValueError):
                continue
    return {}


def _codex_global_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return (base / "config.toml").resolve()


def _configured_project_path(server: dict[str, Any], config_path: Path,
                             project_id: str | None) -> Path | str | None:
    args = server.get("args")
    if not isinstance(args, list) or not args or str(args[0]) != "mcp":
        return None
    configured_path = None
    for index, value in enumerate(args):
        value = str(value)
        if value == "--path" and index + 1 < len(args):
            configured_path = str(args[index + 1])
            break
        if value.startswith("--path="):
            configured_path = value.split("=", 1)[1]
            break
    if not configured_path:
        return None
    if project_id and configured_path == project_id:
        return project_id

    candidate = Path(configured_path).expanduser()
    if not candidate.is_absolute():
        cwd = server.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip() or cwd.strip() == "-":
            return None
        base = Path(cwd).expanduser()
        if not base.is_absolute():
            base = config_path.parent / base
        candidate = base / candidate
    try:
        return candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _global_codex_entries(root: Path, project_id: str | None) -> list[dict[str, Any]]:
    """Find read-only Codex user-config entries explicitly scoped to this project."""
    config_path = _codex_global_config_path()
    if config_path == (root / SUPPORTED_CONFIGS["codex"]).resolve() or not config_path.is_file():
        return []
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    servers = config.get("mcp_servers") if isinstance(config, dict) else None
    if not isinstance(servers, dict):
        return []

    matches = []
    for alias, server in servers.items():
        if not isinstance(server, dict) or server.get("enabled") is False:
            continue
        command = server.get("command")
        if not isinstance(command, str) or Path(command).name.casefold() not in {"graphtyn", "graphtyn.exe"}:
            continue
        target = _configured_project_path(server, config_path, project_id)
        if target != root and target != project_id:
            continue
        matches.append({"alias": str(alias), "configuration": str(config_path),
                        "server": server})
    return matches


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def ensure_project_identity(project: str | Path, aliases: list[str] | None = None) -> dict[str, Any]:
    """Register a project once and persist its identity through folder renames."""
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"La carpeta del proyecto no existe: {root}")
    from .history_import import ProjectIdentityRegistry

    metadata = _read_metadata(root)
    identity = ProjectIdentityRegistry().register(root, aliases=aliases,
                                                   project_id=metadata.get("project_id"))
    metadata.update({"version": 1, "name": metadata.get("name") or root.name,
                     "project_id": identity["id"]})
    _write_json(root / ".graphtyn" / "graphtyn.json", metadata)

    gitignore = root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".graphtyn/" not in current.splitlines():
        gitignore.write_text(current + ("" if not current or current.endswith("\n") else "\n")
                             + ".graphtyn/\n", encoding="utf-8")
    return {**identity, "mcp_server": project_server_name(root, identity["id"])}


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return (slug or "project")[:48]


def project_server_name(project: str | Path, project_id: str) -> str:
    return f"graphtyn_{_slug(Path(project).name)}_{project_id[:8]}"


def _command(tool_profile: str, root: Path) -> dict[str, Any]:
    # Keep the command portable. The Codex writer pins its working directory
    # to the project so the relative --path argument resolves consistently.
    return {"command": "graphtyn",
            "args": ["mcp", "--tool-profile", tool_profile, "--path", "."]}


def _merge_json_config(path: Path, section: str, name: str,
                       server: dict[str, Any]) -> None:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path} no es JSON válido; se conservó sin cambios: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path} debe contener un objeto JSON; se conservó sin cambios")
    else:
        data = {}
    servers = data.setdefault(section, {})
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: {section} debe ser un objeto; se conservó sin cambios")
    current = servers.get(name)
    if current is not None and current != server:
        if server.get("type") == "local":
            managed = (isinstance(current, dict)
                       and current.get("type") == "local"
                       and current.get("command", [])[:3] == server.get("command", [])[:3])
        else:
            managed = (isinstance(current, dict)
                       and current.get("command") == server.get("command")
                       and current.get("args", [])[:3] == server.get("args", [])[:3])
        if not managed:
            raise ValueError(f"{path}: el servidor {name} ya existe y no pertenece a Graphtyn")
    servers[name] = server
    _write_json(path, data)


def _toml_string(value: str) -> str:
    # JSON basic strings use escapes accepted by TOML for these characters.
    return json.dumps(value, ensure_ascii=False)


def _write_codex_config(path: Path, name: str, server: dict[str, Any],
                        project_id: str, root: Path) -> None:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = re.compile(
        rf"(?ms)^# BEGIN GRAPHTYN MCP PROJECT {re.escape(project_id)}\n.*?^# END GRAPHTYN MCP PROJECT\n?"
    )
    current = marker.sub("", current).rstrip()
    table = re.compile(rf"(?m)^\[mcp_servers\.(?:{re.escape(name)}|\"{re.escape(name)}\")\]\s*$")
    if table.search(current):
        raise ValueError(f"{path}: el servidor {name} ya existe y no pertenece a Graphtyn")
    command = server["command"]
    args = ", ".join(_toml_string(item) for item in server["args"])
    block = (f"{_MANAGED_START}{project_id}\n[mcp_servers.{_toml_string(name)}]\n"
             f"command = {_toml_string(command)}\nargs = [{args}]\n"
             f"cwd = {_toml_string(str(root.resolve()))}\n"
             f"enabled = true\n{_MANAGED_END}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current + ("\n\n" if current else "") + block, encoding="utf-8")


def _migrate_legacy_antigravity_mcp(root: Path) -> bool:
    """Move the prior plugin-local Graphtyn entry into Antigravity's workspace config."""
    legacy = root / ".agents/plugins/graphtyn/mcp_config.json"
    manifest_path = root / ".graphtyn/agent-install.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(legacy) not in {str(Path(value)) for value in manifest.get("files", [])}:
            return False
        data = json.loads(legacy.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        old = servers.get("graphtyn") if isinstance(servers, dict) else None
        args = old.get("args", []) if isinstance(old, dict) else []
        if not (isinstance(old, dict) and old.get("command") == "graphtyn"
                and args[:2] == ["mcp", "--tool-profile"]):
            return False
        del servers["graphtyn"]
        if not servers:
            data.pop("mcpServers", None)
        _write_json(legacy, data)
        return True
    except (OSError, ValueError, TypeError):
        return False


def configure_project_integrations(project: str | Path, platforms: list[str], *,
                                   tool_profile: str = "intent") -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    if tool_profile not in {"intent", "memory", "full"}:
        raise ValueError("tool_profile debe ser intent, memory o full")
    identity = ensure_project_identity(root)
    name = project_server_name(root, identity["id"])
    server = _command(tool_profile, root)
    previous = project_integration_status(root)
    for old in previous.get("clients", []):
        if (old.get("platform") in platforms and old.get("status") in {"configured", "command_unavailable"}
                and old.get("alias") != name):
            remove_project_integrations(root, [str(old["platform"])])
    clients = []
    files = []
    for platform in dict.fromkeys(platforms):
        if platform == "openclaw":
            clients.append({"platform": platform, "status": "dynamic_scope", "alias": None,
                            "configuration": None,
                            "note": "OpenClaw selecciona el proyecto por ID con memory_project_context."})
            continue
        relative = SUPPORTED_CONFIGS.get(platform)
        if not relative:
            clients.append({"platform": platform, "status": "instructions_only", "alias": None,
                            "configuration": None,
                            "note": "Este cliente aún no tiene configuración MCP por proyecto automatizada."})
            continue
        path = root / relative
        try:
            if platform == "antigravity":
                _migrate_legacy_antigravity_mcp(root)
            if platform == "codex":
                _write_codex_config(path, name, server, identity["id"], root)
            elif platform == "opencode":
                local = {"type": "local", "command": [server["command"], *server["args"]],
                         "enabled": True}
                _merge_json_config(path, "mcp", name, local)
            else:
                _merge_json_config(path, "mcpServers", name, server)
        except (OSError, ValueError) as exc:
            clients.append({"platform": platform, "status": "needs_review", "alias": name,
                            "configuration": str(path), "note": str(exc)})
            continue
        files.append(str(path))
        clients.append({"platform": platform, "status": "configured", "alias": name,
                        "configuration": str(path), "restart_recommended": True,
                        "command_available": bool(shutil.which("graphtyn")),
                        "note": ("Codex sólo carga la configuración del proyecto cuando éste es de confianza."
                                 if platform == "codex" else "Reinicia o recarga el cliente para descubrir el MCP.")})
    return {"project_id": identity["id"], "project_name": identity.get("canonical_name", root.name),
            "mcp_server": name, "clients": clients, "files": files}


def project_integration_status(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    metadata = _read_metadata(root)
    identity = _registered_identity(root)
    project_id = str(metadata.get("project_id") or identity.get("id") or "") or None
    try:
        manifest = json.loads((root / ".graphtyn" / "agent-install.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    clients = manifest.get("integrations") or []
    for client in clients:
        path = Path(client["configuration"]) if client.get("configuration") else None
        file_exists = bool(path and path.is_file())
        present = False
        if file_exists and client.get("status") == "configured":
            try:
                if client.get("platform") == "codex":
                    text = path.read_text(encoding="utf-8")
                    profile = str(manifest.get("tool_profile") or "intent")
                    present = (f"{_MANAGED_START}{metadata.get('project_id')}" in text
                               and f"mcp_servers.{_toml_string(str(client.get('alias')))}" in text
                               and 'command = "graphtyn"' in text
                               and f'"--tool-profile", "{profile}"' in text
                               and '"--path", "."' in text)
                else:
                    platform = str(client.get("platform"))
                    section = "mcp" if platform == "opencode" else "mcpServers"
                    data = json.loads(path.read_text(encoding="utf-8"))
                    item = data.get(section, {}).get(str(client.get("alias")))
                    if platform == "opencode":
                        args = item.get("command", []) if isinstance(item, dict) else []
                        present = bool(item and args[:1] == ["graphtyn"] and
                                       args[1:] == ["mcp", "--tool-profile", manifest.get("tool_profile", "intent"),
                                                    "--path", "."])
                    else:
                        args = item.get("args", []) if isinstance(item, dict) else []
                        present = bool(item and item.get("command") == "graphtyn"
                                       and args == ["mcp", "--tool-profile", manifest.get("tool_profile", "intent"),
                                                    "--path", "."])
            except (OSError, ValueError, TypeError, AttributeError):
                present = False
        client["configuration_present"] = present
        client["configuration_file_exists"] = file_exists
        client.setdefault("configuration_scope", "project")
        client["command_available"] = bool(shutil.which("graphtyn")) if client.get("status") == "configured" else None
        if client.get("status") == "configured" and not present:
            client["status"] = "missing_or_mismatched"
        elif client.get("status") == "configured" and not client["command_available"]:
            client["status"] = "command_unavailable"

    global_codex = _global_codex_entries(root, project_id)
    for entry in global_codex:
        server = entry["server"]
        command = str(server.get("command") or "")
        available = bool(shutil.which(command))
        clients.append({"platform": "codex", "status": "configured" if available else "command_unavailable",
                        "alias": entry["alias"], "configuration": entry["configuration"],
                        "configuration_scope": "global", "configuration_present": True,
                        "configuration_file_exists": True, "command_available": available,
                        "managed_by_graphtyn": False,
                        "note": "Entrada existente de Codex, reconocida en modo de sólo lectura."})

    capture_configured = bool(manifest.get("capture_configured", False))
    capture_active = False
    capture_watchers = []
    memory_space = {"space_type": "project", "agent_ids": [], "restricted": False, "configured": False}
    try:
        from .memory_scope import resolve_memory_scope
        memory_space = resolve_memory_scope(root)
    except (OSError, RuntimeError, ValueError, TypeError):
        pass
    try:
        from .shared_memory import SharedMemoryStore, existing_store_db
        if existing_store_db(root) is not None:
            memory_status = SharedMemoryStore(root).status()
            capture_watchers = [item for item in memory_status.get("sync_watchers", [])
                                if isinstance(item, dict)]
            capture_active = bool(memory_status.get("continuous_capture_active") or
                                  any(item.get("active") for item in capture_watchers))
            memory_space = dict(memory_status.get("memory_space") or memory_space)
    except (OSError, RuntimeError, ValueError, TypeError):
        pass
    capture_configured = bool(capture_configured or capture_active)

    mcp_server = manifest.get("mcp_server")
    if not mcp_server and global_codex:
        mcp_server = global_codex[0]["alias"]
    return {"project_id": project_id,
            "project_name": identity.get("canonical_name") or metadata.get("name") or root.name,
            "project_aliases": identity.get("aliases", []),
            "mcp_server": mcp_server,
            "clients": clients,
            "mcp_verification": manifest.get("mcp_verification"),
            "capture_configured": capture_configured,
            "capture_active": capture_active,
            "capture_watchers": capture_watchers,
            "memory_scope": memory_space,
            "scope_configured": bool(memory_space.get("configured")),
            "historical_imported_automatically": False}


def verify_project_mcp(project: str | Path) -> dict[str, Any]:
    """Verify the configured project MCP entry without rewriting client settings."""
    import asyncio

    root = Path(project).expanduser().resolve()
    status = project_integration_status(root)
    clients = [item for item in status.get("clients", []) if item.get("status") == "configured"]
    if not clients:
        return {"ok": False, "error": "No hay un cliente con un MCP configurado para este proyecto."}
    profile = "intent"
    try:
        manifest = json.loads((root / ".graphtyn" / "agent-install.json").read_text(encoding="utf-8"))
        profile = str(manifest.get("tool_profile") or profile)
    except (OSError, ValueError, TypeError):
        pass

    global_client = next((item for item in clients
                          if item.get("platform") == "codex"
                          and item.get("configuration_scope") == "global"), None)
    global_entry = None
    if global_client:
        global_entry = next((entry for entry in _global_codex_entries(root, status.get("project_id"))
                             if entry.get("alias") == global_client.get("alias")
                             and entry.get("configuration") == global_client.get("configuration")), None)
        if not global_entry:
            return {"ok": False, "error": "La entrada global de Codex ya no apunta a este proyecto."}
        server = global_entry["server"]
        command = str(server.get("command") or "")
        args = [str(value) for value in server.get("args", [])]
        configured_env = server.get("env") or {}
        if not isinstance(configured_env, dict):
            return {"ok": False, "error": "La variable env de la entrada Codex no es una tabla TOML."}
        server_env = {str(key): str(value) for key, value in configured_env.items()}
        cwd = server.get("cwd")
        cwd = str(cwd) if isinstance(cwd, str) and cwd.strip() and cwd.strip() != "-" else None
        profile = next((args[index + 1] for index, value in enumerate(args[:-1])
                        if value == "--tool-profile"), profile)
        verification_source = {"alias": global_entry["alias"],
                               "configuration": global_entry["configuration"],
                               "configuration_scope": "global"}
    else:
        command = "graphtyn"
        args = ["mcp", "--tool-profile", profile, "--path", "."]
        server_env = None
        cwd = str(root)
        verification_source = {}
    if not shutil.which(command):
        return {"ok": False, "error": f"No se encuentra el comando MCP configurado: {command}"}

    async def handshake() -> dict[str, Any]:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        parameters = StdioServerParameters(command=command, cwd=cwd, args=args, env=server_env)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                tools = await client.list_tools()
        names = sorted(str(item.name) for item in tools.tools)
        if "memory_context" not in names:
            raise RuntimeError("El servidor respondió, pero no expone memory_context en el perfil configurado")
        server_info = getattr(initialized, "server_info", None)
        return {"ok": True, "server": getattr(server_info, "name", "Graphtyn"),
                "tool_count": len(names), "tools": names, **verification_source}

    try:
        result = asyncio.run(asyncio.wait_for(handshake(), timeout=20))
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
    manifest_path = root / ".graphtyn" / "agent-install.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["mcp_verification"] = {**result, "project_id": status.get("project_id"),
                                        "mcp_server": status.get("mcp_server"),
                                        "tool_profile": profile, "verified_at": time.time()}
        _write_json(manifest_path, manifest)
    except (OSError, ValueError, TypeError):
        pass
    return result


def remove_project_integrations(project: str | Path, platforms: list[str]) -> dict[str, Any]:
    """Remove only MCP entries previously generated by Graphtyn for this project."""
    root = Path(project).expanduser().resolve()
    metadata = _read_metadata(root)
    project_id = str(metadata.get("project_id") or "")
    if not project_id:
        return {"ok": True, "removed": [], "preserved": [], "reason": "project identity is not registered"}
    manifest_path = root / ".graphtyn" / "agent-install.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        manifest = {}
    registered = {str(item.get("platform")): item for item in manifest.get("integrations", [])
                  if isinstance(item, dict)}
    removed, preserved = [], []
    for platform in dict.fromkeys(platforms):
        item = registered.get(platform, {})
        if item.get("status") != "configured":
            preserved.append(platform)
            continue
        path = root / SUPPORTED_CONFIGS.get(platform, "")
        try:
            if platform == "codex":
                current = path.read_text(encoding="utf-8") if path.exists() else ""
                marker = re.compile(
                    rf"(?ms)^# BEGIN GRAPHTYN MCP PROJECT {re.escape(project_id)}\n.*?^# END GRAPHTYN MCP PROJECT\n?"
                )
                updated, count = marker.subn("", current)
                if count:
                    path.write_text(updated.rstrip() + ("\n" if updated.strip() else ""), encoding="utf-8")
                    removed.append(platform)
                else:
                    preserved.append(platform)
                continue
            section = "mcp" if platform == "opencode" else "mcpServers"
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            servers = data.get(section) if isinstance(data, dict) else None
            alias = str(item.get("alias") or "")
            existing = servers.get(alias) if isinstance(servers, dict) else None
            args = existing.get("command", []) if platform == "opencode" and isinstance(existing, dict) else (
                existing.get("args", []) if isinstance(existing, dict) else [])
            command = existing.get("command") if isinstance(existing, dict) else None
            expected_args = ["mcp", "--tool-profile", manifest.get("tool_profile", "intent"),
                             "--path", "."]
            managed = (args == ["graphtyn", *expected_args] if platform == "opencode"
                       else command == "graphtyn" and args == expected_args)
            if managed:
                del servers[alias]
                if not servers:
                    data.pop(section, None)
                _write_json(path, data)
                removed.append(platform)
            else:
                preserved.append(platform)
        except (OSError, ValueError, TypeError):
            preserved.append(platform)
    for client in manifest.get("integrations", []):
        if client.get("platform") in removed:
            client["status"] = "removed"
            client["configuration_present"] = False
    if manifest:
        if removed:
            manifest.pop("mcp_verification", None)
        _write_json(manifest_path, manifest)
    return {"ok": True, "removed": removed, "preserved": preserved}
