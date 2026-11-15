"""Regression guard: a memory-sync cycle with no new data does no real work.

A watcher runs this cycle every few seconds for days. Three times a cycle without changes kept a CPU
core busy: re-reading the project registry per session, re-parsing every transcript and spawning one
``git`` per Antigravity workspace URI. The second cycle here must spawn no process, parse no transcript
and process no topic session.
"""
import json
import sqlite3
import subprocess

from graphtyn.core import antigravity_workspaces, history_stream, memory_topics
from graphtyn.core.history_import import save_source, sync_memory_workspace


def _fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "graphtyn-home"))
    # Default sources live under the home directory: keep the developer's own histories out.
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    project = tmp_path / "project"; project.mkdir()
    agy_root = tmp_path / ".gemini" / "antigravity-cli"
    for index in range(3):
        session_id = f"1111111{index}-1111-4111-8111-111111111111"
        transcript = agy_root / "brain" / session_id / ".system_generated" / "logs" / "transcript.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("\n".join(json.dumps(row) for row in [
            {"source": "USER_EXPLICIT", "type": "USER_INPUT", "content": f"Revisa el módulo {index} de pagos"},
            {"source": "MODEL", "type": "GENERIC", "content": f"Revisado el módulo {index}"},
        ]) + "\n", encoding="utf-8")
    db = sqlite3.connect(agy_root / "conversation_summaries.db")
    db.execute("CREATE TABLE conversation_summaries (conversation_id TEXT, workspace_uris TEXT)")
    db.executemany("INSERT INTO conversation_summaries VALUES (?, ?)",
                   [(f"1111111{i}-1111-4111-8111-111111111111", json.dumps([project.as_uri()])) for i in range(3)])
    db.commit(); db.close()
    source_config = tmp_path / "history-sources.json"
    monkeypatch.setattr("graphtyn.core.history_import.sources_config_file", lambda: source_config)
    save_source("antigravity", str(agy_root), label="AGY", project_path=project, agent_id="agy", path=source_config)
    antigravity_workspaces.clear_caches()
    return project


def test_second_idle_cycle_spawns_nothing_and_reparses_nothing(tmp_path, monkeypatch):
    project = _fixture(tmp_path, monkeypatch)
    first = sync_memory_workspace(project, enrich=False)
    assert first["ok"] and first["discovered"] == 3
    assert first["topic_processing"]["sessions"] == 3

    home = tmp_path / "graphtyn-home"

    def written():
        return {str(path.relative_to(home)): path.stat().st_mtime_ns for path in home.rglob("*")
                if path.is_file() and not path.name.endswith(("-shm", ".lock"))}

    before = written()
    spawned, parsed, topics = [], [], []
    real_run, real_preview, real_topics = (subprocess.run, history_stream._preview_jsonl_uncached,
                                           memory_topics.TopicMemoryMixin.process_topics)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a) or real_run(*a, **k))
    monkeypatch.setattr(history_stream, "_preview_jsonl_uncached",
                        lambda *a: parsed.append(a[0]) or real_preview(*a))
    monkeypatch.setattr(memory_topics.TopicMemoryMixin, "process_topics",
                        lambda self, *a, **k: topics.append(a) or real_topics(self, *a, **k))

    second = sync_memory_workspace(project, enrich=False)
    assert second["ok"] and second["discovered"] == 3
    assert len(second["import"].get("imported", [])) == 0
    assert spawned == [], "an idle cycle must not start processes"
    assert parsed == [], "an idle cycle must not re-parse unchanged transcripts"
    assert topics == [], "an idle cycle must not walk sessions without pending messages"
    changed = sorted(name for name, stamp in written().items() if before.get(name) != stamp)
    assert changed == [], f"an idle cycle must not write: {changed}"


def test_a_new_turn_after_idle_cycles_is_still_captured(tmp_path, monkeypatch):
    project = _fixture(tmp_path, monkeypatch)
    sync_memory_workspace(project, enrich=False)
    sync_memory_workspace(project, enrich=False)
    transcript = next((tmp_path / ".gemini").rglob("transcript.jsonl"))
    with transcript.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"source": "USER_EXPLICIT", "type": "USER_INPUT",
                                 "content": "Ahora añade pruebas al módulo de pagos"}) + "\n")
    third = sync_memory_workspace(project, enrich=False)
    assert third["topic_processing"]["sessions"] == 1
    assert third["topic_processing"]["messages"] >= 1
