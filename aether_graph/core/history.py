import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List

class HistoryTracker:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.db_dir = workspace / ".aether-graph"
        self.db_dir.mkdir(exist_ok=True)
        self.db_path = self.db_dir / "history.db"
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
