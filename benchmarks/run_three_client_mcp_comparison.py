#!/usr/bin/env python3
"""Auditable A/B runner contract for OpenCode, Codex, Antigravity and Claude Code.

Preflight is the default. Model sessions require ``--execute`` and explicit
per-client models plus a total token ceiling. The adapters intentionally share
one result schema while retaining the raw event stream for later audits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple


CLIENTS = ("opencode", "codex", "antigravity", "claude")
BENCHMARK_MCP_PROFILE = "query"
EXECUTABLES = {"antigravity": "agy"}
# Read-only evaluation: Claude Code may search and read, never edit or delegate.
CLAUDE_DISALLOWED_TOOLS = "Edit,Write,NotebookEdit,WebFetch,WebSearch,Task,Agent"
ARMS = ("baseline", "graphtyn", "graphtyn_full", "graphtyn_hook", "graphify")
TREATMENT_ARMS = ("graphtyn", "graphtyn_full", "graphtyn_hook")
SERVER_NAMES = {"graphtyn": "graphtyn_benchmark", "graphtyn_full": "graphtyn_benchmark",
                "graphtyn_hook": "graphtyn_benchmark", "graphify": "graphify_benchmark"}
HOOK_CLIENTS = ("claude", "codex", "opencode")


def graphtyn_mcp_args(workspace: Path, full_payload: bool = False) -> list[str]:
    """`graphtyn mcp` arguments; `full_payload` keeps the pre-lean diagnostic package."""
    args = ["mcp", "--tool-profile", BENCHMARK_MCP_PROFILE, "--preload-index",
            "--path", str(workspace.resolve())]
    return args + (["--response-detail", "debug"] if full_payload else [])
GRAPHIFY_GRAPH = Path("graphify-out/graph.json")


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
    if client == "claude":
        result = next((row for row in reversed(events) if row.get("type") == "result"), None)
        if result is None:
            return _empty_usage()
        return _claude_usage(result.get("usage") or {}, result.get("total_cost_usd"))
    raise ValueError(f"unsupported client: {client}")


def _claude_usage(usage: dict, cost: Any = None) -> dict:
    # Anthropic reports cache reads and writes apart from uncached input.
    input_tokens = _int(usage.get("input_tokens"))
    cache_read = _int(usage.get("cache_read_input_tokens"))
    cache_write = _int(usage.get("cache_creation_input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    parts = (input_tokens, cache_read, cache_write, output_tokens)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cache_read,
        "cache_write_input_tokens": cache_write,
        "output_tokens": output_tokens,
        "reasoning_tokens": None,
        "total_tokens": sum(parts) if all(value is not None for value in parts) else None,
        "provider_cost": cost if isinstance(cost, (int, float)) else None,
    }


def _claude_model_calls(events: list[dict]) -> list[dict]:
    """Return one usage record per Anthropic message id, keeping its final value."""
    calls: dict[str, dict] = {}
    for event in events:
        message = event.get("message") or {}
        if event.get("type") == "assistant" and message.get("id") and message.get("usage"):
            calls[message["id"]] = _claude_usage(message["usage"])
    return list(calls.values())


def claude_mcp_evidence(events: list[dict], server: str = "graphtyn_benchmark") -> dict:
    """Prove whether the treatment server connected and was actually called."""
    init = next((row for row in events if row.get("type") == "system" and row.get("subtype") == "init"), {})
    status = next((item.get("status") for item in init.get("mcp_servers") or []
                   if isinstance(item, dict) and item.get("name") == server), None)
    prefix = f"mcp__{server}__"
    calls = [block.get("name", "")[len(prefix):]
             for event in events if event.get("type") == "assistant"
             for block in (event.get("message") or {}).get("content") or []
             if isinstance(block, dict) and block.get("type") == "tool_use"
             and str(block.get("name", "")).startswith(prefix)]
    return {"server_status": status, "tool_calls": calls}


def claude_hook_evidence(events: list[dict]) -> dict:
    """Whether the UserPromptSubmit hook ran and added Graphtyn context."""
    hooks = [event for event in events if event.get("type") == "system"
             and str(event.get("subtype") or "").startswith("hook")
             and event.get("hook_event", event.get("hook_event_name")) == "UserPromptSubmit"]
    text = json.dumps(events, ensure_ascii=False)
    return {"hook_events": len(hooks), "context_injected": "<graphtyn-context" in text}


def expected_hook_context(client: str, workspace: Path, request: str, graphtyn_executable: Path) -> dict:
    """Run the arm's hook once outside session time: what the client receives.

    Codex and OpenCode do not echo hook context in their event streams; the
    hook is deterministic for a given index and prompt, so this records it.
    """
    from graphtyn.core.prompt_context import PARTS
    parts = PARTS if client == "claude" else 1
    payload = json.dumps({"prompt": request, "cwd": str(workspace.resolve()), "hook_event_name": "UserPromptSubmit"})
    contexts, sizes = [], []
    for part in range(1, parts + 1):
        process = subprocess.run([str(graphtyn_executable), f"{client}-context", "hook", "--path",
                                  str(workspace.resolve()), "--part", str(part), "--parts", str(parts)],
                                 input=payload, text=True, capture_output=True, timeout=60)
        text = process.stdout.strip()
        context = json.loads(text)["hookSpecificOutput"]["additionalContext"] if text else ""
        if context:
            contexts.append(context)
            sizes.append(len(context))
    first = contexts[0] if contexts else ""
    marker = first.find('context_id="')
    return {"injected": bool(contexts), "parts": len(contexts), "characters": sizes,
            "context_id": first[marker + 12:first.find('"', marker + 12)] if marker >= 0 else None}


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
            "reported_total_includes": ["input_including_cached", "output_including_reasoning"],
        },
        "antigravity": {
            "source": "result.usage",
            "record_count": sum(event.get("event") == "result" or event.get("type") == "result"
                                for event in events),
            "reported_total_includes": ["input", "output"],
        },
        "claude": {
            "source": "result.usage",
            "record_count": sum(event.get("type") == "result" for event in events),
            "reported_total_includes": ["input", "cache_read_input", "cache_creation_input", "output"],
        },
    }[client]
    technical_fields = {
        "opencode": ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"],
        # OpenAI reports cached input as a subset of input and reasoning as a
        # subset of output. Adding either again would double count usage.
        "codex": ["input_tokens", "output_tokens"],
        "antigravity": ["input_tokens", "cached_input_tokens", "output_tokens"],
        "claude": ["input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"],
    }[client]
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
        "cached_input_is_separate": client in {"antigravity", "claude"},
        "cached_input_is_subset_of_input": client == "codex",
        "reasoning_is_subset_of_output": client == "codex",
        "technical_total_including_cache": technical_total,
        "observed_retry_events": explicit_retries,
        "retry_coverage": "explicit_events_only; null retries cannot be reconstructed",
    }


def usage_trace(client: str, events: list[dict]) -> dict:
    """Preserve every usage record the client exposes without inventing calls."""
    if client == "opencode":
        usage_events = [event for event in events if event.get("type") == "step_finish"]
        records = [normalize_usage(client, [event]) for event in usage_events]
        granularity = "step"
    elif client == "codex":
        usage_events = [event for event in events if event.get("type") == "turn.completed"]
        records = [normalize_usage(client, [event]) for event in usage_events]
        granularity = "session_aggregate"
    elif client == "claude":
        records = _claude_model_calls(events)
        return {
            "granularity": "model_call",
            "per_model_call_available": bool(records),
            "records": records,
            "limitation": ("Records are keyed by Anthropic message id; the session total comes from "
                           "result.usage and is not recomputed from these records."),
        }
    else:
        usage_events = [event for event in events
                        if event.get("event") == "result" or event.get("type") == "result"]
        records = [normalize_usage(client, [event]) for event in usage_events]
        granularity = "session_aggregate"
    return {
        "granularity": granularity,
        "per_model_call_available": False,
        "records": records,
        "limitation": ("The client emitted step totals, not a stable model-call identifier."
                       if client == "opencode" else
                       "The client emitted only aggregate usage; individual model calls cannot be reconstructed."),
    }


def parse_model_args(values: list[str]) -> dict[str, str]:
    models: dict[str, str] = {}
    for value in values:
        client, separator, model = value.partition("=")
        if not separator or client not in CLIENTS or not model:
            raise ValueError(f"invalid --model {value!r}; expected client=model")
        models[client] = model
    return models


def claude_mcp_config(treatment: bool, workspace: Path, graphtyn_executable: Path | None,
                      graphify_bin: Path | None = None, full_payload: bool = False) -> str:
    servers = {}
    if graphify_bin is not None:
        # Graphify's own MCP server with every tool it ships, over the graph
        # built before the session.
        servers["graphify_benchmark"] = {"command": str(graphify_bin / "graphify-mcp"),
                                         "args": [str((workspace / GRAPHIFY_GRAPH).resolve())]}
    if treatment:
        if graphtyn_executable is None:
            raise ValueError("Claude treatment requires graphtyn_executable")
        servers["graphtyn_benchmark"] = {"command": str(graphtyn_executable),
                                         "args": graphtyn_mcp_args(workspace, full_payload)}
    return json.dumps({"mcpServers": servers})


def command_for(client: str, model: str, prompt: str, repo: Path, timeout: int,
                *, treatment: bool = False, graphtyn_executable: Path | None = None,
                claude_bare: bool = False, graphify_bin: Path | None = None,
                prefetch: bool = False, system_prompt: str | None = None,
                full_payload: bool = False, opencode_plugins: bool = False) -> list[str]:
    if graphify_bin is not None and client != "claude":
        raise ValueError("the Graphify arm is only implemented for Claude Code")
    if prefetch and client not in HOOK_CLIENTS:
        raise ValueError(f"the prompt-hook arm is only implemented for {', '.join(HOOK_CLIENTS)}")
    if prefetch and graphtyn_executable is None:
        raise ValueError("the prompt-hook arm requires graphtyn_executable")
    if client == "opencode":
        # --pure also disables project plugins, which carry the OpenCode hook.
        return ["opencode", "run", *([] if opencode_plugins or prefetch else ["--pure"]), "--auto",
                "--dir", str(repo), "--model", model, "--format", "json", prompt]
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
            args = graphtyn_mcp_args(repo, full_payload)
            command.extend([
                "-c", f"mcp_servers.graphtyn_benchmark.command={json.dumps(str(graphtyn_executable))}",
                "-c", "mcp_servers.graphtyn_benchmark.args=" + json.dumps(args),
            ])
        if prefetch:
            from graphtyn.core.prompt_context import (CODEX_CONTEXT_TOKEN_LIMIT, HOOK_TIMEOUT_SECONDS,
                                                      codex_hook_invocation)
            hook = (f"{{type={json.dumps('command')},command={json.dumps(codex_hook_invocation(str(graphtyn_executable), repo.resolve()))},"
                    f"timeout={HOOK_TIMEOUT_SECONDS},additionalContextLimit={CODEX_CONTEXT_TOKEN_LIMIT}}}")
            # Inline user-layer hook: project hooks would need a persisted trust review.
            command += ["--dangerously-bypass-hook-trust", "-c", f"hooks.UserPromptSubmit=[{{hooks=[{hook}]}}]"]
        if system_prompt:
            command += ["-c", f"developer_instructions={json.dumps(system_prompt)}"]
        return command + ["-m", model, "-C", str(repo), prompt]
    if client == "antigravity":
        return ["agy", "-p", prompt, "--model", model, "--output-format", "stream-json",
                "--print-timeout", f"{timeout}s", "--dangerously-skip-permissions",
                "--disable-slash-commands"]
    if client == "claude":
        # --strict-mcp-config hides user/claude.ai servers in both arms; project
        # settings come only from the copied workspace, which excludes .claude/.
        command = ["claude", "-p", prompt, "--model", model,
                   "--output-format", "stream-json", "--verbose",
                   "--strict-mcp-config", "--mcp-config",
                   claude_mcp_config(treatment, repo, graphtyn_executable, graphify_bin, full_payload),
                   "--setting-sources", "project", "--no-session-persistence",
                   "--dangerously-skip-permissions",
                   "--disallowedTools", CLAUDE_DISALLOWED_TOOLS]
        if prefetch:
            from graphtyn.core.prompt_context import HOOK_TIMEOUT_SECONDS, part_invocations
            hooks = [{"type": "command", "timeout": HOOK_TIMEOUT_SECONDS, "command": line}
                     for line in part_invocations(str(graphtyn_executable), repo.resolve())]
            command += ["--settings", json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": hooks}]}})]
        if system_prompt:
            command += ["--append-system-prompt", system_prompt]
        return command + (["--bare"] if claude_bare else [])
    raise ValueError(f"unsupported client: {client}")


def make_workspace(source: Path, destination: Path, treatment: bool,
                   graphtyn_executable: Path, full_payload: bool = False, opencode_hook: bool = False) -> str:
    """Copy only tracked source and install an isolated per-arm MCP config."""
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    files = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).split(b"\0")
    ignored_instructions = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".mcp.json"}
    for raw in files:
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if relative.name in ignored_instructions or relative.parts[0] == ".claude":
            continue
        source_path = source / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            target.symlink_to(os.readlink(source_path))
        elif source_path.is_file():
            shutil.copy2(source_path, target)
        elif source_path.is_dir() and not any(source_path.iterdir()):
            target.mkdir(exist_ok=True)  # submodule that was not checked out (jq's vendor/oniguruma)
        else:
            raise RuntimeError(f"tracked path is neither file nor symlink: {relative}")
    command = [str(graphtyn_executable), *graphtyn_mcp_args(destination, full_payload)]
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
    if opencode_hook:
        from graphtyn.core.prompt_context import OPENCODE_PLUGIN, opencode_plugin_source
        plugin = destination / OPENCODE_PLUGIN
        plugin.parent.mkdir(parents=True, exist_ok=True)
        plugin.write_text(opencode_plugin_source(
            [str(graphtyn_executable), "opencode-context", "hook", "--path", str(destination.resolve())]))
    return commit


def _session_home(workspace: Path) -> Path:
    return workspace.with_name(f"{workspace.name}.graphtyn-home")


def isolated_executable(graphtyn_executable: Path, workspace: Path) -> Path:
    """A wrapper that runs Graphtyn with a GRAPHTYN_HOME of its own for one session.

    The index, MCP server and prompt hooks of a session must not write into the
    user's data home: each workspace is a throwaway copy, and its index would
    stay there (hundreds of MB per Rails session) after the copy is deleted. A
    wrapper isolates every caller, including clients that do not pass their
    environment to MCP servers or hooks.
    """
    home = _session_home(workspace)
    home.mkdir(parents=True, exist_ok=True)
    wrapper = workspace.with_name(f"{workspace.name}.graphtyn")
    wrapper.write_text(f"#!/bin/sh\nGRAPHTYN_HOME={shlex.quote(str(home.resolve()))} "
                       f"exec {shlex.quote(str(graphtyn_executable))} \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper.resolve()


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


def prepare_graphify_graph(workspace: Path, graphify_bin: Path) -> dict:
    """Build Graphify's local code graph (no LLM backend) outside session time."""
    started = time.monotonic()
    env = os.environ.copy()
    env["GRAPHIFY_BACKEND"] = "none"
    process = subprocess.run([str(graphify_bin / "graphify"), "update", str(workspace.resolve())],
                             cwd=workspace, env=env, text=True, capture_output=True, timeout=900)
    graph_path = workspace / GRAPHIFY_GRAPH
    result = {
        "returncode": process.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "stdout": process.stdout.strip()[-500:],
        "stderr": process.stderr.strip()[-500:],
        "included_in_session_time": False,
    }
    if process.returncode != 0 or not graph_path.is_file():
        raise RuntimeError(f"Graphify graph build failed: {result['stderr'] or result['stdout']}")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    result.update(nodes=len(graph.get("nodes", [])), links=len(graph.get("links", graph.get("edges", []))))
    return result


def opencode_config(treatment: bool, source: Path, graphtyn_executable: Path,
                    full_payload: bool = False, instructions: Path | None = None) -> str:
    mcp = {}
    if treatment:
        mcp["graphtyn_benchmark"] = {"type": "local", "enabled": True,
            "command": [str(graphtyn_executable), *graphtyn_mcp_args(source, full_payload)]}
    config = {"$schema": "https://opencode.ai/config.json", "mcp": mcp,
              "tools": {"edit": False, "write": False, "webfetch": False, "task": False},
              "permission": {"edit": "deny"}}
    if instructions is not None:
        config["instructions"] = [str(instructions)]
    return json.dumps(config)


# How the arm instructions phrase the stop rule. `strict` reproduces the runs up
# to 2026-10-27; `targeted` lets the agent look up a part the evidence misses.
STOP_RULES = {
    "strict": "no ejecutes búsquedas, comandos ni lecturas adicionales. ",
    "targeted": ("no releas lo que ya muestra. Si una parte de la pregunta no está cubierta por la evidencia, "
                 "consulta sólo esa parte con una búsqueda o lectura acotada. "),
}


def benchmark_prompt(task: dict, treatment: bool, graphify: bool = False, prefetch: bool = False,
                     stop_rule: str = "strict") -> str:
    common = ("Evaluación de solo lectura. Investiga el repositorio actual y responde en español "
              "con evidencia archivo:línea. No modifiques archivos, no uses red, otros agentes, "
              "memorias ni artefactos del benchmark. Puedes usar búsqueda y lectura local. ")
    if graphify:
        condition = ("Usa primero query_graph del MCP Graphify con la pregunta completa y apóyate en sus "
                     "demás herramientas si lo necesitas. Verifica en fuente sólo los rangos necesarios "
                     "para citar archivo:línea; no explores el repositorio completo. ")
        return common + condition + "Entrega solo la respuesta final.\n\n" + task["request"]
    if prefetch:
        # The hook retrieves with the user message, so the arm's instructions go
        # to the system prompt (see benchmark_messages), as project policy would.
        condition = ("Si el contexto ya incluye un bloque <graphtyn-context> para esta pregunta, es el resultado "
                     "de graph_query_intent: no vuelvas a llamarlo. Si no lo incluye, usa primero "
                     "graph_query_intent del MCP Graphtyn con la pregunta completa. "
                     "Si el resultado tiene missing=[] y do_not_expand=true, responde directamente con sus entidades, "
                     "operaciones y source_evidence: " + STOP_RULES[stop_rule] +
                     "Si falta una obligación nombrada, verifica únicamente su rango exacto en fuente. ")
        return common + condition + "Entrega solo la respuesta final.\n\n" + task["request"]
    condition = ("Usa primero graph_query_intent del MCP Graphtyn con la pregunta completa. "
                 "Si devuelve missing=[] y do_not_expand=true, responde directamente con sus entidades, "
                 "operaciones y source_evidence: " + STOP_RULES[stop_rule] +
                 "Si falta una obligación nombrada, verifica únicamente su rango exacto en fuente. " if treatment else
                 "No uses Graphtyn, Graphify, MCP ni índices generados. ")
    return common + condition + "Entrega solo la respuesta final.\n\n" + task["request"]


def benchmark_messages(task: dict, treatment: bool, graphify: bool = False,
                       prefetch: bool = False, stop_rule: str = "strict") -> tuple[str, str | None]:
    """User message and optional appended system prompt for one arm."""
    prompt = benchmark_prompt(task, treatment, graphify=graphify, prefetch=prefetch, stop_rule=stop_rule)
    if not prefetch:
        return prompt, None
    return task["request"], prompt[:-len(task["request"])].rstrip()


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
    if client == "claude":
        result = next((e for e in reversed(events) if e.get("type") == "result"), {})
        return "" if result.get("is_error") else str(result.get("result") or "").strip()
    result = next((e.get("result", e) for e in reversed(events)
                   if e.get("event") == "result" or e.get("type") == "result"), {})
    return str(result.get("response") or result.get("text") or "").strip()


def run_cell(client: str, model: str, task: dict, treatment: bool, workspace: Path,
             source: Path, destination: Path, timeout: int,
             graphtyn_executable: Path, index_setup: dict | None = None,
             claude_bare: bool = False, repetition: int = 1,
             graphify_bin: Path | None = None, prefetch: bool = False,
             full_payload: bool = False, opencode_plugins: bool = False,
             stop_rule: str = "strict") -> dict:
    arm = ("graphify" if graphify_bin is not None else "graphtyn_hook" if prefetch
           else "graphtyn_full" if full_payload else "graphtyn" if treatment else "baseline")
    prompt, system_prompt = benchmark_messages(task, treatment, graphify=graphify_bin is not None,
                                               stop_rule=stop_rule,
                                               prefetch=prefetch)
    command = command_for(client, model, prompt, workspace, timeout, treatment=treatment,
                          graphtyn_executable=graphtyn_executable, claude_bare=claude_bare,
                          graphify_bin=graphify_bin, prefetch=prefetch,
                          system_prompt=system_prompt if client in ("claude", "codex") else None,
                          full_payload=full_payload, opencode_plugins=opencode_plugins)
    env = os.environ.copy()
    if client == "opencode":
        instructions = None
        if system_prompt:
            # OpenCode has no system-prompt flag; an absolute instructions file
            # outside the workspace plays the role of project policy.
            instructions = destination.parent / f".{destination.name}.instructions.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            instructions.write_text(system_prompt + "\n", encoding="utf-8")
        env["OPENCODE_CONFIG_CONTENT"] = opencode_config(treatment, workspace, graphtyn_executable,
                                                         full_payload, instructions)
    expected_hook = expected_hook_context(client, workspace, task["request"], graphtyn_executable) if prefetch else None
    if client == "claude":
        # Expose MCP tools directly (as in the other clients) and keep cross-run
        # auto-memory out of both arms.
        env["ENABLE_TOOL_SEARCH"] = "false"
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    antigravity_mcp = None
    if client == "antigravity":
        subprocess.run(["agy", "mcp", "remove", "graphtyn_benchmark"],
                       text=True, capture_output=True, check=False)
        if treatment:
            added = subprocess.run([
                "agy", "mcp", "add", "graphtyn_benchmark", str(graphtyn_executable),
                *graphtyn_mcp_args(workspace, full_payload),
            ], text=True, capture_output=True, check=True)
            antigravity_mcp = (added.stdout or added.stderr).strip()
    started = time.monotonic()
    began = datetime.now(timezone.utc).isoformat()
    try:
        try:
            # A closed stdin: `codex exec` otherwise waits for more prompt input.
            process = subprocess.run(command, cwd=workspace, env=env, text=True, capture_output=True,
                                     stdin=subprocess.DEVNULL, timeout=timeout + 15)
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
               "arm": arm, "repetition": repetition, "started_at": began,
               "wall_seconds": round(time.monotonic() - started, 3), "returncode": returncode,
               "timed_out": timed_out, "session_status": session_status,
               "usage": usage, "usage_accounting": usage_accounting(client, events, usage),
               "usage_trace": usage_trace(client, events),
               "answer_present": bool(answer), "index_setup": index_setup,
               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest() if system_prompt else None,
               "stop_rule": stop_rule,
               "raw_event_count": len(events),
               "antigravity_mcp_registration": antigravity_mcp,
               "claude_mcp": (claude_mcp_evidence(events, SERVER_NAMES.get(arm, "graphtyn_benchmark"))
                              if client == "claude" else None),
               "prompt_hook": ({**claude_hook_evidence(events), "expected": expected_hook}
                               if prefetch and client == "claude" else
                               {"expected": expected_hook} if prefetch else None),
               "terminal_errors": [e.get("error") for e in events if e.get("type") == "error"]
                                  + [e.get("result") for e in events
                                     if client == "claude" and e.get("type") == "result" and e.get("is_error")]}
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
        executable = shutil.which(EXECUTABLES.get(client, client))
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
    parser.add_argument("--arm", choices=ARMS,
                        help="Run only one arm; graphify runs only that arm (Claude Code)")
    parser.add_argument("--arms", help="Comma-separated arms alternated per repetition, e.g. graphtyn,graphtyn_hook")
    parser.add_argument("--graphify-bin", type=Path,
                        help="bin/ of an isolated Graphify install (graphify, graphify-mcp); required for --arm graphify")
    parser.add_argument("--initial-tokens", type=int, default=0,
                        help="Previously consumed valid tokens charged against the same ceiling")
    parser.add_argument("--total-token-ceiling", type=int)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--graphtyn-executable", type=Path,
                        default=Path(__file__).resolve().parents[1] / ".venv/bin/graphtyn")
    parser.add_argument("--repetitions", type=int, default=1,
                        help="Repeticiones por celda; el orden de brazos alterna entre repeticiones")
    parser.add_argument("--repetition", type=int, action="append", default=[],
                        help="Ejecuta sólo estas repeticiones (repetible); para reintentos auditados")
    parser.add_argument("--claude-bare", action="store_true",
                        help="Run Claude Code with --bare (skips user CLAUDE.md; requires ANTHROPIC_API_KEY)")
    parser.add_argument("--stop-rule", choices=sorted(STOP_RULES), default="strict",
                        help="How the arm instructions phrase the stop rule (strict reproduces earlier runs)")
    parser.add_argument("--opencode-plugins", action="store_true",
                        help="Run OpenCode without --pure in every arm (the hook arm always needs plugins)")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.repo = args.repo.resolve()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    models = parse_model_args(args.model)
    checks = preflight(models)
    requested_clients = tuple(args.client or CLIENTS)
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
    missing = [row.client for row in checks
               if row.client in requested_clients and (not row.executable or not row.model)]
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
        run_clients = requested_clients
        if args.repetitions < 1:
            raise SystemExit("--repetitions must be at least 1")
        cells = []
        for repetition in range(1, args.repetitions + 1):
            for client_index, client in enumerate(run_clients):
                # Counterbalance by client and by repetition: AB, BA, AB...
                forward = (client_index + repetition - 1) % 2 == 0
                arm_order = (False, True) if forward else (True, False)
                arms = ["graphtyn" if treatment else "baseline" for treatment in arm_order]
                if args.arms:
                    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
                    if set(arms) - set(ARMS):
                        raise SystemExit(f"unknown arms: {sorted(set(arms) - set(ARMS))}")
                    arms = arms if forward else arms[::-1]
                if args.arm:
                    arms = [args.arm]
                cells.extend((repetition, client, arm) for arm in arms)
        if args.repetition:
            cells = [cell for cell in cells if cell[0] in set(args.repetition)]
        graphify_bin = args.graphify_bin.resolve() if args.graphify_bin else None
        if "graphify" in {cell[2] for cell in cells} and graphify_bin is None:
            raise SystemExit("--arm graphify requires --graphify-bin")
        for repetition, client, arm in cells:
            treatment = arm in TREATMENT_ARMS
            if args.total_token_ceiling is not None and total >= args.total_token_ceiling:
                raise SystemExit(f"total token ceiling reached before {client}/{task['id']}")
            run_id = f"{client}_{task['id']}_{arm}"
            if args.repetitions > 1:
                run_id += f"_r{repetition}"
            workspace = args.output_dir / "workspaces" / run_id
            shutil.rmtree(workspace, ignore_errors=True)  # left by an attempt that failed while copying
            executable = isolated_executable(args.graphtyn_executable.resolve(), workspace)
            make_workspace(args.repo.resolve(), workspace, treatment,
                           executable, full_payload=arm == "graphtyn_full",
                           opencode_hook=client == "opencode" and arm == "graphtyn_hook")
            try:
                index_setup = (prepare_graphtyn_index(workspace, executable)
                               if treatment else prepare_graphify_graph(workspace, graphify_bin)
                               if arm == "graphify" else None)
                result = run_cell(client, models[client], task, treatment, workspace, args.repo.resolve(),
                                  args.output_dir / "runs" / run_id, args.timeout,
                                  executable, index_setup=index_setup,
                                  claude_bare=args.claude_bare, repetition=repetition,
                                  graphify_bin=graphify_bin if arm == "graphify" else None,
                                  prefetch=arm == "graphtyn_hook", full_payload=arm == "graphtyn_full",
                                  opencode_plugins=args.opencode_plugins, stop_rule=args.stop_rule)
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
                shutil.rmtree(_session_home(workspace), ignore_errors=True)
                executable.unlink(missing_ok=True)
            results.append(result)
            measured = result["usage"].get("total_tokens")
            # A refused session (usage limit, auth) reports zero usage without any
            # API call; continuing would burn every remaining cell the same way.
            if result.get("session_status") == "error" and not measured:
                (args.output_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
                raise SystemExit(f"{client} returned an error without model usage; stopped")
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
