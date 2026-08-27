"""Portable terminal encoding without writing protocol noise to stdout."""

from __future__ import annotations

import os
import sys
from typing import Any


def configure_utf8_stdio(*, stdout: Any = None, stderr: Any = None,
                         platform_name: str | None = None) -> None:
    """Use UTF-8 on Windows consoles and pipes, tolerating wrapped streams."""
    if (platform_name or os.name).casefold() not in {"nt", "windows"}:
        return
    for stream in (stdout if stdout is not None else sys.stdout,
                   stderr if stderr is not None else sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError, TypeError):
                pass
