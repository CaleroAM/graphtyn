import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from graphtyn.api import agent_activity
from graphtyn.cli import main
from graphtyn.core import prompt_context
from graphtyn.core.history import HistoryTracker
from graphtyn.core.query_log import (ACTION, RETENTION_DAYS, prune_queries, record_query, recent_queries, selection_reasons,
                                     set_logging, usage_summary)

MCP_RUNNER = "from pathlib import Path\nfrom graphtyn.mcp_server import run_mcp_server\nrun_mcp_server(Path(%r))\n"
REQUEST = "¿Cómo se crea un pedido y se calcula su total?"


@pytest.fixture
def project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(home))
    root = tmp_path / "tienda"
    (root / "tienda").mkdir(parents=True)
    (root / "tienda" / "pedidos.py").write_text(
        "from .precios import calcular_total\n\n\ndef crear_pedido(entrada):\n    return calcular_total(entrada)\n")
    (root / "tienda" / "precios.py").write_text(
        "def aplicar(importe):\n    return importe\n\n\ndef calcular_total(entrada):\n    return aplicar(entrada)\n")
    monkeypatch.setattr("sys.argv", ["graphtyn", "reindex", "--path", str(root)])
    main()
    return root


def _mcp(root, requests):
    source = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": source}
    return subprocess.run([sys.executable, "-c", MCP_RUNNER % str(root)], input="\n".join(json.dumps(r) for r in requests) + "\n",
                          capture_output=True, text=True, env=env, timeout=120, check=True)


def _query(request_id, **arguments):
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": "graph_query_intent", "arguments": {"request": REQUEST, "intent": "flow", **arguments}}}


def test_reasons_say_whether_a_word_or_a_relation_brought_each_entity():
    package = {
        "intent_terms": ["cómo", "pedido", "registra"],
        "nodes": [{"id": "a", "name": "crear_pedido", "file": "tienda/pedidos.py"},
                  {"id": "b", "name": "calcular_total", "file": "tienda/precios.py"},
                  {"id": "c", "name": "suelta", "file": "x.py"}],
        "links": [{"source": "a", "target": "b", "label": "llama"}],
    }
    reasons = selection_reasons(package)
    assert reasons["a"] == {"kind": "terms", "text": "Coincide con: pedido"}
    assert reasons["b"] == {"kind": "relation", "text": "Relación «llama» desde crear_pedido"}
    assert reasons["c"]["kind"] == "index"


def test_terms_match_ignoring_case_and_accents_and_skip_short_words():
    package = {"intent_terms": ["Canción", "de"], "nodes": [{"id": "a", "name": "cancion_de_cuna", "file": "m.py"}]}
    assert selection_reasons(package)["a"]["text"] == "Coincide con: Canción"


def test_mcp_query_records_the_client_the_entities_and_why(project):
    _mcp(project, [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "claude-code"}}},
                   _query(2)])
    query = recent_queries(HistoryTracker(project))[0]
    assert (query["agent"], query["source"], query["request"]) == ("claude-code", "mcp", REQUEST)
    assert query["context_id"] and query["delivered"] is True
    by_name = {item["name"]: item for item in query["entities"]}
    assert by_name["crear_pedido"]["file"] == "tienda/pedidos.py"
    assert by_name["crear_pedido"]["why"]["kind"] == "terms"


def test_mcp_followup_records_which_package_it_extends(project):
    first = _mcp(project, [_query(1)])
    assert first.stdout
    with_context = [_query(1), None]
    context = json.loads(json.loads(first.stdout.splitlines()[0])["result"]["content"][0]["text"])["context_id"]
    with_context[1] = _query(2, extends_context_id=context)
    _mcp(project, with_context)
    newest = recent_queries(HistoryTracker(project))[0]
    assert newest["extends_context_id"] == context
    assert usage_summary(recent_queries(HistoryTracker(project)))["extended"] == 1


def test_hook_records_the_client_once_across_its_parts(project):
    payload = {"prompt": "¿Cómo funciona crear_pedido cuando llama a calcular_total?", "cwd": str(project)}
    first = prompt_context.handle_prompt_hook(payload, project, part=1, parts=2, client="codex")
    assert first["reason"] == "code_anchor"
    prompt_context.handle_prompt_hook(payload, project, part=2, parts=2, client="codex")
    queries = recent_queries(HistoryTracker(project))
    assert [(query["agent"], query["source"]) for query in queries] == [("codex", "hook")]


def test_a_failing_log_never_breaks_the_query(tmp_path):
    class Broken:
        def log_event(self, *_args):
            raise OSError("disco lleno")

    record_query(tmp_path, {"intent": "flow", "nodes": []}, source="mcp", tracker=Broken())


def test_activity_endpoint_summarizes_what_passes_through_graphtyn(project):
    tracker = HistoryTracker(project)
    package = {"intent": "flow", "request": "a", "do_not_expand": True,
               "nodes": [{"id": "x", "name": "f", "file": "tienda/pedidos.py"}]}
    record_query(project, package, source="mcp", agent="claude-code", tracker=tracker)
    record_query(project, {**package, "do_not_expand": False}, source="hook", agent="codex", extends="ctx", tracker=tracker)
    data = agent_activity.agent_activity(str(project), 1)
    assert data["ok"] is True and len(data["queries"]) == 1 and data["queries"][0]["agent"] == "codex"
    usage = data["usage"]
    assert usage["queries"] == 2 and usage["sufficient"] == 1 and usage["extended"] == 1
    assert usage["by_agent"] == {"claude-code": 1, "codex": 1}
    assert usage["top_files"] == [("tienda/pedidos.py", 2)]


def test_activity_endpoint_rejects_a_missing_project(tmp_path):
    assert agent_activity.agent_activity(str(tmp_path / "nada"), 5).status_code == 404


def test_old_queries_are_deleted_and_other_events_stay(project):
    tracker = HistoryTracker(project)
    record_query(project, {"intent": "flow", "request": "reciente", "nodes": []}, source="mcp", tracker=tracker)
    tracker.log_event("mcp", "blast_radius", "otro evento", {})
    old = time.time() - (RETENTION_DAYS + 1) * 86400
    with sqlite3.connect(tracker.db_path) as conn:
        conn.execute("INSERT INTO observations (session_id, timestamp, action_type, summary, details) VALUES ('mcp', ?, ?, 's', ?)",
                     (old, ACTION, json.dumps({"request": "antigua"})))
        conn.execute("INSERT INTO observations (session_id, timestamp, action_type, summary, details) VALUES ('mcp', ?, 'blast_radius', 's', '{}')", (old,))
    assert prune_queries(tracker) == 1
    with sqlite3.connect(tracker.db_path) as conn:
        details = [row[0] for row in conn.execute("SELECT details FROM observations WHERE action_type = ?", (ACTION,))]
        kept = conn.execute("SELECT COUNT(*) FROM observations WHERE action_type = 'blast_radius'").fetchone()[0]
    assert len(details) == 1 and "reciente" in details[0] and kept == 2


def test_turning_logging_off_stops_new_records_but_old_ones_still_expire(project):
    tracker = HistoryTracker(project)
    set_logging(tracker, False)
    old = time.time() - (RETENTION_DAYS + 1) * 86400
    with sqlite3.connect(tracker.db_path) as conn:
        conn.execute("INSERT INTO observations (session_id, timestamp, action_type, summary, details) VALUES ('mcp', ?, ?, 's', '{}')", (old, ACTION))
    record_query(project, {"intent": "flow", "request": "x", "nodes": []}, source="mcp", tracker=tracker)
    with sqlite3.connect(tracker.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations WHERE action_type = ?", (ACTION,)).fetchone()[0] == 0


def test_the_switch_reaches_a_real_mcp_process_started_elsewhere(project):
    # MCP has its own environment: the setting must live where every process reads it.
    set_logging(HistoryTracker(project), False)
    _mcp(project, [_query(1)])
    assert recent_queries(HistoryTracker(project)) == []
    set_logging(HistoryTracker(project), True)
    _mcp(project, [_query(1)])
    assert len(recent_queries(HistoryTracker(project))) == 1


def test_settings_endpoint_toggles_logging_and_validates(project, monkeypatch):
    for name in ("GRAPHTYN_MEMORY_TOKENS", "GRAPHTYN_MEMORY_TOKENS_FILE", "GRAPHTYN_MEMORY_HTTP_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    done = agent_activity.agent_activity_settings({"path": str(project), "logging": False}, None)
    assert done == {"ok": True, "logging": False}
    state = agent_activity.agent_activity(str(project), 5)
    assert state["logging"] is False and state["retention_days"] == RETENTION_DAYS
    assert agent_activity.agent_activity_settings({"path": str(project), "logging": "no"}, None).status_code == 422
    assert agent_activity.agent_activity_settings({"path": str(project / "nada"), "logging": True}, None).status_code == 404


def test_settings_endpoint_requires_a_writer_token_when_tokens_are_configured(project, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_MEMORY_TOKENS", json.dumps({"lector": "reader", "escritor": "writer"}))
    payload = {"path": str(project), "logging": False}
    assert agent_activity.agent_activity_settings(payload, None).status_code == 401
    assert agent_activity.agent_activity_settings(payload, "Bearer lector").status_code == 403
    assert agent_activity.agent_activity_settings(payload, "Bearer escritor")["logging"] is False


def test_summary_covers_seven_days_while_the_list_keeps_the_retention_window(project):
    tracker = HistoryTracker(project)
    with sqlite3.connect(tracker.db_path) as conn:
        conn.execute("INSERT INTO observations (session_id, timestamp, action_type, summary, details) VALUES ('mcp', ?, ?, 's', ?)",
                     (time.time() - 10 * 86400, ACTION, json.dumps({"request": "hace diez días"})))
    data = agent_activity.agent_activity(str(project), 5)
    assert [query["request"] for query in data["queries"]] == ["hace diez días"]
    assert data["usage"]["queries"] == 0
