"""The `lean` rendering of a `graph_query_intent` package.

Drops planner diagnostics, entities unrelated to the evidence and lines that
the source excerpts already print. Shared by the MCP server and the first-turn
prompt hooks.
"""
from __future__ import annotations

import json
import re
from typing import Any


def serialized_tokens(value: dict) -> int:
    """Approximate token count of the compact JSON a client receives."""
    return (len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 3) // 4


def _compact_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def trim_operations(output: dict, token_budget: int) -> None:
    """Drop operations from the last entity that has more than one until the payload fits.

    Re-serializing the whole payload after every removal was quadratic: an entity of Redis with
    thousands of `set` operations kept one query busy for hours. Removing the last element of a
    compact JSON list of two or more shortens it by that element plus its comma, so the byte
    count is tracked exactly and the result is the one the old loop produced.
    """
    size = _compact_bytes(output)
    entities = list(output.get("entities", {}).values())
    while (size + 3) // 4 > token_budget:
        candidate = next((entity for entity in reversed(entities) if len(entity.get("ops") or []) > 1), None)
        if not candidate:
            break
        size -= _compact_bytes(candidate["ops"].pop()) + 1


# Planner and diagnostics fields: useful to debug retrieval, not to answer.
_DEBUG_FIELDS = ("request", "planner", "budget", "source_retrieval", "timing_ms", "evidence_mode",
                 "format", "estimated_tokens", "payload_token_budget", "complete")
_RELATION_INTENTS = {"impact", "bindings", "tests"}


def _excerpt_lines(excerpts: list[dict]) -> dict[str, set[int]]:
    """Line numbers actually printed in each file's excerpts (gaps excluded)."""
    printed: dict[str, set[int]] = {}
    for excerpt in excerpts:
        lines = printed.setdefault(str(excerpt.get("file") or ""), set())
        for line in str(excerpt.get("text") or "").split("\n"):
            number, separator, _ = line.partition(": ")
            if separator and number.isdigit():
                lines.add(int(number))
    return printed


def lean_payload(result: dict) -> dict:
    """Answer-ready subset of an intent package.

    When exact source excerpts already satisfy the request, entities that are
    not connected to that evidence are dropped, operations and signatures
    already printed in an excerpt are not repeated, and diagnostics fields are
    removed. Every omission is counted so the agent knows evidence was pruned.
    """
    output = {key: value for key, value in result.items() if key not in _DEBUG_FIELDS}
    if result.get("format") not in (None, "evidence-v1"):
        output["format"] = result["format"]  # a delta must stay recognisable
    excerpts = output.get("source_evidence") or []
    entities = dict(output.get("entities") or {})
    files = output.get("files") or {}
    relations = output.get("relations") or []
    relational = output.get("intent") in _RELATION_INTENTS or bool(output.get("answer_checks"))
    settled = (excerpts and output.get("do_not_expand")
               and (output.get("source_coverage") or {}).get("complete", True) and not relational)
    if settled and entities:
        text = "\n".join(str(item.get("text") or "") for item in excerpts)
        excerpt_symbols = {str(item.get("symbol") or "") for item in excerpts}
        anchored = set(output.get("matches") or [])
        for aliases in (output.get("obligation_evidence") or {}).values():
            anchored.update(aliases)
        for alias, item in entities.items():
            name = str(item.get("name") or "")
            if name in excerpt_symbols or (name and re.search(rf"\b{re.escape(name)}\b", text)):
                anchored.add(alias)
        kept = set(anchored)
        for relation in relations:
            if relation[0] in anchored or relation[2] in anchored:
                kept.update((relation[0], relation[2]))
        if kept:
            entities = {alias: item for alias, item in entities.items() if alias in kept}
            relations = [relation for relation in relations if relation[0] in kept and relation[2] in kept]
            omitted = len(output.get("entities") or {}) - len(entities)
            if omitted:
                output["omitted_unrelated_entities"] = omitted
    printed = _excerpt_lines(excerpts)
    for alias, item in list(entities.items()):
        file_alias, _, line = str(item.get("at") or "").partition(":")
        shown = printed.get(str(files.get(file_alias) or ""), set())
        if not shown:
            continue
        item = dict(item)
        if line.isdigit() and int(line) in shown:
            item.pop("signature", None)
        ops = [op for op in item.get("ops") or [] if not (isinstance(op[2], int) and op[2] in shown)]
        if ops:
            item["ops"] = ops
        else:
            item.pop("ops", None)
        entities[alias] = item
    if "entities" in output:
        output["entities"] = entities
        output["relations"] = relations
        used_files = {str(item.get("at") or "").partition(":")[0] for item in entities.values()}
        used_files |= {str(entry[2]).partition(":")[0] for entry in output.get("call_outline") or []}
        output["files"] = {alias: path for alias, path in files.items() if alias in used_files}
        names = {str(item.get("name") or "") for item in entities.values()} | {
            str(item.get("symbol") or "") for item in excerpts}
        if output.get("citations"):
            output["citations"] = [citation for citation in output["citations"]
                                   if citation.rsplit(" ", 1)[-1] in names
                                   or citation.split(" ", 1)[-1].split(" → ")[0] in names]
    if relations:
        output["legend"] = "relation=[source,label,target,E|I|A,line?]; why=[line,marker,text]"
    else:
        output.pop("legend", None)
    if not relational:
        output.pop("coverage", None)
        output.pop("negative_evidence", None)
    validation = output.pop("validation", None) or {}
    if not validation.get("ok", True) or validation.get("ambiguous_relations"):
        output["validation"] = {key: validation.get(key) for key in ("ok", "ambiguous_relations", "policy")}
    stopping = output.pop("stopping", None) or {}
    if not output.get("do_not_expand") and stopping:
        output["stopping"] = stopping
    if output.get("guidance"):
        sentences = re.split(r"(?<=[.;])\s+", str(output["guidance"]).strip())
        output["guidance"] = " ".join(dict.fromkeys(sentence for sentence in sentences if sentence))
    context = output.get("project_context")
    if isinstance(context, dict):
        output["project_context"] = {key: context[key] for key in ("workspace", "project_id", "project_name")
                                     if context.get(key)}
    for key in ("not_applicable_obligations", "obligation_evidence", "requested_obligations"):
        if not output.get(key):
            output.pop(key, None)
    output["payload_tokens"] = serialized_tokens(output)
    return output
