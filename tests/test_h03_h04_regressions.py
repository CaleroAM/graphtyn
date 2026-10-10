"""Regression tests for findings H03 and H04 (Tasks G04 and G05).

Findings covered:
- H03: Old memory matches are lost from candidate set beyond 500 memories
       (resolved in G04 by building union of authorized lexical and recency candidates).
- H04: Long query prefixes displace intent at the end of query
       (resolved in G05 by retaining discriminant terms across the entire query).
"""

from __future__ import annotations

import os
from pathlib import Path

from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.core import shared_memory


def test_h03_old_memory_retrieval_beyond_500_memories(tmp_path, monkeypatch):
    """Verify that an exact memory with a unique term is recovered even after 500+ routine memories."""
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
    project = tmp_path / "project"
    project.mkdir()

    store = SharedMemoryStore(project)
    session = store.start_session("codex", "Isolated product audit", capture_enabled=True)

    target = store.checkpoint(
        session["id"], "decision", "xylophorino",
        "xylophorino is the archived decision"
    )
    vector_target = store.checkpoint(
        session["id"], "decision", "Archived payload",
        "A historical record found only by its embedding"
    )

    # Initial retrieval succeeds
    before = store.search("xylophorino", requester_agent="codex")
    assert any(x["id"] == target["id"] for x in before)

    # Insert 501 routine decisions
    for i in range(501):
        store.checkpoint(session["id"], "decision", f"Routine {i}", f"Routine event {i}")

    # After 501 new memories, H03 previously caused target to be dropped.
    # With G04 fix, target MUST be retrieved in search results.
    after = store.search("xylophorino", requester_agent="codex")
    assert any(x["id"] == target["id"] for x in after), "Old memory was lost after 500+ routine memories!"

    # Also exercise the vector-only path: the target has no lexical overlap
    # and is older than the 500-row recency window.
    provider = "ollama:test:cosine-v1"
    with store._connect() as conn:
        conn.execute("UPDATE memory_embeddings SET provider=?,dimensions=2,vector_json='[0.0,1.0]'",
                     (provider,))
        conn.execute("UPDATE memory_embeddings SET vector_json='[1.0,0.0]' WHERE memory_id=?",
                     (vector_target["id"],))
    monkeypatch.setattr(shared_memory, "ollama_embedding", lambda _query: [1.0, 0.0])
    semantic = store.search("needle unrelated query", requester_agent="codex")
    assert any(item["id"] == vector_target["id"] for item in semantic), \
        "Vector-only old memory was lost outside the recent candidate window"


def test_h04_long_query_preserves_intent_at_end(tmp_path, monkeypatch):
    """Verify that a long query with 12+ prefix verbs still retrieves a message matching keywords at the end."""
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
    project = tmp_path / "project"
    project.mkdir()

    store = SharedMemoryStore(project)
    session = store.start_session("codex", "Message retrieval audit", capture_enabled=True)

    store.append_message(
        session["id"], "assistant",
        "La fotometria y su incertidumbre requieren calibracion."
    )

    short_query = "fotometria incertidumbre calibracion"
    distractors = [f"ruido{chr(97 + (index // 26))}{chr(97 + (index % 26))}" for index in range(48)]
    prefix = " ".join(distractors) + " "
    long_query = prefix + short_query
    front_query = short_query + " " + prefix
    middle_query = " ".join(distractors[:24]) + " " + short_query + " " + " ".join(distractors[24:])

    short_result = store.search_messages(short_query)
    long_result = store.search_messages(long_query)
    front_result = store.search_messages(front_query)
    middle_result = store.search_messages(middle_query)

    assert short_result["matched_messages"] >= 1, "Short query failed to match message!"
    assert long_result["matched_messages"] >= 1, "Long query prefix displaced keywords at the end!"
    assert front_result["matched_messages"] >= 1, "Long query suffix displaced keywords at the beginning!"
    assert middle_result["matched_messages"] >= 1, "Long query displaced keywords in the middle!"
    assert any("fotometria" in msg.get("matched_terms", []) or "calibracion" in msg.get("matched_terms", [])
               for msg in long_result["messages"])
