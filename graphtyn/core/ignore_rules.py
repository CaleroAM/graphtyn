"""Project exclusions for indexing, read from `.graphtynignore`.

The file uses the familiar subset of `.gitignore` syntax: comments, `!`
negation, a trailing `/` for directories, a leading `/` to anchor at the
project root, and `*`, `?` and `**` wildcards. As in Git, the last matching
rule wins. Paths are matched as POSIX paths relative to the project root.
Unlike Git, rules are evaluated per file rather than by pruning directories,
so `!path` can re-include a file inside an excluded directory.
"""
from __future__ import annotations

import re
from pathlib import Path

IGNORE_FILE = ".graphtynignore"


def _translate(pattern: str) -> str:
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("/**", index) and index + 3 == len(pattern):
            out.append("(?:/.*)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return "".join(out)


class IgnoreRules:
    def __init__(self, lines: list[str] | None = None) -> None:
        self.rules: list[tuple[re.Pattern[str], bool]] = []
        for raw in lines or []:
            line = raw.rstrip("\n").rstrip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            directory_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = "/" in line
            body = _translate(line.lstrip("/"))
            prefix = "^" if anchored else "^(?:.*/)?"
            # Files are matched, so a directory rule needs something beneath it.
            suffix = "/.*$" if directory_only else "(?:/.*)?$"
            self.rules.append((re.compile(prefix + body + suffix), negated))

    @classmethod
    def load(cls, root: str | Path) -> "IgnoreRules":
        path = Path(root) / IGNORE_FILE
        try:
            return cls(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            return cls()

    def __bool__(self) -> bool:
        return bool(self.rules)

    def ignored(self, relative: str) -> bool:
        result = False
        for pattern, negated in self.rules:
            if pattern.match(relative):
                result = not negated
        return result
