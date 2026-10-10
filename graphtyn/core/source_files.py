"""Source-file discovery shared by indexing and incremental watching."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_visible_files(root: Path) -> set[str] | None:
    """Return tracked and non-ignored untracked paths, or ``None`` on failure.

    A working-tree analyzer must see new source and evidence files before their
    first commit. Git still provides the ignore rules, so generated or private
    ignored files remain outside the graph.
    """
    root = Path(root)
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return {
        raw.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for raw in result.stdout.split(b"\0")
        if raw
    }
