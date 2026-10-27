"""Design rationale extracted from marked comments and ADR/RFC citations.

Agents asking *why* code exists need the author's stated reason, which no call
graph contains. Comments such as `# WHY: ...` or `// NOTE: ...` and references
like `ADR-0012` or `RFC 7231` are attached to the symbol they document: the
declaration that starts right below the comment, else the smallest enclosing
symbol, else the file.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_COMMENT = re.compile(r"^\s*(?:#|//+|/\*+|\*|--|;+)\s?(?P<body>.*?)\s*(?:\*/)?\s*$")
# Trailing comments after code (`return x  # RFC 7231`) need a space before them.
_TRAILING = re.compile(r"\s(?:#|//)\s?(?P<body>[^\"'`]*?)\s*$")
_MARKER = re.compile(r"^(?P<marker>WHY|NOTE|RATIONALE|DECISION|HACK|IMPORTANT)\s*[:\-]\s*(?P<text>\S.*)$")
_CITATION = re.compile(r"\b(?P<marker>ADR|RFC)[- ]?(?P<number>\d{1,5})\b")
# Markdown headings and prose start with "#" too; only code comments count.
_PROSE_EXTS = {".md", ".mdx", ".markdown", ".rst", ".txt", ".html", ".htm", ".adoc"}
MAX_PER_NODE = 8
MAX_TEXT = 240


def extract_rationale(text: str) -> list[dict[str, Any]]:
    """Return marked comments with their 1-based line and continuation text."""
    lines = text.splitlines()
    found: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        comment = _COMMENT.match(lines[index]) or _TRAILING.search(lines[index])
        body = comment.group("body") if comment else ""
        marked = _MARKER.match(body) if comment else None
        cited = _CITATION.search(body) if comment and not marked else None
        if not (marked or cited):
            index += 1
            continue
        parts = [marked.group("text") if marked else body]
        follow = index + 1
        # A marked comment may continue on following unmarked comment lines.
        while marked and follow < len(lines) and len(parts) < 4:
            continuation = _COMMENT.match(lines[follow])
            extra = continuation.group("body") if continuation else ""
            if not continuation or not extra or _MARKER.match(extra):
                break
            parts.append(extra)
            follow += 1
        found.append({
            "line": index + 1, "end_line": follow if marked else index + 1,
            "marker": marked.group("marker") if marked else f"{cited.group('marker')}-{cited.group('number')}",
            "text": " ".join(parts)[:MAX_TEXT],
        })
        index = follow if marked else index + 1
    return found


def _owner(symbols: list[dict[str, Any]], entry: dict[str, Any]) -> dict[str, Any] | None:
    line, end = entry["line"], entry["end_line"]
    enclosing = [node for node in symbols
                 if int(node.get("line") or 0) <= line <= int(node.get("end_line") or node.get("line") or 0)]
    inner = (min(enclosing, key=lambda node: int(node.get("end_line") or 0) - int(node.get("line") or 0))
             if enclosing else None)
    below = [node for node in symbols if end < int(node.get("line") or 0) <= end + 3]
    nearest = min(below, key=lambda node: int(node.get("line") or 0)) if below else None
    # A comment documents the declaration right below it only when that
    # declaration is in the same scope; otherwise it explains the body it is in.
    if nearest and (inner is None or int(nearest["line"]) <= int(inner.get("end_line") or inner["line"])):
        return nearest
    return inner


def attach_rationale(nodes: list[dict[str, Any]], contents: dict[str, str],
                     extra_files: dict[str, Path] | None = None) -> int:
    """Attach rationale entries to symbol or file nodes; return how many were found."""
    sources = dict(contents)
    for relative, path in (extra_files or {}).items():
        if relative not in sources:
            try:
                sources[relative] = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
    symbols_by_file: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id.startswith("file:"):
            files[node_id[5:]] = node
        elif node.get("file") and node.get("line") and node.get("kind") not in {"field", "property", "event"}:
            symbols_by_file.setdefault(str(node["file"]), []).append(node)
    total = 0
    for relative, text in sources.items():
        if Path(relative).suffix.lower() in _PROSE_EXTS or not any(
                marker in text for marker in ("WHY", "NOTE", "RATIONALE", "DECISION", "HACK",
                                              "IMPORTANT", "ADR", "RFC")):
            continue
        for entry in extract_rationale(text):
            owner = _owner(symbols_by_file.get(relative, []), entry) or files.get(relative)
            if owner is None:
                continue
            bucket = owner.setdefault("rationale", [])
            if len(bucket) < MAX_PER_NODE:
                bucket.append({key: entry[key] for key in ("line", "marker", "text")})
                total += 1
    return total
