import json
import os
import subprocess
import sys
from pathlib import Path

from graphtyn.core.ambiguity_review import ambiguity_queue, apply_decisions, relation_key, save_decision
from graphtyn.core.answer_validation import validate_answer
from graphtyn.core.change_report import render_change_report
from graphtyn.core.incremental_status import build_update_status, save_update_status


def graph():
    return {"nodes": [
        {"id": "symbol:src/service.py:Service", "name": "Service", "kind": "class", "file": "src/service.py", "line": 3, "details": "Coordinates jobs"},
        {"id": "symbol:src/api.py:handler", "name": "handler", "kind": "function", "file": "src/api.py", "line": 8, "details": "Calls Service"},
        {"id": "file:src/service.py", "name": "service.py", "kind": "file", "details": "src/service.py"}],
        "links": [{"source": "symbol:src/api.py:handler", "target": "symbol:src/service.py:Service", "label": "llama", "confidence": "AMBIGUOUS", "file": "src/api.py", "line": 9}],
        "metadata": {"parser_version": "v1"}}


def test_answer_validation_requires_traceable_evidence():
    result = validate_answer(graph(), "handler calls Service (src/api.py:9). UnknownThing controls billing.")
    assert result["summary"]["total"] == 2
    assert result["summary"]["supported"] >= 1
    assert result["summary"]["unsupported"] >= 1


def test_ambiguity_decisions_are_persistent_and_applied(tmp_path):
    key = relation_key(graph()["links"][0])
    assert ambiguity_queue(graph(), tmp_path)["pending"] == 1
    save_decision(tmp_path, key, "accept", "checked source")
    assert apply_decisions(graph(), tmp_path)["links"][0]["confidence"] == "REVIEWED"
    assert ambiguity_queue(graph(), tmp_path)["reviewed"] == 1
    save_decision(tmp_path, key, "reject")
    assert apply_decisions(graph(), tmp_path)["links"] == []


def test_incremental_status_exposes_added_modified_removed_and_cost(tmp_path):
    old, new = graph(), graph()
    new["nodes"][-1]["details"] = "new summary"
    new["nodes"].append({"id": "file:src/new.py", "name": "new.py", "kind": "file", "details": "src/new.py"})
    status = build_update_status(new, old, mode="incremental", started_at=0, enriched_files=2, ai_calls=1)
    assert status["added"] == ["src/new.py"]
    assert status["modified"] == ["src/service.py"]
    assert status["estimated_paid_tokens"] == 0
    assert json.loads(save_update_status(tmp_path, status).read_text())["local_ai_calls"] == 1


def test_change_report_contains_required_sections(tmp_path):
    report = render_change_report(tmp_path, {"base": "main", "changed_files": ["src/a.py"], "changed_symbols": [], "impacted_nodes": [], "impacted_count": 0, "risk": {"level": "low", "score": 5}, "verification_plan": [], "conflicts": [], "conflict_detection": "checked"})
    for heading in ("GRAPHTYN CHANGE REPORT", "Blast radius", "Recommended verification", "Evidence policy"):
        assert heading in report


def test_docker_and_compose_publish_expected_port():
    root = Path(__file__).resolve().parent.parent
    assert "EXPOSE 9210" in (root / "Dockerfile").read_text()
    assert "127.0.0.1:9210:9210" in (root / "docker-compose.yml").read_text()


def test_real_cli_generates_git_change_report(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    project = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(project), "GRAPHTYN_WATCH": "0"}
    run = subprocess.run([sys.executable, "-m", "graphtyn.cli", "impact", "--base", "HEAD", "--path", str(tmp_path), "--json"], cwd=project, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["changed_files"] == ["app.py"]
    assert Path(data["report"]).is_file()
