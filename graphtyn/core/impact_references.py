"""Textual uses of a symbol that the graph did not resolve, for impact packages.

The parser misses some calls (`write_padded<Char>(...)`, dynamic dispatch), so an
empty or short consumer list is not proof that nothing else uses the symbol. A
bounded scan of the indexed files reports those uses, with their enclosing symbol,
as unverified leads, so an agent told to stop does not stop on a partial list.
"""
from __future__ import annotations

import bisect
import re
import time
from pathlib import Path
from typing import Any

from .path_signals import TEST_PATH, VENDORED_PATH

_SCAN_SECONDS = 2.0
_MAX_FILE_BYTES = 2_000_000
_LISTED_REFERENCES = 40
_COMMENT = ("//", "/*", "*", "#", "--", '"""', "'''")
_ENCLOSING_KINDS = {"function", "method", "class", "struct", "interface", "module", "type"}
_SKIPPED_SUFFIXES = (".md", ".json", ".lock", ".txt", ".rst", ".yml", ".yaml", ".toml", ".svg", ".html", ".css")


def _symbols_by_file(graph: dict[str, Any]) -> dict[str, list[tuple[int, str]]]:
    symbols: dict[str, list[tuple[int, str]]] = {}
    for node in graph.get("nodes", []):
        if node.get("kind") in _ENCLOSING_KINDS and node.get("file") and node.get("line"):
            symbols.setdefault(str(node["file"]), []).append((int(node["line"]), str(node.get("name") or "")))
    return {path: sorted(items) for path, items in symbols.items()}


def _enclosing(symbols: list[tuple[int, str]], line: int) -> str:
    index = bisect.bisect_right(symbols, (line, "\U0010ffff")) - 1
    return symbols[index][1] if index >= 0 else ""


def _scan(root: Path, graph: dict[str, Any], names: set[str], ids: set[Any]) -> tuple[list[list[str]], bool]:
    """Uses outside the definitions and the edges the graph already has."""
    nodes = graph.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes}
    definitions = {(str(node.get("file")), int(node.get("line") or 0)) for node in nodes if node.get("id") in ids}
    resolved_lines, resolved_symbols = set(), set()
    for link in graph.get("links", []):
        source = by_id.get(link.get("source"))
        if source and link.get("target") in ids:
            resolved_lines.add((str(source.get("file")), int(link.get("line") or 0)))
            resolved_symbols.add((str(source.get("file")), str(source.get("name") or "")))
    symbols = _symbols_by_file(graph)
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(name) for name in sorted(names)) + r")(?![\w])")
    needles = [name.encode() for name in names]
    paths = sorted({str(node.get("file")) for node in nodes if node.get("file")},
                   key=lambda path: (bool(TEST_PATH.search(path)), path))
    references, seen = [], set()
    deadline = time.monotonic() + _SCAN_SECONDS
    for path in paths:
        if path.endswith(_SKIPPED_SUFFIXES) or VENDORED_PATH.search(path):
            continue
        if time.monotonic() > deadline:
            return references, True
        try:
            source = root / path
            if source.stat().st_size > _MAX_FILE_BYTES:
                continue
            raw = source.read_bytes()
        except OSError:
            continue
        if not any(needle in raw for needle in needles):
            continue
        for number, text in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            if not pattern.search(text) or text.lstrip().startswith(_COMMENT):
                continue
            if (path, number) in definitions or (path, number) in resolved_lines:
                continue
            owner = _enclosing(symbols.get(path, []), number)
            key = (path, owner)
            if owner in names or key in resolved_symbols or key in seen:
                continue
            seen.add(key)
            references.append([owner, f"{path}:{number}"])
    return references, False


def attach_text_references(root: Path, graph: dict[str, Any] | None, data: dict[str, Any]) -> None:
    """Add unresolved textual uses to an impact package's `direct_consumers`."""
    consumers = data.get("direct_consumers")
    if not graph or not isinstance(consumers, dict):
        return
    names = {str(node.get("name") or "") for node in data.get("matched") or []} - {""}
    if not names:
        return
    ids = {node.get("id") for node in graph.get("nodes", []) if str(node.get("name") or "") in names}
    references, truncated = _scan(Path(root), graph, names, ids)
    consumers["total"] = int(consumers.get("indexed") or 0) + len(references)
    if references:
        consumers["text_references"] = references[:_LISTED_REFERENCES]
        data["negative_evidence"] = {}
        data["guidance"] = (str(data.get("guidance") or "") + " direct_consumers.text_references are textual uses "
                            "the index did not resolve: [enclosing symbol, file:line]; report them as unverified.").strip()
    if truncated or len(references) > _LISTED_REFERENCES:
        consumers["text_references_incomplete"] = True
        data["missing"] = [*data.get("missing", []), "all_text_references"]
        data["complete_for"] = []
        data["do_not_expand"] = False
