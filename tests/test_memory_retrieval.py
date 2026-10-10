from graphtyn.core.memory_retrieval import ranked_vector_hits
from graphtyn.core.semantic_index import alias_tokens


class _Cursor:
    def fetchmany(self, _size):
        return []

    def close(self):
        pass


class _Connection:
    def __init__(self):
        self.sql = ""
        self.params = []

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return _Cursor()


def test_feature_hash_vector_ranking_queries_only_bounded_candidates():
    conn = _Connection()

    result = ranked_vector_hits(conn, provider="feature-hash-v2", query_vector=[1.0],
        candidate_ids=["memory-a", "memory-b"], visibility="unused", stale_clause="unused",
        params=["unused"], limit=50)

    assert result == []
    assert "m.id IN (?,?)" in conn.sql
    assert conn.params == ["feature-hash-v2", "memory-a", "memory-b"]


def test_remote_vector_ranking_preserves_visibility_filter():
    conn = _Connection()

    ranked_vector_hits(conn, provider="ollama:model:cosine-v1", query_vector=[1.0],
        candidate_ids=["memory-a"], visibility="m.scope != 'private'",
        stale_clause="AND m.status != 'deleted'", params=["agent"], limit=50)

    assert "m.scope != 'private'" in conn.sql
    assert "m.status != 'deleted'" in conn.sql
    assert "m.id IN" not in conn.sql
    assert conn.params == ["ollama:model:cosine-v1", "agent"]


def test_alias_expansion_excludes_generic_hyphenated_fragments():
    assert {"identity", "auth", "authentication"} <= set(alias_tokens("comprueba la identidad"))
    assert alias_tokens("absent-scale-topic-00") == []
