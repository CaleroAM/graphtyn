"""Refuse to declare a package complete when its evidence cannot support the request.

Graph retrieval cannot tell which part of a multi-part request a symbol
answers, and lexical part-by-part checks did not separate good from bad
packages. Two checks did, on the dev split of
``benchmarks/task_bank_2026-10-28``:

* **Thin evidence.** Packages that claimed completeness while covering little
  of a request carried far less source per requested part.
* **Unmatched identifiers.** A request that names ``BLPOP`` or ``TRYAGAIN`` is
  not answered by evidence that never mentions them, however large it is.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .lean_package import lean_payload, serialized_tokens

MIN_PARTS = 4
# Calibrated on the dev split: every package below it covered under half of
# its rubric, every package above it at least 60 %.
MIN_TOKENS_PER_PART = 250
_CITATION_REQUEST = re.compile(r"\s*Cit(?:a|e)\b[^.]*(?:archivo|file):l[ií]ne(?:a|s?)\b.*$", re.I | re.S)
# Code-shaped words: COMMANDS and CONSTANTS, snake_case, camelCase and PascalCase compounds.
_IDENTIFIER = re.compile(r"\b(?:[A-Z][A-Z0-9_]{2,}|[A-Za-z]+_[A-Za-z0-9_]+|[a-z]+[A-Z][A-Za-z0-9]*"
                         r"|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b")
GUIDANCE = ("The evidence does not cover the whole request: answer the parts it shows from it, and look up "
            "only what it does not address (one targeted search or exact range each).")


def request_parts(request: str) -> list[str]:
    """Clauses of an enumerated request, without the closing citation instruction."""
    text = _CITATION_REQUEST.sub("", str(request or ""))
    return [part.strip() for part in re.split(r"[,;:?]", text) if len(part.strip()) >= 8]


def named_identifiers(request: str) -> list[str]:
    """Identifiers the request spells out, without the closing citation instruction."""
    return list(dict.fromkeys(_IDENTIFIER.findall(_CITATION_REQUEST.sub("", str(request or "")))))


_ACRONYM_LENGTH = 4
_HITS_PER_NAME = 3
_SCAN_SECONDS = 1.5
_MAX_FILE_BYTES = 1_000_000
_NAMES_CACHE: dict[int, tuple[int, list[str]]] = {}


def _graph_names(graph: dict[str, Any]) -> list[str]:
    cached = _NAMES_CACHE.get(id(graph))
    if cached and cached[0] == len(graph.get("nodes", [])):
        return cached[1]
    names = sorted({str(node.get("name") or "").lower() for node in graph.get("nodes", []) if node.get("name")})
    _NAMES_CACHE.clear()
    _NAMES_CACHE[id(graph)] = (len(graph.get("nodes", [])), names)
    return names


def requested_identifiers(request: str, graph: dict[str, Any] | None = None) -> list[str]:
    """Named identifiers, without prose acronyms: a short all-caps word (`API`, `JWT`) counts only when
    some symbol of the project starts with it (`GET` → `getCommand`)."""
    names = named_identifiers(request)
    if graph is None:
        return names
    known = _graph_names(graph)
    return [name for name in names
            if not (name.isupper() and len(name) <= _ACRONYM_LENGTH)
            or any(symbol.startswith(name.lower()) for symbol in known)]


def identifier_hits(root: Path, graph: dict[str, Any], names: list[str]) -> dict[str, list[list[str]]]:
    """Where identifiers the graph has no symbol for appear in the indexed files: [file:line, code].

    A configuration key or a local variable is not a symbol; three exact locations save the agent a search.
    """
    hits: dict[str, list[list[str]]] = {name: [] for name in names}
    patterns = {name: re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])") for name in names}
    paths = sorted({str(node.get("file") or str(node.get("id") or "").removeprefix("file:"))
                    for node in graph.get("nodes", []) if node.get("kind") == "file" or node.get("file")})
    deadline, base = time.monotonic() + _SCAN_SECONDS, Path(root).resolve()
    for path in paths:
        if time.monotonic() > deadline or all(len(found) >= _HITS_PER_NAME for found in hits.values()):
            break
        source = (base / path).resolve()
        try:
            if not source.is_relative_to(base) or source.stat().st_size > _MAX_FILE_BYTES:
                continue
            raw = source.read_bytes()
        except OSError:
            continue
        wanted = [name for name in names if len(hits[name]) < _HITS_PER_NAME and name.encode() in raw]
        if not wanted:
            continue
        for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            for name in wanted:
                if len(hits[name]) < _HITS_PER_NAME and patterns[name].search(line):
                    hits[name].append([f"{path}:{number}", " ".join(line.split())[:160]])
    return hits


def evidence_tokens(lean: dict[str, Any]) -> int:
    return serialized_tokens({key: lean.get(key) for key in ("entities", "relations", "source_evidence")})


def _verdict(result: dict[str, Any], request: str, graph: dict[str, Any] | None = None,
             root: Path | None = None) -> dict[str, Any]:
    lean = lean_payload(result)
    verdict: dict[str, Any] = {}
    parts = len(request_parts(request))
    tokens = evidence_tokens(lean)
    if parts >= MIN_PARTS and tokens < MIN_TOKENS_PER_PART * parts:
        verdict.update(request_parts=parts, evidence_tokens=tokens, required_tokens=MIN_TOKENS_PER_PART * parts)
    text = json.dumps(lean, ensure_ascii=False).lower()
    # Whole identifiers: `lua_pcallk` does not show that `lua_pcall` was found.
    # A name in capitals only has to start a word (`BLPOP` → `blpopCommand`, `UTF` → `utf8`).
    unmatched = [name for name in requested_identifiers(request, graph)
                 if not re.search(r"(?<![\w])" + re.escape(name.lower()) + ("" if name.isupper() else r"(?![\w])"), text)]
    if unmatched and graph is not None and root is not None:
        # A symbol the graph has but did not select is a real gap; a name that is only text gets its
        # locations; a name found nowhere is reported as absent instead of sending the agent to search.
        names = _graph_names(graph)
        exact = set(names)
        # Like the match above, a name in capitals names a symbol it starts (`UNLINK` → `unlinkCommand`).
        is_symbol = lambda name: name.lower() in exact or (name.isupper() and any(  # noqa: E731
            symbol.startswith(name.lower()) for symbol in names))
        textual = [name for name in unmatched if not is_symbol(name)]
        found = identifier_hits(root, graph, textual) if textual else {}
        located = {name: places for name, places in found.items() if places}
        if located:
            verdict["identifier_hits"] = located
        absent = [name for name in textual if name not in located]
        if absent:
            verdict["absent_identifiers"] = absent
        unmatched = [name for name in unmatched if is_symbol(name)]
    if unmatched:
        verdict["unmatched_identifiers"] = unmatched
    return verdict


def mark_insufficient_evidence(result: dict[str, Any], request: str,
                               mirror: dict[str, Any] | None = None, graph: dict[str, Any] | None = None,
                               root: Path | None = None) -> bool:
    """Withdraw a completeness claim the evidence cannot support; return whether it did.

    `mirror` (the internal package `result` was rendered from) receives the same verdict.
    """
    if not result.get("do_not_expand"):
        return False
    verdict = _verdict(result, request, graph, root)
    located = {key: verdict.pop(key) for key in ("identifier_hits", "absent_identifiers") if key in verdict}
    if located:
        result["identifier_lookup"] = located
        result["guidance"] = (f"{result.get('guidance') or ''} identifier_lookup.identifier_hits shows where named "
                              "identifiers that are not symbols appear [file:line, code]; absent_identifiers appear in no "
                              "indexed file: say so instead of searching.").strip()
        if mirror is not None:
            mirror["identifier_lookup"] = located
    if not verdict:
        return False
    missing = (["request_parts"] if "request_parts" in verdict else []) + (
        ["named_identifiers"] if "unmatched_identifiers" in verdict else [])
    result["missing"] = [*(result.get("missing") or []), *missing]
    result["complete_for"] = []
    result["do_not_expand"] = False
    result["evidence_sufficiency"] = verdict
    stopping = result.get("stopping")
    if isinstance(stopping, dict):
        stopping["sufficient_evidence"] = False
        stopping["reason"] = "evidence does not cover the whole request"
    result["guidance"] = f"{result.get('guidance') or ''} {GUIDANCE}".strip()
    if mirror is not None:
        mirror.update({key: result[key] for key in ("missing", "complete_for", "do_not_expand",
                                                    "evidence_sufficiency", "guidance", "stopping")
                       if key in result})
    return True
