"""OpenClaw discovery and versioned agent-brain routing registry.

The registry is local to Graphtyn. OpenClaw agent labels are presentation only;
all routing uses installation id plus the canonical OpenClaw agent id.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .history_import import (_same_project_path, configured_sources, delete_source, save_source,
                             sources_config_file)
from .ssh import ssh_command
from .storage import atomic_write_json, data_home


REGISTRY_VERSION = 1


def _family_store_path(root_path: str | Path, installation_id: str) -> str:
    root = Path(root_path)
    suffix = str(installation_id).removeprefix("openclaw-")[:8]
    return str(root.parent / f"{root.name}-{suffix}-shared")


def registry_path() -> Path:
    return data_home() / "openclaw-installations.json"


def _read_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or registry_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": REGISTRY_VERSION, "installations": []}
    if not isinstance(value, dict) or not isinstance(value.get("installations", []), list):
        raise ValueError("registro OpenClaw inválido")
    return value


def list_installations(path: Path | None = None) -> list[dict[str, Any]]:
    return _read_registry(path).get("installations", [])


def get_installation(installation_id: str, path: Path | None = None) -> dict[str, Any]:
    item = next((row for row in list_installations(path)
                 if row.get("id") == str(installation_id)), None)
    if item is None:
        raise KeyError(f"instalación OpenClaw desconocida: {installation_id}")
    return item


def installation_for_agent(agent_id: str, *, registry: Path | None = None) -> str:
    """Resolve a sole connected installation; refuse ambiguous agent IDs."""
    canonical = _canonical_agent_id(agent_id)
    matches = [installation["id"] for installation in list_installations(registry)
               if any(row.get("id") == canonical for row in installation.get("agents", []))]
    if not matches:
        raise KeyError(f"no hay instalación OpenClaw conectada para {canonical}")
    if len(matches) != 1:
        raise ValueError(f"{canonical} existe en varias instalaciones; indique installation_id")
    return matches[0]


def _canonical_agent_id(value: str) -> str:
    result = str(value or "").strip().casefold()
    if result.startswith("openclaw/"):
        result = result.split("/", 1)[1]
    if not result or len(result) > 128 or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for ch in result):
        raise ValueError(f"id de agente OpenClaw inválido: {value!r}")
    return result


def _agent_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    agents = config.get("agents") or {}
    entries = agents.get("entries") or agents.get("list") or []
    result: list[dict[str, Any]] = []
    if isinstance(entries, dict):
        iterable = []
        for key, raw in entries.items():
            item = dict(raw) if isinstance(raw, dict) else {}
            item.setdefault("id", key)
            iterable.append(item)
    elif isinstance(entries, list):
        iterable = entries
    else:
        iterable = []
    for raw in iterable:
        if not isinstance(raw, dict):
            continue
        agent_id = _canonical_agent_id(raw.get("id") or raw.get("name") or "")
        identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
        display = str(identity.get("name") or raw.get("name") or agent_id).strip()[:200]
        parent = raw.get("parentAgent") or raw.get("parent_id")
        result.append({"id": agent_id, "agent_id": f"openclaw/{agent_id}",
                       "display_name": display,
                       "workspace": str(raw.get("workspace") or "").strip() or None,
                       "parent_id": _canonical_agent_id(parent) if parent else None,
                       "relation_status": "proposed" if parent else ("root" if agent_id == "main" else "pending"),
                       "relation_evidence": "openclaw.json" if parent else None})
    if not any(row["id"] == "main" for row in result):
        result.append({"id": "main", "agent_id": "openclaw/main", "display_name": "main",
                       "workspace": None, "parent_id": None, "relation_status": "root",
                       "relation_evidence": "OpenClaw primary agent"})
    return sorted({row["id"]: row for row in result}.values(), key=lambda row: row["id"])


def _read_config(config_path: str, *, ssh_target: str | None = None) -> dict[str, Any]:
    if ssh_target:
        if not re.fullmatch(r"[A-Za-z0-9_.@-]+", ssh_target):
            raise ValueError("destino SSH inválido")
        command = f"cat -- {shlex.quote(config_path)}"
        completed = subprocess.run([*ssh_command(ssh_target), command], capture_output=True,
                                   text=True, timeout=15)
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip()[-500:] or "No se pudo leer openclaw.json por SSH")
        payload = completed.stdout
    else:
        payload = Path(config_path).expanduser().read_text(encoding="utf-8")
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("openclaw.json no contiene un objeto JSON")
    return result


def _source_root_from_path(value: str) -> tuple[str | None, str] | None:
    parsed = urlparse(value)
    if parsed.scheme == "ssh":
        parts = Path(parsed.path).parts
        if "agents" not in parts:
            return None
        ix = parts.index("agents")
        if ix + 1 >= len(parts):
            return None
        data_root = str(Path(*parts[:ix]))
        return parsed.netloc, data_root
    candidate = Path(value).expanduser()
    if candidate.name != "agents" and candidate.parent.name != "agents":
        return None
    agent_root = candidate.parent if candidate.parent.name == "agents" else candidate
    return None, str(agent_root.parent)


def discover_openclaw(config_path: str | None = None, *, ssh_target: str | None = None,
                      data_root: str | None = None) -> list[dict[str, Any]]:
    """Find local configs and installations already referenced by registered sources.

    Remote discovery is limited to explicitly configured SSH sources. It never
    scans a network or attempts to find arbitrary SSH hosts.
    """
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    configured = os.environ.get("OPENCLAW_CONFIG_PATH")
    local_paths = [config_path, configured,
                   str(Path.home() / ".openclaw" / "openclaw.json"),
                   str(Path.cwd() / "data" / "openclaw.json")]
    for raw in local_paths:
        if not raw:
            continue
        target = Path(raw).expanduser()
        if target.is_file():
            candidates[("local", str(target.resolve()))] = {
                "kind": "local", "target": "local", "config_path": str(target.resolve()),
                "data_root": str(target.resolve().parent)}
    if ssh_target is None and data_root is None:
        ssh_target = os.environ.get("GRAPHTYN_OPENCLAW_SSH_TARGET") or None
        data_root = os.environ.get("GRAPHTYN_OPENCLAW_DATA_ROOT") or None
        if bool(ssh_target) != bool(data_root):
            raise ValueError("GRAPHTYN_OPENCLAW_SSH_TARGET y GRAPHTYN_OPENCLAW_DATA_ROOT deben configurarse juntos")
    if ssh_target:
        if not data_root or not data_root.startswith("/") or ".." in Path(data_root).parts:
            raise ValueError("el destino SSH requiere --data-root absoluto y sin segmentos '..'")
        candidates[("ssh", f"{ssh_target}:{data_root}")] = {
            "kind": "ssh", "target": ssh_target,
            "config_path": f"{data_root.rstrip('/')}/openclaw.json",
            "data_root": data_root.rstrip("/")}
    for source in configured_sources():
        if source.get("provider") != "openclaw":
            continue
        found = _source_root_from_path(str(source.get("source") or ""))
        if not found:
            continue
        ssh_target, data_root = found
        if ssh_target:
            config = str(Path(data_root) / "openclaw.json")
            candidates[("ssh", f"{ssh_target}:{data_root}")] = {
                "kind": "ssh", "target": ssh_target, "config_path": config,
                "data_root": data_root}
        else:
            config = str(Path(data_root) / "openclaw.json")
            if Path(config).is_file():
                candidates[("local", config)] = {"kind": "local", "target": "local",
                    "config_path": config, "data_root": data_root}
    detected = []
    for candidate in candidates.values():
        try:
            config = _read_config(candidate["config_path"],
                                  ssh_target=candidate["target"] if candidate["kind"] == "ssh" else None)
            agents = _agent_entries(config)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            detected.append({**candidate, "ok": False, "error": str(exc), "agents": []})
            continue
        digest = hashlib.sha256(f"{candidate['kind']}|{candidate['target']}|{candidate['data_root']}".encode()).hexdigest()[:16]
        installation_id = f"openclaw-{digest}"
        registered = next((row for row in list_installations()
                           if row.get("id") == installation_id), None)
        registered_agents = {str(row.get("id")): row for row in
                             (registered or {}).get("agents", []) if isinstance(row, dict)}
        effective_agents = []
        for observed in agents:
            row = dict(observed)
            row["config_parent_id"] = observed.get("parent_id")
            row["config_relation_status"] = observed.get("relation_status")
            saved = registered_agents.get(observed["id"])
            if saved:
                row["parent_id"] = saved.get("parent_id")
                row["relation_status"] = saved.get("relation_status", observed.get("relation_status"))
                row["relation_evidence"] = saved.get("relation_evidence") or observed.get("relation_evidence")
                row["relation_source"] = "graphtyn_registry"
                row["relation_discrepancy"] = (
                    observed.get("parent_id") != saved.get("parent_id")
                    if observed.get("parent_id") or saved.get("parent_id") else False)
            else:
                row["relation_source"] = "openclaw_config"
                row["relation_discrepancy"] = False
            effective_agents.append(row)
        detected.append({**candidate, "id": installation_id, "ok": True,
                         "version": str(config.get("meta", {}).get("lastTouchedVersion") or "unknown"),
                         "registry_status": "connected" if registered else "not_connected",
                         "agents": effective_agents})
    return sorted(detected, key=lambda item: item.get("id", item.get("config_path", "")))


def configure_openclaw_mcp(discovered: dict[str, Any], *, mcp_url: str | None = None,
                           mcp_token: str | None = None) -> dict[str, Any]:
    """Set the Graphtyn MCP entry, backing up the OpenClaw config before edits.

    With no endpoint override, an existing valid entry is preserved. Secrets are
    read from the current config or environment and are never returned.
    """
    config = _read_config(discovered["config_path"],
                          ssh_target=discovered["target"] if discovered["kind"] == "ssh" else None)
    mcp = config.get("mcp") if isinstance(config.get("mcp"), dict) else {}
    servers = mcp.get("servers") if isinstance(mcp.get("servers"), dict) else {}
    existing = servers.get("graphtyn") if isinstance(servers.get("graphtyn"), dict) else {}
    url = str(mcp_url or os.environ.get("GRAPHTYN_MCP_URL") or existing.get("url") or "").strip()
    headers = existing.get("headers") if isinstance(existing.get("headers"), dict) else {}
    authorization = str(headers.get("Authorization") or headers.get("authorization") or "")
    existing_token = authorization[7:] if authorization.casefold().startswith("bearer ") else ""
    token = str(mcp_token or os.environ.get("GRAPHTYN_MCP_TOKEN") or existing_token).strip()
    if not url:
        return {"ok": False, "configured": False,
                "reason": "falta GRAPHTYN_MCP_URL o una entrada mcp.servers.graphtyn existente"}
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or not parsed_url.path.rstrip("/").endswith("/mcp"):
        raise ValueError("GRAPHTYN_MCP_URL debe ser una URL HTTP(S) que termine en /mcp")
    if not token:
        return {"ok": False, "configured": False,
                "reason": "falta GRAPHTYN_MCP_TOKEN para autenticar el servidor MCP"}
    if str(existing.get("url") or "") == url and existing_token == token:
        return {"ok": True, "configured": True, "changed": False, "url": url}
    replacement = json.loads(json.dumps(config))
    if not isinstance(replacement.get("mcp"), dict): replacement["mcp"] = {}
    if not isinstance(replacement["mcp"].get("servers"), dict): replacement["mcp"]["servers"] = {}
    replacement["mcp"]["servers"]["graphtyn"] = {
        **existing, "url": url, "headers": {**headers, "Authorization": f"Bearer {token}"}}
    payload = json.dumps(replacement, ensure_ascii=False, indent=2) + "\n"
    config_path = str(discovered["config_path"])
    backup = f"{config_path}.graphtyn-backup-{time.time_ns()}"
    if discovered["kind"] == "ssh":
        script = (
            "import json,os,shutil,sys,tempfile; "
            "from pathlib import Path; "
            "p=Path(sys.argv[1]); data=sys.stdin.read(); p.parent.mkdir(parents=True,exist_ok=True); "
            "shutil.copy2(p,sys.argv[2]); "
            "fd,t=tempfile.mkstemp(prefix='.'+p.name+'.',suffix='.tmp',dir=str(p.parent)); "
            "os.fchmod(fd,os.stat(sys.argv[2]).st_mode & 0o777); "
            "f=os.fdopen(fd,'w',encoding='utf-8'); f.write(json.dumps(json.loads(data),ensure_ascii=False,indent=2)+'\\n'); f.flush(); os.fsync(f.fileno()); f.close(); os.replace(t,p)"
        )
        command = "python3 -c " + shlex.quote(script) + " " + shlex.quote(config_path) + " " + shlex.quote(backup)
        completed = subprocess.run([*ssh_command(discovered["target"]), command],
                                   input=payload, capture_output=True,
                                   text=True, timeout=20)
        if completed.returncode:
            return {"ok": False, "configured": False,
                    "reason": (completed.stderr or completed.stdout).strip()[-500:] or "falló la actualización remota"}
    else:
        target = Path(config_path)
        mode = target.stat().st_mode & 0o777
        shutil.copy2(target, backup)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, target)
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
    return {"ok": True, "configured": True, "changed": True,
            "url": url, "backup": backup}


def _registered_path(agent_id: str, source_config: Path | None = None) -> str | None:
    """Return an existing brain path only when its OpenClaw sources are exclusive.

    Older registrations often placed every OpenClaw source under one display
    brain (for example Evi). Reusing that path for a newly discovered agent
    would silently revive the cross-agent mixing this registry is meant to
    prevent, even when the source row for that agent appears unambiguous alone.
    """
    canonical = f"openclaw/{agent_id}"
    rows = [row for row in configured_sources(source_config)
            if row.get("provider") == "openclaw" and row.get("project_path")]
    candidates = {str(row["project_path"]) for row in rows
                  if str(row.get("agent_id") or "").casefold() == canonical}
    if len(candidates) != 1:
        return None
    candidate = next(iter(candidates))
    owners = {str(row.get("agent_id") or "").casefold() for row in rows
              if _same_project_path(row.get("project_path"), candidate)}
    if owners != {canonical}:
        return None

    # The project registry is a second ownership signal. If it lists other
    # agents, treat the path as a legacy shared brain even if its source list
    # was partially rewritten already.
    registry_file = data_home() / "registered_projects.json"
    try:
        projects = json.loads(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        projects = []
    for project in projects if isinstance(projects, list) else []:
        if not isinstance(project, dict) or not project.get("path"):
            continue
        if not _same_project_path(project["path"], candidate):
            continue
        listed = {str(value).casefold() for value in project.get("agent_ids", []) if value}
        if listed and listed != {canonical}:
            return None
    return candidate


def _path_is_exclusive_to_agent(raw_path: str, agent_id: str,
                                source_config: Path | None = None) -> bool:
    canonical = f"openclaw/{agent_id}"
    rows = [row for row in configured_sources(source_config)
            if row.get("provider") == "openclaw" and row.get("project_path") and
            _same_project_path(row.get("project_path"), raw_path)]
    if rows and {str(row.get("agent_id") or "").casefold() for row in rows} != {canonical}:
        return False
    registry_file = data_home() / "registered_projects.json"
    try:
        projects = json.loads(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        projects = []
    for project in projects if isinstance(projects, list) else []:
        if not isinstance(project, dict) or not project.get("path") or not _same_project_path(project["path"], raw_path):
            continue
        listed = {str(value).casefold() for value in project.get("agent_ids", []) if value}
        if listed and listed != {canonical}:
            return False
    return bool(rows) or any(isinstance(project, dict) and project.get("path") and
        _same_project_path(project["path"], raw_path) and
        {str(value).casefold() for value in project.get("agent_ids", []) if value} == {canonical}
        for project in projects if isinstance(projects, list))


def connect_openclaw(discovered: dict[str, Any], *, parents: dict[str, str] | None = None,
                     independent: set[str] | None = None,
                     brain_paths: dict[str, str] | None = None,
                     import_history: bool = False,
                     registry: Path | None = None, source_config: Path | None = None) -> dict[str, Any]:
    """Register an installation and isolated agent stores; historical import is separate."""
    if not discovered.get("ok") or not discovered.get("id"):
        raise ValueError("se requiere una instalación OpenClaw detectada y accesible")
    parents = {_canonical_agent_id(k): _canonical_agent_id(v) for k, v in (parents or {}).items()}
    independent = {_canonical_agent_id(value) for value in (independent or set())}
    explicit_paths = {_canonical_agent_id(k): str(Path(v).expanduser().resolve())
                      for k, v in (brain_paths or {}).items()}
    items = _read_registry(registry)
    prior = next((row for row in items["installations"] if row.get("id") == discovered["id"]), None)
    prior_agents = {row["id"]: row for row in (prior or {}).get("agents", [])}
    agent_specs = discovered.get("agents") or []
    by_id = {str(row["id"]): row for row in agent_specs}
    for child, parent in parents.items():
        if child not in by_id or parent not in by_id or child == parent:
            raise ValueError(f"relación de agente inválida: {child} -> {parent}")
    if independent - set(by_id):
        raise ValueError("un agente independiente indicado no pertenece a esta instalación")
    if independent & set(parents):
        raise ValueError("un agente no puede ser independiente y tener padre a la vez")
    confirmed_parent = dict(parents)
    for agent_id, old in prior_agents.items():
        if agent_id not in confirmed_parent and old.get("relation_status") == "confirmed" and old.get("parent_id"):
            confirmed_parent[agent_id] = _canonical_agent_id(old["parent_id"])
    root_ids = {agent_id for agent_id, row in by_id.items()
                if not confirmed_parent.get(agent_id) and not row.get("parent_id") and
                (agent_id == "main" or agent_id in independent or
                 prior_agents.get(agent_id, {}).get("relation_status") == "root" or
                 row.get("relation_status") == "root")}
    root_paths: dict[str, str] = {}
    assigned_paths: set[str] = set()
    order = sorted(root_ids, key=lambda value: (0 if value == "main" else 1 if value == "career" else 2, value))
    for agent_id in order:
        old = prior_agents.get(agent_id, {})
        previous_path = old.get("brain_path")
        reusable_previous = (previous_path if previous_path and
                             _path_is_exclusive_to_agent(previous_path, agent_id,
                                 source_config if isinstance(source_config, Path) else None) else None)
        inferred_path = _registered_path(agent_id,
            source_config if isinstance(source_config, Path) else None)
        path = explicit_paths.get(agent_id) or reusable_previous or (inferred_path if inferred_path and
                                   str(Path(inferred_path).expanduser().resolve()) not in assigned_paths else None)
        if path and str(Path(path).expanduser().resolve()) in assigned_paths:
            raise ValueError(f"dos cerebros raíz no pueden compartir almacén: {agent_id}")
        if not path:
            path = str(data_home() / "brains" / discovered["id"] / agent_id)
        root_paths[agent_id] = str(Path(path).expanduser().resolve())
        assigned_paths.add(root_paths[agent_id])
    # Only relationships passed explicitly by the operator are confirmed.
    # A parent field in an OpenClaw config is shown as a proposal until reviewed.
    root_for: dict[str, str] = {}
    def find_root(agent_id: str, visiting: set[str] | None = None) -> str | None:
        if agent_id in root_paths:
            return agent_id
        visiting = set() if visiting is None else visiting
        if agent_id in visiting:
            raise ValueError("la jerarquía no puede contener ciclos")
        visiting.add(agent_id)
        parent_id = confirmed_parent.get(agent_id)
        result = find_root(parent_id, visiting) if parent_id else None
        visiting.remove(agent_id)
        return result

    for agent_id in by_id:
        root = find_root(agent_id)
        if root:
            root_for[agent_id] = root
    for child in confirmed_parent:
        if child in by_id and child not in root_for:
            raise ValueError(f"la relación confirmada de {child} termina en un cerebro pendiente; "
                             "confirme el padre como independiente o asígnele un padre confirmado")

    normalized: dict[str, dict[str, Any]] = {}
    # Parent-first order supports grandchildren while keeping every private
    # brain physically separate from its family publication store.
    pending = set(by_id)
    ordered: list[str] = []
    while pending:
        ready = sorted(agent_id for agent_id in pending
                       if not confirmed_parent.get(agent_id) or
                       confirmed_parent[agent_id] in ordered)
        if not ready:
            raise ValueError("la jerarquía de agentes contiene una referencia inválida o un ciclo")
        ordered.extend(ready)
        pending.difference_update(ready)

    for agent_id in ordered:
        spec = by_id[agent_id]
        old = prior_agents.get(agent_id, {})
        if agent_id in root_paths:
            brain_path = root_paths[agent_id]
            status = "root"
        elif agent_id in confirmed_parent:
            root_id = root_for[agent_id]
            parent_id = confirmed_parent[agent_id]
            root_path = Path(root_paths[root_id])
            previous_path = old.get("brain_path")
            reusable_previous = (previous_path if previous_path and
                                 _path_is_exclusive_to_agent(previous_path, agent_id,
                                     source_config if isinstance(source_config, Path) else None) else None)
            brain_path = explicit_paths.get(agent_id) or reusable_previous or str(
                root_path.parent / f"{root_path.name}-{discovered['id'].removeprefix('openclaw-')[:8]}-{agent_id}")
            status = "confirmed"
        else:
            parent_id = spec.get("parent_id")
            previous_path = old.get("brain_path")
            reusable_previous = (previous_path if previous_path and
                                 _path_is_exclusive_to_agent(previous_path, agent_id,
                                     source_config if isinstance(source_config, Path) else None) else None)
            inferred_path = _registered_path(agent_id,
                source_config if isinstance(source_config, Path) else None)
            brain_path = explicit_paths.get(agent_id) or reusable_previous or (
                inferred_path if inferred_path and str(Path(inferred_path).expanduser().resolve()) not in assigned_paths else None) or str(
                    data_home() / "brains" / discovered["id"] / agent_id)
            status = "proposed" if parent_id else "pending"
        normalized_path = str(Path(brain_path).expanduser().resolve())
        if normalized_path in assigned_paths and not (
                agent_id in root_paths and normalized_path == root_paths[agent_id]):
            if agent_id in explicit_paths:
                raise ValueError(f"dos agentes no pueden compartir cerebro: {agent_id}")
            brain_path = str(data_home() / "brains" / discovered["id"] / agent_id)
            normalized_path = str(Path(brain_path).expanduser().resolve())
            if normalized_path in assigned_paths:
                raise ValueError(f"ruta de cerebro duplicada: {agent_id}")
        assigned_paths.add(normalized_path)
        if agent_id in root_ids and agent_id != "main":
            root_evidence = "user-confirmed independent"
        elif agent_id == "main":
            root_evidence = "OpenClaw primary agent"
        else:
            root_evidence = "user-confirmed"
        row = {**spec, "brain_path": str(Path(brain_path).expanduser().resolve()),
               "parent_id": confirmed_parent.get(agent_id) or spec.get("parent_id"),
               # Memory capture is opt-out per installation/agent. Existing
               # local choices survive rediscovery; other installations keep
               # the default enabled behavior, including an agent named main.
               "memory_enabled": bool(old.get("memory_enabled", True)),
               "relation_status": status,
               "relation_evidence": (root_evidence if status in {"root", "confirmed"} else
                                     spec.get("relation_evidence") or old.get("relation_evidence"))}
        family_root = root_for.get(agent_id)
        if family_root and (agent_id == family_root or status == "confirmed"):
            root_path = Path(root_paths[family_root])
            row["family_id"] = f"{discovered['id']}:{family_root}"
            row["family_path"] = _family_store_path(root_path, discovered["id"])
        elif status == "root":
            row["family_id"] = f"{discovered['id']}:{agent_id}"
            row["family_path"] = _family_store_path(row["brain_path"], discovered["id"])
        normalized[agent_id] = row
    installation = {key: discovered[key] for key in ("id", "kind", "target", "config_path", "data_root", "version") if key in discovered}
    installation.update({"provider": "openclaw", "schema_version": REGISTRY_VERSION,
                         "agents": list(normalized.values()), "status": "configured",
                         "relationship_events": list((prior or {}).get("relationship_events", [])),
                         "memory_policy_events": list((prior or {}).get("memory_policy_events", []))})
    existing_events = {(event.get("agent_id"), event.get("parent_id"), event.get("relation_status"))
                       for event in installation["relationship_events"] if isinstance(event, dict)}
    for agent in installation["agents"]:
        if agent["id"] not in parents and agent["id"] not in independent:
            continue
        event_key = (agent["agent_id"], agent.get("parent_id"), agent.get("relation_status"))
        if event_key in existing_events:
            continue
        installation["relationship_events"].append({
            "event_id": f"rel-{time.time_ns()}", "agent_id": agent["agent_id"],
            "previous_parent_id": prior_agents.get(agent["id"], {}).get("parent_id"),
            "previous_status": prior_agents.get(agent["id"], {}).get("relation_status"),
            "parent_id": agent.get("parent_id"), "relation_status": agent.get("relation_status"),
            "evidence": "user-confirmed", "changed_at": time.time()})
        existing_events.add(event_key)
    installation["relationship_events"] = installation["relationship_events"][-500:]
    installations = [row for row in items["installations"] if row.get("id") != discovered["id"]]
    installations.append(installation)
    target_registry = registry or registry_path()
    atomic_write_json(target_registry, {"version": REGISTRY_VERSION,
                                        "installations": sorted(installations, key=lambda row: row["id"])})
    try:
        target_registry.chmod(0o600)
    except OSError:
        pass
    if source_config is not False:
        source_file = source_config if isinstance(source_config, Path) else sources_config_file()
        previous_sources = configured_sources(source_file)
        for agent in installation["agents"]:
            canonical = agent["agent_id"]
            raw_source = _source_for_agent(discovered, agent["id"])
            if raw_source:
                if not agent.get("memory_enabled", True):
                    delete_source("openclaw", raw_source, path=source_file)
                else:
                    previous = next((row for row in previous_sources
                                     if row.get("provider") == "openclaw" and
                                     row.get("source") == raw_source), None)
                    baseline = (0 if import_history else
                                float(previous["capture_from"]) if previous and
                                isinstance(previous.get("capture_from"), (int, float)) else time.time())
                    save_source("openclaw", raw_source, label=f"OpenClaw · {agent['display_name']}",
                                project_path=agent["brain_path"], agent_id=canonical,
                                capture_from=baseline, path=source_file)
            _register_brain_path(agent["brain_path"], canonical, name=agent["display_name"])
            _register_agent_identity(agent, installation["id"])
        for agent in installation["agents"]:
            family = agent.get("family_path")
            if family and agent["relation_status"] in {"root", "confirmed"}:
                members = [row["agent_id"] for row in installation["agents"]
                           if row.get("family_id") == agent.get("family_id")]
                root_id = str(agent.get("family_id") or "").split(":", 1)[-1]
                family_root = next((row for row in installation["agents"] if row["id"] == root_id), agent)
                _register_brain_path(family, *members, name=f"Familia · {family_root['display_name']}")
    return installation


def _source_for_agent(discovered: dict[str, Any], agent_id: str) -> str | None:
    data_root = str(discovered["data_root"]).rstrip("/")
    candidate = f"{data_root}/agents/{agent_id}"
    if discovered["kind"] == "ssh":
        return f"ssh://{discovered['target']}{candidate}"
    return candidate if Path(candidate).exists() else None


def _register_brain_path(raw_path: str, *agent_ids: str, name: str | None = None) -> None:
    from .shared_memory import SharedMemoryStore
    # Use the same central store resolver as the persistent watcher. Without
    # this, a one-off CLI connect could create workspace-local SQLite files
    # beside the central stores opened later by systemd.
    os.environ.setdefault("GRAPHTYN_HOME", str(data_home()))
    root = Path(raw_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    owners = sorted({str(value).casefold() for value in agent_ids if value})
    SharedMemoryStore(root)
    target = data_home() / "registered_projects.json"
    try:
        rows = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    if not isinstance(rows, list):
        raise ValueError("registered_projects.json inválido")
    item = next((row for row in rows if isinstance(row, dict) and
                 str(Path(str(row.get("path") or "")).expanduser().resolve()) == str(root)), None)
    if item is None:
        rows.append({"id": root.name, "name": name or root.name, "path": str(root),
                     "mode": "single_folder", "space_type": "agent_brain", "agent_ids": owners})
    else:
        item.update({"space_type": "agent_brain", "agent_ids": owners})
        if name:
            item["name"] = name
    atomic_write_json(target, rows)


def _register_agent_identity(agent: dict[str, Any], installation_id: str) -> None:
    """Expose the canonical OpenClaw id and its display label to dashboard/API clients."""
    target = data_home() / "registered_agents.json"
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        rows = payload.get("agents", []) if isinstance(payload, dict) else payload
    except (OSError, ValueError, TypeError):
        payload, rows = {"version": 1}, []
    if not isinstance(rows, list):
        raise ValueError("registered_agents.json inválido")
    canonical = str(agent["agent_id"]).casefold()
    entry = next((row for row in rows if isinstance(row, dict) and
                  str(row.get("id") or "").casefold() == canonical), None)
    if entry is None:
        entry = {"id": canonical, "paths": []}
        rows.append(entry)
    entry.update({"id": canonical, "name": str(agent.get("display_name") or canonical),
                  "provider": "openclaw"})
    paths = list(entry.get("paths") or [])
    brain_path = str(Path(agent["brain_path"]).expanduser().resolve())
    if brain_path not in paths:
        paths.append(brain_path)
    entry["paths"] = paths
    if isinstance(payload, dict):
        payload["version"] = payload.get("version", 1)
        payload["agents"] = rows
        payload.setdefault("openclaw_installations", {})[installation_id] = {
            **payload.get("openclaw_installations", {}).get(installation_id, {}),
            canonical: brain_path}
    else:
        payload = {"version": 1, "agents": rows,
                   "openclaw_installations": {installation_id: {canonical: brain_path}}}
    atomic_write_json(target, payload)


def resolve_agent(installation_id: str, agent_id: str, *, registry: Path | None = None) -> dict[str, Any]:
    agent_id = _canonical_agent_id(agent_id)
    installation = get_installation(installation_id, registry)
    agent = next((row for row in installation.get("agents", []) if row.get("id") == agent_id), None)
    if not agent:
        raise KeyError(f"agente OpenClaw no registrado: {agent_id}")
    family = [row for row in installation["agents"]
              if row.get("family_id") and row.get("family_id") == agent.get("family_id")]
    return {"installation_id": installation_id, "provider": "openclaw",
            "agent_id": agent["agent_id"], "display_name": agent.get("display_name"),
            "brain_path": agent["brain_path"], "relation_status": agent["relation_status"],
            "memory_enabled": bool(agent.get("memory_enabled", True)),
            "parent_id": agent.get("parent_id"), "family_id": agent.get("family_id"),
            "family_path": agent.get("family_path") if agent.get("relation_status") in {"root", "confirmed"} else None,
            "family_agent_ids": sorted(row["agent_id"] for row in family),
            "sources_pending_review": agent.get("relation_status") == "pending"}


def set_parent(installation_id: str, child_id: str, parent_id: str | None,
               *, confirm: bool, registry: Path | None = None) -> dict[str, Any]:
    """Set a permanent relation only with explicit confirmation."""
    if not confirm:
        raise ValueError("la relación permanente requiere confirm=True")
    target = registry or registry_path()
    items = _read_registry(target)
    installation = next((row for row in items["installations"] if row.get("id") == installation_id), None)
    if not installation:
        raise KeyError(installation_id)
    agents = {row["id"]: row for row in installation["agents"]}
    child = _canonical_agent_id(child_id)
    parent = _canonical_agent_id(parent_id) if parent_id else None
    if child not in agents or parent and parent not in agents or child == parent:
        raise ValueError("agente padre/hijo no pertenece a esta instalación")
    if parent and agents[parent].get("relation_status") not in {"root", "confirmed"}:
        raise ValueError("confirme primero que el padre es raíz o pertenece a una familia confirmada")
    cursor = parent
    while cursor:
        if cursor == child:
            raise ValueError("la jerarquía no puede contener ciclos")
        cursor = agents.get(cursor, {}).get("parent_id")
    row = agents[child]
    previous_parent = row.get("parent_id")
    previous_status = row.get("relation_status")
    row["parent_id"] = parent
    row["relation_status"] = "confirmed" if parent else "root"
    row["relation_evidence"] = "user-confirmed"
    # Recompute the whole tree so moving a root or an intermediate subagent
    # cannot leave descendants attached to stale family metadata.
    def root_of(agent_id: str, seen: set[str] | None = None) -> str | None:
        seen = set() if seen is None else seen
        if agent_id in seen:
            raise ValueError("la jerarquía no puede contener ciclos")
        seen.add(agent_id)
        current_parent = agents[agent_id].get("parent_id")
        return root_of(current_parent, seen) if current_parent else agent_id

    roots = {key: root_of(key) for key in agents}
    installation_row = next(item for item in items["installations"] if item.get("id") == installation_id)
    for agent_id, agent in agents.items():
        family_root = roots[agent_id]
        root = agents[family_root]
        if agent_id == family_root or agent.get("relation_status") == "confirmed":
            family_id = f"{installation_id}:{family_root}"
            family_path = root.get("family_path") or _family_store_path(
                root["brain_path"], installation_id)
            agent["family_id"] = family_id
            agent["family_path"] = family_path
        else:
            agent.pop("family_id", None)
            agent.pop("family_path", None)
    for root_id in set(roots.values()):
        family_id = f"{installation_id}:{root_id}"
        family_path = agents[root_id].get("family_path")
        if family_path:
            _register_brain_path(family_path, *(agent["agent_id"] for agent in agents.values()
                                                if agent.get("family_id") == family_id),
                                 name=f"Familia · {root.get('display_name') or family_root}")
    installation_row.setdefault("relationship_events", []).append({
        "event_id": f"rel-{time.time_ns()}", "agent_id": row["agent_id"],
        "previous_parent_id": previous_parent, "previous_status": previous_status,
        "parent_id": parent, "relation_status": row["relation_status"],
        "evidence": "user-confirmed", "changed_at": time.time()})
    installation_row["relationship_events"] = installation_row["relationship_events"][-500:]
    atomic_write_json(target, items)
    return resolve_agent(installation_id, child, registry=target)


def paths_for_installation(installation_id: str, *, registry: Path | None = None) -> list[str]:
    installation = get_installation(installation_id, registry)
    return sorted({row["brain_path"] for row in installation["agents"]
                   if row.get("memory_enabled", True)})


def set_agent_memory_enabled(installation_id: str, agent_id: str, enabled: bool, *,
                             reason: str = "operator policy", registry: Path | None = None,
                             source_config: Path | None = None) -> dict[str, Any]:
    """Set a per-installation memory policy and align its transcript source.

    Disabling memory removes only this agent's configured OpenClaw source. The
    OpenClaw identity and its private brain remain registered. Re-enabling
    starts at the current time so old transcripts are not imported implicitly.
    """
    if not isinstance(enabled, bool):
        raise ValueError("enabled debe ser booleano")
    canonical = _canonical_agent_id(agent_id)
    target_registry = registry or registry_path()
    payload = _read_registry(target_registry)
    installation = next((row for row in payload["installations"]
                         if row.get("id") == str(installation_id)), None)
    if installation is None:
        raise KeyError(f"instalación OpenClaw desconocida: {installation_id}")
    agent = next((row for row in installation.get("agents", []) if row.get("id") == canonical), None)
    if agent is None:
        raise KeyError(f"agente OpenClaw no registrado: {canonical}")
    previous = bool(agent.get("memory_enabled", True))
    changed = previous != enabled
    event = None
    if changed:
        agent["memory_enabled"] = enabled
        event = {"event_id": f"mem-{time.time_ns()}", "agent_id": agent["agent_id"],
                 "previous_enabled": previous, "memory_enabled": enabled,
                 "reason": str(reason or "operator policy")[:500], "changed_at": time.time()}
        events = installation.setdefault("memory_policy_events", [])
        events.append(event)
        installation["memory_policy_events"] = events[-500:]
        atomic_write_json(target_registry, payload)
        try:
            target_registry.chmod(0o600)
        except OSError:
            pass

    source_file = source_config or sources_config_file()
    raw_source = _source_for_agent(installation, canonical)
    source_changed = False
    if enabled:
        has_source = any(row.get("provider") == "openclaw" and row.get("source") == raw_source
                         for row in configured_sources(source_file)) if raw_source else False
        if raw_source and (changed or not has_source):
            save_source("openclaw", raw_source,
                        label=f"OpenClaw · {agent.get('display_name') or canonical}",
                        project_path=agent["brain_path"], agent_id=agent["agent_id"],
                        capture_from=time.time(), path=source_file)
            source_changed = True
    else:
        configured = configured_sources(source_file)
        matching_sources = {row["source"] for row in configured
            if row.get("provider") == "openclaw" and
            row.get("agent_id") in {canonical, agent["agent_id"]} and
            _same_project_path(row.get("project_path") or "", agent["brain_path"])}
        if raw_source:
            matching_sources.add(raw_source)
        for source in matching_sources:
            source_changed = delete_source("openclaw", source, path=source_file) or source_changed
    return {"ok": True, "changed": changed, "installation_id": installation_id,
            "agent_id": agent["agent_id"], "memory_enabled": enabled,
            "source_changed": source_changed, "event": event}


def assert_agent_memory_enabled(workspace: str | Path, agent_id: str | None, *,
                                registry: Path | None = None) -> None:
    """Reject writes to an OpenClaw brain disabled in its installation policy.

    The policy belongs to the physical brain path, so a dashboard or other
    authorized writer cannot bypass it by using a different requester label.
    Other installations are unaffected because their brain paths differ.
    """
    try:
        target_path = str(Path(workspace).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return
    for installation in list_installations(registry):
        for agent in installation.get("agents", []):
            try:
                same_path = str(Path(agent.get("brain_path") or "").expanduser().resolve()) == target_path
            except (OSError, RuntimeError, ValueError):
                continue
            if same_path and not agent.get("memory_enabled", True):
                raise PermissionError(
                    f"la memoria de {agent.get('agent_id') or agent.get('id') or 'este agente'} está desactivada "
                    f"para la instalación {installation.get('id')}"
                )


def agent_context(installation_id: str, agent_id: str, query: str, *, token_budget: int = 1800,
                  registry: Path | None = None) -> dict[str, Any]:
    """Retrieve own memory plus explicitly published family memory."""
    from .shared_memory import SharedMemoryStore
    route = resolve_agent(installation_id, agent_id, registry=registry)
    if route["relation_status"] not in {"root", "confirmed", "independent"}:
        route["family_path"] = None
    own_budget = max(256, int(token_budget * (.7 if route.get("family_path") else 1)))
    own = SharedMemoryStore(Path(route["brain_path"])).context(
        query, requester_agent=route["agent_id"], token_budget=own_budget,
        agent_ids=[route["agent_id"]])
    shared = None
    if route.get("family_path"):
        shared_budget = max(256, token_budget - own_budget)
        shared = SharedMemoryStore(Path(route["family_path"])).context(
            query, requester_agent=route["agent_id"], token_budget=shared_budget,
            agent_ids=route["family_agent_ids"])
    memories = list(own.get("memories") or [])
    topics = list(own.get("topics") or [])
    if shared:
        memories.extend({**item, "memory_origin": "family_shared"} for item in shared.get("memories", []))
        topics.extend({**item, "memory_origin": "family_shared"} for item in shared.get("topics", []))
    memories.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    topics.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return {"ok": True, "installation_id": installation_id, "agent_id": route["agent_id"],
            "display_name": route["display_name"], "brain_path": route["brain_path"],
            "parent_id": route.get("parent_id"), "relation_status": route["relation_status"],
            "family_id": route.get("family_id"), "shared_path": route.get("family_path"),
            "memories": memories, "topics": topics,
            "coverage": {"own": own.get("coverage"), "family": shared.get("coverage") if shared else None},
            "estimated_tokens": int(own.get("estimated_tokens") or 0) +
                                int(shared.get("estimated_tokens") or 0) if shared else int(own.get("estimated_tokens") or 0),
            "token_budget": token_budget,
            "do_not_expand": bool(own.get("do_not_expand")) and
                             (not shared or bool(shared.get("do_not_expand")))}


def agent_status(installation_id: str, agent_id: str, *,
                 registry: Path | None = None) -> dict[str, Any]:
    from .shared_memory import SharedMemoryStore
    route = resolve_agent(installation_id, agent_id, registry=registry)
    own = SharedMemoryStore(Path(route["brain_path"])).status(agent_ids=[route["agent_id"]])
    shared = None
    if route.get("family_path") and route["relation_status"] in {"root", "confirmed"}:
        shared = SharedMemoryStore(Path(route["family_path"])).status(
            agent_ids=route["family_agent_ids"])
    return {"ok": True, **{key: route.get(key) for key in
            ("installation_id", "provider", "agent_id", "display_name", "brain_path",
             "relation_status", "memory_enabled", "parent_id", "family_id", "family_path",
             "family_agent_ids", "sources_pending_review")},
            "own": own, "family": shared}


def publish_agent_memory(installation_id: str, agent_id: str, memory_id: str, *,
                         registry: Path | None = None) -> dict[str, Any]:
    """Copy one owner-verified memory to the family's explicitly shared store."""
    from .shared_memory import SharedMemoryStore
    route = resolve_agent(installation_id, agent_id, registry=registry)
    if not route.get("memory_enabled", True):
        raise PermissionError(f"la memoria de {route['agent_id']} está desactivada para esta instalación")
    shared_path = route.get("family_path")
    if not shared_path or route.get("relation_status") not in {"root", "confirmed"}:
        raise PermissionError("este agente no pertenece a una familia confirmada")
    source = SharedMemoryStore(Path(route["brain_path"]))
    target = SharedMemoryStore(Path(shared_path))
    memory = source.get(memory_id, requester_agent=route["agent_id"])
    if not memory or memory.get("status") in {"deleted", "quarantined", "contested"}:
        raise ValueError("la memoria no existe o no se puede publicar")
    with target._connect() as db:
        existing = db.execute("SELECT id, metadata_json FROM memories WHERE agent_id=? AND scope='team'",
                              (route["agent_id"],)).fetchall()
    for row in existing:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if metadata.get("installation_id") == installation_id and \
                metadata.get("source_agent_id") == route["agent_id"] and \
                metadata.get("source_memory_id") == memory_id:
            return {"ok": True, "installation_id": installation_id,
                    "source_memory_id": memory_id, "shared_memory_id": row["id"],
                    "family_id": route["family_id"], "publisher": route["agent_id"],
                    "already_published": True}
    provenance = {"explicitly_published": True, "installation_id": installation_id,
                  "source_agent_id": route["agent_id"], "source_brain": route["brain_path"],
                  "source_memory_id": memory_id}
    session_id = f"publish:{installation_id}:{route['agent_id']}:{memory_id}"
    session = target.start_session(route["agent_id"],
        f"Publicación familiar: {memory.get('title') or memory_id}", client="openclaw",
        capture_enabled=True, session_id=session_id)
    published = target.checkpoint(session["id"], str(memory.get("kind") or "fact"),
        str(memory.get("title") or "Memoria compartida"), str(memory.get("content") or ""),
        scope="team", status=str(memory.get("status") or "observed"),
        confidence=float(memory.get("confidence") or 0.7), files=memory.get("files") or [],
        node_ids=memory.get("node_ids") or [], tests=memory.get("tests") or [], metadata=provenance)
    return {"ok": True, "installation_id": installation_id,
            "source_memory_id": memory_id, "shared_memory_id": published.get("id"),
            "family_id": route["family_id"], "publisher": route["agent_id"]}


def revoke_agent_memory(installation_id: str, agent_id: str, shared_memory_id: str, *,
                        registry: Path | None = None) -> dict[str, Any]:
    """Revoke a copy previously published by this same agent."""
    from .shared_memory import SharedMemoryStore
    route = resolve_agent(installation_id, agent_id, registry=registry)
    if not route.get("family_path") or route["relation_status"] not in {"root", "confirmed"}:
        raise PermissionError("este agente no pertenece a una familia confirmada")
    shared = SharedMemoryStore(Path(route["family_path"]))
    memory = shared.get(shared_memory_id, requester_agent=route["agent_id"])
    metadata = (memory or {}).get("metadata") or {}
    if not memory or not metadata.get("explicitly_published") or \
            metadata.get("installation_id") != installation_id or \
            metadata.get("source_agent_id") != route["agent_id"]:
        raise PermissionError("sólo se pueden revocar recuerdos publicados por este agente")
    result = shared.forget(shared_memory_id, requester_agent=route["agent_id"])
    return {"ok": True, "shared_memory_id": shared_memory_id,
            "source_memory_id": metadata.get("source_memory_id"), "result": result}
