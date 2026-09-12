import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from graphtyn.core.memory_consolidation import (
    consolidate_legacy_brain,
    preview_legacy_consolidation,
)
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.core.storage import atomic_write_json, data_home


def _registered_brains(tmp_path, monkeypatch):
    home = tmp_path / "graphtyn-home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    archive, evi, eve = tmp_path / "legacy-mixed", tmp_path / "evi", tmp_path / "eve"
    for path in (archive, evi, eve):
        path.mkdir()
    rows = [
        {"id": "legacy-mixed", "name": "Legacy mixed", "path": str(archive),
         "mode": "single_folder", "space_type": "agent_brain", "legacy": True,
         "agent_ids": ["openclaw/evi", "openclaw/eve"]},
        {"id": "evi", "name": "Evi", "path": str(evi),
         "mode": "single_folder", "space_type": "agent_brain", "legacy": False,
         "agent_ids": ["openclaw/evi"]},
        {"id": "eve", "name": "Eve", "path": str(eve),
         "mode": "single_folder", "space_type": "agent_brain", "legacy": False,
         "agent_ids": ["openclaw/eve"]},
    ]
    atomic_write_json(data_home() / "registered_projects.json", rows)
    return archive, evi, eve


def _seed_archive(archive):
    source = SharedMemoryStore(archive)
    evi_session = source.start_session("openclaw/evi", "CRM · report button", capture_enabled=True,
                                       session_id="old-evi-session")
    user_message = source.append_message(evi_session["id"], "user",
        "Cambia el color del botón de Reportes del CRM a azul.",
        metadata={"occurred_at": 1_700_000_001, "source_message_id": "evi-user-1"})
    source.append_message(evi_session["id"], "assistant", "Actualicé el botón de reportes.",
        metadata={"occurred_at": 1_700_000_002, "source_message_id": "evi-assistant-1"})
    tool_message = source.append_message(evi_session["id"], "tool", "test_report_button_color: passed",
        event_type="test_result", metadata={"occurred_at": 1_700_000_003,
                                             "source_message_id": "evi-tool-1"})
    source.process_topics(evi_session["id"])
    source.checkpoint(evi_session["id"], "decision", "Color del botón Reportes",
        "El botón de Reportes usa azul.", status="verified", tests=["test_report_button_color"],
        metadata={"source_message_ids": [user_message["id"]]})
    topic = source.topics(agent_id="openclaw/evi")["topics"][0]
    source.topic_update(topic["id"], requester_agent="openclaw/evi", reason="Prueba histórica",
                        state="resuelto", verification="prueba superada",
                        message_ids=[tool_message["id"]])

    eve_session = source.start_session("openclaw/eve", "Otro asunto", capture_enabled=True,
                                       session_id="old-eve-session")
    source.append_message(eve_session["id"], "user", "Investiga el costo de stands de AWS.",
                          metadata={"source_message_id": "eve-user-1"})
    source.process_topics(eve_session["id"])
    return source


def test_consolidation_preview_apply_and_repeat_are_scoped_and_auditable(tmp_path, monkeypatch):
    archive, evi_path, eve_path = _registered_brains(tmp_path, monkeypatch)
    source = _seed_archive(archive)
    SharedMemoryStore(evi_path)
    SharedMemoryStore(eve_path)

    preview = preview_legacy_consolidation(archive, evi_path, "openclaw/evi", "legacy-mixed")
    assert preview["dry_run"] is True
    assert preview["eligible"] == {"sessions": 1, "messages": 3, "memories": 1,
                                    "topics": 1, "conversation_sessions": 1,
                                    "relations": 0, "reviews": 0,
                                    "memory_only_sessions": 0, "excluded_sessions": 0,
                                    "excluded_messages": 0}
    assert preview["source_unchanged"] is True

    result = consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
        archive_id="legacy-mixed", consent=True, batch_size=1)
    assert result["ok"] is True
    assert result["imported"]["sessions"] == 1
    assert result["imported"]["messages"] == 3
    assert result["imported"]["memories"] >= 1
    assert result["imported"]["topics"] == 1
    assert result["imported"]["events"] >= 1
    assert result["source_unchanged"] is True
    assert result["source_backup"] and result["target_backup"]
    assert sqlite3.connect(result["source_backup"]).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert sqlite3.connect(result["target_backup"]).execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    target = SharedMemoryStore(evi_path)
    sessions = target.list_sessions(20)
    assert len(sessions) == 1
    assert sessions[0]["agent_id"] == "openclaw/evi"
    details = target.session_detail(sessions[0]["id"])
    assert [message["role"] for message in details["messages"]] == ["user", "assistant", "tool"]
    assert details["messages"][0]["content"].startswith("Cambia el color")
    assert all(message["metadata"]["capture_mode"] == "historical_import"
               for message in target.list_messages(sessions[0]["id"]))
    old_verified = target.search("Color del botón Reportes", requester_agent="openclaw/evi")
    imported_decision = next(row for row in old_verified if row["kind"] == "decision")
    assert imported_decision["status"] == "observed"
    assert imported_decision["metadata"]["legacy_status"] == "verified"
    assert imported_decision["metadata"]["capture_mode"] == "historical_import"
    historical_topic = next(row for row in target.search("CRM", requester_agent="openclaw/evi")
                            if row["metadata"].get("legacy_topic_state"))
    assert historical_topic["metadata"]["legacy_topic_state"] == "resuelto"
    assert historical_topic["metadata"]["legacy_topic_verification"] == "prueba superada"
    assert len(target.topics(requester_agent="openclaw/evi")["topics"]) >= 1

    # Similar legacy data belonging to Eve remains in the archive and is never
    # copied into Evi's private brain.
    assert "Investiga el costo" not in " ".join(row["content"] for row in details["messages"])
    eve_store = SharedMemoryStore(eve_path)
    assert eve_store.list_sessions(20) == []
    with source._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2

    repeated = consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
        archive_id="legacy-mixed", consent=True, batch_size=1)
    assert repeated["ok"] is True
    assert repeated["imported"]["sessions"] == 0
    assert repeated["imported"]["messages"] == 0
    assert repeated["imported"]["memories"] == 0
    assert len(target.list_sessions(20)) == 1


def test_consolidation_requires_exact_destination_owner_and_consent(tmp_path, monkeypatch):
    archive, evi_path, eve_path = _registered_brains(tmp_path, monkeypatch)
    _seed_archive(archive)
    SharedMemoryStore(evi_path)
    with pytest.raises(PermissionError, match="propietario explícito"):
        preview_legacy_consolidation(archive, eve_path, "openclaw/evi", "legacy-mixed")
    with pytest.raises(PermissionError, match="consentimiento explícito"):
        consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
            archive_id="legacy-mixed", consent=False)


def test_consolidation_resumes_after_interruption_without_duplicate_messages(tmp_path, monkeypatch):
    archive, evi_path, _ = _registered_brains(tmp_path, monkeypatch)
    _seed_archive(archive)
    SharedMemoryStore(evi_path)
    calls = []

    def stop_after_first_batch(_percent, _message):
        calls.append(True)
        return False

    paused = consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
        archive_id="legacy-mixed", consent=True, batch_size=1, progress=stop_after_first_batch)
    assert paused["paused"] is True
    assert len(calls) == 1

    resumed = consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
        archive_id="legacy-mixed", consent=True, batch_size=1)
    assert resumed["ok"] is True
    target = SharedMemoryStore(evi_path)
    assert len(target.list_sessions(20)) == 1
    messages = target.list_messages(target.list_sessions(20)[0]["id"])
    assert len(messages) == 3


def test_consolidation_preserves_explicit_memories_without_importing_unconsented_transcript(tmp_path, monkeypatch):
    archive, evi_path, _ = _registered_brains(tmp_path, monkeypatch)
    source = SharedMemoryStore(archive)
    session = source.start_session("openclaw/evi", "Stored historical preference", capture_enabled=False)
    source.checkpoint(session["id"], "fact", "Preferred CRM color", "The CRM report button was blue.",
                      status="observed")
    SharedMemoryStore(evi_path)

    preview = preview_legacy_consolidation(archive, evi_path, "openclaw/evi", "legacy-mixed")
    assert preview["eligible"]["sessions"] == 1
    assert preview["eligible"]["conversation_sessions"] == 0
    assert preview["eligible"]["memory_only_sessions"] == 1
    assert preview["eligible"]["messages"] == 0
    assert preview["eligible"]["memories"] == 1

    result = consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
        archive_id="legacy-mixed", consent=True)
    assert result["ok"] is True
    assert result["imported"]["messages"] == 0
    target = SharedMemoryStore(evi_path)
    assert len(target.list_sessions(20)) == 1
    assert target.list_messages(target.list_sessions(20)[0]["id"]) == []
    memories = target.search("Preferred CRM color", requester_agent="openclaw/evi")
    assert any(item["metadata"].get("capture_mode") == "historical_import" for item in memories)


def test_consolidation_carries_reviewed_topic_relations_only_for_unambiguous_agent_topics(tmp_path, monkeypatch):
    archive, evi_path, _ = _registered_brains(tmp_path, monkeypatch)
    source = SharedMemoryStore(archive)
    first = source.start_session("openclaw/evi", "CRM report button", capture_enabled=True)
    first_message = source.append_message(first["id"], "user",
        "Actualiza el color del botón de Reportes del CRM a azul.",
        metadata={"source_message_id": "report-button-user"})
    source.process_topics(first["id"])
    second = source.start_session("openclaw/evi", "Operator exports", capture_enabled=True)
    second_message = source.append_message(second["id"], "user",
        "La pantalla de Operadores exporta el padrón de clientes a CSV.",
        metadata={"source_message_id": "operator-screen-user"})
    source.process_topics(second["id"])
    source_topics = source.topics(agent_id="openclaw/evi")["topics"]
    assert len(source_topics) == 2
    source_ids = sorted(topic["id"] for topic in source_topics)
    now = 1_700_000_100
    relation = "mismo concepto"
    with source._connect() as db:
        db.execute("""INSERT INTO topic_relations
            (source_topic_id,target_topic_id,relation,confidence,reason,source_message_id,created_at)
            VALUES(?,?,?,'REVIEWED',?,?,?)""",
            (source_ids[0], source_ids[1], relation, "Revisión humana de ejemplo",
             first_message["id"], now))
        db.execute("""INSERT INTO topic_relation_reviews
            (id,source_topic_id,target_topic_id,relation,status,reason,evidence_json,actor,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("review-old-1", source_ids[0], source_ids[1], relation, "accepted",
             "Se confirmó que ambos asuntos forman parte del CRM.",
             json.dumps({"source_message_ids": [first_message["id"], second_message["id"]]}),
             "user", now, now))
    SharedMemoryStore(evi_path)

    preview = preview_legacy_consolidation(archive, evi_path, "openclaw/evi", "legacy-mixed")
    assert preview["eligible"]["relations"] == 1
    assert preview["eligible"]["reviews"] == 1
    result = consolidate_legacy_brain(archive, evi_path, agent_id="openclaw/evi",
        archive_id="legacy-mixed", consent=True)
    assert result["ok"] is True
    assert result["imported"]["relations"] == 1
    assert result["imported"]["reviews"] == 1
    target = SharedMemoryStore(evi_path)
    with target._connect() as db:
        mapped = {row["source_record_id"]: row["target_id"] for row in db.execute(
            """SELECT source_record_id,target_id FROM legacy_consolidation_items
               WHERE archive_id='legacy-mixed' AND agent_id='openclaw/evi' AND record_kind='topic_node'""")}
        assert len(mapped) == 2 and len(set(mapped.values())) == 2
        assert db.execute("""SELECT confidence FROM topic_relations
            WHERE source_topic_id=? AND target_topic_id=? AND relation=?""",
            (mapped[source_ids[0]], mapped[source_ids[1]], relation)).fetchone()[0] == "REVIEWED"
        assert db.execute("""SELECT status FROM topic_relation_reviews
            WHERE source_topic_id=? AND target_topic_id=? AND relation=?""",
            (mapped[source_ids[0]], mapped[source_ids[1]], relation)).fetchone()[0] == "accepted"


def test_api_and_cli_offer_preview_without_importing_by_default(tmp_path, monkeypatch):
    from graphtyn.api import main as api_main

    archive, evi_path, _ = _registered_brains(tmp_path, monkeypatch)
    _seed_archive(archive)
    SharedMemoryStore(evi_path)
    state_dir = data_home()
    monkeypatch.setattr(api_main, "INDEX_STORE", state_dir)
    monkeypatch.setattr(api_main, "REGISTRATION_FILE", state_dir / "registered_projects.json")
    for key in ("GRAPHTYN_MEMORY_HTTP_TOKEN", "GRAPHTYN_MEMORY_TOKENS",
                "GRAPHTYN_MEMORY_TOKENS_FILE"):
        monkeypatch.delenv(key, raising=False)

    response = api_main.memory_consolidate({"source_path": str(archive),
        "target_path": str(evi_path), "agent_id": "openclaw/evi"})
    assert response["ok"] is True and response["dry_run"] is True
    assert response["eligible"]["messages"] == 3
    with sqlite3.connect(SharedMemoryStore(evi_path).db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0

    queued = api_main.memory_consolidate({"source_path": str(archive),
        "target_path": str(evi_path), "agent_id": "openclaw/evi", "apply": True, "consent": True})
    assert queued["ok"] is True and queued["job"]["kind"] == "legacy-consolidation"
    from graphtyn.core.memory_jobs import memory_jobs
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = memory_jobs.get(queued["job"]["id"])
        if job["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(.05)
    assert job["status"] == "completed", job
    assert job["result"]["ok"] is True
    assert api_main.memory_consolidation_get(queued["job"]["id"])["job"]["status"] == "completed"
    archive_view = next(item for item in api_main._load_registered_brains() if item["path"] == str(archive))
    assert archive_view["consolidated_agents"][0]["status"] == "completed"

    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, GRAPHTYN_HOME=str(state_dir))
    command = [sys.executable, "-m", "graphtyn.cli", "memory", "consolidate",
               "--source", str(archive), "--target", str(evi_path),
               "--agent-id", "openclaw/evi"]
    result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["dry_run"] is True
    assert report["will_import"]["messages"] == 0
    with sqlite3.connect(SharedMemoryStore(evi_path).db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
