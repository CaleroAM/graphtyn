"""Portable setup and service artifacts without machine-specific assumptions."""
from __future__ import annotations
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from .history_import import default_sources, save_source
from .storage import data_home, secure_private_file

DASHBOARD_URL = "http://127.0.0.1:9210"


def native_service_kind(system: str | None = None) -> str:
    current = (system or platform.system()).casefold()
    if current == "windows":
        return "windows"
    if current == "linux" and shutil.which("systemctl"):
        return "systemd"
    raise RuntimeError("no hay gestor nativo compatible; use --kind compose o graphtyn serve")


def _graphtyn_executable() -> str:
    name = "graphtyn.exe" if platform.system().casefold() == "windows" else "graphtyn"
    adjacent = Path(sys.executable).absolute().with_name(name)
    return str(adjacent) if adjacent.is_file() else (shutil.which("graphtyn") or "graphtyn")

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
        secure_private_file(token_file)
    return {"ok": True, "project": str(project), "agents": installed, "sources": configured,
            "token_file": str(token_file) if token_file else None}

def service_artifact(project: Path, *, kind: str, output: Path, interval: float = 10,
                     watch: bool = False) -> Path:
    project, output = project.resolve(), output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if kind == "auto": kind = native_service_kind()
    if kind == "systemd":
        # Do not resolve the interpreter symlink: virtualenv/pipx launchers live
        # beside sys.executable even when it points into Nix/store or /usr.
        executable = _graphtyn_executable()
        watch_flag = " --watch" if watch else ""
        content = f"""[Unit]\nDescription=Graphtyn persistent dashboard\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nEnvironment=GRAPHTYN_HOME={data_home()}\nEnvironment=GRAPHTYN_WATCH_INTERVAL={max(1.0, float(interval)):g}\nExecStart=\"{executable}\" serve --host 127.0.0.1 --port 9210{watch_flag} --path \"{project}\"\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=true\nPrivateTmp=true\n\n[Install]\nWantedBy=default.target\n"""
    elif kind == "windows":
        executable = _graphtyn_executable()
        watch_flag = " --watch" if watch else ""
        content = (f'@echo off\r\nsetlocal\r\nset "GRAPHTYN_HOME={data_home()}"\r\n'
                   f'set "GRAPHTYN_WATCH_INTERVAL={max(1.0, float(interval)):g}"\r\n'
                   f'"{executable}" serve --host 127.0.0.1 --port 9210{watch_flag} --path "{project}"\r\n')
    elif kind == "compose":
        content = f"""services:\n  graphtyn:\n    image: graphtyn:latest\n    command: [\"serve\",\"--host\",\"0.0.0.0\",\"--port\",\"9210\",\"--path\",\"/workspace\",\"--watch\"]\n    ports: [\"127.0.0.1:9210:9210\"]\n    volumes:\n      - {project}:/workspace:ro\n      - graphtyn-state:/state\n    environment:\n      GRAPHTYN_HOME: /state\n      GRAPHTYN_MEMORY_TOKENS_FILE: /run/secrets/graphtyn_tokens\n    secrets: [graphtyn_tokens]\n    restart: unless-stopped\nsecrets:\n  graphtyn_tokens:\n    file: ./memory-tokens.json\nvolumes:\n  graphtyn-state:\n"""
    else: raise ValueError("kind debe ser auto, systemd, windows o compose")
    output.write_text(content, encoding="utf-8"); return output


def default_service_output(kind: str) -> Path:
    if kind == "auto": kind = native_service_kind()
    if kind == "systemd":
        return Path.home() / ".config" / "systemd" / "user" / "graphtyn-dashboard.service"
    if kind == "compose":
        return Path.cwd() / "compose.graphtyn.yml"
    if kind == "windows":
        appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return appdata / "Graphtyn" / "graphtyn-dashboard.cmd"
    raise ValueError("kind debe ser auto, systemd, windows o compose")


def manage_user_service(action: str, *, unit: str | None = None, kind: str = "auto",
                        artifact: Path | None = None, run=subprocess.run) -> dict[str, Any]:
    """Manage a native per-user service without requiring administrator rights."""
    if action not in {"enable", "start", "stop", "restart", "status", "uninstall"}:
        raise ValueError("acción de servicio inválida")
    if kind == "auto": kind = native_service_kind()
    if kind not in {"systemd", "windows"}:
        raise ValueError("la administración directa sólo admite systemd o windows")
    unit = unit or ("GraphtynDashboard" if kind == "windows" else "graphtyn-dashboard.service")
    unit_path = ((artifact or default_service_output("windows")) if kind == "windows"
                 else Path.home() / ".config" / "systemd" / "user" / unit)
    commands: list[list[str]] = []
    if kind == "windows" and action == "enable":
        commands = [["schtasks", "/Create", "/TN", unit, "/SC", "ONLOGON", "/TR", f'"{unit_path}"', "/F"],
                    ["schtasks", "/Run", "/TN", unit]]
    elif kind == "windows" and action == "uninstall":
        commands = [["schtasks", "/End", "/TN", unit], ["schtasks", "/Delete", "/TN", unit, "/F"]]
    elif kind == "windows" and action == "restart":
        commands = [["schtasks", "/End", "/TN", unit], ["schtasks", "/Run", "/TN", unit]]
    elif kind == "windows":
        verb = {"start": "/Run", "stop": "/End", "status": "/Query"}[action]
        commands = [["schtasks", verb, "/TN", unit]]
    elif action == "enable":
        commands = [["systemctl", "--user", "daemon-reload"],
                    ["systemctl", "--user", "enable", "--now", unit],
                    ["systemctl", "--user", "restart", unit]]
    elif action == "uninstall":
        commands = [["systemctl", "--user", "disable", "--now", unit],
                    ["systemctl", "--user", "daemon-reload"]]
    else:
        verb = "is-active" if action == "status" else action
        commands = [["systemctl", "--user", verb, unit]]
    outputs = []
    for command in commands:
        result = run(command, capture_output=True, text=True, check=False)
        outputs.append({"command": command, "returncode": result.returncode,
                        "stdout": result.stdout.strip(), "stderr": result.stderr.strip()})
        ignorable_stop = action in {"restart", "uninstall"} and kind == "windows" and command[1] == "/End"
        ignorable_disable = action == "uninstall" and kind == "systemd" and command[2] == "disable"
        if result.returncode and not (ignorable_stop or ignorable_disable):
            return {"ok": False, "action": action, "kind": kind, "unit": unit, "steps": outputs}
        if action == "uninstall" and ((kind == "systemd" and command[2] == "disable")
                                      or (kind == "windows" and command[1] == "/Delete")) and unit_path.exists():
            unit_path.unlink()
    return {"ok": True, "action": action, "kind": kind, "unit": unit, "steps": outputs,
            "dashboard": DASHBOARD_URL}

def rotate_token(*, role: str = "admin", projects: list[str] | None = None,
                 path: Path | None = None, keep_existing: bool = False) -> dict[str, Any]:
    if role not in {"reader", "writer", "admin"}: raise ValueError("rol inválido")
    target = path or data_home() / "memory-tokens.json"
    try: values = json.loads(target.read_text(encoding="utf-8")) if keep_existing else {}
    except (OSError, ValueError): values = {}
    token = secrets.token_urlsafe(32)
    values[token] = {"role": role, "projects": [str(Path(p).expanduser().resolve()) for p in projects or []]}
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(values, indent=2), encoding="utf-8"); secure_private_file(target)
    return {"ok": True, "token": token, "role": role, "projects": values[token]["projects"], "file": str(target)}
