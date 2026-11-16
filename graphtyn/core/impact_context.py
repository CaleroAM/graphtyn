"""What a change to a symbol reaches beyond the list of its callers.

An impact package listed who calls a symbol, with file and line. Agents that trust it
(Codex stops after one query) answered with that list and little else: what the symbol
itself returns or raises, what each caller does with the result, who calls the callers
and which tests exercise them stayed out of the answer. Each of those is a few lines here,
read from the indexed files and bounded.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .impact_references import _scan, _symbols_by_file, direct_consumers, label, owner_at
from .path_signals import TEST_PATH

_CODE_CHARS = 160
_LISTED_CALL_LINES = 40
_LISTED_INDIRECT = 12
_LISTED_TESTS = 8
_LISTED_TEST_FILES = 12
_CHECKED_CONSUMERS = 12
_EFFECTS_PER_TARGET = 6
_TARGETS = 3
# A return, a raise or an error the symbol hands back is what its callers depend on.
_EFFECT = re.compile(r"^(?:return|raise|throw|yield)\b|\bthrow\s+new\b|\b(?:Err|panic!|bail!)\(|\berrors?\.New\(")
_TESTS_REQUESTED = re.compile(r"\b(?:tests?|pruebas?|testing|specs?)\b", re.IGNORECASE)
_INDIRECT_REQUESTED = re.compile(r"indirect|transitiv", re.IGNORECASE)
_TRIVIAL_CALLS = {"Some", "None", "Ok", "Err", "is_some", "is_none", "is_ok", "is_err", "unwrap", "expect", "clone",
                  "into", "as_ref", "to_string", "start", "end", "push", "append", "extend", "format", "print",
                  "println", "isinstance", "super", "self", "this", "String", "Vec", "Box", "new"}
_NOT_CODE = {"documentation_section", "doc", "image", "media", "table"}
# The branch a call sits in decides what it means: `if (responseType === 'stream')`, `case 405:`.
_GUARD = re.compile(r"^(?:\}\s*)?(?:if|else\s+if|elif|else|case|catch|except|switch|when|match)\b")
_GUARD_LOOKBACK = 12
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

    def context(self, path: str, number: int) -> str:
        """The call's statement, after the branch that holds it when there is one.

        An agent given only `return settle(resolve, reject, {` read the file to learn the status
        it settles with and under which condition: one extra turn costs more than these words.
        """
        text, lines = self.statement(path, number), self.lines(path)
        if not text or not 0 < number <= len(lines):
            return text
        indent = len(lines[number - 1]) - len(lines[number - 1].lstrip())
        for above in range(number - 1, max(0, number - 1 - _GUARD_LOOKBACK), -1):
            raw = lines[above - 1]
            stripped = raw.strip()
            if not stripped:
                continue
            depth = len(raw) - len(raw.lstrip())
            if depth < indent:
                if _GUARD.match(stripped):
                    return f"{self.line(path, above)} … {text}"[:_CODE_CHARS * 3]
                break
        return text


def _located(row: list[Any]) -> tuple[str, int] | None:
    path, _, number = str(row[1] if len(row) > 1 else "").rpartition(":")
    return (path, int(number)) if path and number.isdigit() else None


def _with_code(rows: list[list[Any]], source: _Source) -> None:
    """[symbol, file:line] → [symbol, file:line, code at that line]."""
    for row in rows:
        place = _located(row)
        if place and len(row) == 2:
            code = source.context(*place)
            if code:
                row.append(code)


def _caller_rows(edges: dict[Any, list[dict]], by_id: dict[Any, dict], source: _Source,
                 via: dict[Any, str] | None = None, symbols: dict[str, list] | None = None) -> list[list[str]]:
    rows, seen = [], set()
    for node_id, links in edges.items():
        node = by_id[node_id]
        if node.get("kind") in _NOT_CODE:
            continue
        for link in links[:1] if node.get("kind") != "file" else links:
            path, number = str(link.get("file") or node.get("file") or ""), int(link.get("line") or node.get("line") or 0)
            name = label(node)
            if node.get("kind") == "file":
                name = str((link.get("resolution") or {}).get("caller") or "") or owner_at(
                    (symbols or {}).get(path, []), source.lines(path), number) or str(node.get("name") or "")
            if not number or (name, path, number) in seen:
                continue
            seen.add((name, path, number))
            row = [name, f"{path}:{number}", source.context(path, number)]
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


def _target_calls(anchors: list[dict], source: _Source) -> list[list[str]]:
    """What the target itself calls, external callees included (`find_byte`, `quit_byte`)."""
    rows = []
    for node in [node for node in anchors if node.get("kind") in {"function", "method"}][:_TARGETS]:
        calls = [op for op in node.get("operations") or [] if op.get("kind") == "call"
                 and len(str(op.get("name") or "")) > 3 and str(op.get("name")) not in _TRIVIAL_CALLS]
        for op in calls[:_EFFECTS_PER_TARGET + 2]:
            rows.append([str(node.get("name") or ""), f"{node.get('file')}:{op.get('line')}", str(op.get("name"))])
    return rows


def _property_readers(root: Path, graph: dict[str, Any], by_id: dict[Any, dict], callers: set[Any],
                      source: _Source) -> list[list[str]]:
    """Readers of a direct consumer that is a Python property: `request.blueprints` calls nothing."""
    rows = []
    properties = [by_id[node_id] for node_id in callers
                  if str(by_id[node_id].get("file") or "").endswith(".py") and by_id[node_id].get("kind") == "method"
                  and (by_id[node_id].get("parameter_count") or 0) <= 1][:2]
    for node in properties:
        found, _truncated = _scan(Path(root), graph, {str(node.get("name"))}, {node.get("id")}, [node])
        for owner, place in found[:_LISTED_INDIRECT]:
            path, _, number = place.rpartition(":")
            rows.append([owner, place, source.line(path, int(number)) if number.isdigit() else "", label(node)])
    return rows


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


def _is_production(node: dict[str, Any]) -> bool:
    path = str(node.get("file") or "")
    return bool(path) and not TEST_PATH.search(path)


def _set_tests_apart(data: dict[str, Any], consumers: dict[str, Any]) -> None:
    """Uses from test files become per-file counts, so they cannot take the production rows' place.

    A public method is called hundreds of times by its tests: in jsoup `Element.select` every
    listed consumer was a test and the agent answered with them, missing the five production
    callers. The tests that exercise the target stay in `related_tests`.
    """
    by_file: Counter[str] = Counter()
    for key in ("others", "text_references", "call_lines"):
        rows = consumers.get(key) or []
        # A mention with no path (a document) is not a test.
        kept = [row for row in rows if not TEST_PATH.search(str(row[1]).rsplit(":", 1)[0])]
        by_file.update(str(row[1]).rsplit(":", 1)[0] for row in rows if row not in kept)
        if len(kept) < len(rows):
            if kept:
                consumers[key] = kept
            else:
                consumers.pop(key, None)
    for key in ("omitted_by_file", "text_references_more_by_file"):
        counts = consumers.get(key)
        if isinstance(counts, dict):
            tests = {path: count for path, count in counts.items() if TEST_PATH.search(path)}
            by_file.update(tests)
            consumers[key] = {path: count for path, count in counts.items() if path not in tests}
    if by_file:
        consumers["test_consumers"] = {"total": sum(by_file.values()),
                                       "by_file": dict(by_file.most_common(_LISTED_TEST_FILES))}
        data["guidance"] = (str(data.get("guidance") or "") + " direct_consumers.test_consumers counts uses in "
                            "test files per file: those tests may need updating; they are not production consumers.").strip()


def _answer_checks(rows: list[list[Any]], effects: list, target_calls: list, indirect: list, tests: list) -> list[str]:
    """What the answer must cover, from what this package found: an agent tends to stop at the caller list."""
    # A document mention has no line: it is not a consumer the answer must name.
    consumers = list(dict.fromkeys(str(row[0]) for row in rows if row and row[0] and _located(row)))[:_CHECKED_CONSUMERS]
    checks = [f"consumers: name each direct consumer ({', '.join(consumers)}) and what it does with the result, from its call line"] \
        if consumers else []
    if effects or target_calls:
        checks.append("target: state what the target returns, raises or calls (target_effects, target_calls)")
    if indirect:
        checks.append("indirect: name who calls the direct consumers and through which one (indirect_consumers)")
    if tests:
        checks.append("tests: list the related_tests that exercise it")
    return checks


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
    symbols = _symbols_by_file(graph)
    shown = {node.get("id") for node in data.get("nodes") or []}
    direct = direct_consumers(graph, by_id, anchor_ids)
    _name_file_callers(consumers.get("others") or [], symbols, source)
    for key in ("others", "text_references"):
        _with_code(consumers.get(key) or [], source)
    covered = {node_id: links for node_id, links in direct.items() if node_id in shown}
    if covered:
        consumers["call_lines"] = _caller_rows(covered, by_id, source, symbols=symbols)[:_LISTED_CALL_LINES]
        listed = {row[1] for row in consumers["call_lines"]}
        # A file-level call is both a covered consumer and an "other" row: list it once.
        others = [row for row in consumers.get("others") or [] if row[1] not in listed]
        if others:
            consumers["others"] = others
        else:
            consumers.pop("others", None)
    effects = _effects(anchors, source)
    if effects:
        data["target_effects"] = effects
    target_calls = _target_calls(anchors, source)
    if target_calls:
        data["target_calls"] = target_calls
    callers = {node_id for node_id in direct if by_id[node_id].get("kind") != "file"}
    second = {node_id: links for node_id, links in direct_consumers(graph, by_id, callers).items()
              if node_id not in anchor_ids and node_id not in callers}
    names = {node_id: label(by_id[node_id]) for node_id in callers}
    indirect = _caller_rows(second, by_id, source, via=names, symbols=symbols)
    known = {(row[0], row[1]) for row in indirect}
    indirect += [row for row in _property_readers(root, graph, by_id, callers, source) if (row[0], row[1]) not in known]
    if indirect:
        data["indirect_consumers"] = {"total": len(indirect), "listed": indirect[:_LISTED_INDIRECT]}
    rows = [*(consumers.get("others") or []), *(consumers.get("text_references") or []),
            *(consumers.get("call_lines") or [])]
    tests = _tests(anchors, graph, rows, indirect)
    if tests:
        data["related_tests"] = tests
    if not _TESTS_REQUESTED.search(str(request or "")) and any(_is_production(node) for node in anchors):
        _set_tests_apart(data, consumers)
        rows = [*(consumers.get("others") or []), *(consumers.get("text_references") or []),
                *(consumers.get("call_lines") or [])]
    data["answer_checks"] = _answer_checks(rows, effects, target_calls, indirect, tests)
    data["guidance"] = (str(data.get("guidance") or "") + " Each consumer row ends with the code at the call: say what "
                        "that caller does with the result. target_effects are the target's own returns and raises; "
                        "indirect_consumers call a direct consumer (last field); related_tests exercise them.").strip()
    gaps = [label for label, wanted, found in (("tests", _TESTS_REQUESTED, tests), ("indirect_consumers", _INDIRECT_REQUESTED, indirect))
            if wanted.search(str(request or "")) and not found]
    target_names = {str(node.get("name") or "") for node in anchors} - {""}
    unsettled = [row[1] for row in consumers.get("text_references") or []
                 if _is_production({"file": str(row[1]).rsplit(":", 1)[0]}) and not _conclusive(row, target_names)]
    if "consumers" not in (data.get("missing") or []) and unsettled:
        # A textual use is a lead; one whose own code shows a call or a reference is settled by that code.
        # Only the others leave the package incomplete, and the agent reads just those lines.
        gaps.append("verify_text_references")
        consumers["verify_lines"] = unsettled[:_CHECKED_CONSUMERS]
        data["guidance"] += (" missing=verify_text_references: read only the direct_consumers.verify_lines, in one "
                             "command with line numbers, and report what they do; do not search more widely.")
    elif consumers.get("text_references"):
        data["guidance"] += " The attached code of each text_references row shows the use: report it from that code."
    if gaps:
        data["missing"] = list(dict.fromkeys([*data.get("missing", []), *gaps]))
        data["complete_for"] = []
        data["do_not_expand"] = False


def _name_file_callers(rows: list[list[Any]], symbols: dict[str, list], source: _Source) -> None:
    """A row named after its file (a call the graph gave to the file) gets the function that makes it."""
    for row in rows:
        place = _located(row)
        if place and str(row[0]) == Path(place[0]).name:
            row[0] = owner_at(symbols.get(place[0], []), source.lines(place[0]), place[1]) or row[0]


def _conclusive(row: list[Any], names: set[str]) -> bool:
    """Whether a text reference's own code shows a use: a call, or the symbol passed or assigned as a value."""
    code = str(row[2] if len(row) > 2 else "").split(" … ")[-1]
    if not code or not names:
        return False
    alternatives = "|".join(re.escape(name) for name in sorted(names))
    call = re.search(rf"(?<![\w$])(?:{alternatives})\s*(?:<[^>]*>)?\s*\(", code)
    value = re.search(rf"(?:[=(,:?]|\b(?:return|typeof|keyof|instanceof)|=>|\|\||&&)\s*(?:[\w$]+\.)*(?:{alternatives})"
                      rf"\s*(?:[),;}}\]]|$)", code)
    return bool(call or value)


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
    while over_budget() and output.get("target_calls"):
        output["target_calls"].pop()
    while over_budget() and output.get("target_effects"):
        output["target_effects"].pop()
    for key in ("indirect_consumers", "related_tests", "target_effects", "target_calls"):
        if not output.get(key) or (key == "indirect_consumers" and not indirect.get("listed")):
            output.pop(key, None)
