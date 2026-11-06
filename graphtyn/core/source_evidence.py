"""Token-bounded source excerpts for questions the graph cannot fully prove."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .impact_references import attach_text_references, consumer_summary, direct_consumers
from .intent_classifier import names_code, without_project_scope
from .vocabulary import COMMON_WORDS


_PRECISION_MARKERS = (
    "exact", "exacto", "exacta", "orden", "sequence", "secuencia",
    "lifecycle", "ciclo de vida", "when", "cuándo", "cuando", "condition",
    "condición", "condicion", "why", "por qué", "porque", "safe", "safety",
    "seguro", "seguridad", "defer", "panic", "timeout", "branch", "rama",
    "deep copy", "copia profunda", "reset", "pool", "trace", "traza",
)

_OBLIGATION_MARKERS = {
    "order_and_control_flow": ("orden", "sequence", "secuencia", "flow", "flujo", "lifecycle", "ciclo de vida"),
    "conditions_and_branches": ("condition", "condición", "condicion", "branch", "rama", "when", "cuándo", "cuando"),
    "state_mutation": ("state", "estado", "reset", "pool", "copy", "copia", "safe", "segur"),
    "failure_semantics": ("panic", "error", "timeout", "recover", "fallo", "defer"),
}

_SOURCE_OBLIGATION_PATTERNS = {
    "validation_gate": re.compile(r"perform_validations\s*\([^)]*\)\s*\?\s*super\s*:\s*false", re.I),
    "save_callbacks": re.compile(r"_run_save_callbacks\s*\{\s*super\s*\}", re.I),
    "create_callbacks": re.compile(r"_run_create_callbacks\s*\{\s*super\s*\}", re.I),
    "transaction_entry": re.compile(r"def\s+save\b[\s\S]{0,300}with_transaction_returning_status\s*\{\s*super\s*\}", re.I),
    "transaction_rollback": re.compile(r"raise\s+ActiveRecord::Rollback\s+unless\s+status", re.I),
    "persistence_adapter": re.compile(r"connection\.(?:insert|update|delete)\s*\(", re.I),
    "save_failure_result": re.compile(
        r"perform_validations\s*\([^)]*\)\s*\?\s*super\s*:\s*false|rescue\s+ActiveRecord::RecordInvalid",
        re.I,
    ),
    "callback_abort": re.compile(r"throw(?:s|ing)?\s+\+?:abort\+?|throw\s*:abort", re.I),
}


# Language-neutral vocabulary that maps request wording to identifiers that
# usually spell the concept in source. Used only to focus long bodies.
_FOCUS_EXPANSIONS = {
    "aridad": ("arity", "argc"), "arity": ("arity", "argc"),
    "autenticación": ("auth",), "autenticacion": ("auth",), "authentication": ("auth",),
    "autorización": ("auth", "perm"), "autorizacion": ("auth", "perm"), "permiso": ("perm",),
    "rechazo": ("reject", "deny", "err"), "rechazos": ("reject", "deny", "err"),
    "rechaza": ("reject", "deny", "err"), "reject": ("reject", "deny", "err"),
    "error": ("err", "fail"), "fallo": ("err", "fail"), "falla": ("err", "fail"),
    "ejecuta": ("call(", "exec", "invoke"), "ejecución": ("call(", "exec", "invoke"),
    "ejecucion": ("call(", "exec", "invoke"), "execute": ("call(", "exec", "invoke"),
    "existencia": ("exist", "unknown", "null"), "existence": ("exist", "unknown", "null"),
    "protegidos": ("protected",), "protegido": ("protected",),
    "reutilización": ("reus", "cache", "last"), "reutilizacion": ("reus", "cache", "last"),
    "bloqueo": ("block", "lock"), "bloqueados": ("block",), "cola": ("queue",),
    "transacción": ("transaction", "multi", "queue"), "transaccion": ("transaction", "multi", "queue"),
    "validación": ("valid", "check"), "validacion": ("valid", "check"),
    "búfer": ("buffer",), "buffer": ("buffer",), "salida": ("out", "write"),
}
_FOCUS_STOPWORDS = {"cómo", "como", "desde", "explica", "menos", "dentro", "donde", "punto",
                    "finalmente", "evidencia", "archivo", "línea", "linea", "cita", "qué", "que",
                    "ocurre", "dos", "ramas", "the", "and", "with", "from", "where", "what"}


_COMMENT_LINE = re.compile(r"\s*(?:/\*|\*|//|#(?!\s*(?:if|else|elif|endif|define|include)\b)|--|\"\"\"|''')")


def _focus_terms(request: str) -> list[str]:
    found = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\w]{2,}", request)
    words = [word.lower() for word in found]
    # Short lowercase words match inside identifiers ("con" in `config_`); DEL or `err` are spelled on purpose.
    terms = [word.lower() for word in found if word.lower() not in _FOCUS_STOPWORDS
             and (len(word) >= 4 or not word.islower()) and word.lower() not in COMMON_WORDS]
    for word in words:
        terms.extend(_FOCUS_EXPANSIONS.get(word, ()))
    return list(dict.fromkeys(terms))


# Explaining a named symbol needs its body: its signature and calls do not say what it does.
_BEHAVIOR_QUESTION = re.compile(
    r"\b(?:qu[eé] hace|c[oó]mo funciona|expl[ií]ca(?:me)?|what does|how does|how do|explain|o que faz|como funciona|"
    r"que fait|comment fonctionne|was macht|wie funktioniert|cosa fa|come funziona)\b", re.IGNORECASE)


# Asks what one symbol does and names nothing inside it: the whole body is the answer.
_WHOLE_SYMBOL_QUESTION = re.compile(
    r"^\W*(?:expl[ií]ca(?:me)?\s+|explain\s+|expliquez\s+|erkl[aä]re\s+|spiega\s+)?"
    r"(?:qu[eé] hace|c[oó]mo funciona|what does|what|how does|how|o que faz|como funciona|que fait|comment fonctionne|"
    r"was macht|wie funktioniert|cosa fa|come funziona)?\s*"
    r"(?:(?:la|el|the|a|o|le|die|der|das|il)\s+)?"
    r"(?:(?:funci[oó]n|m[eé]todo|clase|function|method|class|fun[cç][aã]o|fonction|m[eé]thode|funktion|methode|funzione|metodo)\s+)?"
    r"[`'\"]?(?P<symbol>[A-Za-z_][\w:.#]*)[`'\"]?(?:\(\))?\s*(?:do|does|work|works|macht|fa)?\s*[?.!]?\s*$", re.IGNORECASE)
_ELIDED_LINES = re.compile(r"\(\d+ lines omitted\)")
_LISTED_CALLERS = 15
_SINGLE_ASPECT_WORDS = 16


def whole_symbol_name(request: str) -> str | None:
    """The symbol a question asks to explain as a whole, if that is all it asks."""
    question = re.split(r"[?.!](?:\s|$)", without_project_scope(request).strip(), maxsplit=1)[0]
    match = _WHOLE_SYMBOL_QUESTION.match(question) if _BEHAVIOR_QUESTION.search(question) else None
    return re.split(r"::|\.|#", match["symbol"])[-1].lower() if match else None


def elided_bodies(output: dict[str, Any]) -> list[str]:
    """Whole bodies the package was asked for but delivers with lines missing."""
    wanted = (output.get("source_coverage") or {}).get("whole_bodies") or []
    return [f"source_body:{symbol}" for symbol in wanted
            if any(str(item.get("symbol") or "").lower() == symbol and _ELIDED_LINES.search(str(item.get("text") or ""))
                   for item in output.get("source_evidence") or [])]


def select_evidence_mode(request: str, requested: str = "auto", intent: str = "flow") -> str:
    """Choose source expansion only for questions that need body-level proof."""
    if requested in {"compact", "balanced", "precision"}:
        return requested
    text = str(request or "").lower()
    # A multi-part explanation stays out: more text there flips its stop signal, not its coverage.
    short_question = len(re.split(r"[?.!](?:\s|$)", text.strip(), maxsplit=1)[0].split()) <= _SINGLE_ASPECT_WORDS
    if any(marker in text for marker in _PRECISION_MARKERS) or (
            _BEHAVIOR_QUESTION.search(text) and short_question and names_code(request)):
        return "precision"
    if intent == "flow" and len(re.findall(r"\b(?:and|y|then|después|además|también)\b", text)) >= 2:
        return "balanced"
    return "compact"


def requested_obligations(request: str) -> list[str]:
    text = str(request or "").lower()
    return [name for name, markers in _OBLIGATION_MARKERS.items() if any(marker in text for marker in markers)]


def _explicit_source_symbols(request: str, candidates: list[dict[str, Any]]) -> list[str]:
    """Return code-like symbols that an exact-flow question names explicitly."""
    available = {str(node.get("name") or "").lower() for node in candidates}
    qualified_members = [
        parts[-1].lower()
        for token in re.findall(r"[A-Za-z_][\w]*(?:(?:::|\.|#)[A-Za-z_][\w]*)+", request)
        if len(parts := [part for part in re.split(r"::|\.|#", token) if part]) >= 2
    ]
    underscored = [
        token.lower()
        for token in re.findall(r"(?<!\w)_?[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+", request)
    ]
    # camelCase/PascalCase identifiers (processCommand, ServeHTTP) are as
    # explicit as snake_case ones; plain words never contain an inner capital.
    camel = [token.lower() for token in re.findall(r"(?<!\w)[A-Za-z]+[a-z][A-Z][A-Za-z0-9]*", request)]
    # A selected type whose exact name the request spells ("format_string/fstring")
    # is named on purpose; plain function names stay ambiguous with prose.
    # Case must match exactly: prose "array" or "true" is not the class `Array`.
    words = set(re.findall(r"[A-Za-z_]\w{3,}", request))
    types = [str(node.get("name") or "").lower() for node in candidates
             if node.get("kind") in {"class", "struct", "interface", "type", "union"}
             and str(node.get("name") or "") in words]
    return list(dict.fromkeys(
        symbol for symbol in [*qualified_members, *underscored, *camel, *types] if symbol in available
    ))


def _safe_source(root: Path, relative: str) -> Path | None:
    try:
        root = root.resolve()
        candidate = (root / relative).resolve()
        candidate.relative_to(root)
        return candidate if candidate.is_file() else None
    except (OSError, ValueError):
        return None


def _numbered_excerpt(path: Path, start: int, end: int, line_budget: int) -> tuple[str, int, int]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", 0, 0
    if not lines:
        return "", 0, 0
    start = max(1, min(start, len(lines)))
    end = max(start, min(end, len(lines)))
    if end - start + 1 > line_budget:
        end = start + line_budget - 1
    text = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
    return text, start, end


def _focused_excerpt(path: Path, start: int, end: int, line_budget: int,
                     terms: list[str], char_budget: int = 6_000) -> tuple[str, int, int]:
    """Keep the lines of a long body that match the request, in source order.

    Rare terms weigh more than terms present on every line, so a 400-line
    function contributes its ACL check or final call instead of only its first
    screen. Line numbers stay real, and gaps are marked so citations stay exact.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", 0, 0
    start = max(1, min(start, len(lines)))
    end = max(start, min(end, len(lines)))
    if end - start + 1 <= line_budget or not terms:
        return _numbered_excerpt(path, start, end, line_budget)
    body = range(start, end + 1)
    lowered = {number: lines[number - 1].lower() for number in body}
    frequency = {term: sum(term in text for text in lowered.values()) for term in terms}
    # Square-root damping: a concept the request names on purpose ("reject"
    # branches) recurs on many lines and must not lose to a rare substring.
    weights = {term: count ** -0.5 for term, count in frequency.items() if count}
    # Comments mention terms incidentally ("DELs", "trim"); code lines decide.
    scores = {number: sum(weight for term, weight in weights.items() if term in text)
              * (0.25 if _COMMENT_LINE.match(text) else 1.0)
              for number, text in lowered.items()}
    # Indentation is dropped: the real line number already locates each line.
    cost = {number: len(lines[number - 1].strip()) + len(str(number)) + 3 for number in body}
    keep = {number for number in range(start, min(end, start + 3) + 1)} | {end}
    spent = sum(cost[number] for number in keep)
    for number in sorted(body, key=lambda value: (-scores[value], value)):
        if not scores[number] or len(keep) >= line_budget:
            break
        window = [value for value in range(number - 1, number + 2)
                  if start <= value <= end and value not in keep]
        extra = sum(cost[value] for value in window)
        if spent + extra > char_budget:
            continue
        keep.update(window)
        spent += extra
    rendered, previous = [], None
    for number in sorted(keep):
        if previous is not None and number > previous + 1:
            rendered.append(f"…: ({number - previous - 1} lines omitted)")
        rendered.append(f"{number}: {lines[number - 1].strip()}")
        previous = number
    return "\n".join(rendered), start, end


def _whole_body_excerpt(path: Path, start: int, end: int, char_budget: int = 14_000) -> tuple[str, int, int]:
    """A complete body with real line numbers: comments go first, then the middle."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", 0, 0
    start = max(1, min(start, len(lines)))
    end = max(start, min(end, len(lines)))
    body = list(range(start, end + 1))
    cost = {number: len(lines[number - 1].strip()) + len(str(number)) + 3 for number in body}
    keep = body
    if sum(cost.values()) > char_budget:
        keep = [number for number in body if not _COMMENT_LINE.match(lines[number - 1])]
    dropped_code: set[int] = set()
    while sum(cost[number] for number in keep) > char_budget and len(keep) > 8:
        middle = keep.pop(len(keep) // 2)
        dropped_code.add(middle)
    rendered, previous = [], start - 1
    for number in keep:
        if number > previous + 1:
            gap = range(previous + 1, number)
            label = "lines" if any(value in dropped_code for value in gap) else "comment lines"
            rendered.append(f"…: ({len(gap)} {label} omitted)")
        rendered.append(f"{number}: {lines[number - 1].strip()}")
        previous = number
    return "\n".join(rendered), start, end


def _declaration_comment_start(path: Path, line: int, limit: int = 12) -> int:
    """First line of the comment above a declaration, never another symbol's code."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return line
    start = line
    while start > 1 and line - start < limit and (
            not lines[start - 2].strip() or _COMMENT_LINE.match(lines[start - 2])):
        start -= 1
    while start < line and not lines[start - 1].strip():
        start += 1
    return start


_TYPE_KINDS = {"class", "struct", "interface", "type", "union"}
_BRACE_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".java", ".cs", ".go", ".rs",
                   ".js", ".jsx", ".ts", ".tsx", ".php", ".kt", ".swift", ".scala"}


def _brace_block_end(path: Path, line: int, max_lines: int = 400) -> int | None:
    """Line closing the first `{` opened at or after `line`, ignoring strings and comments."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    depth, opened, in_block = 0, False, False
    for number in range(max(1, line), min(len(lines), line + max_lines) + 1):
        text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', "", lines[number - 1])
        position = 0
        while position < len(text):
            if in_block:
                close = text.find("*/", position)
                if close < 0:
                    break
                in_block, position = False, close + 2
                continue
            if text.startswith("//", position):
                break
            if text.startswith("/*", position):
                in_block, position = True, position + 2
                continue
            char = text[position]
            if char == "{":
                depth, opened = depth + 1, True
            elif char == "}" and opened:
                depth -= 1
                if depth == 0:
                    return number
            position += 1
    return None


def _sync_stopping(result: dict[str, Any]) -> None:
    stopping = result.get("stopping")
    if stopping:
        stopping["sufficient_evidence"] = bool(
            stopping.get("sufficient_evidence") and not result.get("missing")
            and result.get("do_not_expand")
        )


def _collect_candidates(result: dict[str, Any], request: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Graph-selected nodes (and projected route edges) whose bodies may be read."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Framework resolvers often know the exact JSX/TSX line that invokes a
    # backend route even when the parser does not model the nested JSX branch
    # as an operation. Read a tiny edge-centered window before broad symbol
    # bodies so UI permissions and state guards are not cut off.
    request_terms = list(dict.fromkeys([
        *(str(term).lower() for term in result.get("intent_terms", [])),
        *(term.lower() for term in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\w.-]{2,}", request)),
    ]))
    projected = [link for link in result.get("links", []) if link.get("projected_from") and link.get("file") and link.get("line")]
    projected.sort(key=lambda link: (
        -sum(term in f"{link.get('evidence', '')} {link.get('source', '')} {link.get('target', '')}".lower()
             for term in request_terms),
        str(link.get("file")), -int(link.get("line") or 0),
    ))
    projected_keys: set[str] = set()
    for link in projected:
        route_key = str(link.get("evidence") or link.get("target") or "")
        if route_key in projected_keys or len(projected_keys) >= 2:
            continue
        projected_keys.add(route_key)
        line = int(link.get("line") or 1)
        node_id = f"edge:{link.get('file')}:{line}"
        if node_id in seen:
            continue
        seen.add(node_id)
        candidates.append({
            "id": node_id, "name": link.get("evidence") or link.get("label"),
            "kind": "function", "file": link.get("file"),
            "line": max(1, line - 7), "end_line": line + 5,
        })
    for group in (result.get("matched", []), result.get("nodes", [])):
        for node in group:
            node_id = str(node.get("id") or "")
            source_kinds = {"method", "function", "constructor"}
            named_type = (node.get("kind") in {"class", "struct", "interface", "type", "union"}
                          and re.search(rf"(?<!\w){re.escape(str(node.get('name') or ''))}(?!\w)", request) is not None)
            if node_id in seen or (node.get("kind") not in source_kinds and not named_type):
                continue
            if not node.get("file") or not node.get("line"):
                continue
            seen.add(node_id)
            candidates.append(node)
    return candidates, request_terms


def _rank_candidates(result: dict[str, Any], request: str, candidates: list[dict[str, Any]],
                     request_terms: list[str], required_symbols: list[str]) -> dict[str, int]:
    """Order candidates in place; returns how many obligations each node backs."""
    obligation_counts: dict[str, int] = {}
    obligation_weights: dict[str, int] = {}
    priority = {"missing_artifact_behavior": 4, "integrity_schema": 3, "record_identity": 2}
    for label, node_ids in (result.get("obligation_evidence") or {}).items():
        for node_id in node_ids:
            obligation_counts[str(node_id)] = obligation_counts.get(str(node_id), 0) + 1
            obligation_weights[str(node_id)] = obligation_weights.get(str(node_id), 0) + priority.get(label, 1)
    # Ties keep the package's selection order: the entry point before the
    # stages it calls, whatever their paths.
    position = {str(node.get("id") or ""): index for index, node in enumerate(result.get("nodes") or [])}
    candidates.sort(key=lambda node: (
        -int(str(node.get("name") or "").lower() in required_symbols),
        -obligation_weights.get(str(node.get("id") or ""), 0),
        -obligation_counts.get(str(node.get("id") or ""), 0),
        -int(node.get("kind") in {"class", "struct", "interface", "type", "union"}
             and str(node.get("name") or "").lower() in request_terms),
        -sum(term in (
            " ".join(str(node.get(key) or "") for key in ("name", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                                 for op in node.get("operations", []))
        ).lower() for term in request_terms if len(term) >= 5),
        position.get(str(node.get("id") or ""), len(position)),
        str(node.get("file") or ""), int(node.get("line") or 0),
    ))

    qualified = [
        (owner.lower(), member.lower())
        for owner, member in re.findall(r"([A-Za-z_][\w]*)\s*(?:::|\.|#)\s*([A-Za-z_][\w]*)", str(request or ""))
    ]
    primary_file = ""
    for node in candidates:
        signature = " ".join(str(node.get(key) or "") for key in ("container", "signature", "owner_signature")).lower()
        if any(str(node.get("name") or "").lower() == member and re.search(rf"\b{re.escape(owner)}\b", signature)
               for owner, member in qualified):
            primary_file = str(node.get("file") or "")
            break
    if primary_file:
        # Once a qualified declaration is resolved, keep its sibling methods
        # ahead of generic homonyms from unrelated files.
        candidates.sort(key=lambda node: str(node.get("file") or "") != primary_file)

    return obligation_counts


def _select_excerpts(root: Path, candidates: list[dict[str, Any]], required_symbols: list[str],
                     obligation_counts: dict[str, int], focus_terms: list[str], mode: str,
                     max_snippets: int, line_budget: int, char_budget: int,
                     whole_body: bool = False) -> list[dict[str, Any]]:
    """Read bounded, focused excerpts of the ranked candidates."""
    def relevance(node: dict[str, Any]) -> int:
        searchable = (" ".join(str(node.get(key) or "") for key in ("name", "signature", "details"))
                      + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                                       for op in node.get("operations", []))).lower()
        return sum(term in searchable for term in focus_terms if len(term) >= 4)

    excerpts = []
    remaining = char_budget
    resolved_symbols: set[str] = set()
    for node in candidates:
        if len(excerpts) >= max_snippets or remaining < 200:
            break
        node_id = str(node.get("id") or "")
        name = str(node.get("name") or "").lower()
        # The first (best-ranked) declaration answers a named symbol; homonyms
        # in other files must earn their place like any other neighbour.
        required = name in required_symbols and name not in resolved_symbols
        if required:
            resolved_symbols.add(name)
        # With a named entry point, unrelated neighbours only dilute the budget.
        if (required_symbols and not required and not obligation_counts.get(node_id)
                and relevance(node) < 2):
            continue
        source = _safe_source(root, str(node["file"]))
        if not source:
            continue
        start = int(node.get("line") or 1)
        if mode == "precision":
            # Short declaration comments often define failure behavior (for
            # example callback abort semantics) that the AST body omits.
            start = _declaration_comment_start(source, start) if whole_body and required else max(1, start - 12)
        declared_end = int(node.get("end_line") or start + line_budget - 1)
        if node.get("kind") in _TYPE_KINDS and source.suffix.lower() in _BRACE_SUFFIXES:
            # Macro-heavy headers make parsers close a type at its first
            # member body; the braces in the source give the real extent.
            declared_end = max(declared_end, _brace_block_end(source, int(node.get("line") or start)) or 0)
        if whole_body and required:
            text, actual_start, actual_end = _whole_body_excerpt(source, start, declared_end)
        elif focus_terms:
            text, actual_start, actual_end = _focused_excerpt(
                source, start, declared_end, line_budget * (2 if required else 1), focus_terms,
                char_budget=6_000 if required else 2_500)
        else:
            text, actual_start, actual_end = _numbered_excerpt(source, start, declared_end, line_budget)
        text = text[:remaining]
        if not text:
            continue
        excerpts.append({
            "symbol": node.get("name"), "file": node.get("file"),
            "start_line": actual_start, "end_line": actual_end, "text": text,
            "_node_id": str(node.get("id") or ""),
        })
        remaining -= len(text)

    return excerpts


def _record_source_coverage(result: dict[str, Any], excerpts: list[dict[str, Any]], required_symbols: list[str],
                            obligations: list[str], mode: str, max_snippets: int, line_budget: int) -> None:
    """Attach the excerpts and reconcile coverage, missing and stopping."""
    excerpt_ids = {item["_node_id"] for item in excerpts}
    source_obligations = {}
    for label, node_ids in (result.get("obligation_evidence") or {}).items():
        pattern = _SOURCE_OBLIGATION_PATTERNS.get(label)
        source_obligations[label] = (
            any(pattern.search(str(item.get("text") or "")) for item in excerpts)
            if pattern else
            bool(excerpt_ids.intersection(str(node_id) for node_id in node_ids))
        )
    source_symbols = {
        symbol: any(str(item.get("symbol") or "").lower() == symbol for item in excerpts)
        for symbol in required_symbols
    }
    for item in excerpts:
        node_id = item.pop("_node_id")
        item["covers"] = []
        for label, node_ids in (result.get("obligation_evidence") or {}).items():
            pattern = _SOURCE_OBLIGATION_PATTERNS.get(label)
            if ((pattern and pattern.search(str(item.get("text") or "")))
                    or (not pattern and node_id in {str(value) for value in node_ids})):
                item["covers"].append(label)
        symbol = str(item.get("symbol") or "").lower()
        if symbol in required_symbols:
            item["covers"].append(f"source_symbol:{symbol}")
        item["covers"] = list(dict.fromkeys(item["covers"]))

    missing_source = [label for label, covered in source_obligations.items() if not covered]
    missing_source.extend(
        f"source_symbol:{symbol}" for symbol, covered in source_symbols.items() if not covered
    )
    result["source_coverage"] = {
        "required_obligations": source_obligations,
        "required_symbols": source_symbols,
        "complete": not missing_source,
    }
    if missing_source:
        result["missing"] = list(dict.fromkeys([*result.get("missing", []), *missing_source]))
        result["complete_for"] = []

    result["source_evidence"] = excerpts
    result["source_retrieval"] = {
        "enabled": bool(excerpts), "mode": mode, "snippets": len(excerpts),
        "characters": sum(len(item["text"]) for item in excerpts),
        "max_snippets": max_snippets, "line_budget_per_symbol": line_budget,
        "scope": "only graph-selected symbol bodies",
    }
    if excerpts:
        if not missing_source:
            result["complete_for"] = list(dict.fromkeys([*result.get("complete_for", []), *obligations]))
            result["missing"] = [item for item in result.get("missing", []) if item not in obligations]
        # A snippet is evidence for the obligations it actually covers; its
        # mere presence must not override an earlier missing/stopping signal.
        stopping = result.get("stopping") or {}
        result["do_not_expand"] = bool(
            stopping.get("sufficient_evidence", True)
            and not result.get("missing")
            and result.get("validation", {}).get("ok", True)
        )
        source_guidance = (
            "Answer from relations, operations and exact source excerpts. Cite file:line. "
            "Use excerpt order for conditions and control flow; do not re-read these excerpts. "
            "Look up only a part of the request they do not address. "
            "Lines marked as omitted were not read: read those exact ranges if the answer needs them."
        )
        # Source evidence strengthens factual claims.  It must not erase the
        # implementation order and exploration limits chosen by the planner.
        existing_guidance = str(result.get("guidance") or "").strip()
        result["guidance"] = " ".join(
            part for part in (existing_guidance, source_guidance) if part
        )


def _attach_whole_body_context(graph: dict[str, Any] | None, result: dict[str, Any], symbols: list[str]) -> None:
    """Declare whether each body is complete, and who calls the explained symbol."""
    coverage = result.setdefault("source_coverage", {})
    coverage["whole_bodies"] = symbols
    result["guidance"] = (str(result.get("guidance") or "") + " Explain each stage of the body and name its constants, "
                          "flags and callees exactly as written.").strip()
    elided = elided_bodies(result)
    if elided:
        coverage["complete"] = False
        result["missing"] = list(dict.fromkeys([*result.get("missing", []), *elided]))
        result["complete_for"] = []
        result["do_not_expand"] = False
    if graph:
        by_id = {node.get("id"): node for node in graph.get("nodes", [])}
        anchors = {node_id for node_id, node in by_id.items() if str(node.get("name") or "").lower() in symbols}
        summary = consumer_summary(direct_consumers(graph, by_id, anchors), by_id, set())
        summary["omitted"] += max(0, len(summary["others"]) - _LISTED_CALLERS)
        summary["others"] = summary["others"][:_LISTED_CALLERS]
        result["direct_consumers"] = summary


def attach_source_evidence(
    root: Path,
    result: dict[str, Any],
    request: str,
    requested_mode: str = "auto",
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add a few exact symbol bodies when structural evidence is insufficient.

    This runs after graph selection and sends no unrelated files. Limits are
    deliberately small and deterministic. With `graph`, an impact package also
    gets a bounded scan for uses the index did not resolve.
    """
    attach_text_references(root, graph, result)
    mode = select_evidence_mode(request, requested_mode, str(result.get("intent") or "flow"))
    result["evidence_mode"] = mode
    obligations = list(dict.fromkeys([
        *result.get("requested_obligations", []),
        *requested_obligations(request),
    ]))
    result["requested_obligations"] = obligations
    if mode == "compact" or result.get("intent") in {"overview", "impact"}:
        result["source_retrieval"] = {"enabled": False, "reason": "structural evidence is sufficient for this request"}
        _sync_stopping(result)
        return result

    max_snippets = 1 if mode == "balanced" else 10
    line_budget = 60 if mode == "balanced" else 100
    char_budget = 5_000 if mode == "balanced" else 20_000
    candidates, request_terms = _collect_candidates(result, request)
    required_symbols = _explicit_source_symbols(request, candidates) if mode == "precision" else []
    whole_symbol = whole_symbol_name(request) if mode == "precision" else None
    available = {str(node.get("name") or "").lower() for node in candidates}
    whole_symbol = whole_symbol if whole_symbol in available else None
    if whole_symbol and whole_symbol not in required_symbols:
        required_symbols.append(whole_symbol)
    obligation_counts = _rank_candidates(result, request, candidates, request_terms, required_symbols)
    # The words of "what does X do" say nothing about which lines of X matter.
    focus_terms = _focus_terms(request) if mode == "precision" and not whole_symbol else []
    excerpts = _select_excerpts(root, candidates, required_symbols, obligation_counts, focus_terms, mode,
                                max_snippets, line_budget, char_budget, whole_body=bool(whole_symbol))
    _record_source_coverage(result, excerpts, required_symbols, obligations, mode, max_snippets, line_budget)
    if whole_symbol:
        _attach_whole_body_context(graph, result, [whole_symbol])
    _sync_stopping(result)
    return result
