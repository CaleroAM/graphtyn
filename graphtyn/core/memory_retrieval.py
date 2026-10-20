"""Bounded vector candidate selection for shared-memory retrieval."""

from __future__ import annotations

import heapq
import json
import sqlite3
from typing import Any


def semantic_relevance(query_terms: set[str], text_terms: set[str],
                       identifier_terms: list[str]) -> tuple[int, float, float]:
    """Score shared language and exact identifier evidence for RRF ranking."""
    overlap = len(query_terms & text_terms)
    semantic_bonus = min(0.08, overlap / max(1, len(query_terms)) * 0.12)
    identifier_bonus = 0.08 if identifier_terms and any(
        term in text_terms for term in identifier_terms
    ) else 0.0
    return overlap, semantic_bonus, identifier_bonus


def ranked_vector_hits(
    conn: sqlite3.Connection,
    *,
    provider: str,
    query_vector: list[float] | None,
    candidate_ids: list[str],
    visibility: str,
    stale_clause: str,
    params: list[Any],
    limit: int,
) -> list[tuple[float, str, dict[str, Any]]]:
    """Rank local-hash candidates without scanning the full embedding table."""
    if query_vector is None:
        return []
    if provider == "feature-hash-v2":
        if not candidate_ids:
            return []
        marks = ",".join("?" for _ in candidate_ids)
        cursor = conn.execute(f"""SELECT m.*,e.vector_json AS _vector_json
            FROM memories m JOIN memory_embeddings e ON e.memory_id=m.id
            WHERE e.provider=? AND m.id IN ({marks})""", [provider, *candidate_ids])
    else:
        cursor = conn.execute(f"""SELECT m.*,e.vector_json AS _vector_json
            FROM memories m JOIN memory_embeddings e ON e.memory_id=m.id
            WHERE e.provider=? AND {visibility} {stale_clause}""", [provider, *params])
    heap: list[tuple[float, str, dict[str, Any]]] = []
    while batch := cursor.fetchmany(256):
        for row in batch:
            try:
                vector = json.loads(row["_vector_json"])
                if len(vector) != len(query_vector):
                    continue
                score = sum(a * b for a, b in zip(query_vector, vector))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if score <= 0:
                continue
            item = dict(row)
            item.pop("_vector_json", None)
            entry = (score, str(row["id"]), item)
            if len(heap) < limit:
                heapq.heappush(heap, entry)
            elif entry[:2] > heap[0][:2]:
                heapq.heapreplace(heap, entry)
    cursor.close()
    return sorted(heap, key=lambda entry: (-entry[0], entry[1]))


def ranked_message_vector_hits(
    conn: sqlite3.Connection,
    *,
    provider: str,
    query_vector: list[float] | None,
    candidate_ids: list[str],
    owner_clause: str,
    owner_params: list[Any],
    limit: int,
) -> list[tuple[float, str]]:
    """Return bounded semantic message candidates without reading transcripts."""
    if query_vector is None:
        return []
    candidate_clause = ""
    values: list[Any] = [provider]
    if candidate_ids:
        marks = ",".join("?" for _ in candidate_ids)
        candidate_clause = f" AND m.id IN ({marks})"
        values.extend(candidate_ids)
    elif provider == "feature-hash-v2":
        return []
    values.extend(owner_params)
    cursor = conn.execute(f"""SELECT m.id,e.vector_json
        FROM messages m JOIN sessions s ON s.id=m.session_id
        JOIN message_embeddings e ON e.message_id=m.id
        WHERE e.provider=? AND s.capture_enabled=1
          AND m.role IN ('user','assistant'){candidate_clause}{owner_clause}""", values)
    heap: list[tuple[float, str]] = []
    while batch := cursor.fetchmany(256):
        for row in batch:
            try:
                vector = json.loads(row["vector_json"])
                if len(vector) != len(query_vector):
                    continue
                score = sum(a * b for a, b in zip(query_vector, vector))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if score <= 0:
                continue
            entry = (score, str(row["id"]))
            if len(heap) < limit:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                heapq.heapreplace(heap, entry)
    cursor.close()
    return sorted(heap, key=lambda entry: (-entry[0], entry[1]))
