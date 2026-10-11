import json
import subprocess

from graphtyn.core.watcher import ProjectWatcher


def test_watcher_includes_untracked_nonignored_sources(tmp_path):
    project = tmp_path / "project"
    store = tmp_path / "store"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (project / "new.py").write_text("value = 1\n", encoding="utf-8")
    (project / "ignored.py").write_text("secret = 1\n", encoding="utf-8")

    event = ProjectWatcher(project, store).scan_once(refresh=False)

    assert event["created"] == ["new.py"]


def test_watcher_detects_create_modify_delete(tmp_path):
    project = tmp_path / "project"
    store = tmp_path / "store"
    project.mkdir()
    watcher = ProjectWatcher(project, store, interval=0.1)

    source = project / "service.ts"
    source.write_text("export const value = 1;\n", encoding="utf-8")
    created = watcher.scan_once(refresh=False)
    assert created["created"] == ["service.ts"]

    source.write_text("export const value = 2;\n", encoding="utf-8")
    modified = watcher.scan_once(refresh=False)
    assert modified["modified"] == ["service.ts"]

    source.unlink()
    removed = watcher.scan_once(refresh=False)
    assert removed["removed"] == ["service.ts"]
    manifest = json.loads((store / "watch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"] == {}


def test_watcher_retries_when_refresh_fails(tmp_path, monkeypatch):
    project = tmp_path / "project"
    store = tmp_path / "store"
    project.mkdir()
    source = project / "service.cs"
    source.write_text("class Service {}\n", encoding="utf-8")
    watcher = ProjectWatcher(project, store)

    monkeypatch.setattr(watcher, "_refresh", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        watcher.scan_once(refresh=True)
    except RuntimeError:
        pass
    assert watcher._manifest == {}

    events = []
    monkeypatch.setattr(watcher, "_refresh", lambda changed, removed: events.append((changed, removed)))
    event = watcher.scan_once(refresh=True)
    assert event["created"] == ["service.cs"]
    assert events and events[0][0] == {"service.cs"}


def test_watcher_refreshes_index_atomically(tmp_path):
    project = tmp_path / "project"
    store = tmp_path / "store"
    project.mkdir()
    source = project / "service.py"
    source.write_text("def first():\n    return 1\n", encoding="utf-8")
    watcher = ProjectWatcher(project, store)

    watcher.scan_once(refresh=True)
    first_graph = json.loads((store / "index.json").read_text(encoding="utf-8"))
    assert first_graph["metadata"]["reindex_mode"] == "incremental_watch"
    assert any(node.get("name") == "first" for node in first_graph["nodes"])

    source.write_text("def second():\n    return 2\n", encoding="utf-8")
    watcher.scan_once(refresh=True)
    second_graph = json.loads((store / "index.json").read_text(encoding="utf-8"))
    assert any(node.get("name") == "second" for node in second_graph["nodes"])
    assert not (store / "index.tmp").exists()


def test_watcher_reconciles_offline_changes_before_start_returns(tmp_path):
    project = tmp_path / "project"
    store = tmp_path / "store"
    project.mkdir()
    source = project / "service.py"
    source.write_text("def before_restart():\n    return 1\n", encoding="utf-8")

    first = ProjectWatcher(project, store)
    first.scan_once(refresh=True)
    source.write_text("def after_restart():\n    return 2\n", encoding="utf-8")

    restarted = ProjectWatcher(project, store, interval=60)
    restarted.start()
    try:
        graph = json.loads((store / "index.json").read_text(encoding="utf-8"))
        assert any(node.get("name") == "after_restart" for node in graph["nodes"])
        assert not any(node.get("name") == "before_restart" for node in graph["nodes"])
        assert restarted.version == 1
        assert restarted.last_event["modified"] == ["service.py"]
    finally:
        restarted.stop()


def test_watcher_rebuilds_existing_index_when_manifest_is_missing(tmp_path):
    project = tmp_path / "project"
    store = tmp_path / "store"
    project.mkdir()
    source = project / "service.py"
    source.write_text("def current_source():\n    return 1\n", encoding="utf-8")
    store.mkdir()
    (store / "index.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")

    watcher = ProjectWatcher(project, store, interval=60)
    watcher.start()
    try:
        graph = json.loads((store / "index.json").read_text(encoding="utf-8"))
        assert any(node.get("name") == "current_source" for node in graph["nodes"])
        assert watcher.last_event["created"] == ["service.py"]
    finally:
        watcher.stop()
