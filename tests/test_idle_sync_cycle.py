"""An idle memory-sync cycle reuses what did not change: AGY workspaces, scope and topic cursors."""
import json
import os
import sqlite3
import subprocess

from graphtyn.core import antigravity_workspaces as agy
from graphtyn.core import history_import
from graphtyn.core.history_import import PENDING_TOPIC_SESSIONS
from graphtyn.core.memory_scope import resolve_memory_scope
from graphtyn.core.shared_memory import SharedMemoryStore


def _agy_root(tmp_path, rows):
    root = tmp_path / "antigravity-cli"
    root.mkdir()
    db = sqlite3.connect(root / "conversation_summaries.db")
    db.execute("CREATE TABLE conversation_summaries (conversation_id TEXT, workspace_uris TEXT)")
    db.executemany("INSERT INTO conversation_summaries VALUES (?, ?)", rows)
    db.commit(); db.close()
    return root


def test_workspace_map_runs_git_once_per_path_and_rebuilds_when_the_database_changes(tmp_path, monkeypatch):
    agy.clear_caches()
    project = tmp_path / "project"; (project / "src").mkdir(parents=True)
    uri = (project / "src").as_uri()
    root = _agy_root(tmp_path, [("a", json.dumps([uri])), ("b", json.dumps([uri]))])
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=f"{project}\n", stderr="")

    monkeypatch.setattr(agy.subprocess, "run", fake_run)
    first = agy.antigravity_workspace_map(root / "brain")
    assert first == {"a": str(project.resolve()), "b": str(project.resolve())}
    assert len(calls) == 1
    first["a"] = "changed by the caller"
    assert agy.antigravity_workspace_map(root)["a"] == str(project.resolve())
    assert len(calls) == 1

    db = sqlite3.connect(root / "conversation_summaries.db")
    db.execute("INSERT INTO conversation_summaries VALUES (?, ?)", ("c", json.dumps([uri])))
    db.commit(); db.close()
    os.utime(root / "conversation_summaries.db", ns=(1, 1))
    assert set(agy.antigravity_workspace_map(root)) == {"a", "b", "c"}
    assert len(calls) == 1  # the Git root of that path is still remembered


def test_git_root_expires(tmp_path, monkeypatch):
    agy.clear_caches()
    calls = []
    monkeypatch.setattr(agy.subprocess, "run", lambda command, **kwargs: calls.append(command) or
                        subprocess.CompletedProcess(command, 128, stdout="", stderr=""))
    clock = [1000.0]
    monkeypatch.setattr(agy.time, "monotonic", lambda: clock[0])
    assert agy.git_toplevel(tmp_path) == str(tmp_path)
    agy.git_toplevel(tmp_path)
    clock[0] += agy.GIT_ROOT_TTL + 1
    agy.git_toplevel(tmp_path)
    assert len(calls) == 2


def test_default_roots_skip_a_root_nested_in_another(tmp_path, monkeypatch):
    outer = tmp_path / "antigravity-cli"
    monkeypatch.setattr(history_import, "default_sources",
                        lambda: {"antigravity": [tmp_path / ".agy", outer, outer / "brain"]})
    assert history_import._default_roots("antigravity") == [tmp_path / ".agy", outer]


def test_memory_scope_is_reused_until_its_files_change(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    brain = tmp_path / "brain"; brain.mkdir()
    registry = home / "registered_projects.json"
    registry.write_text(json.dumps([{"path": str(brain), "space_type": "agent_brain",
                                     "agent_ids": ["openclaw/a"]}]), encoding="utf-8")
    from graphtyn.core import memory_scope
    resolved = []
    real = memory_scope._resolve_memory_scope
    monkeypatch.setattr(memory_scope, "_resolve_memory_scope",
                        lambda *args, **kwargs: resolved.append(args) or real(*args, **kwargs))
    first = resolve_memory_scope(brain)
    first["agent_ids"].append("mutated")
    assert resolve_memory_scope(brain)["agent_ids"] == ["openclaw/a"]
    assert len(resolved) == 1

    registry.write_text(json.dumps([{"path": str(brain), "space_type": "agent_brain",
                                     "agent_ids": ["openclaw/b"]}]), encoding="utf-8")
    os.utime(registry, ns=(2, 2))
    assert resolve_memory_scope(brain)["agent_ids"] == ["openclaw/b"]
    assert len(resolved) == 2


def test_only_sessions_past_a_topic_cursor_are_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    store = SharedMemoryStore(tmp_path / "project")
    done = store.start_session("agy", "done", capture_enabled=True)["id"]
    fresh = store.start_session("agy", "fresh", capture_enabled=True)["id"]
    store.append_message(done, "user", "Cambia el botón de Jugar en src/ui/menu.py")
    store.append_message(fresh, "user", "Revisa la textura del fondo")
    store.process_topics(done)

    def pending():
        with store._connect() as db:
            return [row[0] for row in db.execute(PENDING_TOPIC_SESSIONS)]

    assert pending() == [fresh]
    assert store.process_topics(fresh, coverage=False)["coverage"] is None
    assert pending() == []
    store.append_message(done, "assistant", "Hecho")
    assert pending() == [done]
    with store._connect() as db:  # the file-reference cursor alone also counts
        db.execute("UPDATE topic_progress SET cursor=(SELECT MAX(rowid) FROM messages) WHERE session_id=?", (done,))
        db.execute("UPDATE topic_file_progress SET cursor=0 WHERE session_id=?", (done,))
    assert pending() == [done]
