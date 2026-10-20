#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("three_client", HERE / "run_three_client_mcp_comparison.py")
COMMON = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(COMMON)


def clean(repo: Path) -> bool:
    return not subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip()


def configuration(treatment: bool, graph_path: Path) -> str:
    mcp = {"graphtyn_modiaceb_ee21e22c": {"enabled": False},
           "graphtyn": {"enabled": False}, "graphify": {"enabled": False}}
    if treatment:
        mcp["graphtyn_benchmark"] = {"type": "local", "enabled": True, "command": [
            "graphtyn", "mcp", "--tool-profile", "intent", "--path", str(graph_path)
        ]}
    return json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": mcp,
                       "tools": {"webfetch": False, "task": False},
                       "permission": {"edit": "allow", "bash": "allow", "read": "allow"}})


def prompt(task: str, treatment: bool) -> str:
    common = ("Trabaja únicamente en el repositorio actual. Implementa la tarea completa, edita los archivos "
              "necesarios y ejecuta pruebas relevantes. No uses red, otros agentes, benchmarks, memorias ni "
              "credenciales. No hagas commit. Conserva compatibilidad y evita cambios ajenos. ")
    condition = ("Primero usa graph_query_intent una vez con la tarea completa; verifica sus ubicaciones en "
                 "fuente y usa lectura local para cubrir lo que falte. Antes de terminar usa graph_query_intent "
                 "con intent=impact sobre tu cambio y corrige consumidores omitidos. " if treatment else
                 "No uses Graphtyn, Graphify, MCP, índices ni reportes generados. Investiga con herramientas locales. ")
    return common + condition + "Al final resume cambios y pruebas.\n\nTAREA:\n" + task


def run_arm(name: str, repo: Path, graph_path: Path, model: str, task: str, output: Path) -> dict:
    treatment = name == "graphtyn"
    if not clean(repo):
        raise SystemExit(f"worktree is not clean before {name}: {repo}")
    env = os.environ.copy()
    env["OPENCODE_CONFIG_CONTENT"] = configuration(treatment, graph_path)
    command = ["opencode", "run", "--pure", "--auto", "--dir", str(repo), "--model", model,
               "--format", "json", prompt(task, treatment)]
    started = time.monotonic()
    process = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True, timeout=900)
    events = COMMON.parse_json_lines(process.stdout)
    usage = COMMON.normalize_usage("opencode", events)
    answer = COMMON.answer_from_events("opencode", events)
    destination = output / name
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    (destination / "answer.txt").write_text(answer + "\n")
    (destination / "stderr.txt").write_text(process.stderr)
    diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary"], text=True)
    status = subprocess.check_output(["git", "-C", str(repo), "status", "--short"], text=True)
    (destination / "change.patch").write_text(diff)
    result = {"arm": name, "model": model, "returncode": process.returncode,
              "wall_seconds": round(time.monotonic() - started, 3), "usage": usage,
              "tool_calls": sum(e.get("type") == "tool_use" for e in events),
              "answer_present": bool(answer), "status": status.splitlines()}
    (destination / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--graph-path", type=Path, required=True)
    parser.add_argument("--arm", action="append", choices=("baseline", "graphtyn"),
                        help="Run only selected arms; completed arms are never repeated")
    parser.add_argument("--no-token-ceiling", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    results_path = args.output / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    total = sum((row.get("usage") or {}).get("total_tokens") or 0 for row in results)
    completed = {row["arm"] for row in results}
    for arm in tuple(args.arm or ("baseline", "graphtyn")):
        if arm in completed:
            print(f"REUSE_COMPLETED {arm}")
            continue
        result = run_arm(arm, Path(protocol["arms"][arm]), args.graph_path.resolve(),
                         protocol["model"], protocol["task"], args.output)
        results.append(result)
        measured = result["usage"].get("total_tokens")
        if measured is None:
            raise SystemExit(f"{arm} did not report total tokens")
        total += measured
        (args.output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        if not args.no_token_ceiling and total > protocol["token_ceiling"]:
            raise SystemExit(f"token ceiling exceeded after {arm}: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
