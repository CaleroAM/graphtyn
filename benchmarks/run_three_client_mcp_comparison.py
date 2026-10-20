#!/usr/bin/env python3
"""Auditable A/B runner contract for OpenCode, Codex and Antigravity.

Preflight is the default. Model sessions require ``--execute`` and explicit
per-client models plus a total token ceiling. The adapters intentionally share
one result schema while retaining the raw event stream for later audits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple


CLIENTS = ("opencode", "codex", "antigravity")


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def normalize_usage(client: str, events: list[dict], *, opencode_semantics: str = "per-step") -> dict:
    """Normalize reported usage without estimating absent fields."""
    if client == "opencode":
        samples = []
        for event in events:
            if event.get("type") != "step_finish":
                continue
            tokens = event.get("part", {}).get("tokens", {}) or {}
            cache = tokens.get("cache", {}) or {}
            samples.append({
                "input_tokens": _int(tokens.get("input")) or 0,
                "cached_input_tokens": _int(cache.get("read")) or 0,
                "cache_write_input_tokens": _int(cache.get("write")) or 0,
                "output_tokens": _int(tokens.get("output")) or 0,
                "reasoning_tokens": _int(tokens.get("reasoning")) or 0,
                "total_tokens": _int(tokens.get("total")) or 0,
                "provider_cost": tokens.get("cost", event.get("part", {}).get("cost")),
            })
        if not samples:
            return _empty_usage()
        selected = samples[-1:] if opencode_semantics == "cumulative" else samples
        result = {key: sum((row[key] or 0) for row in selected)
                  for key in selected[0] if key != "provider_cost"}
        costs = [row["provider_cost"] for row in selected if isinstance(row["provider_cost"], (int, float))]
        result["provider_cost"] = sum(costs) if costs else None
        return result

    if client == "codex":
        event = next((row for row in reversed(events) if row.get("type") == "turn.completed"), None)
        usage = (event or {}).get("usage") or {}
        input_tokens = _int(usage.get("input_tokens"))
        output_tokens = _int(usage.get("output_tokens"))
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": _int(usage.get("cached_input_tokens")),
            "cache_write_input_tokens": _int(usage.get("cache_write_input_tokens")),
            "output_tokens": output_tokens,
            "reasoning_tokens": _int(usage.get("reasoning_output_tokens") or usage.get("reasoning_tokens")),
            "total_tokens": ((input_tokens + output_tokens)
                             if input_tokens is not None and output_tokens is not None else _int(usage.get("total_tokens"))),
            "provider_cost": usage.get("cost"),
        }

    if client == "antigravity":
        result = next((row.get("result", row) for row in reversed(events)
                       if row.get("event") == "result" or row.get("type") == "result"), {})
        usage = result.get("usage") or {}
        input_tokens = _int(usage.get("input_tokens") or usage.get("inputTokens"))
        output_tokens = _int(usage.get("output_tokens") or usage.get("outputTokens"))
        total = _int(usage.get("total_tokens") or usage.get("totalTokens"))
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": _int(usage.get("cached_input_tokens") or usage.get("cachedInputTokens")
                                         or usage.get("cache_read_tokens")),
            "cache_write_input_tokens": _int(usage.get("cache_write_input_tokens") or usage.get("cacheWriteInputTokens")),
            "output_tokens": output_tokens,
            "reasoning_tokens": _int(usage.get("reasoning_tokens") or usage.get("thoughtsTokenCount")
                                      or usage.get("thinking_tokens")),
            "total_tokens": total if total is not None else (
                input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None),
            "provider_cost": usage.get("cost"),
        }
    raise ValueError(f"unsupported client: {client}")


def _empty_usage() -> dict:
    return {key: None for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                                   "output_tokens", "reasoning_tokens", "total_tokens", "provider_cost")}


def usage_accounting(client: str, events: list[dict], usage: dict) -> dict:
    """Describe provider semantics and expose comparable derived consumption."""
    semantics = {
        "opencode": {
            "source": "step_finish",
            "record_count": sum(event.get("type") == "step_finish" for event in events),
            "reported_total_includes": ["input", "cached_input", "output", "reasoning"],
        },
        "codex": {
            "source": "turn.completed",
            "record_count": sum(event.get("type") == "turn.completed" for event in events),
            "reported_total_includes": ["input", "output"],
        },
        "antigravity": {
            "source": "result.usage",
            "record_count": sum(event.get("event") == "result" or event.get("type") == "result"
                                for event in events),
            "reported_total_includes": ["input", "output"],
        },
    }[client]
    technical_fields = ["input_tokens", "cached_input_tokens", "output_tokens"]
    if client == "opencode":
        technical_fields.append("reasoning_tokens")
    values = [usage.get(key) for key in technical_fields]
    technical_total = sum(values) if all(isinstance(value, int) for value in values) else None
    explicit_retries = sum(
        event.get("type") in {"retry", "turn.retry", "step_retry"}
        or event.get("event") == "retry"
        or event.get("status") == "retrying"
        for event in events
    )
    return {
        **semantics,
        "cached_input_is_separate": client != "opencode",
        "reasoning_is_separate_or_subcomponent": client != "opencode",
        "technical_total_including_cache": technical_total,
        "observed_retry_events": explicit_retries,
        "retry_coverage": "explicit_events_only; null retries cannot be reconstructed",
    }


def parse_model_args(values: list[str]) -> dict[str, str]:
    models: dict[str, str] = {}
    for value in values:
        client, separator, model = value.partition("=")
        if not separator or client not in CLIENTS or not model:
            raise ValueError(f"invalid --model {value!r}; expected client=model")
        models[client] = model
    return models


def command_for(client: str, model: str, prompt: str, repo: Path, timeout: int,
                *, treatment: bool = False, graphtyn_executable: Path | None = None) -> list[str]:
    if client == "opencode":
        return ["opencode", "run", "--pure", "--auto", "--dir", str(repo),
                "--model", model, "--format", "json", prompt]
    if client == "codex":
        command = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                "--json", "--color", "never",
                "--dangerously-bypass-approvals-and-sandbox",
                "--disable", "apps", "--disable", "plugins", "--disable", "memories",
                "--disable", "multi_agent", "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
                ]
        if treatment:
            if graphtyn_executable is None:
                raise ValueError("Codex treatment requires graphtyn_executable")
            args = ["mcp", "--tool-profile", "intent", "--path", str(repo.resolve())]
            command.extend([
                "-c", f"mcp_servers.graphtyn_benchmark.command={json.dumps(str(graphtyn_executable))}",
                "-c", "mcp_servers.graphtyn_benchmark.args=" + json.dumps(args),
            ])
        return command + ["-m", model, "-C", str(repo), prompt]
    if client == "antigravity":
        return ["agy", "-p", prompt, "--model", model, "--output-format", "stream-json",
                "--print-timeout", f"{timeout}s", "--dangerously-skip-permissions",
                "--disable-slash-commands"]
    raise ValueError(f"unsupported client: {client}")


def make_workspace(source: Path, destination: Path, treatment: bool,
                   graphtyn_executable: Path) -> str:
    """Copy only tracked source and install an isolated per-arm MCP config."""
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    files = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).split(b"\0")
    ignored_instructions = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
    for raw in files:
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if relative.name in ignored_instructions:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    command = [str(graphtyn_executable), "mcp", "--tool-profile", "intent",
               "--path", str(destination.resolve())]
    server = {"command": command[0], "args": command[1:]}
    (destination / ".agents").mkdir(parents=True, exist_ok=True)
    (destination / ".agents/mcp_config.json").write_text(json.dumps({
        "mcpServers": {"graphtyn_benchmark": server} if treatment else {}
    }, indent=2) + "\n")
    (destination / ".codex").mkdir(parents=True, exist_ok=True)
    codex = ""
    if treatment:
        args = ", ".join(json.dumps(value) for value in command[1:])
        codex = (f"[mcp_servers.graphtyn_benchmark]\ncommand = {json.dumps(command[0])}\n"
                 f"args = [{args}]\ncwd = {json.dumps(str(destination))}\nenabled = true\n")
    (destination / ".codex/config.toml").write_text(codex)
    (destination / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "mcp": ({"graphtyn_benchmark": {"type": "local", "enabled": True, "command": command}}
                if treatment else {})
    }, indent=2) + "\n")
    return commit


def prepare_graphtyn_index(workspace: Path, graphtyn_executable: Path) -> dict:
    """Build the one-time project index outside measured agent-session time."""
    started = time.monotonic()
    process = subprocess.run(
        [str(graphtyn_executable), "reindex", "--path", str(workspace.resolve()),
         "--engine", "ast_pure", "--mode", "fast"],
        text=True, capture_output=True, timeout=300,
    )
    result = {
        "returncode": process.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "stdout": process.stdout.strip()[-500:],
        "stderr": process.stderr.strip()[-500:],
        "included_in_session_time": False,
    }
    if process.returncode != 0:
        raise RuntimeError(f"Graphtyn preindex failed: {result['stderr'] or result['stdout']}")
    return result


def opencode_config(treatment: bool, source: Path, graphtyn_executable: Path) -> str:
    mcp = {}
    if treatment:
        mcp["graphtyn_benchmark"] = {"type": "local", "enabled": True,
            "command": [str(graphtyn_executable), "mcp", "--tool-profile", "intent",
                        "--path", str(source.resolve())]}
    return json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": mcp,
                       "tools": {"edit": False, "write": False, "webfetch": False, "task": False},
                       "permission": {"edit": "deny"}})


def benchmark_prompt(task: dict, treatment: bool) -> str:
    common = ("Evaluación de solo lectura. Investiga el repositorio actual y responde en español "
              "con evidencia archivo:línea. No modifiques archivos, no uses red, otros agentes, "
              "memorias ni artefactos del benchmark. Puedes usar búsqueda y lectura local. ")
    condition = ("Usa primero graph_query_intent del MCP Graphtyn con la pregunta completa; "
                 "verifica en fuente solamente las obligaciones que falten. " if treatment else
                 "No uses Graphtyn, Graphify, MCP ni índices generados. ")
    return common + condition + "Entrega solo la respuesta final.\n\n" + task["request"]


def parse_json_lines(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def answer_from_events(client: str, events: list[dict]) -> str:
    if client == "opencode":
        return "\n".join(e.get("part", {}).get("text", "") for e in events if e.get("type") == "text").strip()
    if client == "codex":
        messages = [e.get("item", {}).get("text", "") for e in events
                    if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
        return messages[-1].strip() if messages else ""
    result = next((e.get("result", e) for e in reversed(events)
                   if e.get("event") == "result" or e.get("type") == "result"), {})
    return str(result.get("response") or result.get("text") or "").strip()


def run_cell(client: str, model: str, task: dict, treatment: bool, workspace: Path,
             source: Path, destination: Path, timeout: int,
             graphtyn_executable: Path, index_setup: dict | None = None) -> dict:
    prompt = benchmark_prompt(task, treatment)
    command = command_for(client, model, prompt, workspace, timeout, treatment=treatment,
                          graphtyn_executable=graphtyn_executable)
    env = os.environ.copy()
    if client == "opencode":
        env["OPENCODE_CONFIG_CONTENT"] = opencode_config(treatment, workspace, graphtyn_executable)
    antigravity_mcp = None
    if client == "antigravity":
        subprocess.run(["agy", "mcp", "remove", "graphtyn_benchmark"],
                       text=True, capture_output=True, check=False)
        if treatment:
            added = subprocess.run([
                "agy", "mcp", "add", "graphtyn_benchmark", str(graphtyn_executable),
                "mcp", "--tool-profile", "intent", "--path", str(workspace.resolve()),
            ], text=True, capture_output=True, check=True)
            antigravity_mcp = (added.stdout or added.stderr).strip()
    started = time.monotonic()
    began = datetime.now(timezone.utc).isoformat()
    try:
        try:
            process = subprocess.run(command, cwd=workspace, env=env, text=True, capture_output=True,
                                     timeout=timeout + 15)
            stdout, stderr, returncode, timed_out = process.stdout, process.stderr, process.returncode, False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            returncode, timed_out = 124, True
    finally:
        if client == "antigravity":
            subprocess.run(["agy", "mcp", "remove", "graphtyn_benchmark"],
                           text=True, capture_output=True, check=False)
    events = parse_json_lines(stdout)
    usage = normalize_usage(client, events)
    answer = answer_from_events(client, events)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    (destination / "answer.txt").write_text(answer + "\n")
    (destination / "stderr.txt").write_text(stderr)
    session_status = ("timeout" if timed_out else "error" if returncode != 0
                      else "complete" if answer else "incomplete")
    summary = {"client": client, "model": model, "task_id": task["id"],
               "arm": "graphtyn" if treatment else "baseline", "started_at": began,
               "wall_seconds": round(time.monotonic() - started, 3), "returncode": returncode,
               "timed_out": timed_out, "session_status": session_status,
               "usage": usage, "usage_accounting": usage_accounting(client, events, usage),
               "answer_present": bool(answer), "index_setup": index_setup,
               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "raw_event_count": len(events),
               "antigravity_mcp_registration": antigravity_mcp,
               "terminal_errors": [e.get("error") for e in events if e.get("type") == "error"]}
    (destination / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


class Preflight(NamedTuple):
    client: str
    executable: str | None
    version: str | None
    model: str | None


def preflight(models: dict[str, str]) -> list[Preflight]:
    rows = []
    for client in CLIENTS:
        executable = shutil.which("agy" if client == "antigravity" else client)
        version = None
        if executable:
            probe = subprocess.run([executable, "--version"], text=True, capture_output=True, timeout=15)
            version = (probe.stdout or probe.stderr).strip() or None
        rows.append(Preflight(client, executable, version, models.get(client)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, help="Task/rubric JSON; required with --execute")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", action="append", default=[], metavar="CLIENT=MODEL")
    parser.add_argument("--client", action="append", choices=CLIENTS,
                        help="Run only selected clients; intended for audited continuation after a stop")
    parser.add_argument("--arm", choices=("baseline", "graphtyn"),
                        help="Run only one arm; intended for an audited retry of an invalid cell")
    parser.add_argument("--initial-tokens", type=int, default=0,
                        help="Previously consumed valid tokens charged against the same ceiling")
    parser.add_argument("--total-token-ceiling", type=int)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--graphtyn-executable", type=Path,
                        default=Path(__file__).resolve().parents[1] / ".venv/bin/graphtyn")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.repo = args.repo.resolve()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    models = parse_model_args(args.model)
    checks = preflight(models)
    report = {
        "protocol_status": protocol.get("status"),
        "repo": str(args.repo.resolve()),
        "clients": [row._asdict() for row in checks],
        "mcp": "one implementation; isolated stdio process per treatment session",
        "hard_per_session_token_limit_available": False,
        "execution_requested": args.execute,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    missing = [row.client for row in checks if not row.executable or not row.model]
    if missing:
        raise SystemExit("missing executable or explicit model for: " + ", ".join(missing))
    if args.execute:
        if args.total_token_ceiling is not None and args.total_token_ceiling <= 0:
            raise SystemExit("--total-token-ceiling must be positive when supplied")
        if not args.tasks:
            raise SystemExit("--execute requires --tasks")
        task_spec = json.loads(args.tasks.read_text(encoding="utf-8"))
        tasks = {task["id"]: task for task in task_spec["tasks"]}
        selected = [tasks[task_id] for task_id in protocol["design"]["tasks"] if task_id in tasks]
        if not selected:
            raise SystemExit("no protocol tasks found in --tasks")
        # Phase 1 is deliberately one task, both arms and all clients.
        task = selected[0]
        total = args.initial_tokens
        results = []
        run_clients = tuple(args.client or CLIENTS)
        for client_index, client in enumerate(run_clients):
            arm_order = ((False, True) if client_index % 2 == 0 else (True, False))
            if args.arm:
                arm_order = (args.arm == "graphtyn",)
            for treatment in arm_order:
                if args.total_token_ceiling is not None and total >= args.total_token_ceiling:
                    raise SystemExit(f"total token ceiling reached before {client}/{task['id']}")
                run_id = f"{client}_{task['id']}_{'graphtyn' if treatment else 'baseline'}"
                workspace = args.output_dir / "workspaces" / run_id
                make_workspace(args.repo.resolve(), workspace, treatment,
                               args.graphtyn_executable.resolve())
                try:
                    index_setup = (prepare_graphtyn_index(workspace, args.graphtyn_executable.resolve())
                                   if treatment else None)
                    result = run_cell(client, models[client], task, treatment, workspace, args.repo.resolve(),
                                      args.output_dir / "runs" / run_id, args.timeout,
                                      args.graphtyn_executable.resolve(), index_setup=index_setup)
                finally:
                    shutil.rmtree(workspace, ignore_errors=True)
                results.append(result)
                measured = result["usage"].get("total_tokens")
                if measured is None:
                    (args.output_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
                    raise SystemExit(f"{client} did not report total tokens; stopped")
                total += measured
                (args.output_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
                if args.total_token_ceiling is not None and total > args.total_token_ceiling:
                    raise SystemExit(f"total token ceiling exceeded after {run_id}: {total}")
        print(f"PHASE_1_COMPLETE sessions={len(results)} total_tokens={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
