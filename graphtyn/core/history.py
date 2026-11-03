import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from .storage import data_home, project_store_dir

class HistoryTracker:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        local_db = workspace / ".graphtyn" / "history.db"
        home_db_dir = project_store_dir(data_home(), workspace, create=False)
        home_db = home_db_dir / "history.db"

        if local_db.exists():
            self.db_dir = workspace / ".graphtyn"
            self.db_path = local_db
        elif home_db.exists():
            self.db_dir = home_db_dir
            self.db_path = home_db
        else:
            try:
                self.db_dir = workspace / ".graphtyn"
                self.db_dir.mkdir(exist_ok=True)
                test_file = self.db_dir / ".write_test"
                test_file.touch()
                test_file.unlink()
                self.db_path = local_db
            except OSError:
                self.db_dir = home_db_dir
                self.db_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = home_db

        self._init_db()


    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    action_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON observations(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON observations(timestamp)")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.commit()

    def log_event(self, session_id: str, action_type: str, summary: str, details: Dict[str, Any]) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO observations (session_id, timestamp, action_type, summary, details) VALUES (?, ?, ?, ?, ?)",
                (session_id, time.time(), action_type, summary, json.dumps(details, ensure_ascii=False))
            )
            conn.commit()
            return cursor.lastrowid

    def search_events(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            q = f"%{query.lower()}%"
            cursor.execute(
                "SELECT id, session_id, timestamp, action_type, summary FROM observations WHERE LOWER(summary) LIKE ? OR LOWER(action_type) LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (q, q, limit)
            )
            rows = cursor.fetchall()
            return [
                {"id": r[0], "session_id": r[1], "timestamp": r[2], "action_type": r[3], "summary": r[4]}
                for r in rows
            ]

    def get_timeline(self, session_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    "SELECT id, session_id, timestamp, action_type, summary FROM observations WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                    (session_id, limit)
                )
            else:
                cursor.execute(
                    "SELECT id, session_id, timestamp, action_type, summary FROM observations ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            return [
                {"id": r[0], "session_id": r[1], "timestamp": r[2], "action_type": r[3], "summary": r[4]}
                for r in rows
            ]

    def events_since(self, action_type: str, since: float, limit: int = 30) -> List[Dict[str, Any]]:
        """Newest first, each event's details merged with its id, time and session."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, session_id, timestamp, details FROM observations "
                "WHERE action_type = ? AND timestamp >= ? ORDER BY timestamp DESC, id DESC LIMIT ?",
                (action_type, since, limit),
            ).fetchall()
        return [{"source": row[1], **json.loads(row[3]), "id": row[0], "timestamp": row[2]} for row in rows]

    def prune_events(self, action_type: str, before: float) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("DELETE FROM observations WHERE action_type = ? AND timestamp < ?",
                                (action_type, before)).rowcount

    def get_setting(self, name: str, default: str = "") -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
        return row[0] if row else default

    def set_setting(self, name: str, value: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO settings (name, value) VALUES (?, ?) "
                         "ON CONFLICT(name) DO UPDATE SET value = excluded.value", (name, value))

    def get_observation(self, obs_id: int) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, session_id, timestamp, action_type, summary, details FROM observations WHERE id = ?",
                (obs_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0], "session_id": row[1], "timestamp": row[2],
                    "action_type": row[3], "summary": row[4], "details": json.loads(row[5])
                }
            return {}
