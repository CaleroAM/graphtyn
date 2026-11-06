"""Native Claude Code capture: a Stop hook that syncs the turn's transcript.

Claude Code runs the hook after each turn with a JSON payload on stdin that
names the transcript. The hook only schedules a detached worker so the client
never waits on Graphtyn, and the worker reuses the incremental, idempotent
sync used by the background watcher, so both paths never ingest a turn twice.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HOOK_COMMAND = "graphtyn memory claude-hook"
# Private to this user and project; Claude Code keeps it out of version control.
SETTINGS = Path(".claude") / "settings.local.json"


def _settings(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / SETTINGS
    if not path.exists():
        return path, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} no es JSON válido; se conservó sin cambios: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError(f"{path} debe contener un objeto JSON con hooks como objeto")
    return path, data


def _is_managed(group: Any, command: str = HOOK_COMMAND) -> bool:
    return isinstance(group, dict) and any(
        isinstance(hook, dict) and str(hook.get("command") or "").split(" --", 1)[0] == command
        for hook in group.get("hooks") or [])


def install_claude_hook(root: str | Path, event: str, command: str, timeout: int,
                        invocation: str | None = None,
                        invocations: list[str] | None = None, matcher: str | None = None) -> dict[str, Any]:
    """Register a managed hook group once for `event`, preserving user hooks.

    `command` identifies the managed hooks; `invocation(s)` are the exact
    command lines to run when they carry extra options.
    """
    invocations = invocations or [invocation or command]
    from .storage import atomic_write_json
    root = Path(root).expanduser().resolve()
    path, data = _settings(root)
    groups = data.setdefault("hooks", {}).setdefault(event, [])
    if not isinstance(groups, list):
        raise ValueError(f"{path}: hooks.{event} debe ser una lista")
    if not any(_is_managed(group, command) for group in groups):
        group: dict[str, Any] = {"matcher": matcher} if matcher else {}
        group["hooks"] = [{"type": "command", "command": line, "timeout": timeout} for line in invocations]
        groups.append(group)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, data)
    return {"ok": True, "settings": str(path), "hook": event,
            "command": invocations[0] if len(invocations) == 1 else invocations}


def uninstall_claude_hook(root: str | Path, event: str, command: str) -> dict[str, Any]:
    from .storage import atomic_write_json
    root = Path(root).expanduser().resolve()
    path, data = _settings(root)
    groups = (data.get("hooks") or {}).get(event)
    if not isinstance(groups, list) or not any(_is_managed(group, command) for group in groups):
        return {"ok": True, "removed": False, "settings": str(path)}
    remaining = [group for group in groups if not _is_managed(group, command)]
    if remaining:
        data["hooks"][event] = remaining
    else:
        del data["hooks"][event]
        if not data["hooks"]:
            del data["hooks"]
    atomic_write_json(path, data)
    return {"ok": True, "removed": True, "settings": str(path)}


def install_claude_capture(root: str | Path) -> dict[str, Any]:
    """Register the Stop hook once, preserving every user-defined hook."""
    return install_claude_hook(root, "Stop", HOOK_COMMAND, 10)


def uninstall_claude_capture(root: str | Path) -> dict[str, Any]:
    return uninstall_claude_hook(root, "Stop", HOOK_COMMAND)


def capture_enabled(root: Path) -> bool:
    """Capture requires the project's explicit opt-in recorded at installation."""
    try:
        manifest = json.loads((root / ".graphtyn" / "agent-install.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return isinstance(manifest, dict) and bool((manifest.get("claude_capture") or {}).get("enabled"))


def _project_root(cwd: str | None) -> Path | None:
    if not cwd:
        return None
    current = Path(cwd).expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".graphtyn" / "graphtyn.json").is_file():
            return candidate
    return None


def handle_stop_hook(payload: dict[str, Any], *, spawn=subprocess.Popen) -> dict[str, Any]:
    """Validate the hook payload and start the sync worker without blocking."""
    transcript = payload.get("transcript_path")
    root = _project_root(payload.get("cwd"))
    if not isinstance(transcript, str) or not Path(transcript).is_file():
        return {"scheduled": False, "reason": "transcript_missing"}
    if root is None:
        return {"scheduled": False, "reason": "project_not_registered"}
    if not capture_enabled(root):
        return {"scheduled": False, "reason": "capture_not_enabled", "path": str(root)}
    log = root / ".graphtyn" / "claude-capture.log"
    with log.open("a", encoding="utf-8") as stream:
        spawn([sys.executable, "-m", "graphtyn.cli", "memory", "claude-hook", "--worker",
               "--transcript", transcript, "--path", str(root)],
              cwd=str(root), stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
              start_new_session=True, close_fds=True)
    return {"scheduled": True, "path": str(root), "transcript": transcript}


def run_capture_worker(root: str | Path, transcript: str) -> dict[str, Any]:
    from .history_import import sync_memory_workspace
    return sync_memory_workspace(root, provider="claude", source=[transcript],
                                 provider_model="deterministic", enrich=False)
