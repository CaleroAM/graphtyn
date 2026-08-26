"""Portable setup and service artifacts without machine-specific assumptions."""
from __future__ import annotations
import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any
from .history_import import default_sources, save_source
from .storage import data_home

def detect_environment(project: Path) -> dict[str, Any]:
    sources = []
    for provider, candidates in default_sources().items():
        for path in candidates:
            if path.exists(): sources.append({"provider": provider, "source": str(path)})
    return {"project": str(project.resolve()), "state_home": str(data_home()),
            "commands": {name: bool(shutil.which(name)) for name in ("docker", "ssh", "ollama", "git")},
            "sources": sources, "container": Path("/.dockerenv").exists(),
            "warnings": ([] if project.exists() else ["project_path_missing"])}

def apply_setup(project: Path, *, agents: list[str], sources: list[dict[str, str]],
                create_token: bool = True) -> dict[str, Any]:
    from .agent_installer import install_agent
    project = project.expanduser().resolve(); project.mkdir(parents=True, exist_ok=True)
    dot = project / ".graphtyn"; dot.mkdir(exist_ok=True)
    (dot / "graphtyn.json").write_text(json.dumps({"version": 1, "name": project.name}, indent=2), encoding="utf-8")
    installed = {agent: install_agent(project, agent) for agent in agents}
    configured = [save_source(row["provider"], row["source"], label="setup discovery") for row in sources]
    token_file = None
    if create_token:
        token_file = data_home() / "memory-tokens.json"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps({secrets.token_urlsafe(32): {"role": "admin", "projects": [str(project)]}}, indent=2), encoding="utf-8")
        token_file.chmod(0o600)
    return {"ok": True, "project": str(project), "agents": installed, "sources": configured,
            "token_file": str(token_file) if token_file else None}

def service_artifact(project: Path, *, kind: str, output: Path, interval: float = 10) -> Path:
    project, output = project.resolve(), output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if kind == "systemd":
        content = f"""[Unit]\nDescription=Graphtyn conversation synchronization\nAfter=network-online.target\n\n[Service]\nType=simple\nEnvironment=GRAPHTYN_HOME={data_home()}\nExecStart={shutil.which('graphtyn') or 'graphtyn'} memory sync --consent --watch --interval {interval:g} --path {project}\nRestart=on-failure\nNoNewPrivileges=true\nPrivateTmp=true\n\n[Install]\nWantedBy=default.target\n"""
    elif kind == "compose":
        content = f"""services:\n  graphtyn:\n    image: graphtyn:latest\n    command: [\"serve\",\"--host\",\"0.0.0.0\",\"--port\",\"9210\",\"--path\",\"/workspace\",\"--watch\"]\n    ports: [\"127.0.0.1:9210:9210\"]\n    volumes:\n      - {project}:/workspace:ro\n      - graphtyn-state:/state\n    environment:\n      GRAPHTYN_HOME: /state\n      GRAPHTYN_MEMORY_TOKENS_FILE: /run/secrets/graphtyn_tokens\n    secrets: [graphtyn_tokens]\n    restart: unless-stopped\nsecrets:\n  graphtyn_tokens:\n    file: ./memory-tokens.json\nvolumes:\n  graphtyn-state:\n"""
    else: raise ValueError("kind debe ser systemd o compose")
    output.write_text(content, encoding="utf-8"); return output

def rotate_token(*, role: str = "admin", projects: list[str] | None = None,
                 path: Path | None = None, keep_existing: bool = False) -> dict[str, Any]:
    if role not in {"reader", "writer", "admin"}: raise ValueError("rol inválido")
    target = path or data_home() / "memory-tokens.json"
    try: values = json.loads(target.read_text(encoding="utf-8")) if keep_existing else {}
    except (OSError, ValueError): values = {}
    token = secrets.token_urlsafe(32)
    values[token] = {"role": role, "projects": [str(Path(p).expanduser().resolve()) for p in projects or []]}
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(values, indent=2), encoding="utf-8"); target.chmod(0o600)
    return {"ok": True, "token": token, "role": role, "projects": values[token]["projects"], "file": str(target)}
