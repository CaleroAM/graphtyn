"""Shared SSH command construction for remote harness history sources."""
from __future__ import annotations

import os
from pathlib import Path


def ssh_command(target: str, *, connect_timeout: int = 8) -> list[str]:
    """Build a non-interactive SSH argv, optionally using a dedicated config.

    ``-F`` selects a caller-owned SSH config instead of inheriting a broken or
    container-specific global config. The same setting is consumed by CLI
    discovery, config updates, and history synchronization workers.
    """
    command = ["ssh"]
    configured = os.environ.get("GRAPHTYN_SSH_CONFIG", "").strip()
    if configured:
        config_path = Path(configured).expanduser()
        if not config_path.is_file():
            raise FileNotFoundError(f"GRAPHTYN_SSH_CONFIG no existe o no es un archivo: {config_path}")
        command.extend(["-F", str(config_path.resolve())])
    command.extend(["-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(connect_timeout)}", target])
    return command
