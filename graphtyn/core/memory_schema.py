"""SQLite schema and additive migrations for shared project memory."""

from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, display_name TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_aliases (
                    alias TEXT PRIMARY KEY, canonical TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual', created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
                    task TEXT NOT NULL, branch TEXT, base_commit TEXT, worktree TEXT,
                    capture_enabled INTEGER NOT NULL DEFAULT 0,
                    started_at REAL NOT NULL, ended_at REAL, status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    agent_id TEXT NOT NULL REFERENCES agents(id), kind TEXT NOT NULL,
                    scope TEXT NOT NULL, status TEXT NOT NULL, title TEXT NOT NULL,
                    content TEXT NOT NULL, task TEXT, branch TEXT, base_commit TEXT,
                    observed_commit TEXT, confidence REAL NOT NULL,
                    files_json TEXT NOT NULL, node_ids_json TEXT NOT NULL,
                    tests_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, supersedes_id TEXT REFERENCES memories(id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL REFERENCES agents(id), role TEXT NOT NULL,
                    content TEXT NOT NULL, event_type TEXT, metadata_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL, created_at REAL NOT NULL,
                    UNIQUE(session_id, content_sha256, role)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_dedupe
                    ON memories(session_id, content_sha256, kind);
                CREATE INDEX IF NOT EXISTS idx_memory_created ON memories(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_scope_status ON memories(scope, status);
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL,
                    action TEXT NOT NULL, agent_id TEXT, session_id TEXT,
                    memory_id TEXT, details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL, dimensions INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL, vector_json TEXT NOT NULL,
                    updated_at REAL NOT NULL, PRIMARY KEY(memory_id, provider)
                );
                CREATE TABLE IF NOT EXISTS legacy_imports (
                    source_key TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
                    imported_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS legacy_consolidation_runs (
                    id TEXT PRIMARY KEY, archive_id TEXT NOT NULL,
                    archive_path TEXT NOT NULL, source_db TEXT NOT NULL,
                    target_path TEXT NOT NULL, agent_id TEXT NOT NULL,
                    status TEXT NOT NULL, source_backup TEXT NOT NULL DEFAULT '',
                    target_backup TEXT NOT NULL DEFAULT '', report_json TEXT NOT NULL DEFAULT '{}',
                    started_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS legacy_consolidation_runs_recent
                    ON legacy_consolidation_runs(archive_id, agent_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS legacy_consolidation_items (
                    source_key TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    archive_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                    record_kind TEXT NOT NULL, source_session_id TEXT NOT NULL DEFAULT '',
                    source_record_id TEXT NOT NULL DEFAULT '', source_digest TEXT NOT NULL DEFAULT '',
                    target_id TEXT NOT NULL, imported_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS legacy_consolidation_items_lookup
                    ON legacy_consolidation_items(archive_id, agent_id, record_kind);
                CREATE TABLE IF NOT EXISTS memory_sync_watchers (
                    watcher_id TEXT PRIMARY KEY, pid INTEGER NOT NULL,
                    status TEXT NOT NULL, heartbeat REAL NOT NULL,
                    interval REAL NOT NULL DEFAULT 5, error TEXT NOT NULL DEFAULT '',
                    last_cycle_started REAL, last_cycle_finished REAL, last_success_at REAL,
                    cycle_count INTEGER NOT NULL DEFAULT 0,
                    failed_cycle_count INTEGER NOT NULL DEFAULT 0,
                    last_result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS memory_provenance (
                    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    agent_id TEXT NOT NULL REFERENCES agents(id),
                    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
                    observed_at REAL NOT NULL,
                    PRIMARY KEY(memory_id, session_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS memory_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL, operation TEXT NOT NULL,
                    agent_id TEXT, session_id TEXT, context_id TEXT,
                    provider TEXT, local_input_tokens INTEGER NOT NULL DEFAULT 0,
                    local_output_tokens INTEGER NOT NULL DEFAULT 0,
                    remote_context_tokens INTEGER NOT NULL DEFAULT 0,
                    raw_history_tokens_avoided INTEGER NOT NULL DEFAULT 0,
                    embedding_characters INTEGER NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_memory_telemetry_time
                    ON memory_telemetry(timestamp DESC);
                CREATE TABLE IF NOT EXISTS memory_space_policy (
                    id INTEGER PRIMARY KEY CHECK(id=1), workspace_path TEXT NOT NULL,
                    space_type TEXT NOT NULL, agent_ids_json TEXT NOT NULL,
                    restricted INTEGER NOT NULL, policy_version INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_routing_state (
                    source_key TEXT PRIMARY KEY, provider TEXT NOT NULL, agent_id TEXT NOT NULL,
                    external_session_id TEXT NOT NULL, status TEXT NOT NULL,
                    projects_json TEXT NOT NULL DEFAULT '[]', reason TEXT NOT NULL DEFAULT '',
                    source_fingerprint TEXT NOT NULL DEFAULT '', message_count INTEGER NOT NULL DEFAULT 0,
                    routed_message_count INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS project_routing_state_status
                    ON project_routing_state(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS project_routing_events (
                    event_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, provider TEXT NOT NULL,
                    agent_id TEXT NOT NULL, external_session_id TEXT NOT NULL, status TEXT NOT NULL,
                    projects_json TEXT NOT NULL DEFAULT '[]', reason TEXT NOT NULL DEFAULT '',
                    source_fingerprint TEXT NOT NULL DEFAULT '', message_count INTEGER NOT NULL DEFAULT 0,
                    routed_message_count INTEGER NOT NULL DEFAULT 0, recorded_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS project_routing_events_source
                    ON project_routing_events(source_key, recorded_at DESC);
                CREATE TABLE IF NOT EXISTS local_executions (
                    execution_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    exit_code INTEGER,
                    outcome TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL NOT NULL,
                    executor TEXT NOT NULL,
                    log_path TEXT,
                    log_digest_sha256 TEXT NOT NULL,
                    git_commit TEXT,
                    git_dirty INTEGER,
                    git_diff_digest TEXT,
                    environment_digest_sha256 TEXT NOT NULL,
                    test_files_json TEXT NOT NULL DEFAULT '[]',
                    data_files_json TEXT NOT NULL DEFAULT '[]',
                    declared_dependencies_json TEXT NOT NULL DEFAULT '[]',
                    artifact_digests_json TEXT NOT NULL DEFAULT '{}',
                    measured_metrics_json TEXT NOT NULL DEFAULT '{}',
                    metric_sources_json TEXT NOT NULL DEFAULT '{}',
                    input_fingerprints_json TEXT NOT NULL DEFAULT '{}',
                    post_input_fingerprints_json TEXT NOT NULL DEFAULT '{}',
                    inputs_changed INTEGER NOT NULL DEFAULT 0,
                    pre_git_context_json TEXT NOT NULL DEFAULT '{}',
                    post_git_context_json TEXT NOT NULL DEFAULT '{}',
                    rejected_metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS local_executions_lookup
                    ON local_executions(log_digest_sha256, git_commit);
            """

EXECUTION_COLUMN_MIGRATIONS = {
    "input_fingerprints_json": "TEXT NOT NULL DEFAULT '{}'",
    "post_input_fingerprints_json": "TEXT NOT NULL DEFAULT '{}'",
    "inputs_changed": "INTEGER NOT NULL DEFAULT 0",
    "pre_git_context_json": "TEXT NOT NULL DEFAULT '{}'",
    "post_git_context_json": "TEXT NOT NULL DEFAULT '{}'",
    "rejected_metrics_json": "TEXT NOT NULL DEFAULT '{}'",
    "metric_sources_json": "TEXT NOT NULL DEFAULT '{}'",
}

WATCHER_COLUMN_MIGRATIONS = {
    "last_cycle_started": "REAL",
    "last_cycle_finished": "REAL",
    "last_success_at": "REAL",
    "cycle_count": "INTEGER NOT NULL DEFAULT 0",
    "failed_cycle_count": "INTEGER NOT NULL DEFAULT 0",
    "last_result_json": "TEXT NOT NULL DEFAULT '{}'",
}

MIGRATION_VERSIONS = (1, 2, 3, 7, 9, 10)


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, migrations: dict[str, str]
) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column, declaration in migrations.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def initialize_memory_schema(conn: sqlite3.Connection, applied_at: float) -> None:
    """Create the current schema and apply idempotent additive migrations."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    _add_missing_columns(conn, "local_executions", EXECUTION_COLUMN_MIGRATIONS)
    _add_missing_columns(conn, "memory_sync_watchers", WATCHER_COLUMN_MIGRATIONS)
    try:
        conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            memory_id UNINDEXED, title, content, task, files, nodes,
            tokenize='unicode61 remove_diacritics 2'
        )""")
    except sqlite3.OperationalError:
        pass
    conn.executemany(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
        [(version, applied_at) for version in MIGRATION_VERSIONS],
    )
