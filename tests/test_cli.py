import json
import os
import subprocess
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "aether-graph"


def _run_cli(args, cwd, home):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([str(CLI)] + args, cwd=str(cwd), env=env,
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
    assert "AetherGraph" in hook.read_text(encoding="utf-8")
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

    configs = list((home / ".aether-graph").rglob("config.json"))
    assert configs, "config.json no persistido"
    data = json.loads(configs[0].read_text(encoding="utf-8"))
    assert data["respect_git"] is False


def test_reindex_ast_local_fallback_no_server(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), http_proxy="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1", no_proxy="")
    res = subprocess.run([str(CLI), "reindex", "--engine", "ast_pure", "--path", str(git_repo)],
                         cwd=str(git_repo), env=env, capture_output=True, text=True, timeout=90)
    assert res.returncode == 0
    assert "Reindexado AST local" in res.stdout
    assert "nodos" in res.stdout and "conectores" in res.stdout


def test_reindex_via_server_when_available(git_repo, tmp_path):
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 9210), timeout=1)
        s.close()
    except OSError:
        pytest.skip("servidor aether-graph no activo")
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["reindex", "--engine", "ast_pure", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    assert "modo full" in res.stdout


def test_init_creates_aether_dir(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["init", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    assert (git_repo / ".aether-graph" / "aether.json").exists()


def test_query_returns_matching_symbols(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    res = _run_cli(["query", "helper", "--path", str(git_repo)], git_repo, home)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["query"] == "helper"
    assert len(data["matches"]) >= 1


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
    assert ".aether-graph/" in gi.read_text(encoding="utf-8")

    res2 = _run_cli(["init", "--path", str(tmp_path)], tmp_path, home)
    assert res2.returncode == 0
    lines = gi.read_text(encoding="utf-8").splitlines()
    assert lines.count(".aether-graph/") == 1


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


def test_pr_impact_cli_json(git_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (git_repo / "a.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    result = _run_cli(["pr-impact", "--path", str(git_repo), "--json"], git_repo, home)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["changed_files"] == ["a.py"]
    assert data["risk"]["score"] > 0
