"""What a change to a symbol reaches beyond the list of its callers.

An impact package listed who calls a symbol, with file and line. Agents that trust it
(Codex stops after one query) answered with that list and little else: what the symbol
itself returns or raises, what each caller does with the result, who calls the callers
and which tests exercise them stayed out of the answer. Each of those is a few lines here,
read from the indexed files and bounded.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .impact_references import direct_consumers
from .path_signals import TEST_PATH

_CODE_CHARS = 160
_LISTED_CALL_LINES = 40
_LISTED_INDIRECT = 12
_LISTED_TESTS = 8
_EFFECTS_PER_TARGET = 6
_TARGETS = 3
# A return, a raise or an error the symbol hands back is what its callers depend on.
_EFFECT = re.compile(r"^(?:return|raise|throw|yield)\b|\bthrow\s+new\b|\b(?:Err|panic!|bail!)\(|\berrors?\.New\(")
_TESTS_REQUESTED = re.compile(r"\b(?:tests?|pruebas?|testing|specs?)\b", re.IGNORECASE)
_INDIRECT_REQUESTED = re.compile(r"indirect|transitiv", re.IGNORECASE)
_NOT_CODE = {"documentation_section", "doc", "image", "media", "table"}
_GENERIC_TOKENS = {"find", "with", "from", "into", "self", "this", "value", "data", "make", "create", "update",
                   "handle", "process", "test", "tests", "spec", "main", "util", "utils", "helper", "base", "impl"}


class _Source:
    """Lines of indexed files, read once, never outside the project root."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.files: dict[str, list[str]] = {}

    def lines(self, path: str) -> list[str]:
        if path not in self.files:
            source = (self.root / path).resolve()
            try:
                inside = source.is_relative_to(self.root)
                self.files[path] = source.read_text(encoding="utf-8", errors="replace").splitlines() if inside else []
            except OSError:
                self.files[path] = []
        return self.files[path]

    def line(self, path: str, number: int) -> str:
        lines = self.lines(path)
        return " ".join(lines[number - 1].split())[:_CODE_CHARS] if 0 < number <= len(lines) else ""

    def statement(self, path: str, number: int) -> str:
        """The line, and the next ones while its parentheses stay open (`return a or (`)."""
        text, lines = self.line(path, number), self.lines(path)
        depth, following = text.count("(") - text.count(")"), number
        while depth > 0 and following < min(len(lines), number + 4):
            following += 1
            extra = self.line(path, following)
            depth += extra.count("(") - extra.count(")")
            text = f"{text} {extra}"
        return text[:_CODE_CHARS * 2]


def _located(row: list[Any]) -> tuple[str, int] | None:
    path, _, number = str(row[1] if len(row) > 1 else "").rpartition(":")
    return (path, int(number)) if path and number.isdigit() else None


def _with_code(rows: list[list[Any]], source: _Source) -> None:
    """[symbol, file:line] → [symbol, file:line, code at that line]."""
    for row in rows:
        place = _located(row)
        if place and len(row) == 2:
            code = source.line(*place)
            if code:
                row.append(code)


def _caller_rows(edges: dict[Any, list[dict]], by_id: dict[Any, dict], source: _Source,
                 via: dict[Any, str] | None = None) -> list[list[str]]:
    rows, seen = [], set()
    for node_id, links in edges.items():
        node = by_id[node_id]
        if node.get("kind") in _NOT_CODE:
            continue
        for link in links[:1] if node.get("kind") != "file" else links:
            name = str((link.get("resolution") or {}).get("caller") or node.get("name") or "") \
                if node.get("kind") == "file" else str(node.get("name") or "")
            path, number = str(link.get("file") or node.get("file") or ""), int(link.get("line") or node.get("line") or 0)
            if not number or (name, path, number) in seen:
                continue
            seen.add((name, path, number))
            row = [name, f"{path}:{number}", source.line(path, number)]
            if via is not None:
                row.append(via.get(link.get("target"), ""))
            rows.append(row)
    rows.sort(key=lambda row: (bool(TEST_PATH.search(row[1])), row[1]))
    return rows


def _effects(anchors: list[dict], source: _Source) -> list[list[str]]:
    effects = []
    callables = [node for node in anchors if node.get("kind") in {"function", "method"}
                 and not TEST_PATH.search(str(node.get("file") or ""))]
    for node in callables[:_TARGETS]:
        path, start = str(node.get("file") or ""), int(node.get("line") or 0)
        end = int(node.get("end_line") or start)
        found = 0
        for number in range(start, min(end, start + 400) + 1):
            code = source.line(path, number)
            if code and _EFFECT.search(code):
                effects.append([str(node.get("name") or ""), f"{path}:{number}", source.statement(path, number)])
                found += 1
                if found >= _EFFECTS_PER_TARGET:
                    break
    return effects


def _name_tokens(name: str) -> set[str]:
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name)
    return {word.lower() for word in words if len(word) >= 4 and word.lower() not in _GENERIC_TOKENS}


def _tests(anchors: list[dict], graph: dict[str, Any], rows: list[list[Any]], indirect: list[list[str]]) -> list[list[str]]:
    """Test files that use the symbol, call one of its consumers, or are named after it."""
    reasons: dict[str, tuple[int, str]] = {}

    def add(path: str, rank: int, reason: str) -> None:
        if TEST_PATH.search(path) and (path not in reasons or reasons[path][0] > rank):
            reasons[path] = (rank, reason)

    targets = sorted({str(node.get("name") or "") for node in anchors} - {""})
    for row in rows:
        place = _located(row)
        if place:
            add(place[0], 0, f"uses {', '.join(targets)}")
    for row in indirect:
        place = _located(row)
        if place and row[3]:
            add(place[0], 1, f"calls {row[3]}")
    tokens = set().union(*(_name_tokens(name) for name in targets)) if targets else set()
    if tokens:
        for node in graph.get("nodes", []):
            # File nodes keep their path in the id.
            path = str(node.get("file") or str(node.get("id") or "").removeprefix("file:"))
            stem = Path(path).stem.replace("_", " ").replace("-", " ").title().replace(" ", "")
            if node.get("kind") == "file" and TEST_PATH.search(path) and tokens <= _name_tokens(stem):
                add(path, 2, "named after it")
    return [[path, reason] for path, (_rank, reason) in sorted(reasons.items(), key=lambda item: (item[1][0], item[0]))][:_LISTED_TESTS]


def attach_impact_context(root: Path, graph: dict[str, Any] | None, data: dict[str, Any], request: str) -> None:
    """Call lines, the target's own effects, callers of callers and related tests for an impact package."""
    consumers = data.get("direct_consumers")
    if data.get("intent") != "impact" or not graph or not isinstance(consumers, dict):
        return
    by_id = {node.get("id"): node for node in graph.get("nodes", [])}
    anchors = [by_id[node.get("id")] for node in data.get("matched") or [] if node.get("id") in by_id]
    anchor_ids = {node.get("id") for node in anchors}
    if not anchor_ids:
        return
    source = _Source(root)
    shown = {node.get("id") for node in data.get("nodes") or []}
    direct = direct_consumers(graph, by_id, anchor_ids)
    for key in ("others", "text_references"):
        _with_code(consumers.get(key) or [], source)
    covered = {node_id: links for node_id, links in direct.items() if node_id in shown}
    if covered:
        consumers["call_lines"] = _caller_rows(covered, by_id, source)[:_LISTED_CALL_LINES]
    effects = _effects(anchors, source)
    if effects:
        data["target_effects"] = effects
    callers = {node_id for node_id in direct if by_id[node_id].get("kind") != "file"}
    second = {node_id: links for node_id, links in direct_consumers(graph, by_id, callers).items()
              if node_id not in anchor_ids and node_id not in callers}
    names = {node_id: str(by_id[node_id].get("name") or "") for node_id in callers}
    indirect = _caller_rows(second, by_id, source, via=names)
    if indirect:
        data["indirect_consumers"] = {"total": len(indirect), "listed": indirect[:_LISTED_INDIRECT]}
    rows = [*(consumers.get("others") or []), *(consumers.get("text_references") or []),
            *(consumers.get("call_lines") or [])]
    tests = _tests(anchors, graph, rows, indirect)
    if tests:
        data["related_tests"] = tests
    data["guidance"] = (str(data.get("guidance") or "") + " Each consumer row ends with the code at the call: say what "
                        "that caller does with the result. target_effects are the target's own returns and raises; "
                        "indirect_consumers call a direct consumer (last field); related_tests exercise them.").strip()
    gaps = [label for label, wanted, found in (("tests", _TESTS_REQUESTED, tests), ("indirect_consumers", _INDIRECT_REQUESTED, indirect))
            if wanted.search(str(request or "")) and not found]
    if gaps:
        data["missing"] = list(dict.fromkeys([*data.get("missing", []), *gaps]))
        data["complete_for"] = []
        data["do_not_expand"] = False


def shrink_impact_context(output: dict[str, Any], over_budget: Callable[[], bool]) -> None:
    """Give way to the evidence an answer must cite: callers of callers, tests, code, effects."""
    consumers = output.get("direct_consumers") if isinstance(output.get("direct_consumers"), dict) else {}
    indirect = output.get("indirect_consumers") or {}
    while over_budget() and indirect.get("listed"):
        indirect["listed"].pop()
    while over_budget() and output.get("related_tests"):
        output["related_tests"].pop()
    rows = [row for key in ("text_references", "others", "call_lines") for row in reversed(consumers.get(key) or [])]
    for row in rows:
        if not over_budget():
            break
        del row[2:]
    while over_budget() and output.get("target_effects"):
        output["target_effects"].pop()
    for key in ("indirect_consumers", "related_tests", "target_effects"):
        if not output.get(key) or (key == "indirect_consumers" and not indirect.get("listed")):
            output.pop(key, None)
