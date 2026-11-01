"""Lexical and structural ranking signals shared by intent retrieval."""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from .path_signals import TEST_PATH, VENDORED_PATH
from .vocabulary import COMMON_WORDS, is_prose_word

BEHAVIOR_KINDS = {"function", "method", "def"}
HOMONYM_CAP = 2
# Flow package policy, measured on benchmarks/task_bank_2026-10-28 (fifth
# round). A flow keeps FLOW_NODE_CAP entities: a larger cap squeezes the source
# excerpts out of the fixed token budget and lost coverage on held-out tasks.
# Half of it (CHAIN_SHARE) is reserved for the stages the leading entry point
# (CHAIN_SEEDS) calls up to CHAIN_DEPTH hops away, skipping utilities with more
# than UTILITY_FAN_IN callers; OUTLINE_LIMIT further stages are listed by name
# and location only. COMMAND_NAMES maps a command written in capitals (BLPOP)
# to its handler (blpopCommand). The benchmarks switch these to compare policies.
FLOW_NODE_CAP = 9
CHAIN_SHARE = 0.5
CHAIN_SEEDS = 1
CHAIN_DEPTH = 3
UTILITY_FAN_IN = 12
OUTLINE_LIMIT = 12
COMMAND_NAMES = True
# STATE_LIMIT outline entries join a stage to functions that use the same rare
# state field (`server.ready_keys`): flows handed over through shared state.
STATE_LIMIT = 4
# CITE_STAGES asks the agent to name every stage of the flow it relies on.
CITE_STAGES = False
CITE_STAGES_GUIDANCE = (" Name every stage of the flow your answer relies on, from entities and call_outline,"
                        " each with its file:line; a stage you leave out is a gap in the answer.")
STATE_FAN = 6
_POLICY_KEYS = ("FLOW_NODE_CAP", "CHAIN_SHARE", "CHAIN_SEEDS", "CHAIN_DEPTH", "UTILITY_FAN_IN", "OUTLINE_LIMIT",
                "COMMAND_NAMES", "STATE_LIMIT", "STATE_FAN", "FOREIGN_ANCHORS", "KEEP_HANDLERS_OUTSIDE_ANCHORS",
                "CITE_STAGES")


def apply_flow_policy(spec: str) -> dict[str, Any]:
    """Override the flow policy from `KEY=VALUE,...` (GRAPHTYN_FLOW_POLICY); returns what changed."""
    changed: dict[str, Any] = {}
    for pair in filter(None, (part.strip() for part in str(spec or "").split(","))):
        key, _, value = pair.partition("=")
        key = key.strip().upper()
        if key not in _POLICY_KEYS:
            raise ValueError(f"unknown flow policy key {key!r}; expected one of {', '.join(_POLICY_KEYS)}")
        current = globals()[key]
        converted = (value.strip().lower() in ("1", "true", "yes") if isinstance(current, bool)
                     else type(current)(float(value)) if isinstance(current, (int, float)) else value)
        globals()[key] = changed[key] = converted
    return changed


_FIELD = re.compile(r"(?:->|\.)([A-Za-z_]\w{3,})\b(?!\s*\()|@([A-Za-z_]\w{3,})")
_FIELD_INDEX: dict[int, tuple[int, dict[str, set[Any]]]] = {}
# Bundled third-party code (`deps/jemalloc/…`) never anchors a package unless
# the request names it; KEEP_HANDLERS_OUTSIDE_ANCHORS keeps command handlers of
# other files through the anchor-file partition.
FOREIGN_ANCHORS = True
KEEP_HANDLERS_OUTSIDE_ANCHORS = True
_FOREIGN_DIR = re.compile(r"(?:^|/)(?:deps|vendor|vendored|third_party|third-party|external|node_modules)/([^/]+)/", re.I)
_HANDLER_FORMS = ("{}command", "{}_command", "cmd_{}", "{}cmd", "{}_cmd")


class NameFrequency:
    """How many callable names spell each request term.

    A term spelled by few callable names is distinctive (``evict`` in
    ``performEvictions``); one spelled by a large share of them (``redis`` in
    Redis, ``format`` in fmt) says nothing about which of them a request means.
    """

    def __init__(self, nodes: list[dict[str, Any]], terms: list[str], generic: set[str]) -> None:
        production = [node for node in nodes if not TEST_PATH.search(str(node.get("file") or ""))]
        names = [str(node.get("name") or "").lower() for node in nodes if node.get("kind") in BEHAVIOR_KINDS]
        self.ceiling = max(25, len(names) // 400)
        blob = "\n".join(names)
        self.structural = _structural_segments(production)
        self.counts = {term: blob.count(term) for term in dict.fromkeys(term.lower() for term in terms)
                       if len(term) >= 5 and term not in generic and term not in COMMON_WORDS
                       and not is_prose_word(term) and _normalized(term) not in self.structural}
        self.distinctive = [term for term, count in self.counts.items() if 0 < count <= self.ceiling]

    def pervasive(self, term: str) -> bool:
        """A term spelled by too many names, or naming a directory of the tree (``activerecord``)."""
        return self.counts.get(term, 0) > 4 * self.ceiling or _normalized(term) in self.structural

    def hits(self, name: str) -> int:
        lowered = name.lower()
        return min(2, sum(term in lowered and term != lowered for term in self.distinctive))


class HomonymHints:
    """What a request says about which homonym of a named method it means.

    The owner it describes (`persistido` → `Persistence#update`) and a call form
    written with its arguments (`update(attributes)`) that only one declaration's
    signature spells.
    """

    def __init__(self, request: str, terms: list[str], generic: set[str]) -> None:
        self.owner_terms = [term for term in dict.fromkeys(terms)
                            if len(term) >= 5 and term not in COMMON_WORDS and term not in generic]
        self.call_forms = {re.sub(r"\s+", "", form).lower()
                           for form in re.findall(r"\b[A-Za-z_]\w*\([^()]{1,60}\)", str(request or ""))}

    def owner_match(self, node: dict[str, Any]) -> bool:
        return self.owner_score(node) > 0

    def owner_score(self, node: dict[str, Any]) -> int:
        """Request terms in the owner: the class itself (`AutosaveAssociation`) counts twice its namespace."""
        container = str(node.get("container") or "").lower()
        namespace = str(node.get("namespace") or "").lower()
        return sum(2 * (term in container) + (term in namespace) for term in self.owner_terms)

    def signature_match(self, node: dict[str, Any]) -> bool:
        signature = re.sub(r"\s+", "", str(node.get("signature") or "")).lower()
        return any(form in signature for form in self.call_forms)


def _normalized(term: str) -> str:
    return term.lower().replace("_", "").replace("-", "")


def _structural_segments(nodes: list[dict[str, Any]], share: int = 20) -> set[str]:
    """Directory names that contain at least 1/`share` of the indexed files."""
    files = {str(node.get("file") or "").replace("\\", "/") for node in nodes if node.get("file")}
    counts: dict[str, int] = {}
    for path in files:
        for segment in set(path.split("/")[:-1]):
            counts[_normalized(segment)] = counts.get(_normalized(segment), 0) + 1
    floor = max(20, len(files) // share)
    return {segment for segment, count in counts.items() if count >= floor and len(segment) >= 3}


def with_call_chain(graph: dict[str, Any], ranked: list[tuple[int, dict[str, Any]]],
                    name_frequency: NameFrequency, keep_first: set[Any],
                    seeds: int = 1, limit: int = 4, depth: int = 3,
                    reserved: int = 0, budget: int = 0) -> list[tuple[int, dict[str, Any]]]:
    """Place the stages a leading entry point calls right after it.

    A flow continues through the functions its entry point calls even when
    their names share no word with the request (``format_to_n`` →
    ``vformat_to_n``, ``update`` → ``save`` → ``create_or_update`` →
    ``_update_record``). A callee is a stage when it spells a distinctive
    request term, was already retrieved, or is a sibling method of its caller
    reached through an extracted call; unrelated helpers (logging, allocation)
    are not. Nearer stages and those spelling request terms go first.
    """
    by_id = {node.get("id"): node for node in graph.get("nodes", [])}
    calls: dict[Any, list[dict[str, Any]]] = {}
    for link in graph.get("links", []):
        if link.get("label") == "llama" and str(link.get("confidence") or "") != "AMBIGUOUS":
            calls.setdefault(link.get("source"), []).append(link)
    if reserved:
        seeds, limit, depth = CHAIN_SEEDS, reserved, CHAIN_DEPTH
    callers: dict[Any, set[Any]] = {}
    for caller_id, links in calls.items():
        for link in links:
            callers.setdefault(link.get("target"), set()).add(caller_id)
    seed_items = [item for item in ranked[:4]
                  if item[1].get("kind") in BEHAVIOR_KINDS and item[1].get("id") in calls
                  and not TEST_PATH.search(str(item[1].get("file") or ""))][:seeds]
    if not seed_items:
        return ranked
    seed_ids = {item[1].get("id") for item in seed_items}
    ranked_ids = {item[1].get("id") for item in ranked}
    stages: dict[Any, tuple[int, int]] = {}
    frontier = list(seed_ids)
    for level in range(depth):
        following = []
        for caller_id in frontier:
            caller = by_id.get(caller_id) or {}
            for link in calls.get(caller_id, []):
                target = link.get("target")
                node = by_id.get(target)
                if (not node or target in seed_ids or target in stages or node.get("kind") not in BEHAVIOR_KINDS
                        or TEST_PATH.search(str(node.get("file") or ""))
                        or VENDORED_PATH.search(str(node.get("file") or ""))):
                    continue
                hits = name_frequency.hits(str(node.get("name") or ""))
                # Another method of the same object: an extracted same-class call,
                # or a Ruby self call or `super` resolved along the ancestors.
                sibling = (str((link.get("resolution") or {}).get("strategy") or "").startswith("ruby-")
                           or (str(link.get("confidence") or "EXTRACTED") == "EXTRACTED"
                               and node.get("file") == caller.get("file")
                               and node.get("container") == caller.get("container")))
                # With a reserved budget any callee is a stage unless it is a
                # utility called from everywhere (logging, allocation, replies).
                open_stage = reserved and len(callers.get(target, ())) <= UTILITY_FAN_IN
                if hits or target in ranked_ids or sibling or open_stage:
                    stages[target] = (level, hits)
                    following.append(target)
        frontier = following
    # The entry point's own class carries the flow's main line; stages from
    # other owners (transaction or logging wrappers) come after it.
    owners = {(by_id[seed_id].get("file"), by_id[seed_id].get("container")) for seed_id in seed_ids}
    chosen = sorted(stages, key=lambda node_id: (
        (by_id[node_id].get("file"), by_id[node_id].get("container")) not in owners,
        stages[node_id][0], -stages[node_id][1], str(node_id)))[:limit]
    if not chosen:
        return ranked
    # Stages follow the seeds and every mandatory representative, so a named
    # obligation never loses its slot to a stage the graph inferred.
    last_seed = max(index for index, item in enumerate(ranked)
                    if item[1].get("id") in seed_ids or item[1].get("id") in keep_first)
    if reserved:
        # A reserved share comes before the representatives that do not fit
        # the rest of the budget: they are lexical guesses, the stages are
        # what the entry point executes.
        last_seed = min(last_seed, max(max(budget - reserved, 1) - 1,
                                       max(index for index, item in enumerate(ranked)
                                           if item[1].get("id") in seed_ids)))
    chain = [(ranked[last_seed][0], dict(by_id[node_id])) for node_id in chosen]
    chosen_ids = set(chosen)
    head = [item for item in ranked[:last_seed + 1] if item[1].get("id") not in chosen_ids]
    tail = [item for item in ranked[last_seed + 1:] if item[1].get("id") not in chosen_ids]
    return head + chain + tail


def call_outline(graph: dict[str, Any], selected: list[dict[str, Any]], name_frequency: NameFrequency,
                 limit: int, seeds: int = 2, depth: int = 3) -> list[dict[str, Any]]:
    """Call stages beyond the package, by name and location only.

    A flow's deeper stages rarely share a word with the request; listing them
    as `caller → callee @ file:line` costs a few tokens each and lets the agent
    read exactly the range it needs instead of searching. Breadth-first from
    the leading entry points, skipping utilities called from everywhere and
    the stages already in the package.
    """
    by_id = {node.get("id"): node for node in graph.get("nodes", [])}
    calls: dict[Any, list[dict[str, Any]]] = {}
    callers: dict[Any, set[Any]] = {}
    for link in graph.get("links", []):
        if link.get("label") == "llama" and str(link.get("confidence") or "") != "AMBIGUOUS":
            calls.setdefault(link.get("source"), []).append(link)
            callers.setdefault(link.get("target"), set()).add(link.get("source"))
    selected_ids = {node.get("id") for node in selected}
    frontier = [node.get("id") for node in selected
                if node.get("kind") in BEHAVIOR_KINDS and node.get("id") in calls
                and not TEST_PATH.search(str(node.get("file") or ""))][:seeds]
    seen = set(frontier)
    reached: list[Any] = []
    outline: list[dict[str, Any]] = []
    for _level in range(depth):
        following = []
        for caller_id in frontier:
            for link in sorted(calls.get(caller_id, []), key=lambda item: int(item.get("line") or 0)):
                target = link.get("target")
                node = by_id.get(target)
                if (not node or target in seen or node.get("kind") not in BEHAVIOR_KINDS
                        or TEST_PATH.search(str(node.get("file") or ""))
                        or VENDORED_PATH.search(str(node.get("file") or ""))):
                    continue
                if len(callers.get(target, ())) > UTILITY_FAN_IN and not name_frequency.hits(str(node.get("name") or "")):
                    continue
                seen.add(target)
                following.append(target)
                reached.append(target)
                if target not in selected_ids and len(outline) < limit:
                    outline.append({"caller": str(by_id.get(caller_id, {}).get("name") or ""),
                                    "callee": str(node.get("name") or ""), "file": str(node.get("file") or ""),
                                    "line": node.get("line"),
                                    "confidence": str(link.get("confidence") or "EXTRACTED")})
        frontier = following
    # Stages the entry point reaches first: their state is the flow's hand-over.
    stages = reached + [node.get("id") for node in selected]
    return outline + state_outline(graph, stages, {*selected_ids, *seen}, by_id)


def _field_users(graph: dict[str, Any]) -> dict[str, set[Any]]:
    """Behaviour nodes per state field their operations read or write, cached per graph."""
    nodes = graph.get("nodes", [])
    cached = _FIELD_INDEX.get(id(graph))
    if cached and cached[0] == len(nodes):
        return cached[1]
    users: dict[str, set[Any]] = {}
    for node in nodes:
        if node.get("kind") in BEHAVIOR_KINDS:
            for operation in node.get("operations") or []:
                for match in _FIELD.finditer(str(operation.get("text") or "")):
                    users.setdefault(match.group(1) or match.group(2), set()).add(node.get("id"))
    _FIELD_INDEX.clear()
    _FIELD_INDEX[id(graph)] = (len(nodes), users)
    return users


def state_outline(graph: dict[str, Any], stage_ids: list[Any], known: set[Any],
                  by_id: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
    """Functions that share a rare state field with a stage (`server.ready_keys`)."""
    if not STATE_LIMIT:
        return []
    users = _field_users(graph)
    fields_of: dict[Any, set[str]] = {}
    for field, ids in users.items():
        if 2 <= len(ids) <= STATE_FAN:
            for node_id in ids:
                fields_of.setdefault(node_id, set()).add(field)
    outline: list[dict[str, Any]] = []
    for stage_id in stage_ids:
        for field in sorted(fields_of.get(stage_id, ())):
            for other in sorted(users[field] - known, key=str):
                node = by_id.get(other) or {}
                if TEST_PATH.search(str(node.get("file") or "")) or not node.get("file"):
                    continue
                known.add(other)
                outline.append({"caller": f"{by_id.get(stage_id, {}).get('name')}~{field}",
                                "callee": str(node.get("name") or ""), "file": str(node.get("file") or ""),
                                "line": node.get("line"), "confidence": "STATE"})
                if len(outline) >= STATE_LIMIT:
                    return outline
    return outline


def command_handlers(request: str, nodes: list[dict[str, Any]], excluded_kinds: set[str]) -> set[str]:
    """Handler names of the commands a request writes in capitals.

    Servers name a command's entry point after it (`BLPOP` → `blpopCommand`,
    `GET` → `cmd_get`), so the request names the handler without spelling it.
    Capitals also spell policies (`TTL`, `LRU`), so the caller must not pin
    the package to a handler's file.
    """
    if not COMMAND_NAMES:
        return set()
    words = {word.lower() for word in re.findall(r"(?<![\w.])[A-Z][A-Z0-9]{1,19}(?![\w.])", str(request or ""))}
    forms = {form.format(word) for word in words for form in _HANDLER_FORMS}
    return {name for name in (str(node.get("name") or "").lower() for node in nodes
                              if node.get("kind") in BEHAVIOR_KINDS and node.get("kind") not in excluded_kinds)
            if name in forms}


def flow_outline(graph: dict[str, Any], selected: list[dict[str, Any]],
                 name_frequency: NameFrequency, guidance: str = "") -> dict[str, Any]:
    """Flow package fields: `call_outline` and, under CITE_STAGES, the citation guidance."""
    outline = call_outline(graph, selected, name_frequency, OUTLINE_LIMIT) if OUTLINE_LIMIT and selected else []
    fields: dict[str, Any] = {"call_outline": outline} if outline else {}
    if CITE_STAGES and selected:
        fields["guidance"] = guidance + CITE_STAGES_GUIDANCE
    return fields


def render_call_outline(items: list[dict[str, Any]], file_alias: Any) -> dict[str, Any]:
    """Package fields for `call_outline`, with files referenced by alias."""
    outline = [[item["caller"], item["callee"],
                file_alias(item["file"]) + (f":{item['line']}" if item.get("line") else ""),
                str(item.get("confidence") or "EXTRACTED")[:1]]
               for item in items if item.get("file")]
    if not outline:
        return {}
    return {"call_outline": outline,
            "call_outline_legend": ("[caller, callee, F:line, E|I|S]: further stages of the flow, outside "
                                    "entities; S = shares the state field after ~ with that stage instead of "
                                    "being called; read only the ranges the answer needs")}


def foreign_code(path: str, request_lower: str) -> bool:
    """A file of a bundled dependency (`deps/jemalloc/…`) whose name the request does not mention."""
    match = _FOREIGN_DIR.search(str(path or "").replace("\\", "/"))
    return bool(match) and match.group(1).lower() not in request_lower


def written_identifiers(request: str) -> list[str]:
    """Identifiers the request writes in code form: camelCase, snake_case or a call."""
    return re.findall(r"\b(?:[a-z]+[A-Z]\w*|[A-Za-z]\w*_\w+|\w+\(\))", str(request or ""))


_TYPE_KINDS = {"class", "module", "struct", "interface", "trait", "enum", "type"}


def named_nodes(nodes: list[dict[str, Any]], symbol_terms: list[str], excluded_kinds: set[str],
                request: str) -> list[dict[str, Any]]:
    """Nodes the request names. A type is named only as written (`Record`); `record.reload` names a variable."""
    return [node for node in nodes
            if str(node.get("name") or "").lower() in symbol_terms and node.get("kind") not in excluded_kinds
            and (node.get("kind") not in _TYPE_KINDS or str(node.get("name") or "") in str(request))]


def local_anchor_files(files: set[str], request_lower: str) -> set[str]:
    """Anchor files outside bundled dependencies the request does not name."""
    return {path for path in files if not foreign_code(path, request_lower)} if FOREIGN_ANCHORS else files


def keep_handlers(request: str, handlers: set[str], mandatory_ids: set[Any], external: list, anchored: list,
                  connected: list, fallback: list, reserve: int) -> tuple[list, list, list, int]:
    """Keep command handlers of other files through the anchor-file partition.

    A command's handler outranks an anchor reached through a plain word ("el
    hash"), not one the request writes as an identifier (`syncCommand`).
    """
    if not KEEP_HANDLERS_OUTSIDE_ANCHORS or written_identifiers(request):
        return anchored, connected, fallback, reserve
    kept = [item for item in external if item[1].get("id") in mandatory_ids
            and str(item[1].get("name") or "").lower() in handlers]
    connected = [item for item in connected if item[1].get("id") not in mandatory_ids]
    fallback = [item for item in fallback if item[1].get("id") not in mandatory_ids]
    return kept + anchored, connected, fallback, max(1, reserve - len(kept))


def flow_markers(markers: tuple[str, ...], request_lower: str) -> tuple[str, ...]:
    """Flow operation markers the request itself names.

    The markers describe common web-application operations; applied to every
    flow they favour unrelated save/send code in other domains.
    """
    return tuple(marker for marker in markers if marker in request_lower)


def cap_homonyms(ranked: list[tuple[int, dict[str, Any]]], keep: set[Any]) -> list[tuple[int, dict[str, Any]]]:
    """Keep at most HOMONYM_CAP candidates per name, plus every mandatory one.

    Overloads and specializations of one name (fmt's many ``format``) say the
    same thing; two of them leave room for the other requested stages.
    """
    seen: dict[str, int] = {}
    capped = []
    for item in ranked:
        name = str(item[1].get("name") or "").lower()
        if seen.get(name, 0) >= HOMONYM_CAP and item[1].get("id") not in keep:
            continue
        seen[name] = seen.get(name, 0) + 1
        capped.append(item)
    return capped


if os.environ.get("GRAPHTYN_FLOW_POLICY"):
    try:
        apply_flow_policy(os.environ["GRAPHTYN_FLOW_POLICY"])
    except ValueError as error:  # a typo must not stop the MCP server
        print(f"graphtyn: GRAPHTYN_FLOW_POLICY ignored: {error}", file=sys.stderr)
