#!/usr/bin/env python3
"""Paired modIAceb benchmark: baseline, Graphtyn and Graphify."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("common", HERE / "run_three_client_mcp_comparison.py")
COMMON = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(COMMON)

CONDITIONS = ("baseline", "graphtyn", "graphify")


def opencode_config(condition: str, workspace: Path, *, edit: bool,
                    graphtyn: Path, graphify_python: Path, graphify_graph: Path,
                    graphify_url: str | None) -> str:
    # Explicitly disable user-level servers so a benchmark arm cannot fall back
    # to a different product through OpenCode's merged global configuration.
    mcp: dict[str, dict] = {
        "graphtyn": {"enabled": False},
        "unityMCP": {"enabled": False},
    }
    if condition == "graphtyn":
        mcp["graphtyn_benchmark"] = {
            "type": "local", "enabled": True,
            "command": [str(graphtyn), "mcp", "--tool-profile", "intent",
                        "--path", str(workspace.resolve())],
        }
    elif condition == "graphify":
        if graphify_url:
            mcp["graphify"] = {"type": "remote", "enabled": True, "url": graphify_url}
        else:
            mcp["graphify"] = {
                "type": "local", "enabled": True,
                "command": [str(graphify_python), str(HERE / "graphify_query_mcp.py"),
                            "--graph", str(graphify_graph)],
            }
    return json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "mcp": mcp,
        "tools": {"edit": edit, "write": edit, "webfetch": False, "task": False},
        "permission": {"edit": "allow" if edit else "deny", "bash": "allow", "read": "allow"},
    })


def prompt(kind: str, condition: str, task: str) -> str:
    edit = kind == "edit_manifest"
    common = (
        "Trabaja únicamente en el repositorio actual. No uses red, otros agentes, memorias ni "
        "artefactos de benchmarks. "
    )
    if edit:
        common += ("Implementa la tarea completa, edita los archivos necesarios, ejecuta pruebas "
                   "relevantes y no hagas commit. Al final resume cambios y pruebas. ")
    else:
        common += ("Evaluación de solo lectura: no modifiques archivos ni ejecutes el sistema. "
                   "Responde en español con evidencia archivo:línea. ")
    if condition == "graphtyn":
        tool = ("Usa primero graph_query_intent del MCP Graphtyn una vez con la tarea completa y "
                "verifica localmente solo la evidencia que falte. Respeta do_not_expand y complete_for. ")
    elif condition == "graphify":
        tool = ("Usa primero graphify_query_graph del MCP Graphify una vez con la tarea completa y "
                "verifica localmente solo la evidencia que falte. No ejecutes Graphtyn ni uses su CLI; "
                "si la herramienta Graphify no está disponible, indícalo y detente. ")
    else:
        tool = "No uses Graphtyn, Graphify, MCP ni índices generados; investiga localmente. "
    return common + tool + "\n\nTAREA:\n" + task


def initialize_workspace(source: Path, workspace: Path, graphtyn: Path) -> str:
    commit = COMMON.make_workspace(source, workspace, False, graphtyn)
    # The source repository contains a tracked Graphtyn skill. It can steer the
    # Graphify arm toward the wrong CLI even when its MCP is configured.
    shutil.rmtree(workspace / ".agents" / "skills" / "graphtyn", ignore_errors=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(["git", "-c", "user.name=Benchmark", "-c", "user.email=benchmark@invalid",
                    "commit", "-qm", "frozen source"], cwd=workspace, check=True)
    return commit


def run_cell(kind: str, condition: str, task: str, source: Path, destination: Path,
             model: str, graphtyn: Path, graphify_python: Path,
             graphify_graph: Path, graphify_url: str | None, timeout: int) -> dict:
    workspace = destination.parent.parent / "workspaces" / destination.name
    commit = initialize_workspace(source, workspace, graphtyn)
    index_setup = COMMON.prepare_graphtyn_index(workspace, graphtyn) \
        if condition == "graphtyn" else None
    destination.mkdir(parents=True, exist_ok=False)
    edit = kind == "edit_manifest"
    env = os.environ.copy()
    env["OPENCODE_CONFIG_CONTENT"] = opencode_config(
        condition, workspace, edit=edit, graphtyn=graphtyn,
        graphify_python=graphify_python, graphify_graph=graphify_graph,
        graphify_url=graphify_url,
    )
    command = ["opencode", "run", "--pure", "--auto", "--dir", str(workspace),
               "--model", model, "--format", "json", prompt(kind, condition, task)]
    started = time.monotonic()
    try:
        process = subprocess.run(command, cwd=workspace, env=env, text=True,
                                 capture_output=True, timeout=timeout)
        stdout, stderr, returncode, timed_out = process.stdout, process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        returncode, timed_out = 124, True
    events = COMMON.parse_json_lines(stdout)
    usage = COMMON.normalize_usage("opencode", events)
    answer = COMMON.answer_from_events("opencode", events)
    (destination / "events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events))
    (destination / "answer.txt").write_text(answer + "\n")
    (destination / "stderr.txt").write_text(stderr)
    diff = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=workspace, text=True)
    (destination / "change.patch").write_text(diff)
    status = subprocess.check_output(["git", "status", "--short"], cwd=workspace, text=True).splitlines()
    result = {
        "kind": kind, "condition": condition, "model": model, "source_commit": commit,
        "returncode": returncode, "timed_out": timed_out,
        "wall_seconds": round(time.monotonic() - started, 3),
        "usage": usage, "answer_present": bool(answer),
        "usage_accounting": COMMON.usage_accounting("opencode", events, usage),
        "session_status": ("timeout" if timed_out else "error" if returncode != 0
                           else "complete" if answer else "incomplete"),
        "index_setup": index_setup,
        "tool_calls": sum(event.get("type") == "tool_use" for event in events),
        "status": status,
    }
    (destination / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    shutil.rmtree(workspace, ignore_errors=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--edit-protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="opencode/deepseek-v4.1-flash-free")
    parser.add_argument("--graphtyn", type=Path, default=Path(__file__).resolve().parents[1] / ".venv/bin/graphtyn")
    parser.add_argument("--graphify-python", type=Path, required=True)
    parser.add_argument("--graphify-graph", type=Path, required=True)
    parser.add_argument("--graphify-url", help="Prestarted Graphify MCP HTTP endpoint")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--cell", action="append", help="Run only KIND:CONDITION; completed cells are reused")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    for path in (args.repo, args.tasks, args.edit_protocol, args.graphtyn,
                 args.graphify_python, args.graphify_graph):
        if not path.exists():
            raise SystemExit(f"missing required path: {path}")
    args.output.mkdir(parents=True, exist_ok=True)
    preflight = {
        "model": args.model,
        "opencode_version": subprocess.check_output(["opencode", "--version"], text=True).strip(),
        "graphtyn_version": subprocess.check_output([str(args.graphtyn), "--version"], text=True).strip(),
        "graphify_version": subprocess.check_output(
            [str(args.graphify_python), "-c", "import importlib.metadata as m; print(m.version('graphifyy'))"], text=True).strip(),
        "source_commit": subprocess.check_output(["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip(),
        "execution_requested": args.execute,
    }
    (args.output / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
    print(json.dumps(preflight, indent=2))
    if not args.execute:
        return 0
    frozen = json.loads(args.tasks.read_text())
    c1 = next(task["request"] for task in frozen["tasks"] if task["id"] == "C1")
    edit = json.loads(args.edit_protocol.read_text())["task"]
    tasks = {"question_C1": c1, "edit_manifest": edit}
    default_order = [
        ("question_C1", "baseline"), ("question_C1", "graphtyn"), ("question_C1", "graphify"),
        ("edit_manifest", "graphify"), ("edit_manifest", "graphtyn"), ("edit_manifest", "baseline"),
    ]
    selected = []
    for value in args.cell or []:
        kind, separator, condition = value.partition(":")
        if not separator or kind not in tasks or condition not in CONDITIONS:
            raise SystemExit(f"invalid --cell {value!r}")
        selected.append((kind, condition))
    order = selected or default_order
    results_path = args.output / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    completed = {(row["kind"], row["condition"]) for row in results}
    for kind, condition in order:
        if (kind, condition) in completed:
            print(f"REUSE_COMPLETED {kind}:{condition}")
            continue
        run_id = f"{kind}_{condition}"
        result = run_cell(
            kind, condition, tasks[kind], args.repo.resolve(), args.output / "runs" / run_id,
            args.model, args.graphtyn.resolve(), args.graphify_python.resolve(),
            args.graphify_graph.resolve(), args.graphify_url, args.timeout,
        )
        results.append(result)
        results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        print(f"COMPLETED {run_id} total={result['usage'].get('total_tokens')} answer={result['answer_present']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
