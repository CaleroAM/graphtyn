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

from .path_signals import TEST_PATH, VENDORED_PATH, in_named_scope, package_root

_SCAN_SECONDS = 2.0
_MAX_FILE_BYTES = 2_000_000
_LISTED_REFERENCES = 40
_LISTED_FILES = 40
_COMMENT = ("//", "/*", "*", "#", "--", '"""', "'''")
_ENCLOSING_KINDS = {"function", "method", "class", "struct", "interface", "module", "type"}
_BLOCK_OPENERS = {"/*": "*/", '"""': '"""', "'''": "'''"}
_DECLARATIONS = ("package ",)
_SKIPPED_SUFFIXES = (".md", ".json", ".lock", ".txt", ".rst", ".yml", ".yaml", ".toml", ".svg", ".html", ".css")


CONSUMER_LABELS = {"llama", "usa", "referencia", "implementa", "hereda", "suscribe", "escucha",
                    "despacha", "invoca ruta", "valida con", "crea", "despacha evento"}
_LISTED_CONSUMERS = 40


_ANCESTRY_LABELS = {"hereda", "incluye", "implementa"}
_ANCESTRY_DEPTH = 8


def impact_targets(nodes: list[dict], names: set[str], package_roots: set[str],
                   links: list[dict] | None = None) -> list[dict]:
    """Definitions a change affects: those of the package the request names, when it has them.

    A homonym elsewhere still counts when its class descends from that package
    (`ActionMailer::MailDeliveryJob#perform` overrides `ActiveJob::Base#perform`).
    """
    named = [node for node in nodes if str(node.get("name") or "").lower() in names]
    inside = [node for node in named if in_named_scope(node, package_roots)]
    outside = [node for node in named if not in_named_scope(node, package_roots)]
    if not inside or not outside or not links:
        return inside or named
    return inside + _overrides(outside, nodes, links, package_roots)


_TYPE_KINDS = {"class", "module", "struct", "interface", "trait", "protocol", "enum"}


def named_owner_members(named: list[dict], request: str, links: list[dict] | None) -> list[dict]:
    """`the matched method of the Sink trait`: the member of the named type and what implements it.

    These are the anchors; the other homonyms are still reported, as omitted ones. Without this,
    every `matched` in the repository competes for the anchors, and the most called homonym
    (`Gitignore::matched`) displaces the declaration that was asked about. Implementations with
    no edge (Java enum constant bodies) must stay visible, so nothing is dropped here.
    """
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", request or ""))
    # The owner is written as declared (`Sink`, not `sink`) and is not the member's own name.
    members = [node for node in named if node.get("kind") not in _TYPE_KINDS
               and (owner := str(node.get("container") or "")) in words and owner != node.get("name")]
    if not members:
        return []
    member_ids = {node.get("id") for node in members}
    implementing = {link.get("source") for link in links or ()
                    if link.get("label") in {"implementa", "hereda"} and link.get("target") in member_ids}
    return members + [node for node in named if node.get("id") in implementing and node.get("id") not in member_ids]


def _overrides(candidates: list[dict], nodes: list[dict], links: list[dict], package_roots: set[str]) -> list[dict]:
    by_id = {node.get("id"): node for node in nodes}
    parents: dict[Any, set[Any]] = {}
    for link in links:
        if link.get("label") in _ANCESTRY_LABELS and str(link.get("confidence") or "") != "AMBIGUOUS":
            parents.setdefault(link.get("source"), set()).add(link.get("target"))
    owners = {(str(node.get("file") or ""), str(node.get("name") or "")): node.get("id")
              for node in nodes if node.get("kind") in {"class", "module", "struct", "interface", "trait"}}

    def descends(owner: Any) -> bool:
        frontier, seen = [owner], {owner}
        for _depth in range(_ANCESTRY_DEPTH):
            frontier = [parent for current in frontier for parent in parents.get(current, ()) if parent not in seen]
            seen.update(frontier)
            if any(in_named_scope(by_id.get(parent, {}), package_roots) for parent in frontier):
                return True
        return False

    return [node for node in candidates
            if (owner := owners.get((str(node.get("file") or ""), str(node.get("container") or "")))) and descends(owner)]


def one_per_name(anchors: list[dict], limit: int) -> list[dict]:
    """The first definition of each name, then the rest: every requested name must reach the text scan."""
    seen, first, rest = set(), [], []
    for node in anchors:
        name = str(node.get("name") or "")
        (rest if name in seen else first).append(node)
        seen.add(name)
    return (first + rest)[:limit]


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


def _symbols_by_file(graph: dict[str, Any]) -> dict[str, list[tuple[int, str, int]]]:
    symbols: dict[str, list[tuple[int, str, int]]] = {}
    for node in graph.get("nodes", []):
        if node.get("kind") in _ENCLOSING_KINDS and node.get("file") and node.get("line"):
            start = int(node["line"])
            symbols.setdefault(str(node["file"]), []).append(
                (start, str(node.get("name") or ""), int(node.get("end_line") or 0)))
    return {path: sorted(items) for path, items in symbols.items()}


def _enclosing(symbols: list[tuple[int, str, int]], line: int, before: bool = False) -> str:
    """The innermost symbol whose range holds `line`; with `before`, one that starts above it.

    The nearest symbol above is not the owner: in Koa's `handleRequest`, the one-line arrow
    `const handleResponse = () => respond(ctx)` precedes `.catch(onerror)`, which belongs to
    `handleRequest`. Symbols without an end line keep the nearest-above rule.
    """
    index = bisect.bisect_left(symbols, (line if before else line + 1, "")) - 1
    nearest = symbols[index][1] if index >= 0 else ""
    while index >= 0:
        _start, name, end = symbols[index]
        if not end or end >= line:
            return name
        index -= 1
    return nearest


def _scan(root: Path, graph: dict[str, Any], names: set[str], ids: set[Any], anchors: list[dict]) -> tuple[list[list[str]], bool]:
    """Uses outside the definitions and the edges the graph already has."""
    nodes = graph.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes}
    definitions = {(str(node.get("file")), int(node.get("line") or 0)) for node in nodes if node.get("id") in ids}
    resolved_lines, resolved_symbols = set(), set()
    for link in graph.get("links", []):
        source = by_id.get(link.get("source"))
        # Only a consumer edge resolves a use: `contiene` points at a definition, not at a call.
        if source and link.get("target") in ids and str(link.get("label") or "") in CONSUMER_LABELS:
            # A file-level caller has no `file` of its own: the edge says where the call is.
            resolved_lines.add((str(link.get("file") or source.get("file")), int(link.get("line") or 0)))
            resolved_symbols.add((str(source.get("file")), str(source.get("name") or "")))
    symbols = _symbols_by_file(graph)
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(name) for name in sorted(names)) + r")(?![\w])")
    needles = [name.encode() for name in names]
    # `self.sink.matched(` is a use; "matched lines" in a message is not, and must not fill the list first.
    call = re.compile(r"(?:\.|::|->)\s*(?:" + "|".join(re.escape(name) for name in sorted(names)) + r")\s*[(<!]")
    # `org.jsoup.select.Elements` names a package, not the `select` method.
    alternatives = "|".join(re.escape(name) for name in sorted(names))
    qualified = re.compile(r"\w\.(?:" + alternatives + r")\.[A-Z*{]")
    # `"select"` in a list of HTML tag names is a string, not a use of `select`.
    quoted = re.compile(r"([\"'`])(?:" + alternatives + r")\1")
    bare_call = re.compile(r"(?<![\w.])(?:" + alternatives + r")\s*\(")
    # In a monorepo, uses inside the symbol's own component matter first and fill the list.
    homes = {package_root(node) for node in anchors if node.get("file")}
    paths = sorted({str(node.get("file")) for node in nodes if node.get("file")},
                   key=lambda path: (bool(TEST_PATH.search(path)), package_root({"file": path}) not in homes, path))
    references, seen = [], set()
    deadline = time.monotonic() + _SCAN_SECONDS
    for path in paths:
        if path.endswith(_SKIPPED_SUFFIXES) or VENDORED_PATH.search(path):
            continue
        if time.monotonic() > deadline:
            return _calls_first(references), True
        try:
            source = root / path
            if source.stat().st_size > _MAX_FILE_BYTES:
                continue
            raw = source.read_bytes()
        except OSError:
            continue
        if not any(needle in raw for needle in needles):
            continue
        closing = None
        for number, text in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            stripped = text.lstrip()
            if closing:
                # Inside a block comment or docstring: `<code>doc.select("b")</code>` is an example.
                closing = None if closing in stripped else closing
                continue
            opener = next((mark for mark in _BLOCK_OPENERS if stripped.startswith(mark)), None)
            if opener and _BLOCK_OPENERS[opener] not in stripped[len(opener):]:
                closing = _BLOCK_OPENERS[opener]
            if not pattern.search(text) or stripped.startswith(_COMMENT) or stripped.startswith(_DECLARATIONS):
                continue
            if len(pattern.findall(text)) == len(qualified.findall(text)) + len(quoted.findall(text)):
                continue
            if (path, number) in resolved_lines:
                continue
            # `const onerror = (err) => ctx.onerror(err)` defines a homonym and calls the target.
            defined = (path, number) in definitions
            if defined and not call.search(text):
                continue
            owner = _enclosing(symbols.get(path, []), number, before=defined)
            key = (path, owner)
            if owner in names or key in resolved_symbols or key in seen:
                continue
            seen.add(key)
            references.append([owner, f"{path}:{number}", 0 if call.search(text) else 1 if bare_call.search(text) else 2])
    return _calls_first(references), False


def _calls_first(references: list[list]) -> list[list[str]]:
    """Production code first, then member calls, bare calls and other mentions, in scan order.

    Tests call a public method hundreds of times; their member calls must not fill the list
    ahead of the production uses (jsoup `Element.select`). The rank is dropped.
    """
    return [reference[:2] for reference in sorted(
        references, key=lambda reference: (bool(TEST_PATH.search(reference[1])), reference[2]))]


def attach_text_references(root: Path, graph: dict[str, Any] | None, data: dict[str, Any]) -> None:
    """Add unresolved textual uses to an impact package's `direct_consumers`."""
    consumers = data.get("direct_consumers")
    if not graph or not isinstance(consumers, dict):
        return
    names = {str(node.get("name") or "") for node in data.get("matched") or []} - {""}
    if not names:
        return
    ids = {node.get("id") for node in graph.get("nodes", []) if str(node.get("name") or "") in names}
    references, truncated = _scan(Path(root), graph, names, ids, data.get("matched") or [])
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


def homonym_rows(graph: dict[str, Any], omitted: list[dict[str, Any]], anchors: list[dict[str, Any]]) -> list[Any]:
    """Other definitions of the name, the project's own by owner: `OsFs.OpenFile` says more than `os.go:64`.

    A session given only file:line listed `os.go:64` as a homonym and never said it was
    `OsFs`, one of the implementations it was asked for. Definitions in test files stay a bare
    file:line, after the others, so a package near its budget does not lose a fact to them.
    """
    anchor_names = {node.get("id"): f"{node.get('container') + '.' if node.get('container') else ''}{node.get('name')}"
                    for node in anchors}
    implements = {link.get("source"): anchor_names[link.get("target")] for link in graph.get("links", [])
                  if link.get("label") == "implementa" and link.get("target") in anchor_names}
    own, tests = [], []
    for node in omitted:
        place = f"{node.get('file') or ''}:{node.get('line') or ''}"
        if TEST_PATH.search(str(node.get("file") or "")):
            tests.append(place)
            continue
        row = [f"{node.get('container') + '.' if node.get('container') else ''}{node.get('name') or ''}", place]
        if node.get("id") in implements:
            row.append(f"implements {implements[node.get('id')]}")
        own.append(row)
    return own + tests


def owned_implementations(graph: dict[str, Any], anchors: list[dict[str, Any]]) -> set[str]:
    """Definitions with an `implementa` edge to an anchor, whatever the package selected."""
    ids = {node.get("id") for node in anchors}
    return {link.get("source") for link in graph.get("links", []) if link.get("label") == "implementa" and link.get("target") in ids}


def whole_graph_counts(result: dict, incoming_calls: int, implementations: int) -> tuple[int, int]:
    """Consumers and implementations in the whole graph, not only those the package selected.

    A session read `implementations: 4` as the total of a Go interface that six types implement.
    """
    return (max(incoming_calls, int((result.get("direct_consumers") or {}).get("total") or 0)),
            max(implementations, int(result.get("implementations_total") or 0)))
