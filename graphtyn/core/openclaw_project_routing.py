"""Route OpenClaw conversation turns to explicitly identified project memories.

OpenClaw agents often run from a shared/default agent workspace rather than a
repository directory. This router therefore uses an exact registered project
name/alias in a user-authored turn as a project signal, while preserving the
native session and message IDs. Ambiguous or unnamed project references stay
in the agent brain and are reported for review.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from .storage import data_home, unsafe_project_root


_PROJECT_CUE = {"proyecto", "proyectos", "project", "projects", "repo", "repositorio",
                "repository", "carpeta", "folder", "aplicacion", "application", "codigo",
                "codebase", "workspace"}
_OTHER_PROJECT = re.compile(r"\b(?:otro|otra|diferente|distinto|distinta|another|different)\s+(?:proyecto|project)\b")


def _normalize_label(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(value or ""))
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip()


def _label_forms(value: str) -> set[str]:
    raw = str(value or "").strip()
    if not raw:
        return set()
    forms = {_normalize_label(raw)}
    # Users commonly type CamelCase repository names as separate words.
    forms.add(_normalize_label(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw)))
    return {item for item in forms if item}


def registered_project_targets(*, home: Path | None = None) -> list[dict[str, Any]]:
    """Return usable, non-brain project registrations and their known aliases."""
    root = Path(home or data_home())
    registrations_path = root / "registered_projects.json"
    identities_path = root / "project-identities.json"
    try:
        registrations = json.loads(registrations_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        registrations = []
    try:
        identities_payload = json.loads(identities_path.read_text(encoding="utf-8"))
        identities = identities_payload.get("projects", []) if isinstance(identities_payload, dict) else []
    except (OSError, ValueError, TypeError):
        identities = []

    targets: dict[str, dict[str, Any]] = {}
    for row in registrations if isinstance(registrations, list) else []:
        if not isinstance(row, dict) or not row.get("path") or row.get("legacy"):
            continue
        if str(row.get("space_type") or "project").casefold() != "project":
            continue
        if str(row.get("mode") or "").casefold() == "master_folder":
            continue
        try:
            path = Path(str(row["path"])).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if not path.is_dir() or unsafe_project_root(path):
            continue
        key = str(path)
        target = targets.setdefault(key, {
            "id": str(row.get("id") or path.name),
            "name": str(row.get("name") or path.name),
            "path": key,
            "aliases": set(),
            "identity_ids": set(),
        })
        target["aliases"].update({path.name, str(row.get("name") or "")})
        for alias in row.get("aliases") or []:
            if isinstance(alias, str):
                target["aliases"].add(alias)

    for identity in identities if isinstance(identities, list) else []:
        if not isinstance(identity, dict):
            continue
        raw_paths = identity.get("paths") or []
        for raw_path in raw_paths:
            try:
                path_key = str(Path(str(raw_path)).expanduser().resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            target = targets.get(path_key)
            if not target:
                continue
            target["identity_ids"].add(str(identity.get("id") or ""))
            if identity.get("canonical_name"):
                target["aliases"].add(str(identity["canonical_name"]))
            for alias in identity.get("aliases") or []:
                if isinstance(alias, str):
                    target["aliases"].add(alias)

    result = []
    for target in targets.values():
        target["aliases"] = sorted({alias.strip() for alias in target["aliases"] if alias and alias.strip()})
        target["match_forms"] = sorted({form for alias in target["aliases"] for form in _label_forms(alias)})
        identities = sorted(value for value in target.pop("identity_ids") if value)
        # Prefer Graphtyn's stable identity ID when one exists; otherwise the
        # registered project ID remains stable enough for local routing.
        if identities:
            target["id"] = identities[0]
        result.append(target)
    return sorted(result, key=lambda item: (item["name"].casefold(), item["path"]))


def resolve_registered_project(hint: str, *, targets: list[dict[str, Any]] | None = None,
                               home: Path | None = None
                               ) -> dict[str, Any]:
    """Resolve an exact project ID, name, alias, or registered path.

    This intentionally avoids substring and fuzzy matching: memory retrieval
    must never silently select one project when the request could mean another.
    """
    value = str(hint or "").strip()
    projects = targets if targets is not None else registered_project_targets(home=home)
    if not value:
        return {"status": "unresolved", "project": None, "candidates": []}

    path_matches = []
    if any(mark in value for mark in ("/", "\\", "~")):
        try:
            normalized_path = str(Path(value).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            normalized_path = ""
        if normalized_path:
            path_matches = [project for project in projects if project.get("path") == normalized_path]
    if path_matches:
        matches = path_matches
    else:
        normalized = _normalize_label(value)
        matches = [project for project in projects
                   if normalized and normalized in {
                       _normalize_label(project.get("id", "")),
                       _normalize_label(project.get("name", "")),
                       *project.get("match_forms", []),
                   }]

    # A stable identity ID takes precedence over a colliding display alias.
    id_matches = [project for project in matches
                  if _normalize_label(project.get("id", "")) == _normalize_label(value)]
    if len(id_matches) == 1:
        return {"status": "matched", "project": id_matches[0], "candidates": []}
    if len(matches) == 1:
        return {"status": "matched", "project": matches[0], "candidates": []}
    candidates = [{"id": item.get("id"), "name": item.get("name")} for item in matches]
    return {"status": "ambiguous" if matches else "unresolved", "project": None,
            "candidates": candidates}


def _alias_in_text(text: str, alias: str) -> bool:
    normalized_text = _normalize_label(text)
    if not normalized_text or not alias:
        return False
    padded_text = f" {normalized_text} "
    padded_alias = f" {alias} "
    start = padded_text.find(padded_alias)
    if start < 0:
        return False
    # Short acronyms are easy to mention as ordinary nouns. Require project
    # language nearby unless the name itself is multiword.
    if len(alias.replace(" ", "")) >= 5 or " " in alias:
        return True
    words_before = padded_text[:start].split()[-4:]
    words_after = padded_text[start + len(padded_alias):].split()[:4]
    return bool(_PROJECT_CUE.intersection(words_before + words_after))


def _alias_has_project_cue(text: str, alias: str) -> bool:
    """Whether a registered name is locally identified as a project target."""
    normalized_text = _normalize_label(text)
    if not normalized_text or not alias:
        return False
    padded_text = f" {normalized_text} "
    padded_alias = f" {alias} "
    start = 0
    while True:
        index = padded_text.find(padded_alias, start)
        if index < 0:
            return False
        words_before = padded_text[:index].split()[-2:]
        words_after = padded_text[index + len(padded_alias):].split()[:2]
        if _PROJECT_CUE.intersection(words_before + words_after):
            return True
        start = index + len(padded_alias)


def _mentioned_targets(text: str, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = []
    project_cued = []
    for target in targets:
        aliases = [alias for alias in target.get("match_forms", []) if _alias_in_text(text, alias)]
        if aliases:
            matched.append(target)
            if any(_alias_has_project_cue(text, alias) for alias in aliases):
                project_cued.append(target)
    # A named tool/product may share its name with a registered project. When
    # one target is explicitly introduced as a project/repository, incidental
    # mentions of other registered names must not make that turn ambiguous.
    return project_cued or matched


def _workspace_target(value: str | None, targets: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        workspace = Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    matches = []
    for target in targets:
        path = Path(target["path"])
        if workspace == path or path in workspace.parents:
            matches.append(target)
    return max(matches, key=lambda item: len(Path(item["path"]).parts), default=None)


def _fingerprint(session: dict[str, Any], messages: list[dict[str, Any]], project_id: str = "") -> str:
    payload = {
        "provider": session.get("provider"), "agent_id": session.get("agent_id"),
        "external_session_id": session.get("external_session_id"), "project_id": project_id,
        "messages": [{"role": item.get("role"), "content": item.get("content"),
                      "source_message_id": (item.get("metadata") or {}).get("source_message_id")}
                     for item in messages],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def route_openclaw_sessions(sessions: list[dict[str, Any]], *, targets: list[dict[str, Any]] | None = None
                            ) -> dict[str, Any]:
    """Split captured sessions by explicit project turns without guessing.

    A registered project path in the session workspace is a strong default.
    Otherwise a user-authored message must identify a registered project. A
    nearby project cue takes priority over incidental mentions of other target
    names. The active project is carried across follow-up turns and changes
    when a new project is explicitly named. A message naming several projects
    explicitly suspends routing until the user identifies one.
    """
    targets = targets if targets is not None else registered_project_targets()
    by_path = {item["path"]: item for item in targets}
    segments: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    for session in sessions:
        messages = [item for item in session.get("messages") or [] if isinstance(item, dict)]
        source_id = str(session.get("external_session_id") or "")
        agent_id = str(session.get("agent_id") or "").casefold()
        provider = str(session.get("provider") or "openclaw").casefold()
        source_fingerprint = str(session.get("fingerprint") or _fingerprint(session, messages))
        active = _workspace_target(session.get("workspace"), targets)
        reasons: dict[str, str] = {active["path"]: "registered_workspace"} if active else {}
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        ambiguous_turns = 0
        unnamed_switches = 0
        unassigned_messages = 0
        for message in messages:
            role = str(message.get("role") or "").casefold()
            content = str(message.get("content") or "")
            if role == "user":
                matches = _mentioned_targets(content, targets)
                if len(matches) == 1:
                    active = matches[0]
                    reasons.setdefault(active["path"], "explicit_project_name")
                elif len(matches) > 1:
                    active = None
                    ambiguous_turns += 1
                elif _OTHER_PROJECT.search(_normalize_label(content)):
                    active = None
                    unnamed_switches += 1
            if active:
                grouped[active["path"]].append(message)
            else:
                unassigned_messages += 1

        routed_projects = []
        for path, routed_messages in grouped.items():
            target = by_path[path]
            project_id = str(target["id"])
            route_method = reasons.get(path, "explicit_project_name")
            source_workspace = str(session.get("workspace") or "")
            routed_message_rows = []
            for index, message in enumerate(routed_messages):
                metadata = dict(message.get("metadata") or {})
                metadata.update({
                    "provider": provider,
                    "source_session_id": source_id,
                    "project_id": project_id,
                    "project_name": target["name"],
                    "project_path": target["path"],
                    "project_route_method": route_method,
                    "capture_mode": "project_routed_incremental",
                })
                if source_workspace:
                    metadata["source_workspace"] = source_workspace
                metadata.setdefault("source_message_id", f"{source_id}:{index}")
                routed_message_rows.append({**message, "metadata": metadata})
            external_id = f"openclaw-project:{source_id}:{project_id}"
            stamps = [(item.get("metadata") or {}).get("occurred_at") for item in routed_message_rows]
            stamps = [float(value) for value in stamps if isinstance(value, (int, float))]
            segment = {
                "provider": provider,
                "agent_id": agent_id,
                "external_session_id": external_id,
                "source_external_session_id": source_id,
                "task": f"{target['name']}: {str(session.get('task') or 'OpenClaw conversation')[:140]}",
                "messages": routed_message_rows,
                "source": session.get("source"),
                "workspace": target["path"],
                "explicit_project_selection": True,
                "capture_mode": "project_routed_incremental",
                "project_id": project_id,
                "project_name": target["name"],
                "project_path": target["path"],
                "project_route_method": route_method,
                "source_fingerprint": source_fingerprint,
                "fingerprint": _fingerprint(session, routed_message_rows, project_id),
                "occurred_at": min(stamps, default=session.get("occurred_at")),
                "updated_at": max(stamps, default=session.get("updated_at")),
                "message_count": len(routed_message_rows),
            }
            segments.append(segment)
            routed_projects.append({"id": project_id, "name": target["name"], "path": target["path"],
                                    "messages": len(routed_messages), "method": route_method})

        status = ("partial" if routed_projects and (ambiguous_turns or unnamed_switches or unassigned_messages)
                  else "routed" if routed_projects else "ambiguous" if ambiguous_turns or unnamed_switches
                  else "unassigned")
        states.append({
            "provider": provider, "agent_id": agent_id, "external_session_id": source_id,
            "source_fingerprint": source_fingerprint, "message_count": len(messages),
            "routed_message_count": sum(item["messages"] for item in routed_projects),
            "status": status, "projects": routed_projects,
            "ambiguous_turns": ambiguous_turns, "unnamed_project_switches": unnamed_switches,
            "unassigned_messages": unassigned_messages,
            "reason": ("multiple registered projects named in one user turn" if ambiguous_turns else
                       "project switch mentioned without a registered project name" if unnamed_switches else
                       "no registered project name or matching workspace" if not routed_projects else ""),
        })
    return {"segments": segments, "sessions": states,
            "summary": {
                "discovered_sessions": len(states),
                "routed_sessions": sum(bool(row["projects"]) for row in states),
                "routed_segments": len(segments),
                "routed_messages": sum(row["routed_message_count"] for row in states),
                "partial_sessions": sum(row["status"] == "partial" for row in states),
                "ambiguous_sessions": sum(row["status"] == "ambiguous" for row in states),
                "unassigned_sessions": sum(row["status"] == "unassigned" for row in states),
            }}
