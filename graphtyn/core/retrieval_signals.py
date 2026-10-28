"""Lexical and structural ranking signals shared by intent retrieval."""

from __future__ import annotations

from typing import Any

from .path_signals import TEST_PATH, VENDORED_PATH
from .vocabulary import COMMON_WORDS

BEHAVIOR_KINDS = {"function", "method", "def"}
HOMONYM_CAP = 2


class NameFrequency:
    """How many callable names spell each request term.

    A term spelled by few callable names is distinctive (``evict`` in
    ``performEvictions``); one spelled by a large share of them (``redis`` in
    Redis, ``format`` in fmt) says nothing about which of them a request means.
    """

    def __init__(self, nodes: list[dict[str, Any]], terms: list[str], generic: set[str]) -> None:
        names = [str(node.get("name") or "").lower() for node in nodes if node.get("kind") in BEHAVIOR_KINDS]
        self.ceiling = max(25, len(names) // 400)
        blob = "\n".join(names)
        self.counts = {term: blob.count(term) for term in dict.fromkeys(term.lower() for term in terms)
                       if len(term) >= 5 and term not in generic and term not in COMMON_WORDS}
        self.distinctive = [term for term, count in self.counts.items() if 0 < count <= self.ceiling]

    def pervasive(self, term: str) -> bool:
        return self.counts.get(term, 0) > 4 * self.ceiling

    def hits(self, name: str) -> int:
        lowered = name.lower()
        return min(2, sum(term in lowered and term != lowered for term in self.distinctive))


def with_call_chain(graph: dict[str, Any], ranked: list[tuple[int, dict[str, Any]]],
                     name_frequency: NameFrequency, keep_first: set[Any],
                     seeds: int = 1, limit: int = 3) -> list[tuple[int, dict[str, Any]]]:
    """Place the direct callees of the leading entry points right after them.

    A flow continues through the functions its entry point calls even when
    their names share no word with the request (``format_to_n`` →
    ``vformat_to_n``). Callees spelling a distinctive request term go first.
    """
    by_id = {node.get("id"): node for node in graph.get("nodes", [])}
    callers = {link.get("source") for link in graph.get("links", []) if link.get("label") == "llama"}
    seed_items = [item for item in ranked[:4]
                  if item[1].get("kind") in BEHAVIOR_KINDS and item[1].get("id") in callers
                  and not TEST_PATH.search(str(item[1].get("file") or ""))][:seeds]
    if not seed_items:
        return ranked
    seed_ids = {item[1].get("id") for item in seed_items}
    ranked_ids = {item[1].get("id") for item in ranked}
    callees: dict[Any, int] = {}
    for link in graph.get("links", []):
        target = link.get("target")
        if (link.get("label") != "llama" or link.get("source") not in seed_ids
                or str(link.get("confidence") or "") == "AMBIGUOUS" or target in seed_ids):
            continue
        node = by_id.get(target)
        if (not node or node.get("kind") not in BEHAVIOR_KINDS
                or TEST_PATH.search(str(node.get("file") or "")) or VENDORED_PATH.search(str(node.get("file") or ""))):
            continue
        callees[target] = max(callees.get(target, 0), name_frequency.hits(str(node.get("name") or "")))
    # An unrelated helper call (logging, allocation) is not a stage of the flow:
    # keep callees that spell a request term or were already retrieved.
    callees = {node_id: hits for node_id, hits in callees.items() if hits or node_id in ranked_ids}
    chosen = sorted(callees, key=lambda node_id: (-callees[node_id], node_id not in ranked_ids, str(node_id)))[:limit]
    if not chosen:
        return ranked
    # Callees follow the seeds and every mandatory representative, so a named
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
