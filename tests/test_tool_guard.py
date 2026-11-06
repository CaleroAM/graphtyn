import json

from graphtyn.core import tool_guard
from graphtyn.core.history import HistoryTracker
from graphtyn.core.query_log import record_query, set_logging
from graphtyn.core.storage import data_home, project_store_dir


def _project(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "billing.py").write_text("def charge():\n    pass\n", encoding="utf-8")
    store = project_store_dir(data_home(), root)
    store.mkdir(parents=True, exist_ok=True)
    (store / "index.json").write_text("{}", encoding="utf-8")
    return root


def _package(root, *, complete=True, agent="claude-code"):
    package = {"intent": "flow", "request": "¿Cómo se cobra?", "do_not_expand": complete, "source_evidence": [{}],
               "nodes": [{"id": "s:charge", "name": "charge", "kind": "function", "file": "src/billing.py", "line": 1}]}
    record_query(root, package, source="mcp", agent=agent, request=package["request"], context_id="ctx-1")


def _call(root, tool, tool_input, session="s1", now=None):
    payload = {"tool_name": tool, "tool_input": tool_input, "session_id": session, "cwd": str(root)}
    return tool_guard.handle_tool_hook(payload, now=now)


def test_a_read_the_complete_package_covers_gets_a_note_with_its_entities(tmp_path):
    root = _project(tmp_path)
    _package(root)

    outcome = _call(root, "Read", {"file_path": str(root / "src" / "billing.py")})

    assert outcome["recorded"] and outcome["target"] == "src/billing.py"
    assert "ctx-1" in outcome["note"] and "charge:1" in outcome["note"] and "src/billing.py" in outcome["note"]
    output = json.loads(tool_guard.hook_output(outcome))
    assert output["hookSpecificOutput"] == {"hookEventName": "PreToolUse", "additionalContext": outcome["note"]}


def test_package_notes_stop_after_two_per_session(tmp_path):
    root = _project(tmp_path)
    _package(root)
    notes = [_call(root, "Read", {"file_path": "src/billing.py"})["note"] for _ in range(4)]

    assert [bool(note) for note in notes] == [True, True, False, False]


def test_an_incomplete_package_or_another_client_gives_no_package_note(tmp_path):
    root = _project(tmp_path)
    _package(root, complete=False)
    assert not _call(root, "Read", {"file_path": "src/billing.py"})["note"]

    other = _project(tmp_path / "other")
    _package(other, agent="codex")
    assert not _call(other, "Read", {"file_path": "src/billing.py"})["note"]


def test_a_first_broad_search_without_a_query_is_reminded_once_per_session(tmp_path):
    root = _project(tmp_path)

    first = _call(root, "Grep", {"pattern": "charge"})
    second = _call(root, "Bash", {"command": "rg -n charge src/"})
    other_session = _call(root, "Glob", {"pattern": "**/*.py"}, session="s2")

    assert "graph_query_intent" in first["note"] and not second["note"] and other_session["note"]


def test_an_edit_another_session_made_recently_is_reported(tmp_path):
    root = _project(tmp_path)
    _call(root, "Edit", {"file_path": "src/billing.py"}, session="codex-session", now=1_000_000)

    same = _call(root, "Edit", {"file_path": "src/billing.py"}, session="codex-session", now=1_000_060)
    other = _call(root, "Write", {"file_path": "src/billing.py"}, session="s1", now=1_000_120)
    late = _call(root, "Edit", {"file_path": "src/billing.py"}, session="s3", now=1_000_000 + 3 * 3600)

    assert not same["note"] and "edited src/billing.py 1 min ago" in other["note"] and not late["note"]


def test_nothing_is_recorded_with_the_activity_log_off_or_without_an_index(tmp_path):
    root = _project(tmp_path)
    set_logging(HistoryTracker(root), False)
    assert _call(root, "Read", {"file_path": "src/billing.py"}) == {"recorded": False, "reason": "logging_off"}
    bare = tmp_path / "bare"
    bare.mkdir()
    assert _call(bare, "Read", {"file_path": "x.py"})["reason"] == "no_index"


def test_shell_commands_count_only_when_they_read_or_search():
    assert tool_guard.classify("Bash", {"command": "rg -n charge src/billing.py"}) == ("search", "src/billing.py", [])
    assert tool_guard.classify("Bash", {"command": "cd src && sed -n 1,20p billing.py"}) == ("read", "billing.py", [])
    assert tool_guard.classify("Bash", {"command": "git status"}) is None
    assert tool_guard.classify("mcp__graphtyn__graph_query_intent", {}) is None
    assert tool_guard.classify("Read", {"file_path": "/a/b.py", "offset": 10, "limit": 20}) == ("read", "/a/b.py", [10, 20])


def test_gaps_count_reads_outside_the_package_that_preceded_them(tmp_path):
    root = _project(tmp_path)
    _package(root)
    now = HistoryTracker(root).events_since("query_intent", 0, 1)[0]["timestamp"]
    _call(root, "Read", {"file_path": "src/billing.py"}, now=now + 10)
    _call(root, "Read", {"file_path": "src/tax.py"}, now=now + 20)
    _call(root, "Grep", {"pattern": "tax"}, now=now + 30)
    _call(root, "Read", {"file_path": "src/late.py"}, now=now + 3600)

    result = tool_guard.gaps(HistoryTracker(root), 7, now=now + 4000)

    assert result["followed_by_tools"] == 1 and result["reads_after"] == 2 and result["searches_after"] == 1
    assert result["reads_outside_package"] == 1 and result["top_outside_files"] == [("src/tax.py", 1)]


def test_install_registers_one_matched_group_and_keeps_user_hooks(tmp_path):
    root = tmp_path / "project"
    settings = root / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "./mine.sh"}]}]}}), encoding="utf-8")

    tool_guard.install(root)
    tool_guard.install(root)
    groups = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]

    assert len(groups) == 2 and groups[1]["matcher"] == tool_guard.CLAUDE_MATCHER
    assert groups[1]["hooks"][0]["command"] == tool_guard.HOOK_COMMAND and tool_guard.installed(root)
    tool_guard.uninstall(root)
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"] == groups[:1]
