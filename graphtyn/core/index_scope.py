"""The part of a project directory Graphtyn covers, set with ``graphtyn scope``.

A project such as a home directory holds other projects, downloads and caches. Without a scope,
indexing it walks and parses all of them, and every agent working anywhere below it is attached to
its graph. An include scope limits both:

- indexing walks only the directories that can hold an included path and indexes only included
  files. Hidden paths such as ``.config/nvim`` are indexed when a rule names them, and an
  included text file is indexed even when its extension is not a known source type;
- a working directory below the project counts as part of it only when it lies on an included
  path, so an agent in an unrelated subdirectory is not given this project's graph or memory.

Rules use the ``.graphtynignore`` syntax but are always anchored at the project root: ``.bashrc``
means the root file, ``nixos/`` a root directory, ``.config/nvim/**/*.lua`` a pattern below it.
A ``!rule`` removes paths again. Secret stores (SSH, GnuPG, cloud credentials, keys, tokens) are
never indexed, whatever the rules say.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

from .ignore_rules import IgnoreRules

CONFIG_KEY = "include"
TEXT_LIMIT = 256 * 1024
_WILDCARD = re.compile(r"[*?\[]")
_SECRET_DIRS = {
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store", ".pki", ".gcloud",
    "gcloud", "keyrings", ".graphtyn",
}
_SECRET_NAMES = re.compile(
    r"(?i)^(?:\.netrc|\.pgpass|\.git-credentials|\.npmrc|\.pypirc|\.env(?:\..*)?|id_[a-z0-9]+(?:\.pub)?|"
    r"known_hosts|authorized_keys|hosts\.yml|.*credentials?.*|.*secrets?.*|.*tokens?.*|.*password.*|"
    r".*\.(?:pem|key|p12|pfx|crt|cer|kdbx|gpg|asc|keystore|jks))$"
)


def _anchored(rule: str) -> str:
    rule = rule.strip()
    negated = rule.startswith("!")
    body = rule[1:] if negated else rule
    return ("!" if negated else "") + "/" + body.lstrip("/")


class IndexScope:
    """Include rules of one project; an empty scope covers the whole directory as before."""

    def __init__(self, rules: list[str] | None = None) -> None:
        self.rules = [rule.strip() for rule in rules or [] if rule.strip() and not rule.strip().startswith("#")]
        self._match = IgnoreRules([_anchored(rule) for rule in self.rules])
        anchors, dropped = set(), set()
        for rule in self.rules:
            negated = rule.startswith("!")
            literal = []
            for part in rule.lstrip("!").strip("/").split("/"):
                if not part or _WILDCARD.search(part):
                    break
                literal.append(part)
            if not negated:
                anchors.add("/".join(literal))
            elif rule.endswith("/") and not _WILDCARD.search(rule) and literal:
                dropped.add("/".join(literal))
        self.anchors = sorted(anchors)
        # `!dir/` removes a whole directory: the walk skips it unless a rule reaches inside it.
        self.dropped = sorted(dropped)

    def __bool__(self) -> bool:
        return bool(self.rules)

    @classmethod
    def load(cls, store_dir: Path | None) -> "IndexScope":
        """The scope saved in a project's ``config.json`` inside the Graphtyn store."""
        if store_dir is None:
            return cls()
        try:
            config = json.loads((Path(store_dir) / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return cls()
        rules = config.get(CONFIG_KEY) if isinstance(config, dict) else None
        return cls([str(rule) for rule in rules] if isinstance(rules, list) else None)

    def includes(self, relative: str) -> bool:
        """Whether a file, as a POSIX path relative to the root, is inside the scope."""
        return not self or self._match.ignored(relative)

    def named(self, relative: str) -> bool:
        """Whether a directory is on the literal path of a rule, so hidden or build names are wanted."""
        return any(anchor == relative or anchor.startswith(relative + "/") for anchor in self.anchors)

    def reaches(self, relative: str) -> bool:
        """Whether a directory can hold an included path: it is on a rule's path or inside it."""
        if not self or relative in ("", "."):
            return True
        if any(relative == gone or relative.startswith(gone + "/") for gone in self.dropped) and not any(
                anchor.startswith(relative + "/") for anchor in self.anchors):
            return False
        return any(not anchor or anchor == relative or anchor.startswith(relative + "/")
                   or relative.startswith(anchor + "/") for anchor in self.anchors)

    def walk(self, root: Path, skip_dir) -> Iterator[Path]:
        """Files below ``root`` without entering directories the scope cannot reach.

        ``skip_dir(name)`` drops a directory the indexer never reads (hidden, builds, vendored code)
        unless a rule names it on its literal path.
        """
        root = Path(root)
        for current, dirs, files in os.walk(root):
            relative = Path(current).relative_to(root).as_posix()
            relative = "" if relative == "." else relative
            kept = []
            for name in sorted(dirs):
                child = f"{relative}/{name}" if relative else name
                if is_secret_path(child) or not self.reaches(child):
                    continue
                if skip_dir(name) and not self.named(child):
                    continue
                kept.append(name)
            dirs[:] = kept
            for name in sorted(files):
                yield Path(current) / name

    def files(self, root: Path, skip_dir) -> Iterator[tuple[Path, str]]:
        """Included files as ``(path, relative)``, without secrets or unnamed skipped directories."""
        root = Path(root)
        for path in self.walk(root, skip_dir):
            relative = path.relative_to(root).as_posix()
            if not self.includes(relative) or is_secret_path(relative) or not path.is_file():
                continue
            parts = relative.split("/")[:-1]
            if any(skip_dir(part) and not self.named("/".join(parts[:index + 1])) for index, part in enumerate(parts)):
                continue
            yield path, relative


def indexed_paths(root: Path, scope: IndexScope, skipped_parts: set[str]) -> Iterator[Path]:
    """Files the indexer considers, before extension, Git and ``.graphtynignore`` checks.

    Without a scope: every file outside hidden and skipped directories, except GitHub workflows.
    With one: the included files, walking only directories the scope reaches.
    """
    if scope:
        yield from (path for path, _ in scope.files(root, lambda name: name in skipped_parts or name.startswith(".")))
        return
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        workflow = len(parts) >= 3 and parts[0] == ".github" and parts[1] == "workflows"
        hidden = any(part.startswith(".") and not (workflow and index == 0) for index, part in enumerate(parts))
        if not hidden and not any(part in skipped_parts for part in parts):
            yield path


def is_secret_path(relative: str) -> bool:
    """Credential stores and key files, never indexed even when a scope includes them."""
    parts = relative.split("/")
    return any(part in _SECRET_DIRS for part in parts) or bool(_SECRET_NAMES.match(parts[-1]))


def is_text_file(path: Path) -> bool:
    """A small file without NUL bytes: an included config file Graphtyn can read as text."""
    try:
        if path.stat().st_size > TEXT_LIMIT:
            return False
        with path.open("rb") as stream:
            return b"\0" not in stream.read(4096)
    except OSError:
        return False


def store_scope(root: Path) -> IndexScope:
    """The scope of the project at ``root`` from the default Graphtyn store, without creating it."""
    from .storage import data_home, project_store_dir
    try:
        return IndexScope.load(project_store_dir(data_home(), Path(root), migrate_legacy=False, create=False))
    except OSError:
        return IndexScope()


def covers(root: Path, target: str | Path, scope: IndexScope | None = None) -> bool:
    """Whether ``target`` (a working directory or file) belongs to the project at ``root``.

    Outside a scoped project's included paths, a subdirectory belongs to no project of this root:
    callers looking for the nearest indexed ancestor keep looking above it.
    """
    try:
        root_path = Path(root).expanduser().resolve()
        target_path = Path(target).expanduser().resolve()
        relative = target_path.relative_to(root_path).as_posix()
    except (OSError, RuntimeError, ValueError):
        return False
    scope = store_scope(root_path) if scope is None else scope
    if not scope or relative in ("", "."):
        return True
    if is_secret_path(relative):
        return False
    return scope.reaches(relative) or scope.includes(relative)
