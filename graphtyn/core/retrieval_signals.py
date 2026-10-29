"""Lexical and structural ranking signals shared by intent retrieval."""

from __future__ import annotations

import re
from typing import Any

from .path_signals import TEST_PATH, VENDORED_PATH
from .vocabulary import COMMON_WORDS, is_prose_word

BEHAVIOR_KINDS = {"function", "method", "def"}
HOMONYM_CAP = 2


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
        owner = f"{node.get('container') or ''} {node.get('namespace') or ''}".lower()
        return any(term in owner for term in self.owner_terms)

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
                    seeds: int = 1, limit: int = 4, depth: int = 3) -> list[tuple[int, dict[str, Any]]]:
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
                if hits or target in ranked_ids or sibling:
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
    chain = [(ranked[last_seed][0], dict(by_id[node_id])) for node_id in chosen]
    chosen_ids = set(chosen)
    head = [item for item in ranked[:last_seed + 1] if item[1].get("id") not in chosen_ids]
    tail = [item for item in ranked[last_seed + 1:] if item[1].get("id") not in chosen_ids]
    return head + chain + tail


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

