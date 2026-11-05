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
from collections import Counter
from pathlib import Path
from typing import Any

from .path_signals import TEST_PATH, VENDORED_PATH

_SCAN_SECONDS = 2.0
_MAX_FILE_BYTES = 2_000_000
_LISTED_REFERENCES = 40
_LISTED_FILES = 40
_COMMENT = ("//", "/*", "*", "#", "--", '"""', "'''")
_ENCLOSING_KINDS = {"function", "method", "class", "struct", "interface", "module", "type"}
_SKIPPED_SUFFIXES = (".md", ".json", ".lock", ".txt", ".rst", ".yml", ".yaml", ".toml", ".svg", ".html", ".css")


CONSUMER_LABELS = {"llama", "usa", "referencia", "implementa", "hereda", "suscribe", "escucha",
                    "despacha", "invoca ruta", "valida con", "crea", "despacha evento"}
_LISTED_CONSUMERS = 40


def direct_consumers(graph: dict[str, Any], by_id: dict[Any, dict], anchor_ids: set[Any]) -> dict[Any, list[dict]]:
    """Every indexed incoming consumer edge of the anchors, in the whole graph."""
    consumers: dict[Any, list[dict]] = {}
    for link in graph.get("links", []):
        if (str(link.get("label") or "") in CONSUMER_LABELS and link.get("target") in anchor_ids
                and link.get("source") in by_id and link.get("source") not in anchor_ids):
            consumers.setdefault(link["source"], []).append(link)
    return consumers


def _consumer_rows(consumers: dict[Any, list[dict]], by_id: dict[Any, dict], shown: set[Any]) -> tuple[list[list[str]], int]:
    """One row per consumer outside `shown`, and how many symbols `shown` already covers.

    A call attributed to a whole file is listed under the function that makes it:
    "format.h" would leave the agent reading the file to find out who calls.
    """
    rows, covered, seen = [], 0, set()
    for node_id, edges in consumers.items():
        node = by_id[node_id]
        path = str(node.get("file") or "")
        if node.get("kind") == "file":
            for edge in edges:
                at = f"{edge.get('file') or path}:{edge.get('line') or ''}"
                row = (str((edge.get("resolution") or {}).get("caller") or node.get("name") or ""), at)
                if row not in seen:
                    seen.add(row)
                    rows.append(list(row))
        elif node_id in shown:
            covered += 1
        else:
            rows.append([node.get("name"), f"{path}:{edges[0].get('line') or node.get('line') or ''}"])
    return rows, covered


def consumer_summary(consumers: dict[Any, list[dict]], by_id: dict[Any, dict], shown: set[Any]) -> dict[str, Any]:
    """How many consumers exist and where the ones outside the selected nodes are.

    The node budget caps what is expanded, not what the agent is told exists.
    """
    rows, covered = _consumer_rows(consumers, by_id, shown)
    # Located code first: a mention in a document, with no line, must not displace it.
    rows.sort(key=lambda row: (row[1].endswith(":"), bool(TEST_PATH.search(row[1])), row[1], str(row[0])))
    per_file = Counter(row[1].rsplit(":", 1)[0] for row in rows[_LISTED_CONSUMERS:])
    return {"indexed": covered + len(rows), "total": covered + len(rows),
            "omitted": max(0, len(rows) - _LISTED_CONSUMERS),
            "omitted_by_file": dict(per_file.most_common(_LISTED_CONSUMERS)), "others": rows[:_LISTED_CONSUMERS]}


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
            # A file-level caller has no `file` of its own: the edge says where the call is.
            resolved_lines.add((str(link.get("file") or source.get("file")), int(link.get("line") or 0)))
            resolved_symbols.add((str(source.get("file")), str(source.get("name") or "")))
    symbols = _symbols_by_file(graph)
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(name) for name in sorted(names)) + r")(?![\w])")
    needles = [name.encode() for name in names]
    # In a monorepo, uses inside the symbol's own component matter first and fill the list.
    homes = {str(node.get("file")).split("/", 1)[0] for node in nodes if node.get("id") in ids and node.get("file")}
    paths = sorted({str(node.get("file")) for node in nodes if node.get("file")},
                   key=lambda path: (bool(TEST_PATH.search(path)), path.split("/", 1)[0] not in homes, path))
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
    if len(references) > _LISTED_REFERENCES:
        # Every use is accounted for per file, so the agent has no gap to go and search for.
        per_file = Counter(reference[1].rsplit(":", 1)[0] for reference in references[_LISTED_REFERENCES:])
        consumers["text_references_more_by_file"] = dict(per_file.most_common(_LISTED_FILES))
        consumers["text_references_more_files_omitted"] = max(0, len(per_file) - _LISTED_FILES)
        data["guidance"] += (" text_references_more_by_file counts the remaining uses per file; report those counts "
                             "instead of searching for each use.")
    if truncated:
        consumers["text_references_incomplete"] = True
        data["missing"] = [*data.get("missing", []), "all_text_references"]
        data["complete_for"] = []
        data["do_not_expand"] = False
