#!/usr/bin/env python3
"""Quarantine memory rows that belong to another agent identity.

The operation is deliberately reversible: sessions and memories remain in the
SQLite backup and are marked ``quarantined`` instead of being deleted.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path


def repair(db_path: Path, owners: set[str], label: str) -> dict[str, int | str]:
    owners = {value.strip().casefold() for value in owners if value.strip()}
    if not owners:
        raise ValueError("se requiere al menos una identidad propietaria")
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        marks = ",".join("?" for _ in owners)
        sessions = db.execute(
            f"SELECT id,agent_id FROM sessions WHERE lower(agent_id) NOT IN ({marks})", sorted(owners)
        ).fetchall()
        session_ids = [str(row["id"]) for row in sessions]
        if not session_ids:
            return {"db": str(db_path), "sessions": 0, "memories": 0}
        session_marks = ",".join("?" for _ in session_ids)
        memory_rows = db.execute(
            f"SELECT id FROM memories WHERE session_id IN ({session_marks})", session_ids
        ).fetchall()
        memory_ids = [str(row["id"]) for row in memory_rows]
        now = time.time()
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            f"UPDATE sessions SET capture_enabled=0,status='quarantined',ended_at=COALESCE(ended_at,?) WHERE id IN ({session_marks})",
            [now, *session_ids]
        )
        if memory_ids:
            memory_marks = ",".join("?" for _ in memory_ids)
            db.execute(
                f"UPDATE memories SET status='quarantined',updated_at=? WHERE id IN ({memory_marks})",
                [now, *memory_ids]
            )
        for row in sessions:
            db.execute(
                "INSERT INTO audit_log(timestamp,action,agent_id,session_id,memory_id,details_json) VALUES(?,?,?,?,?,?)",
                (now, "agent_scope_quarantine", str(row["agent_id"]), str(row["id"]), None,
                 json.dumps({"brain": label, "allowed_agent_ids": sorted(owners),
                             "reason": "session imported into a brain owned by another agent"}, ensure_ascii=False))
            )
        db.commit()
    return {"db": str(db_path), "sessions": len(session_ids), "memories": len(memory_ids)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--owner", action="append", required=True)
    parser.add_argument("--label", default="agent-brain")
    args = parser.parse_args()
    print(json.dumps(repair(args.db, set(args.owner), args.label), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
