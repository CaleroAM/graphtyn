import json
import subprocess
import sys

from graphtyn.core.agent_installer import install_agent, update_agent_manifest
from graphtyn.core.claude_capture import (HOOK_COMMAND, handle_stop_hook, install_claude_capture,
                                          run_capture_worker, uninstall_claude_capture)
from graphtyn.core.memory_scope import ensure_project_memory_scope
from graphtyn.core.shared_memory import SharedMemoryStore


def _transcript(path, project):
    rows = [
        {"type": "user", "sessionId": "s-1", "cwd": str(project), "uuid": "u1",
         "timestamp": "2026-10-25T10:00:00Z",
         "message": {"role": "user", "content": "<system-reminder>\nSYSTEM_POLICY\n</system-reminder>\n\n"
                                                "<graphtyn-context context_id=\"c1\">\nPREFETCHED_GRAPH\n"
                                                "</graphtyn-context>\nAgrega validación de email"}},
        {"type": "user", "sessionId": "s-1", "cwd": str(project), "uuid": "n1",
         "message": {"role": "user", "content": "<task-notification>\n<task-id>x</task-id>"}},
        {"type": "user", "sessionId": "s-1", "cwd": str(project), "uuid": "m1", "isMeta": True,
         "message": {"role": "user", "content": "Caveat: local command output"}},
        {"type": "assistant", "sessionId": "s-1", "cwd": str(project), "uuid": "a1",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "privado"},
             {"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}},
        {"type": "user", "sessionId": "s-1", "cwd": str(project), "uuid": "u2",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t1", "content": "SECRET_TOOL_OUTPUT"}]}},
        {"type": "assistant", "sessionId": "s-1", "cwd": str(project), "uuid": "a2",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "Añadí validate_email."}]}},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_hook_install_is_idempotent_and_preserves_user_hooks(tmp_path):
    settings = tmp_path / ".claude/settings.local.json"
    settings.parent.mkdir()
    user_hook = {"matcher": "", "hooks": [{"type": "command", "command": "echo done"}]}
    settings.write_text(json.dumps({"hooks": {"Stop": [user_hook]}, "model": "sonnet"}))

    install_claude_capture(tmp_path)
    install_claude_capture(tmp_path)
    stop = json.loads(settings.read_text())["hooks"]["Stop"]
    assert stop[0] == user_hook
    assert [group["hooks"][0]["command"] for group in stop].count(HOOK_COMMAND) == 1

    assert uninstall_claude_capture(tmp_path)["removed"] is True
    assert json.loads(settings.read_text()) == {"hooks": {"Stop": [user_hook]}, "model": "sonnet"}


def test_stop_hook_requires_opt_in_and_never_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    install_agent(project, "claude")
    transcript = _transcript(tmp_path / "s-1.jsonl", project)
    spawned = []
    payload = {"transcript_path": str(transcript), "cwd": str(project / "src"), "session_id": "s-1"}

    assert handle_stop_hook(payload, spawn=lambda *a, **k: spawned.append(a))["reason"] == "capture_not_enabled"
    update_agent_manifest(project, claude_capture={"enabled": True})
    result = handle_stop_hook(payload, spawn=lambda command, **kwargs: spawned.append(command))

    assert result["scheduled"] is True and result["path"] == str(project.resolve())
    assert spawned[0][-4:] == ["--transcript", str(transcript), "--path", str(project.resolve())]
    assert handle_stop_hook({"cwd": str(project)})["reason"] == "transcript_missing"


def test_worker_captures_only_conversation_once(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    project = tmp_path / "proj"
    project.mkdir()
    ensure_project_memory_scope(project, agent_ids=["claude"])
    transcript = _transcript(tmp_path / "s-1.jsonl", project)

    run_capture_worker(project, str(transcript))
    run_capture_worker(project, str(transcript))

    with SharedMemoryStore(project)._connect() as db:
        rows = [tuple(row) for row in db.execute("SELECT agent_id, role, content FROM messages ORDER BY rowid")]
    assert rows == [("claude", "user", "Agrega validación de email"),
                    ("claude", "assistant", "Añadí validate_email.")]


def test_reinstalling_agent_keeps_claude_capture_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "state"))
    install_agent(tmp_path, "claude")
    update_agent_manifest(tmp_path, claude_capture={"enabled": True})
    install_agent(tmp_path, "claude")
    manifest = json.loads((tmp_path / ".graphtyn/agent-install.json").read_text())
    assert manifest["claude_capture"] == {"enabled": True}


def test_cli_hook_exits_cleanly_on_bad_stdin(tmp_path):
    process = subprocess.run([sys.executable, "-m", "graphtyn.cli", "memory", "claude-hook"],
                             input="not json", text=True, capture_output=True, cwd=tmp_path)
    assert process.returncode == 0
    assert "claude-hook" in process.stderr
