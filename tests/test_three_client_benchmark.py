import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "run_three_client_mcp_comparison.py"
_SPEC = importlib.util.spec_from_file_location("run_three_client_mcp_comparison", _SCRIPT)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MODULE)


def test_normalizes_all_three_clients_without_inventing_missing_cost():
    opencode = _MODULE.normalize_usage("opencode", [
        {"type": "step_finish", "part": {"tokens": {"input": 10, "output": 2, "total": 12}}},
        {"type": "step_finish", "part": {"tokens": {"input": 4, "output": 1, "total": 5}}},
    ])
    codex = _MODULE.normalize_usage("codex", [
        {"type": "turn.completed", "usage": {"input_tokens": 20, "cached_input_tokens": 5,
                                                  "output_tokens": 3}},
    ])
    antigravity = _MODULE.normalize_usage("antigravity", [
        {"event": "result", "result": {"usage": {"inputTokens": 30, "outputTokens": 4,
                                                       "totalTokens": 34}}},
    ])
    assert opencode["total_tokens"] == 17
    assert codex["total_tokens"] == 23
    assert antigravity["total_tokens"] == 34
    assert all(row["provider_cost"] is None for row in (opencode, codex, antigravity))


def test_usage_accounting_separates_provider_total_cache_and_observed_retries():
    events = [
        {"type": "turn.completed", "usage": {
            "input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 3,
        }},
        {"type": "retry"},
    ]
    usage = _MODULE.normalize_usage("codex", events)

    accounting = _MODULE.usage_accounting("codex", events, usage)

    assert usage["total_tokens"] == 23
    assert accounting["technical_total_including_cache"] == 23
    assert accounting["cached_input_is_separate"] is False
    assert accounting["cached_input_is_subset_of_input"] is True
    assert accounting["reasoning_is_subset_of_output"] is True
    assert accounting["observed_retry_events"] == 1
    assert accounting["retry_coverage"].startswith("explicit_events_only")


def test_codex_usage_trace_discloses_aggregate_only():
    events = [{"type": "turn.completed", "usage": {
        "input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 3,
    }}]

    trace = _MODULE.usage_trace("codex", events)

    assert trace["granularity"] == "session_aggregate"
    assert trace["per_model_call_available"] is False
    assert trace["records"][0]["total_tokens"] == 23


def test_requires_explicit_client_model_mapping():
    assert _MODULE.parse_model_args(["codex=gpt-x", "antigravity=gemini-y"]) == {
        "codex": "gpt-x", "antigravity": "gemini-y"
    }


def test_preflight_can_be_filtered_to_one_requested_client(monkeypatch):
    monkeypatch.setattr(_MODULE.shutil, "which", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(_MODULE.subprocess, "run", lambda *args, **kwargs: type(
        "Probe", (), {"stdout": "1.0", "stderr": ""})())

    rows = _MODULE.preflight({"codex": "gpt-test"})
    missing = [row.client for row in rows
               if row.client in {"codex"} and (not row.executable or not row.model)]

    assert missing == []


def test_commands_bind_clients_to_isolated_workspace():
    workspace = Path("/tmp/isolated-benchmark")
    opencode = _MODULE.command_for("opencode", "provider/model", "prompt", workspace, 30)
    codex = _MODULE.command_for("codex", "model", "prompt", workspace, 30)
    assert opencode[opencode.index("--dir") + 1] == str(workspace)
    assert "--auto" in opencode
    assert "--skip-git-repo-check" in codex
    assert "--dangerously-bypass-approvals-and-sandbox" in codex


def test_antigravity_noninteractive_run_can_read_and_call_mcp():
    command = _MODULE.command_for("antigravity", "model", "prompt", Path("/tmp/work"), 30)
    assert "--dangerously-skip-permissions" in command
    assert "--sandbox" not in command


def test_codex_treatment_injects_mcp_despite_ignored_user_config():
    command = _MODULE.command_for(
        "codex", "model", "prompt", Path("/tmp/work"), 30,
        treatment=True, graphtyn_executable=Path("/tmp/graphtyn"),
    )
    rendered = " ".join(command)
    assert "mcp_servers.graphtyn_benchmark.command" in rendered
    assert "mcp_servers.graphtyn_benchmark.args" in rendered
    configured = next(value for value in command
                      if value.startswith("mcp_servers.graphtyn_benchmark.args="))
    mcp_args = __import__("json").loads(configured.split("=", 1)[1])
    assert mcp_args[mcp_args.index("--tool-profile") + 1] == "query"
    assert "--preload-index" in mcp_args


def test_workspace_copy_preserves_tracked_symlink(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    (source / "target").mkdir()
    (source / "target" / "data.txt").write_text("data", encoding="utf-8")
    (source / "linked").symlink_to("target", target_is_directory=True)
    subprocess.run(["git", "add", "target/data.txt", "linked"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True)

    _MODULE.make_workspace(source, destination, False, Path("/tmp/graphtyn"))

    assert (destination / "linked").is_symlink()
    assert (destination / "linked").readlink() == Path("target")
    assert (destination / "linked" / "data.txt").read_text(encoding="utf-8") == "data"


def _claude_events():
    usage = {"input_tokens": 12, "cache_read_input_tokens": 100,
             "cache_creation_input_tokens": 30, "output_tokens": 8}
    tool_use = {"type": "tool_use", "name": "mcp__graphtyn_benchmark__graph_query_intent", "input": {}}
    return [
        {"type": "system", "subtype": "init",
         "mcp_servers": [{"name": "graphtyn_benchmark", "status": "connected"}]},
        {"type": "assistant", "message": {"id": "msg_1", "content": [tool_use],
                                          "usage": {**usage, "output_tokens": 3}}},
        {"type": "assistant", "message": {"id": "msg_2", "content": [{"type": "text", "text": "ok"}],
                                          "usage": usage}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Respuesta final",
         "total_cost_usd": 0.01, "usage": usage},
    ]


def test_claude_usage_counts_cache_once_and_traces_each_model_call():
    events = _claude_events()

    usage = _MODULE.normalize_usage("claude", events)
    accounting = _MODULE.usage_accounting("claude", events, usage)
    trace = _MODULE.usage_trace("claude", events)

    assert usage["total_tokens"] == 150
    assert usage["cached_input_tokens"] == 100
    assert usage["provider_cost"] == 0.01
    assert accounting["cached_input_is_separate"] is True
    assert accounting["technical_total_including_cache"] == 150
    assert trace["granularity"] == "model_call"
    assert [row["output_tokens"] for row in trace["records"]] == [3, 8]
    assert _MODULE.answer_from_events("claude", events) == "Respuesta final"


def test_claude_missing_result_reports_no_tokens_and_failed_result_has_no_answer():
    assert _MODULE.normalize_usage("claude", [])["total_tokens"] is None
    failed = [{"type": "result", "is_error": True, "result": "API error"}]
    assert _MODULE.answer_from_events("claude", failed) == ""


def test_claude_mcp_evidence_proves_connection_and_calls():
    evidence = _MODULE.claude_mcp_evidence(_claude_events())
    assert evidence == {"server_status": "connected", "tool_calls": ["graph_query_intent"]}


def test_claude_command_is_read_only_and_isolates_mcp_per_arm():
    workspace = Path("/tmp/work")
    baseline = _MODULE.command_for("claude", "model", "prompt", workspace, 30)
    treatment = _MODULE.command_for("claude", "model", "prompt", workspace, 30, treatment=True,
                                    graphtyn_executable=Path("/tmp/graphtyn"))

    assert baseline[:3] == ["claude", "-p", "prompt"]
    for command in (baseline, treatment):
        assert "--strict-mcp-config" in command
        assert command[command.index("--setting-sources") + 1] == "project"
        assert "Edit" in command[command.index("--disallowedTools") + 1].split(",")
        assert "--bare" not in command
    empty = __import__("json").loads(baseline[baseline.index("--mcp-config") + 1])
    assert empty == {"mcpServers": {}}
    server = __import__("json").loads(treatment[treatment.index("--mcp-config") + 1])["mcpServers"]["graphtyn_benchmark"]
    assert server["command"] == "/tmp/graphtyn"
    assert server["args"][server["args"].index("--tool-profile") + 1] == "query"
    assert server["args"][-1] == str(workspace.resolve())
    assert _MODULE.command_for("claude", "m", "p", workspace, 30, claude_bare=True)[-1] == "--bare"


def test_workspace_copy_drops_tracked_claude_configuration(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    (source / ".claude").mkdir()
    (source / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (source / ".mcp.json").write_text("{}", encoding="utf-8")
    (source / "app.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True)

    destination = tmp_path / "destination"
    _MODULE.make_workspace(source, destination, False, Path("/tmp/graphtyn"))

    assert (destination / "app.py").is_file()
    assert not (destination / ".claude").exists()
    assert not (destination / ".mcp.json").exists()


def test_repetitions_alternate_arm_order_and_tag_runs(tmp_path, monkeypatch):
    import json
    import sys
    calls = []
    protocol = tmp_path / "protocol.json"
    tasks = tmp_path / "tasks.json"
    protocol.write_text(json.dumps({"status": "x", "design": {"tasks": ["T"]}}))
    tasks.write_text(json.dumps({"tasks": [{"id": "T", "request": "q"}]}))
    monkeypatch.setattr(_MODULE, "preflight", lambda models: [
        _MODULE.Preflight("claude", "/bin/claude", "1", models.get("claude"))])
    monkeypatch.setattr(_MODULE, "make_workspace", lambda *args, **kwargs: "sha")
    monkeypatch.setattr(_MODULE, "prepare_graphtyn_index", lambda *args, **kwargs: {"seconds": 0})

    def fake_run_cell(client, model, task, treatment, *args, repetition=1, **kwargs):
        calls.append((repetition, "graphtyn" if treatment else "baseline"))
        return {"usage": {"total_tokens": 10}, "repetition": repetition}

    monkeypatch.setattr(_MODULE, "run_cell", fake_run_cell)
    monkeypatch.setattr(sys, "argv", ["run", "--protocol", str(protocol), "--tasks", str(tasks),
                                      "--repo", str(tmp_path), "--output-dir", str(tmp_path / "out"),
                                      "--client", "claude", "--model", "claude=m", "--repetitions", "3",
                                      "--execute"])

    assert _MODULE.main() == 0
    assert calls == [(1, "baseline"), (1, "graphtyn"), (2, "graphtyn"), (2, "baseline"),
                     (3, "baseline"), (3, "graphtyn")]


def test_claude_graphify_arm_registers_only_the_graphify_server():
    workspace = Path("/tmp/work")
    command = _MODULE.command_for("claude", "model", "prompt", workspace, 30,
                                  graphify_bin=Path("/opt/graphify/bin"))
    config = json.loads(command[command.index("--mcp-config") + 1])

    assert list(config["mcpServers"]) == ["graphify_benchmark"]
    assert config["mcpServers"]["graphify_benchmark"]["command"] == "/opt/graphify/bin/graphify-mcp"
    assert config["mcpServers"]["graphify_benchmark"]["args"] == ["/tmp/work/graphify-out/graph.json"]
    assert "query_graph" in _MODULE.benchmark_prompt({"request": "q"}, False, graphify=True)
    with pytest.raises(ValueError):
        _MODULE.command_for("opencode", "m", "p", workspace, 30, graphify_bin=Path("/opt/graphify/bin"))


def test_codex_graphify_arm_registers_only_the_graphify_server():
    workspace = Path("/tmp/work")
    command = _MODULE.command_for("codex", "model", "prompt", workspace, 30, graphify_bin=Path("/opt/graphify/bin"))
    settings = [command[index + 1] for index, part in enumerate(command) if part == "-c"]

    assert 'mcp_servers.graphify_benchmark.command="/opt/graphify/bin/graphify-mcp"' in settings
    assert 'mcp_servers.graphify_benchmark.args=["/tmp/work/graphify-out/graph.json"]' in settings
    assert not any(setting.startswith("mcp_servers.graphtyn_benchmark") for setting in settings)
    assert "--ignore-user-config" in command


def test_graphify_arm_builds_its_graph_and_requires_the_install(tmp_path, monkeypatch):
    import sys
    calls = []
    protocol = tmp_path / "protocol.json"
    tasks = tmp_path / "tasks.json"
    protocol.write_text(json.dumps({"status": "x", "design": {"tasks": ["T"]}}))
    tasks.write_text(json.dumps({"tasks": [{"id": "T", "request": "q"}]}))
    monkeypatch.setattr(_MODULE, "preflight", lambda models: [
        _MODULE.Preflight("claude", "/bin/claude", "1", models.get("claude"))])
    monkeypatch.setattr(_MODULE, "make_workspace", lambda *args, **kwargs: "sha")
    monkeypatch.setattr(_MODULE, "prepare_graphify_graph", lambda *args, **kwargs: {"seconds": 1})

    def fake_run_cell(client, model, task, treatment, *args, repetition=1, graphify_bin=None, index_setup=None, **kwargs):
        calls.append((repetition, treatment, graphify_bin, index_setup))
        return {"usage": {"total_tokens": 10}, "repetition": repetition}

    monkeypatch.setattr(_MODULE, "run_cell", fake_run_cell)
    argv = ["run", "--protocol", str(protocol), "--tasks", str(tasks), "--repo", str(tmp_path),
            "--output-dir", str(tmp_path / "out"), "--client", "claude", "--model", "claude=m",
            "--repetitions", "2", "--arm", "graphify", "--execute"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        _MODULE.main()

    monkeypatch.setattr(sys, "argv", argv + ["--graphify-bin", str(tmp_path)])
    assert _MODULE.main() == 0
    assert calls == [(1, False, tmp_path, {"seconds": 1}), (2, False, tmp_path, {"seconds": 1})]


def test_prompt_hook_arm_sends_only_the_request_and_moves_instructions_to_system_prompt():
    task = {"request": "Traza processCommand"}
    message, system = _MODULE.benchmark_messages(task, True, prefetch=True)
    assert message == "Traza processCommand"
    assert "graphtyn-context" in system and not system.endswith("Traza processCommand")
    assert _MODULE.benchmark_messages(task, True)[1] is None

    command = _MODULE.command_for("claude", "m", message, Path("/tmp/work"), 30, treatment=True,
                                  graphtyn_executable=Path("/opt/graphtyn"), prefetch=True, system_prompt=system)
    settings = json.loads(command[command.index("--settings") + 1])
    hooks = settings["hooks"]["UserPromptSubmit"][0]["hooks"]
    assert [hook["command"] for hook in hooks] == [
        "/opt/graphtyn claude-context hook --path /tmp/work --part 1 --parts 2",
        "/opt/graphtyn claude-context hook --path /tmp/work --part 2 --parts 2"]
    assert command[command.index("--append-system-prompt") + 1] == system


def test_codex_hook_arm_inlines_a_trusted_user_layer_hook_and_developer_instructions():
    message, system = _MODULE.benchmark_messages({"request": "Traza processCommand"}, True, prefetch=True)
    command = _MODULE.command_for("codex", "m", message, Path("/tmp/work"), 30, treatment=True,
                                  graphtyn_executable=Path("/opt/graphtyn"), prefetch=True, system_prompt=system)

    assert "--dangerously-bypass-hook-trust" in command
    hooks = next(value for value in command if value.startswith("hooks.UserPromptSubmit="))
    assert '"/opt/graphtyn codex-context hook --path /tmp/work"' in hooks and "additionalContextLimit=" in hooks
    instructions = next(value for value in command if value.startswith("developer_instructions="))
    assert json.loads(instructions.split("=", 1)[1]) == system
    assert command[-1] == "Traza processCommand"


def test_full_payload_arm_requests_debug_detail_in_every_client(tmp_path):
    for client in ("claude", "codex"):
        command = _MODULE.command_for(client, "m", "q", tmp_path, 30, treatment=True,
                                      graphtyn_executable=Path("/opt/graphtyn"), full_payload=True)
        assert any("--response-detail" in value for value in command)
    config = json.loads(_MODULE.opencode_config(True, tmp_path, Path("/opt/graphtyn"), full_payload=True))
    assert config["mcp"]["graphtyn_benchmark"]["command"][-2:] == ["--response-detail", "debug"]
    assert "--response-detail" not in json.dumps(_MODULE.opencode_config(True, tmp_path, Path("/opt/graphtyn")))


def test_opencode_hook_arm_installs_the_plugin_and_keeps_plugins_enabled(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "a.py").write_text("def f():\n    return 1\n")
    subprocess.run(["git", "-C", str(source), "add", "a.py"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
                   check=True)
    workspace = tmp_path / "workspace"

    _MODULE.make_workspace(source, workspace, True, Path("/opt/graphtyn"), opencode_hook=True)

    plugin = (workspace / ".opencode/plugins/graphtyn-context.js").read_text()
    assert json.dumps(["/opt/graphtyn", "opencode-context", "hook", "--path", str(workspace.resolve())]) in plugin
    hook = _MODULE.command_for("opencode", "m", "q", workspace, 30, treatment=True,
                               graphtyn_executable=Path("/opt/graphtyn"), prefetch=True)
    assert "--pure" not in hook
    assert "--pure" in _MODULE.command_for("opencode", "m", "q", workspace, 30, treatment=True)
    with pytest.raises(ValueError):
        _MODULE.command_for("cursor", "m", "q", workspace, 30, treatment=True,
                            graphtyn_executable=Path("/opt/graphtyn"), prefetch=True)


def test_stop_rule_variants_keep_earlier_prompts_reproducible():
    task = {"request": "Traza processCommand"}
    strict = _MODULE.benchmark_prompt(task, True)
    assert "no ejecutes búsquedas, comandos ni lecturas adicionales" in strict
    targeted = _MODULE.benchmark_prompt(task, True, stop_rule="targeted")
    assert "no releas lo que ya muestra" in targeted and "consulta sólo esa parte" in targeted
    assert _MODULE.benchmark_messages(task, True, prefetch=True, stop_rule="targeted")[1].count("sólo esa parte") == 1


def test_antigravity_hook_arm_installs_the_project_hook_pinned_to_the_workspace(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=source, check=True)
    workspace = tmp_path / "workspace"

    _MODULE.make_workspace(source, workspace, True, Path("/opt/graphtyn"), antigravity_hook=True)

    hook = json.loads((workspace / ".agents/hooks.json").read_text())["graphtyn-context"]["PreInvocation"][0]
    assert hook["command"] == f"/opt/graphtyn antigravity-context hook --path {workspace.resolve()}"


def test_antigravity_hook_evidence_reads_the_injection_from_its_transcript(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    logs = tmp_path / ".gemini/antigravity-cli/brain/c1/.system_generated/logs"
    logs.mkdir(parents=True)
    (logs / "transcript_full.jsonl").write_text(
        json.dumps({"type": "USER_INPUT", "content": "<graphtyn-context pegado por el usuario"}) + "\n"
        + json.dumps({"type": "EPHEMERAL_MESSAGE", "content": "<graphtyn-context x>"}) + "\n")

    assert _MODULE.antigravity_hook_evidence([{"event": "init", "conversation_id": "c1"}]) == {
        "conversation_id": "c1", "context_injected": True, "injected_characters": [20]}
    assert _MODULE.antigravity_hook_evidence([])["context_injected"] is False
