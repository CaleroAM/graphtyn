"""What an agent reads, searches and edits after a Graphtyn package, and what it should know first.

A PreToolUse hook calls `handle_tool_hook` before each read, search or edit. It never
blocks a tool. It records the action in the project's activity log (the same opt-in
setting and 30-day retention as the query log) and may return one factual note:

- the latest complete package (`do_not_expand=true`) already includes the file being read,
  or covers the request a search is about;
- no Graphtyn query ran recently and the agent starts a broad search;
- another session edited the same file in the last minutes.

`gaps` turns the log into what packages missed: which files agents still read afterwards.
"""
from __future__ import annotations

import os
import re
import shlex
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .history import HistoryTracker
from .query_log import ACTION as QUERY_ACTION
from .query_log import RETENTION_DAYS, logging_enabled

ACTION = "agent_tool"
HOOK_COMMAND = "graphtyn tool-guard hook"
HOOK_TIMEOUT_SECONDS = 5
# Claude Code tools the hook watches; everything else never starts the hook.
CLAUDE_MATCHER = "Read|Grep|Glob|Bash|Edit|Write|MultiEdit|NotebookEdit"
PACKAGE_WINDOW = 30 * 60
EDIT_WINDOW = 30 * 60
# A read within this time after a query is what that package did not answer.
FOLLOW_WINDOW = 15 * 60
NOTES_PER_PACKAGE = 2
_LISTED_ENTITIES = 4

_TOOLS = {"Read": "read", "NotebookRead": "read", "Grep": "search", "Glob": "search", "LS": "search",
          "Edit": "edit", "Write": "edit", "MultiEdit": "edit", "NotebookEdit": "edit"}
_SEARCH_COMMAND = re.compile(r"^(?:rg|grep|egrep|ag|ack|find|fd|git\s+grep|ls\s+-[a-z]*R)\b")
_READ_COMMAND = re.compile(r"^(?:cat|head|tail|less|more|bat|nl|sed\s+-n)\b")
_AGENT_FAMILIES = ("claude", "codex", "opencode", "antigravity", "gemini", "openclaw", "cursor")


def agent_family(name: str) -> str:
    lowered = str(name or "").lower()
    return next((family for family in _AGENT_FAMILIES if family in lowered), lowered or "?")


def _command_action(command: str) -> tuple[str, str] | None:
    """The first read or search of a shell command line, and its file argument when it has one."""
    for segment in re.split(r"&&|\|\||;|\|", command):
        segment = segment.strip()
        kind = "search" if _SEARCH_COMMAND.match(segment) else "read" if _READ_COMMAND.match(segment) else ""
        if not kind:
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        paths = [word for word in words[1:] if not word.startswith("-") and ("/" in word or "." in word)]
        return kind, (paths[-1] if paths else segment[:120])
    return None


def classify(tool_name: str, tool_input: dict[str, Any]) -> tuple[str, str, list[int]] | None:
    """(read|search|edit, target, [offset, limit]) for a watched tool call, or None."""
    if tool_name == "Bash":
        found = _command_action(str(tool_input.get("command") or ""))
        return (found[0], found[1], []) if found else None
    kind = _TOOLS.get(tool_name)
    if not kind:
        return None
    if kind == "search":
        target = str(tool_input.get("path") or tool_input.get("pattern") or "")
        return kind, target, []
    lines = [int(tool_input[key]) for key in ("offset", "limit") if isinstance(tool_input.get(key), int)]
    return kind, str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""), lines


def project_root(cwd: str | None, explicit: Path | None = None) -> Path | None:
    """The indexed project the hook runs in: the explicit path, or the nearest indexed ancestor."""
    from .storage import data_home, project_store_dir
    candidates = [explicit] if explicit else [Path(cwd or os.getcwd()).resolve(), *Path(cwd or os.getcwd()).resolve().parents][:8]
    for candidate in candidates:
        if candidate and (project_store_dir(data_home(), candidate, create=False) / "index.json").is_file():
            return candidate.resolve()
    return None


def _relative(root: Path, target: str) -> str:
    if not target or not (target.startswith("/") or target.startswith(".")):
        return target
    try:
        return Path(target).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return target


def _package_files(query: dict[str, Any]) -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    for item in query.get("entities") or []:
        if item.get("file"):
            files.setdefault(str(item["file"]), []).append(f"{item.get('name')}:{item.get('line') or ''}")
    for item in query.get("stages") or []:
        if item.get("file"):
            files.setdefault(str(item["file"]), []).append(f"{item.get('callee')}:{item.get('line') or ''}")
    return files


def _latest_package(tracker: HistoryTracker, family: str, now: float) -> dict[str, Any] | None:
    for query in tracker.events_since(QUERY_ACTION, now - PACKAGE_WINDOW, 20):
        if agent_family(query.get("agent") or query.get("source")) == family:
            return query
    return None


def _session_events(tracker: HistoryTracker, session: str, since: float) -> list[dict[str, Any]]:
    return [event for event in tracker.events_since(ACTION, since, 500) if event.get("source") == session]


def _edit_note(tracker: HistoryTracker, session: str, target: str, now: float) -> str:
    for event in tracker.events_since(ACTION, now - EDIT_WINDOW, 500):
        if event.get("kind") == "edit" and event.get("target") == target and event.get("source") != session:
            minutes = max(1, round((now - float(event["timestamp"])) / 60))
            return (f"Graphtyn activity log: a {event.get('agent') or 'another'} session "
                    f"({str(event.get('source'))[:8]}) edited {target} {minutes} min ago; this edit may overlap it.")
    return ""


def _package_note(query: dict[str, Any], kind: str, target: str, now: float) -> str:
    minutes = max(1, round((now - float(query["timestamp"])) / 60))
    files = _package_files(query)
    header = (f"Graphtyn package {query.get('context_id') or ''} ({query.get('intent')}, do_not_expand=true, "
              f"{minutes} min ago) for «{str(query.get('request') or '')[:120]}»")
    if kind == "read" and target in files:
        located = ", ".join(files[target][:_LISTED_ENTITIES])
        return (f"{header} already includes {target}: {located}. Its source_evidence excerpts are in the "
                "conversation; only a range outside them is new.")
    if kind == "search":
        listed = ", ".join(list(files)[:_LISTED_ENTITIES])
        return f"{header} marked its evidence as sufficient; it covers {len(files)} files ({listed})."
    return ""


def handle_tool_hook(payload: dict[str, Any], root: Path | None = None, agent: str = "claude",
                     now: float | None = None) -> dict[str, Any]:
    """Record the tool call and return the note for the agent, if any. Never raises into the client."""
    now = time.time() if now is None else now
    found = classify(str(payload.get("tool_name") or ""), payload.get("tool_input") or {})
    if not found:
        return {"recorded": False, "reason": "not_watched"}
    root = project_root(payload.get("cwd"), root)
    if root is None:
        return {"recorded": False, "reason": "no_index"}
    tracker = HistoryTracker(root)
    tracker.prune_events(ACTION, now - RETENTION_DAYS * 86400)
    if not logging_enabled(tracker):
        return {"recorded": False, "reason": "logging_off"}
    kind, target, lines = found
    target = _relative(root, target)
    session = str(payload.get("session_id") or agent)
    family = agent_family(agent)
    note, note_key = "", ""
    if kind == "edit":
        note = _edit_note(tracker, session, target, now)
        note_key = f"edit:{target}" if note else ""
    else:
        query = _latest_package(tracker, family, now)
        earlier = _session_events(tracker, session, now - PACKAGE_WINDOW)
        if query and query.get("do_not_expand") and query.get("delivered", True):
            key = f"package:{query.get('context_id') or query.get('id')}"
            if sum(event.get("note_key") == key for event in earlier) < NOTES_PER_PACKAGE:
                note = _package_note(query, kind, target, now)
                note_key = key if note else ""
        elif query is None and kind == "search" and not any(event.get("note_key") == "no_query" for event in earlier):
            note = ("No Graphtyn query ran in this project in the last 30 minutes; graph_query_intent returns the "
                    "flow, consumers or impact of a code question with file:line evidence.")
            note_key = "no_query"
    tracker.log_event(session, ACTION, f"{kind} {target}"[:200],
                      {"agent": family, "kind": kind, "target": target[:300], "lines": lines, "note_key": note_key},
                      timestamp=now)
    return {"recorded": True, "kind": kind, "target": target, "note": note}


def hook_output(outcome: dict[str, Any], event: str = "PreToolUse") -> str:
    import json
    if not outcome.get("note"):
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": outcome["note"]}},
                      ensure_ascii=False)


def gaps(tracker: HistoryTracker, days: int = 7, now: float | None = None) -> dict[str, Any]:
    """What agents read after a package: the files it did not include are its gaps."""
    now = time.time() if now is None else now
    since = now - days * 86400
    queries = sorted(tracker.events_since(QUERY_ACTION, since, 2000), key=lambda query: query["timestamp"])
    tools = sorted(tracker.events_since(ACTION, since, 20000), key=lambda event: event["timestamp"])
    followed, after, outside_total = 0, Counter(), 0
    outside: Counter[str] = Counter()
    for index, query in enumerate(queries):
        family = agent_family(query.get("agent") or query.get("source"))
        later = [other["timestamp"] for other in queries[index + 1:]
                 if agent_family(other.get("agent") or other.get("source")) == family]
        end = min([query["timestamp"] + FOLLOW_WINDOW, *later[:1]])
        files = _package_files(query)
        actions = [event for event in tools if event.get("agent") == family
                   and query["timestamp"] <= event["timestamp"] < end and event.get("kind") in {"read", "search"}]
        followed += bool(actions)
        after.update(event["kind"] for event in actions)
        for event in actions:
            if event["kind"] == "read" and event.get("target") not in files:
                outside_total += 1
                outside[str(event.get("target"))] += 1
    return {"days": days, "queries": len(queries), "followed_by_tools": followed,
            "reads_after": after["read"], "searches_after": after["search"], "reads_outside_package": outside_total,
            "top_outside_files": outside.most_common(5), "watched": bool(tools)}


def install(root: str | Path) -> dict[str, Any]:
    from .claude_capture import install_claude_hook
    return install_claude_hook(root, "PreToolUse", HOOK_COMMAND, HOOK_TIMEOUT_SECONDS, matcher=CLAUDE_MATCHER)


def uninstall(root: str | Path) -> dict[str, Any]:
    from .claude_capture import uninstall_claude_hook
    return uninstall_claude_hook(root, "PreToolUse", HOOK_COMMAND)


def installed(root: str | Path) -> bool:
    from .claude_capture import _is_managed, _settings
    _path, data = _settings(Path(root).expanduser().resolve())
    return any(_is_managed(group, HOOK_COMMAND) for group in (data.get("hooks") or {}).get("PreToolUse") or [])
