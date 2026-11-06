import json
import os
import time

import pytest

from graphtyn.core import index_freshness
from graphtyn.core.storage import data_home, project_store_dir
from graphtyn.core.tree_sitter_backend import PARSER_VERSION


def _index(tmp_path, version="treesitter-v21-old", engine="onboarding_ast_pure"):
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    store = project_store_dir(data_home(), root)
    store.mkdir(parents=True, exist_ok=True)
    graph = {"nodes": [], "links": [], "metadata": {"indexed_with": engine, "incremental": {"cache_version": version}}}
    (store / "index.json").write_text(json.dumps(graph), encoding="utf-8")
    return root.resolve(), graph, store


@pytest.fixture
def spawned(monkeypatch):
    calls = []
    monkeypatch.setattr(index_freshness.subprocess, "Popen", lambda command, **_: calls.append(command))
    monkeypatch.setattr(index_freshness, "_STARTED", set())
    monkeypatch.setenv(index_freshness.AUTO_ENV, "1")
    return calls


def test_only_an_index_from_another_parser_is_stale():
    assert index_freshness.stale_status({"metadata": {"incremental": {"cache_version": PARSER_VERSION}}}) is None
    assert index_freshness.stale_status({"nodes": []}) is None
    status = index_freshness.stale_status({"metadata": {"incremental": {}}})
    assert status["built_with"] == "unknown" and status["current"] == PARSER_VERSION


def test_a_stale_index_is_rebuilt_once_with_its_engine(tmp_path, spawned):
    root, graph, store = _index(tmp_path)

    first = index_freshness.check(root, graph)
    second = index_freshness.check(root, graph)

    assert first["rebuilding"] and second["rebuilding"] and len(spawned) == 1
    assert spawned[0][-2:] == [str(root), "ast_pure"] and (store / index_freshness.LOCK_NAME).exists()


def test_another_process_respects_a_fresh_lock_and_retries_an_old_one(tmp_path, spawned, monkeypatch):
    root, graph, store = _index(tmp_path)
    lock = store / index_freshness.LOCK_NAME
    lock.write_text("123 ast_pure\n", encoding="utf-8")

    assert index_freshness.check(root, graph)["rebuilding"] and not spawned
    monkeypatch.setattr(index_freshness, "_STARTED", set())
    old = time.time() - index_freshness.LOCK_SECONDS - 60
    os.utime(lock, (old, old))
    index_freshness.check(root, graph)
    assert len(spawned) == 1


def test_cloud_indexes_and_disabled_rebuilds_only_report_the_command(tmp_path, spawned, monkeypatch):
    root, graph, _store = _index(tmp_path, engine="ast_cloud")
    assert index_freshness.check(root, graph)["action"] == f"graphtyn reindex --path {root}"
    monkeypatch.setenv(index_freshness.AUTO_ENV, "0")
    root, graph, _store = _index(tmp_path / "other")
    assert not index_freshness.check(root, graph)["rebuilding"] and not spawned


def test_graph_answers_carry_the_status_and_a_note(tmp_path, spawned):
    root, graph, _store = _index(tmp_path)
    index_freshness.check(root, graph)

    result = index_freshness.annotate({"guidance": "Cite file:line."}, root)

    assert result["index_status"]["built_with"] == "treesitter-v21-old"
    assert result["guidance"].startswith("Cite file:line. The index was built with parser treesitter-v21-old")
    current_root, current, _store = _index(tmp_path / "current", version=PARSER_VERSION)
    index_freshness.check(current_root, current)
    assert "index_status" not in index_freshness.annotate({}, current_root)


def test_the_rebuild_releases_its_lock_only_when_it_succeeds(tmp_path, monkeypatch):
    root, _graph, store = _index(tmp_path)
    lock = store / index_freshness.LOCK_NAME
    import graphtyn.api.main as api

    lock.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(api, "_execute_reindex", lambda payload: (_ for _ in ()).throw(RuntimeError("boom")))
    assert index_freshness._rebuild(str(root), "ast_pure") == 1 and lock.exists()
    seen = []
    monkeypatch.setattr(api, "_execute_reindex", lambda payload: seen.append(payload) or {"ok": True})
    assert index_freshness._rebuild(str(root), "ast_local_llm") == 0 and not lock.exists()
    assert seen == [{"path": str(root), "engine": "ast_local_llm"}]


def test_the_mcp_loader_checks_the_saved_index(tmp_path, spawned):
    from graphtyn.core.ast_parser import ASTParser
    from graphtyn.mcp_server import _tag_graph_result, get_workspace_graph_with_meta

    root, _graph, _store = _index(tmp_path)
    get_workspace_graph_with_meta(root, ASTParser())

    assert _tag_graph_result({}, root)["index_status"]["rebuilding"] and len(spawned) == 1
