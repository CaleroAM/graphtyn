import json
import subprocess

from graphtyn.core.agent_installer import install_agent, install_ci
from graphtyn.core.global_graph import list_projects, query_global, register_project, remove_project
from graphtyn.core.verification import verify_python_edits
from graphtyn.core.work_memory import attach_learning, reflect, save_result


def _graph(name="Service"):
    return {"nodes": [{"id": f"symbol:x:{name}", "name": name, "kind": "class", "degree": 2}], "links": []}


def test_global_registry_namespaces_projects_and_marks_cross_repo_candidates(tmp_path):
    registry = tmp_path / "global.json"
    first, second = tmp_path / "api", tmp_path / "web"
    first.mkdir(); second.mkdir()
    register_project(_graph(), first, "api", registry)
    result = register_project(_graph(), second, "web", registry)
    assert {item["tag"] for item in list_projects(registry)} == {"api", "web"}
    assert {node["id"] for node in result["nodes"]} == {"api::symbol:x:Service", "web::symbol:x:Service"}
    assert any(link["confidence"] == "AMBIGUOUS" for link in result["links"])
    assert set(query_global("Service", registry)["projects"]) == {"api", "web"}
    remove_project("api", registry)
    assert [item["tag"] for item in list_projects(registry)] == ["web"]


def test_memory_reflection_weights_outcomes_and_detects_stale_sources(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("value = 1\n", encoding="utf-8")
    save_result(tmp_path, "where?", "service", ["Service"], "useful", ["service.py"])
    first = reflect(tmp_path)
    assert first["nodes"]["Service"]["label"] == "preferred"
    assert first["stale_records"] == 0
    source.write_text("value = 2\n", encoding="utf-8")
    second = reflect(tmp_path)
    assert second["stale_records"] == 1
    assert "re-verify" in (tmp_path / ".graphtyn" / "LESSONS.md").read_text(encoding="utf-8")
    context = attach_learning({"nodes": [{"id": "x", "name": "Service"}]}, tmp_path)
    assert context["learning"]["Service"]["stale_signals"] == 1


def test_differential_verifier_is_honest_about_semantic_edits(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "calc.py"
    source.write_text("def total(x):\n    return x + 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "calc.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    source.write_text("def total(x):\n    return x + 2\n", encoding="utf-8")
    result = verify_python_edits(tmp_path, "HEAD")
    assert result["counts"]["unsupported"] == 1
    assert result["counts"]["equivalent"] == 0


def test_agent_installer_is_idempotent(tmp_path):
    install_agent(tmp_path, "cursor")
    install_agent(tmp_path, "cursor")
    text = (tmp_path / ".cursor/rules/graphtyn.mdc").read_text(encoding="utf-8")
    assert text.count("# Graphtyn") == 1


def test_ci_installer_generates_auditable_github_workflow(tmp_path):
    target = install_ci(tmp_path, "github", "medium")
    text = target.read_text(encoding="utf-8")
    assert "graphtyn ci-check" in text
    assert "--max-risk medium" in text
    assert "pull_request" in text
