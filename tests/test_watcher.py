import json

from aether_graph.core.watcher import ProjectWatcher


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
