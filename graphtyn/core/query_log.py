"""What agents asked Graphtyn and what they received, for the dashboard's activity panel.

Reasons are derived afterwards from the package: they explain a selection without
taking part in it. Logging must never break the query it describes.
"""
from __future__ import annotations

import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from .history import HistoryTracker

ACTION = "query_intent"
RETENTION_DAYS = 30
# In the project's database, not the environment: clients launch MCP and hooks with their own.
LOGGING_SETTING = "activity_log"
MAX_ENTITIES = 24
MAX_STAGES = 40
_MIN_TERM = 4


def _plain(text: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _shared_terms(node: dict[str, Any], terms: list[str]) -> list[str]:
    haystack = _plain(f"{node.get('name')} {node.get('file')}")
    return [term for term in terms if len(_plain(term)) >= _MIN_TERM and _plain(term) in haystack]


def _relation_reason(node_id: str, links: list[dict[str, Any]], names: dict[str, str]) -> str:
    for link in links:
        source, target = str(link.get("source")), str(link.get("target"))
        if target == node_id and source in names:
            return f"«{link.get('label')}» desde {names[source]}"
        if source == node_id and target in names:
            return f"«{link.get('label')}» hacia {names[target]}"
    return ""


def selection_reasons(package: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Why each entity of the package is there, by node id."""
    nodes = [node for node in package.get("nodes") or [] if node.get("id")]
    terms = [str(term) for term in package.get("intent_terms") or []]
    names = {str(node["id"]): str(node.get("name") or node["id"]) for node in nodes}
    reasons = {}
    for node in nodes:
        node_id = str(node["id"])
        shared = _shared_terms(node, terms)
        relation = _relation_reason(node_id, package.get("links") or [], names)
        if shared:
            reasons[node_id] = {"kind": "terms", "text": "Coincide con: " + ", ".join(shared)}
        elif relation:
            reasons[node_id] = {"kind": "relation", "text": "Relación " + relation}
        else:
            reasons[node_id] = {"kind": "index", "text": "La eligió la búsqueda del índice; no comparte palabras con la pregunta"}
    return reasons


def query_record(package: dict[str, Any], *, source: str, agent: str, request: str, workspace: Path,
                 result: dict[str, Any] | None = None, context_id: str = "", extends: str = "") -> dict[str, Any]:
    """The bounded log entry for one package; `result` is what the client received, when rendered."""
    delivered = result if result is not None else package
    reasons = selection_reasons(package)
    return {
        "agent": agent, "source": source, "request": request[:240], "intent": package.get("intent"),
        "context_id": context_id, "extends_context_id": extends, "workspace": str(workspace),
        "do_not_expand": bool(delivered.get("do_not_expand")), "complete_for": delivered.get("complete_for") or [],
        "missing": delivered.get("missing") or [],
        "delivered": bool(delivered.get("source_evidence") or delivered.get("do_not_expand")),
        "estimated_tokens": delivered.get("estimated_tokens", delivered.get("payload_tokens")),
        "entities": [{"id": node["id"], "name": node.get("name"), "kind": node.get("kind"), "file": node.get("file"),
                      "line": node.get("line"), "why": reasons.get(str(node["id"]))}
                     for node in (package.get("nodes") or [])[:MAX_ENTITIES] if node.get("id")],
        "stages": [{"caller": item.get("caller"), "callee": item.get("callee"), "file": item.get("file"),
                    "line": item.get("line"), "kind": str(item.get("confidence") or "EXTRACTED")[:1]}
                   for item in (package.get("call_outline") or [])[:MAX_STAGES] if isinstance(item, dict)],
    }


def record_query(workspace: Path, package: dict[str, Any], *, source: str, agent: str = "", request: str = "",
                 result: dict[str, Any] | None = None, context_id: str = "", extends: str = "",
                 tracker: HistoryTracker | None = None) -> None:
    try:
        tracker = tracker or HistoryTracker(workspace)
        prune_queries(tracker)
        if not logging_enabled(tracker):
            return
        details = query_record(package, source=source, agent=agent or source, request=request or str(package.get("request") or ""),
                               workspace=workspace, result=result, context_id=context_id, extends=extends)
        tracker.log_event(source, ACTION, f"Consulta {details['intent']} de una ronda", details)
    except Exception:  # noqa: BLE001 - the activity log never breaks a query
        pass


def logging_enabled(tracker: HistoryTracker) -> bool:
    return tracker.get_setting(LOGGING_SETTING, "on") != "off"


def set_logging(tracker: HistoryTracker, enabled: bool) -> None:
    tracker.set_setting(LOGGING_SETTING, "on" if enabled else "off")


def prune_queries(tracker: HistoryTracker, now: float | None = None) -> int:
    """Questions are the user's words: they do not outlive the retention window, even with logging off."""
    return tracker.prune_events(ACTION, (now if now is not None else time.time()) - RETENTION_DAYS * 86400)


def recent_queries(tracker: HistoryTracker, limit: int = 30, days: int = RETENTION_DAYS) -> list[dict[str, Any]]:
    return tracker.events_since(ACTION, time.time() - days * 86400, limit)


def usage_summary(queries: list[dict[str, Any]], days: int = 7) -> dict[str, Any]:
    """What passes through Graphtyn; what an agent reads afterwards is not visible from here."""
    since = time.time() - days * 86400
    queries = [query for query in queries if query.get("timestamp", since) >= since]
    files: Counter[str] = Counter()
    for query in queries:
        files.update({str(item["file"]) for item in query.get("entities") or [] if item.get("file")})
    return {
        "days": days,
        "queries": len(queries),
        "by_agent": dict(Counter(str(query.get("agent") or query.get("source") or "?") for query in queries).most_common()),
        "sufficient": sum(1 for query in queries if query.get("do_not_expand")),
        "extended": sum(1 for query in queries if query.get("extends_context_id")),
        "not_delivered": sum(1 for query in queries if query.get("delivered") is False),
        "top_files": files.most_common(5),
    }
