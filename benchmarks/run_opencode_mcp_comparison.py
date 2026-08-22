#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def config(command: list[str] | None, name: str, project: Path) -> str:
    mcp = {
        "unityMCP": {"enabled": False},
        "graphify": {"enabled": False},
        "aether-graph": {"enabled": False},
    }
    if command is not None:
        mcp[name] = {"type": "local", "command": command, "enabled": True, "timeout": 15000}
    result = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": mcp,
    }
    if command is not None:
        result["tools"] = {key: False for key in ("bash", "read", "glob", "grep", "edit", "write", "webfetch", "task", "skill")}
    else:
        project_pattern = str(project / "**")
        result["tools"] = {key: False for key in ("edit", "write", "webfetch", "task", "skill")}
        result["permission"] = {
            "external_directory": {project_pattern: "allow"},
            "edit": "deny",
        }
    return json.dumps(result)


def run_task(project: Path, model: str, variant: str, command: list[str] | None, task: dict) -> dict:
    if command is None:
        prompt = (
            f"Sin usar AetherGraph ni Graphify, investiga exclusivamente el repositorio {project} con las herramientas locales de OpenCode. "
            f"{task['prompt']} Responde en español con evidencia concreta de archivo y línea; evita suposiciones y no modifiques archivos."
        )
    else:
        prompt = (
            f"Usa exclusivamente {variant} y no leas archivos directamente. "
            f"{task['prompt']} Responde en español con evidencia concreta del grafo y evita suposiciones."
        )
    env = os.environ.copy()
    env["OPENCODE_CONFIG_CONTENT"] = config(command, variant.lower(), project)
    started = time.monotonic()
    process = subprocess.run(
        ["opencode", "run", "--model", model, "--format", "json", prompt],
        cwd=project, env=env, text=True, capture_output=True, timeout=600,
    )
    answer: list[str] = []
    tool_calls = 0
    last_tokens = {"input": 0, "output": 0, "reasoning": 0, "total": 0}
    errors: list[str] = []
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            answer.append(event.get("part", {}).get("text", ""))
        elif event.get("type") == "tool_use":
            tool_calls += 1
        elif event.get("type") == "step_finish":
            tokens = event.get("part", {}).get("tokens", {})
            if int(tokens.get("total", 0)) >= int(last_tokens.get("total", 0)):
                last_tokens = tokens
        elif event.get("type") == "error":
            errors.append(json.dumps(event, ensure_ascii=False))
    usage = {
        "input_tokens": int(last_tokens.get("input", 0)),
        "output_tokens": int(last_tokens.get("output", 0)),
        "thinking_tokens": int(last_tokens.get("reasoning", 0)),
        "total_tokens": int(last_tokens.get("total", 0)),
    }
    return {
        "task_id": task["id"],
        "variant": variant,
        "model": model,
        "status": "SUCCESS" if process.returncode == 0 and answer else "ERROR",
        "duration_seconds": round(time.monotonic() - started, 4),
        "usage": usage,
        "tool_calls": tool_calls,
        "answer": "\n".join(answer),
        "terminal_error": "\n".join(errors or ([process.stderr.strip()] if process.stderr.strip() else [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="opencode/x-preview-f-free")
    parser.add_argument("--aether", type=Path, required=True)
    parser.add_argument("--graphify", type=Path, required=True)
    parser.add_argument("--variant", choices=("Graphify", "AetherGraph", "Baseline"), action="append")
    parser.add_argument("--task", action="append", help="Ejecuta sólo estos task_id y conserva los demás resultados")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))["tasks"]
    if args.task:
        selected_tasks = set(args.task)
        tasks = [task for task in tasks if task["id"] in selected_tasks]
    variants = {
        "Graphify": [str(args.graphify), "--graph", str(args.project / "graphify-out/graph.json")],
        "AetherGraph": [str(args.aether), "mcp", "--path", str(args.project)],
        "Baseline": None,
    }
    selected = set(args.variant or variants)
    for variant, command in variants.items():
        if variant not in selected:
            continue
        output = args.output_dir / f"tour_agent_runs_{variant.lower()}_x_preview_f_free.json"
        runs: list[dict] = json.loads(output.read_text(encoding="utf-8")) if output.exists() and args.task else []
        by_task = {run["task_id"]: run for run in runs}
        for index, task in enumerate(tasks, 1):
            print(f"[{variant}] {index}/{len(tasks)} {task['id']}", flush=True)
            by_task[task["id"]] = run_task(args.project, args.model, variant, command, task)
            runs = list(by_task.values())
            output.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
