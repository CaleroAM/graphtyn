import json
from aether_graph.core.storage import project_store_dir

def test_homonymous_nested_projects_have_distinct_store(tmp_path):
    base = tmp_path / "store"
    outer = tmp_path / "same"
    inner = outer / "same"
    inner.mkdir(parents=True)
    assert project_store_dir(base, outer) != project_store_dir(base, inner)

def test_legacy_store_migrates_only_for_exact_project(tmp_path):
    base = tmp_path / "store"
    project = tmp_path / "demo"
    project.mkdir()
    legacy = base / "demo"
    legacy.mkdir(parents=True)
    (legacy / "index.json").write_text(json.dumps({"metadata": {"path": str(project)}, "nodes": [], "links": []}))
    target = project_store_dir(base, project)
    assert target != legacy and (target / "index.json").exists()

def test_legacy_store_from_other_path_is_not_migrated(tmp_path):
    base = tmp_path / "store"
    project = tmp_path / "demo"
    project.mkdir()
    legacy = base / "demo"
    legacy.mkdir(parents=True)
    (legacy / "index.json").write_text(json.dumps({"metadata": {"path": "/different/demo"}}))
    target = project_store_dir(base, project)
    assert not (target / "index.json").exists()
