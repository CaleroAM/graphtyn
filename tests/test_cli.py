import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "graphtyn.cli"]


def _run_cli(args, cwd, home):
    env = dict(os.environ, GRAPHTYN_HOME=str(home / ".graphtyn"))
    return subprocess.run(CLI + args, cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=90)


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_hook_install_and_uninstall(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["hook", "install", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    hook = git_repo / ".git" / "hooks" / "post-commit"
    assert hook.exists()
    assert "Graphtyn" in hook.read_text(encoding="utf-8")
    assert os.access(hook, os.X_OK)

    res2 = _run_cli(["hook", "uninstall", "--path", str(git_repo)], git_repo, home)
    assert res2.returncode == 0
    assert not hook.exists()

    res3 = _run_cli(["hook", "uninstall", "--path", str(git_repo)], git_repo, home)
    assert res3.returncode == 0
    assert "No hay hook" in res3.stdout


def test_gitignore_on_off_writes_isolated_config(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    on = _run_cli(["gitignore", "on", "--path", str(git_repo)], git_repo, home)
    assert on.returncode == 0
    assert "ON" in on.stdout
    off = _run_cli(["gitignore", "off", "--path", str(git_repo)], git_repo, home)
    assert off.returncode == 0
    assert "OFF" in off.stdout

    configs = list((home / ".graphtyn").rglob("config.json"))
    assert configs, "config.json no persistido"
    data = json.loads(configs[0].read_text(encoding="utf-8"))
    assert data["respect_git"] is False


def test_report_command_writes_graphtyn_report(git_repo, tmp_path):
    (git_repo / "README.md").write_text("# Demo\n\nDemo coordinates background jobs for a local operations team.\n", encoding="utf-8")
    home = tmp_path / "home-report"
    home.mkdir()
    result = _run_cli(["report", "--path", str(git_repo)], git_repo, home)
    assert result.returncode == 0, result.stderr
    report = git_repo / "GRAPHTYN_REPORT.md"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Demo coordinates background jobs" in text
    assert "## Report metrics" in text


def test_reindex_ast_local_fallback_no_server(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, GRAPHTYN_HOME=str(home / ".graphtyn"), http_proxy="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1", no_proxy="")
    res = subprocess.run(CLI + ["reindex", "--engine", "ast_pure", "--path", str(git_repo)],
                         cwd=str(git_repo), env=env, capture_output=True, text=True, timeout=90)
    assert res.returncode == 0
    assert "Reindexado AST local" in res.stdout
    assert "nodos" in res.stdout and "conectores" in res.stdout


def test_reindex_uses_server_or_safe_local_fallback_when_daemon_is_available(git_repo, tmp_path):
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 9210), timeout=1)
        s.close()
    except OSError:
        pytest.skip("servidor graphtyn no activo")
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["reindex", "--engine", "ast_pure", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    # A persistent daemon can reject an unregistered temporary project. The CLI
    # must then preserve functionality through its deterministic local fallback.
    assert "modo full" in res.stdout or "Reindexado AST local completado" in res.stdout


def test_init_creates_graphtyn_dir(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["init", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    assert (git_repo / ".graphtyn" / "graphtyn.json").exists()


def test_memory_projects_registers_remote_workspace_alias(git_repo, tmp_path):
    home = tmp_path / "home-project-alias"
    home.mkdir()
    alias = "/srv/agents/workspace/career"
    result = _run_cli(["memory", "projects", "--path", str(git_repo), "--alias", alias], git_repo, home)
    assert result.returncode == 0, result.stderr
    current = json.loads(result.stdout)["current"]
    assert alias in current["aliases"]


def test_query_returns_matching_symbols(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["query", "helper", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["query"] == "helper"
    assert len(data["matches"]) >= 1


def test_context_returns_grouped_compact_evidence(git_repo, tmp_path):
    home = tmp_path / "home-context"
    home.mkdir()
    res = _run_cli(["context", "helper", "a.py", "--path", str(git_repo), "--limit", "5"], git_repo, home)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["symbols"] == ["helper", "a.py"]
    assert len(data["contexts"]) == 2
    assert data["estimated_tokens"] > 0


def test_path_finds_bfs_route(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "a.py").write_text("def start_fn():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import start_fn\n\ndef end_fn():\n    return start_fn()\n", encoding="utf-8")
    res = _run_cli(["path", "start_fn", "end_fn", "--path", str(tmp_path)], tmp_path, home)
    assert res.returncode == 0
    assert "start_fn" in res.stdout and "end_fn" in res.stdout
    assert " -> " in res.stdout


def test_export_md_writes_architecture(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["export-md", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    out = git_repo / "ARCHITECTURE.md"
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "helper" in content


def test_init_creates_and_updates_gitignore(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["init", "--path", str(tmp_path)], tmp_path, home)
    assert res.returncode == 0
    gi = tmp_path / ".gitignore"
    assert gi.exists()
    assert ".graphtyn/" in gi.read_text(encoding="utf-8")

    res2 = _run_cli(["init", "--path", str(tmp_path)], tmp_path, home)
    assert res2.returncode == 0
    lines = gi.read_text(encoding="utf-8").splitlines()
    assert lines.count(".graphtyn/") == 1


def test_benchmark_cli_writes_reproducible_json(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"expected_symbols": [
        {"file": "a.py", "name": "helper", "kind": "function"}
    ]}), encoding="utf-8")
    output = tmp_path / "result.json"
    result = _run_cli([
        "benchmark", "--path", str(git_repo), "--ground-truth", str(truth),
        "--cache", str(tmp_path / "cache.json"), "--output", str(output),
    ], git_repo, home)
    assert result.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ground_truth"]["symbol_recall"] == 1
    assert data["warm_cache_seconds"] >= 0


def test_agent_benchmark_compares_token_reduction(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    treatment = tmp_path / "treatment.json"
    baseline = tmp_path / "baseline.json"
    treatment.write_text(json.dumps({"status": "SUCCESS", "duration_seconds": 80,
        "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}))
    baseline.write_text(json.dumps({"status": "SUCCESS", "duration_seconds": 100,
        "usage": {"input_tokens": 200, "output_tokens": 40, "total_tokens": 240}}))
    result = _run_cli(["agent-benchmark", "--treatment", str(treatment),
        "--baseline", str(baseline)], git_repo, home)
    assert result.returncode == 0
    assert json.loads(result.stdout)["reduction"]["total_tokens"] == 0.5


def test_agent_benchmark_reports_paired_quality(git_repo, tmp_path):
    home = tmp_path / "home2"
    home.mkdir()
    treatment = tmp_path / "treatment-paired.json"
    baseline = tmp_path / "baseline-paired.json"
    treatment.write_text(json.dumps([{"task_id": "q1", "quality_score": 1, "duration_seconds": 1, "usage": {"total_tokens": 50}}]))
    baseline.write_text(json.dumps([{"task_id": "q1", "quality_score": 0, "duration_seconds": 2, "usage": {"total_tokens": 100}}]))
    result = _run_cli(["agent-benchmark", "--treatment", str(treatment), "--baseline", str(baseline)], git_repo, home)
    data = json.loads(result.stdout)
    assert data["paired"]["quality_wins"] == 1
    assert data["paired"]["mean_token_delta"] == -50
    assert data["paired"]["token_permutation_p"] == 1.0


def test_agent_grade_scores_atomic_facts(git_repo, tmp_path):
    home = tmp_path / "home-grade"
    home.mkdir()
    runs = tmp_path / "runs.json"
    tasks = tmp_path / "tasks.json"
    runs.write_text(json.dumps([{"task_id": "q", "response": "Alpha and Beta"}]))
    tasks.write_text(json.dumps({"tasks": [{"id": "q", "key_facts": [
        {"id": "both", "patterns": ["Alpha", "Beta"]},
        {"id": "partial", "patterns": ["Alpha", "Gamma"]}
    ], "forbidden_facts": [{"id": "wrong", "patterns": ["Alpha", "Beta"]}]}]}))
    result = _run_cli(["agent-grade", "--runs", str(runs), "--tasks", str(tasks)], git_repo, home)
    data = json.loads(result.stdout)
    assert data[0]["quality_score"] == 0.75
    assert data[0]["adjusted_quality_score"] == 0.25


def test_agent_install_antigravity_uses_project_gemini_policy(git_repo, tmp_path):
    home = tmp_path / "home-antigravity"
    home.mkdir()
    result = _run_cli(["agent-install", "antigravity", "--path", str(git_repo)], git_repo, home)
    assert result.returncode == 0, result.stderr
    policy = (git_repo / "GEMINI.md").read_text(encoding="utf-8")
    assert "graphtyn query-intent" in policy
    assert "memory_ingest_turn" in policy
    assert "Before any repository listing" in policy
    assert "do_not_expand=true" in policy
    assert "without reopening files" in policy
    manifest = json.loads((git_repo / ".graphtyn" / "agent-install.json").read_text())
    assert manifest["platforms"] == ["antigravity"]
    assert manifest["tool_profile"] == "intent"
    mcp = json.loads((git_repo / ".agents/plugins/graphtyn/mcp_config.json").read_text())
    assert mcp["mcpServers"]["graphtyn"]["args"][-1] == "intent"
    assert (git_repo / ".agents/skills/graphtyn/SKILL.md").is_file()


def test_onboard_builds_index_and_full_antigravity_integration(git_repo, tmp_path):
    home = tmp_path / "home-onboard"
    home.mkdir()
    result = _run_cli(["onboard", "--agent", "antigravity", "--tool-profile", "full",
                       "--no-token", "--path", str(git_repo)], git_repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["index"]["nodes"] >= 1
    assert Path(data["index"]["index"]).is_file()
    assert data["dashboard"] == "http://127.0.0.1:9210"
    mcp = json.loads((git_repo / ".agents/plugins/graphtyn/mcp_config.json").read_text())
    assert mcp["mcpServers"]["graphtyn"]["args"] == ["mcp", "--tool-profile", "full"]


def test_onboard_indexes_unicode_tracked_paths(git_repo, tmp_path):
    nested = git_repo / "Assets" / "Código"
    nested.mkdir(parents=True)
    (nested / "GameManager.cs").write_text(
        "public class GameManager { public void Iniciar() {} }", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unicode fixture"], cwd=git_repo, check=True)
    home = tmp_path / "home-unicode"
    home.mkdir()
    result = _run_cli(["onboard", "--no-token", "--path", str(git_repo)], git_repo, home)
    assert result.returncode == 0, result.stderr
    graph = json.loads(Path(json.loads(result.stdout)["index"]["index"]).read_text(encoding="utf-8"))
    assert any(node["id"] == "file:Assets/Código/GameManager.cs" for node in graph["nodes"])


def test_agent_install_all_deduplicates_shared_instruction_files(git_repo, tmp_path):
    home = tmp_path / "home-all-agents"
    home.mkdir()
    result = _run_cli(["agent-install", "all", "--path", str(git_repo)], git_repo, home)
    assert result.returncode == 0, result.stderr
    files = json.loads(result.stdout)["files"]
    assert len(files) == len(set(files))
    assert files.count(str(git_repo / "AGENTS.md")) == 1


def test_agent_policies_enforce_context_stop_contract():
    root = Path(__file__).resolve().parents[1]
    for policy_path in (root / "AGENTS.md", root / "skills" / "graphtyn" / "SKILL.md"):
        policy = policy_path.read_text(encoding="utf-8")
        assert "do_not_expand=true" in policy
        assert "entire file" in policy
        assert "before" in policy.lower()


def test_pr_impact_cli_json(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (git_repo / "a.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    result = _run_cli(["pr-impact", "--path", str(git_repo), "--json"], git_repo, home)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["changed_files"] == ["a.py"]
    assert data["risk"]["score"] > 0


def test_global_cli_add_list_and_query(git_repo, tmp_path):
    home = tmp_path / "home-global"
    home.mkdir()
    registry = tmp_path / "registry.json"
    add = _run_cli(["global", "add", "--as", "demo", "--path", str(git_repo),
                    "--registry", str(registry)], git_repo, home)
    assert add.returncode == 0, add.stderr
    listing = _run_cli(["global", "list", "--registry", str(registry)], git_repo, home)
    assert json.loads(listing.stdout)["projects"][0]["tag"] == "demo"
    query = _run_cli(["global", "query", "helper", "--registry", str(registry)], git_repo, home)
    assert json.loads(query.stdout)["nodes"]


def test_memory_cli_and_ci_install(git_repo, tmp_path):
    home = tmp_path / "home-memory"
    home.mkdir()
    saved = _run_cli(["memory", "save", "--question", "where", "--answer", "helper",
                      "--nodes", "helper", "--files", "a.py", "--outcome", "useful",
                      "--path", str(git_repo)], git_repo, home)
    assert saved.returncode == 0, saved.stderr
    reflected = _run_cli(["memory", "reflect", "--path", str(git_repo)], git_repo, home)
    assert json.loads(reflected.stdout)["nodes"]["helper"]["label"] == "preferred"
    installed = _run_cli(["ci-install", "github", "--path", str(git_repo)], git_repo, home)
    assert installed.returncode == 0
    assert (git_repo / ".github/workflows/graphtyn.yml").is_file()


def test_memory_doctor_and_benchmark_cli(git_repo, tmp_path):
    home = tmp_path / "home-memory-benchmark"
    home.mkdir()
    doctor = _run_cli(["memory", "doctor", "--path", str(git_repo)], git_repo, home)
    dataset = Path(__file__).resolve().parents[1] / "benchmarks" / "shared_memory_v1.json"
    benchmark = _run_cli(["memory", "benchmark", "--dataset", str(dataset), "--path", str(git_repo)], git_repo, home)

    assert doctor.returncode == 0
    assert json.loads(doctor.stdout)["ok"] is True
    assert benchmark.returncode == 0
    metrics = json.loads(benchmark.stdout)["metrics"]
    assert metrics["recall_at_5"] == 1.0
    assert metrics["attribution_accuracy"] == 1.0
