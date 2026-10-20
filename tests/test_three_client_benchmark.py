import importlib.util
from pathlib import Path


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
    assert accounting["technical_total_including_cache"] == 28
    assert accounting["cached_input_is_separate"] is True
    assert accounting["observed_retry_events"] == 1
    assert accounting["retry_coverage"].startswith("explicit_events_only")


def test_requires_explicit_client_model_mapping():
    assert _MODULE.parse_model_args(["codex=gpt-x", "antigravity=gemini-y"]) == {
        "codex": "gpt-x", "antigravity": "gemini-y"
    }


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
