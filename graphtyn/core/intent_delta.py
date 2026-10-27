"""Delta packages for `graph_query_intent` calls that extend a previous context."""
from __future__ import annotations

import hashlib


def _evidence_identities(evidence: dict) -> tuple[dict[str, tuple], set[tuple], dict[str, str]]:
    """Return alias-independent identities for safe context deltas."""
    files = evidence.get("files") or {}
    entity_ids: dict[str, tuple] = {}
    for alias, entity in (evidence.get("entities") or {}).items():
        at = str(entity.get("at") or "")
        file_alias, _, line = at.partition(":")
        entity_ids[alias] = (
            files.get(file_alias, file_alias), line, entity.get("kind"),
            entity.get("namespace"), entity.get("container"), entity.get("name"),
        )
    relations = {
        (entity_ids.get(relation[0]), relation[1], entity_ids.get(relation[2]), *relation[3:])
        for relation in evidence.get("relations", [])
        if len(relation) >= 4
    }
    return entity_ids, relations, files


def _source_evidence_identities(evidence: dict) -> set[tuple[str, int, int, str]]:
    """Identify excerpts independently of ordering and local entity aliases."""
    return {
        (
            str(item.get("file") or ""), int(item.get("start_line") or 0),
            int(item.get("end_line") or 0),
            hashlib.sha256(str(item.get("text") or "").encode("utf-8")).hexdigest()[:12],
        )
        for item in evidence.get("source_evidence", [])
    }


def _intent_delta(previous: dict, previous_id: str, result: dict, raw: dict, context_id: str) -> dict:
    """The part of a follow-up package that the extended context did not already show."""
    old_entity_ids, old_relations, _old_files = _evidence_identities(previous)
    new_entity_ids, _new_relations, _new_files = _evidence_identities(result)
    old_identities = set(old_entity_ids.values())
    new_relations = []
    for relation in result.get("relations", []):
        identity = (new_entity_ids.get(relation[0]), relation[1],
                    new_entity_ids.get(relation[2]), *relation[3:])
        if identity not in old_relations:
            new_relations.append(relation)
    referenced_aliases = {
        endpoint for relation in new_relations for endpoint in (relation[0], relation[2])
    }
    delta_entities = {
        alias: value for alias, value in result.get("entities", {}).items()
        if new_entity_ids.get(alias) not in old_identities or alias in referenced_aliases
    }
    referenced_files = {str(value.get("at") or "").split(":", 1)[0]
                        for value in delta_entities.values() if value.get("at")}
    old_excerpt_ids = _source_evidence_identities(previous)
    new_excerpts = [
        item for item in result.get("source_evidence", [])
        if (
            str(item.get("file") or ""), int(item.get("start_line") or 0),
            int(item.get("end_line") or 0),
            hashlib.sha256(str(item.get("text") or "").encode("utf-8")).hexdigest()[:12],
        ) not in old_excerpt_ids
    ]
    result = {
        "format": "evidence-delta-v1", "extends": previous_id, "context_id": context_id,
        "files": {alias: path for alias, path in result.get("files", {}).items()
                  if alias in referenced_files},
        "entities": delta_entities,
        "relations": new_relations,
        "complete_for": result.get("complete_for", []), "missing": result.get("missing", []),
        "do_not_expand": result.get("do_not_expand", False),
        "stopping": result.get("stopping", {}),
        "guidance": result.get("guidance"),
    }
    if new_excerpts:
        result["source_evidence"] = new_excerpts
    if previous.get("implementation_context") != raw.get("implementation_context") \
            and raw.get("implementation_context"):
        result["implementation_context"] = raw["implementation_context"]
    return result
