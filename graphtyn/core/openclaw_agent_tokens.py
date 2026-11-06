"""A Graphtyn MCP server and a bound token for each OpenClaw agent.

With one shared token, every OpenClaw agent can read any registered memory store,
including other agents' private brains, and can claim any `requester_agent`. OpenClaw
sends fixed headers per MCP server and has no per-agent server list, so each agent gets
its own server (`graphtyn-<agent>`) whose token is bound to `openclaw/<agent>` and limited
to the registered code projects plus that agent's brain and family store. Each agent's
tool policy denies the servers of the others. Every server keeps the read-only
project-memory tools of the shared one.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from .storage import data_home

SERVER_PREFIX = "graphtyn-"
SHARED_SERVER = "graphtyn"
TOOL_FILTER = {"include": ["memory_project_context", "memory_message_window", "memory_status"]}
_COPIED_KEYS = ("transport", "supportsParallelToolCalls", "connectionTimeoutMs", "requestTimeoutMs", "sslVerify")


def server_name(agent_id: str) -> str:
    """OpenClaw's provider-safe MCP server name for an agent."""
    return SERVER_PREFIX + (re.sub(r"[^a-z0-9_-]", "-", agent_id.lower()).strip("-") or "agent")


def code_projects(registry: Path | None = None) -> list[str]:
    """Registered project directories that are code projects, not agent brains."""
    path = registry or data_home() / "registered_projects.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = rows if isinstance(rows, list) else rows.get("projects", []) if isinstance(rows, dict) else []
    brains = (data_home() / "brains").resolve()
    projects: list[str] = []
    for row in rows:
        raw = row.get("path") if isinstance(row, dict) else row
        if not raw:
            continue
        project = Path(str(raw)).expanduser().resolve()
        if project.is_dir() and brains not in (project, *project.parents) and str(project) not in projects:
            projects.append(str(project))
    return projects


def _allowed(agent: dict[str, Any], projects: list[str]) -> list[str]:
    own = [agent.get("brain_path") if agent.get("memory_enabled", True) else None, agent.get("family_path")]
    stores = [str(Path(p).expanduser().resolve()) for p in own if p and Path(p).expanduser().is_dir()]
    return list(dict.fromkeys([*projects, *stores]))


def _write_private_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_tokens(tokens_file: Path) -> dict[str, Any]:
    try:
        tokens = json.loads(Path(tokens_file).expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError:
        tokens = {}
    if not isinstance(tokens, dict):
        raise ValueError("el archivo de tokens debe contener un objeto JSON")
    return tokens


def ensure_agent_tokens(tokens_file: Path, installation_id: str, agents: list[dict[str, Any]],
                        projects: list[str]) -> dict[str, str]:
    """One reader token per agent, reused on later runs; returns agent id → token."""
    tokens_file = Path(tokens_file).expanduser()
    tokens = _read_tokens(tokens_file)
    issued: dict[str, str] = {}
    for agent in agents:
        bound = f"openclaw/{agent['id']}"
        token = next((value for value, config in tokens.items() if isinstance(config, dict)
                      and config.get("agent_id") == bound and config.get("installation") == installation_id),
                     None) or "gto_" + secrets.token_urlsafe(32)
        tokens[token] = {"role": "reader", "agent_id": bound, "installation": installation_id,
                         "projects": _allowed(agent, projects)}
        issued[agent["id"]] = token
    _write_private_json(tokens_file, tokens)
    return issued


def revoke_shared(tokens_file: Path, token: str) -> bool:
    """Remove the token every agent shared before, unless an agent is bound to it."""
    tokens_file = Path(tokens_file).expanduser()
    tokens = _read_tokens(tokens_file)
    config = tokens.get(token)
    if not token or config is None or (isinstance(config, dict) and config.get("agent_id")):
        return False
    del tokens[token]
    _write_private_json(tokens_file, tokens)
    return True


def shared_token(config: dict[str, Any]) -> str:
    server = ((config.get("mcp") or {}).get("servers") or {}).get(SHARED_SERVER) or {}
    authorization = str((server.get("headers") or {}).get("Authorization") or "")
    return authorization[7:] if authorization.casefold().startswith("bearer ") else ""


def per_agent_config(config: dict[str, Any], url: str, tokens: dict[str, str]) -> dict[str, Any]:
    """`config` with one server per agent, no shared server, and each agent denied the others."""
    replacement = json.loads(json.dumps(config))
    servers = replacement.setdefault("mcp", {}).setdefault("servers", {})
    names = {agent: server_name(agent) for agent in tokens}
    template = servers.pop(SHARED_SERVER, None) or next(
        (server for name, server in servers.items() if name.startswith(SERVER_PREFIX)), {})
    base = {key: template[key] for key in _COPIED_KEYS if key in template}
    for name in [name for name in servers if name.startswith(SERVER_PREFIX) and name not in names.values()]:
        del servers[name]  # an agent that no longer exists
    for agent, token in tokens.items():
        servers[names[agent]] = {"url": url, "transport": "streamable-http", **base,
                                 "headers": {"Authorization": f"Bearer {token}"}, "toolFilter": TOOL_FILTER}
    entries = replacement.setdefault("agents", {}).setdefault("entries", {})

    def entry(agent: str) -> dict[str, Any]:
        if isinstance(entries, dict):
            return entries.setdefault(agent, {})
        found = next((item for item in entries if isinstance(item, dict) and (item.get("id") or item.get("name")) == agent),
                     None)
        if found is None:
            found = {"id": agent}
            entries.append(found)
        return found

    for agent in tokens:
        tools = entry(agent).setdefault("tools", {})
        kept = [rule for rule in tools.get("deny") or [] if not str(rule).startswith(SERVER_PREFIX)]
        tools["deny"] = kept + sorted(f"{names[other]}__*" for other in tokens if other != agent)
    return replacement


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:10]
