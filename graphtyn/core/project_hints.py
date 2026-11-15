"""Project evidence of imported sessions, resolved once per import.

A memory watcher re-imports every known session each cycle. Looking each one up read the project
registry, resolved every registered path and re-read the OpenClaw brain policy, so a watcher over a few
thousand sessions kept a CPU core busy. These answers depend on the space and the hint, not the session.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


def brain_refusal(root: Path) -> str:
    """Why this space's OpenClaw brain refuses writes, or "" when it accepts them."""
    from .openclaw_integration import assert_agent_memory_enabled
    try:
        assert_agent_memory_enabled(root, None)
    except PermissionError as exc:
        return str(exc)
    return ""


def is_path_hint(hint: str) -> bool:
    return (hint.startswith("~") or Path(hint).is_absolute() or PurePosixPath(hint).is_absolute()
            or PureWindowsPath(hint).is_absolute())


class ProjectHints:
    """Registered projects by exact path and by name, memoized for one import."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry
        self._owners: dict[str, dict[str, Any]] | None = None
        self._paths: dict[str, str] = {}
        self._names: dict[str, dict[str, Any] | None] = {}

    def path_owner(self, hint: str) -> dict[str, Any] | None:
        """The first registered project with this exact path, after resolving both sides."""
        if hint not in self._paths:
            try:
                self._paths[hint] = str(Path(hint).expanduser().resolve())
            except (OSError, RuntimeError, ValueError):
                self._paths[hint] = ""
        if not self._paths[hint]:
            return None
        if self._owners is None:
            self._owners = {}
            for item in self._registry.list():
                for value in item.get("paths", []):
                    self._owners.setdefault(str(Path(value).expanduser().resolve()), item)
        return self._owners.get(self._paths[hint])

    def named(self, hint: str) -> dict[str, Any] | None:
        if hint not in self._names:
            self._names[hint] = self._registry.resolve(hint)
        return self._names[hint]
