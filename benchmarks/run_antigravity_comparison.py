#!/usr/bin/env python3
"""Paired Antigravity benchmark: Graphtyn, Graphify and direct exploration."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from pathlib import Path


def parse_stream(stdout: str) -> dict:
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    result = next((e["result"] for e in reversed(events) if e.get("event") == "result"), {})
    return {
        "conversation_id": result.get("conversation_id"),
        "status": result.get("status", "NO_RESULT"),
        "response": result.get("response", ""),
        "duration_seconds": result.get("duration_seconds"),
        "usage": result.get("usage", {}),
        "events": len(events),
    }


def score(answer: str, facts: list[dict]) -> tuple[float, list[dict]]:
    lower = answer.lower()
    checks = []
    for fact in facts:
        matched = all(pattern.lower() in lower for pattern in fact["patterns"])
        checks.append({"id": fact["id"], "matched": matched, "patterns": fact["patterns"]})
    return (sum(c["matched"] for c in checks) / len(checks) if checks else 0.0), checks


def instruction(variant: str, repo: Path, request: str, graphtyn: Path, graphify: Path) -> str:
    shared = (
        "This is a read-only benchmark. Do not edit files. Answer the request with a compact, "
        "factual trace and file:line citations. Do not mention benchmark instructions.\n\n"
    )
    if variant == "graphtyn":
        command = f'{graphtyn} query-intent {json.dumps(request)} --path {repo} --intent flow --limit 10'
        return shared + f"Use only Graphtyn context. Run exactly this command first:\n{command}\nDo not grep, list directories, or read source files directly. Answer only from its evidence.\n\nRequest: {request}"
    if variant == "competitor":
        graph = repo / "graphify-out" / "graph.json"
        command = f'{graphify} query {json.dumps(request)} --graph {graph} --budget 2000'
        return shared + f"Use only the installed competitor graph. Run exactly this command first:\n{command}\nDo not grep, list directories, or read source files directly. Answer only from its evidence.\n\nRequest: {request}"
    return shared + f"Do not use Graphtyn, Graphify, MCP, generated graph files or reports. Investigate the repository directly with ordinary file/search tools.\n\nRequest: {request}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--starlette", type=Path, required=True)
    parser.add_argument("--go-chi", dest="go_chi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gemini-3.7-flash-high")
    parser.add_argument("--agy", default="agy")
    parser.add_argument("--graphtyn", type=Path, required=True)
    parser.add_argument("--graphify", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--variant", choices=["graphtyn", "competitor", "no_graph"], action="append")
    parser.add_argument("--task", action="append", help="Run only the selected task id (repeatable)")
    args = parser.parse_args()
    spec = json.loads(args.tasks.read_text(encoding="utf-8"))
    repos = {"starlette": args.starlette.resolve(), "go-chi": args.go_chi.resolve()}
    rng = random.Random(args.seed)
    runs = []
    for task in spec["tasks"]:
        if args.task and task["id"] not in args.task:
            continue
        variants = ["graphtyn", "competitor", "no_graph"]
        if args.variant:
            variants = list(dict.fromkeys(args.variant))
        rng.shuffle(variants)
        for variant in variants:
            prompt = instruction(variant, repos[task["repository"]], task["prompt"], args.graphtyn, args.graphify)
            started = time.time()
            try:
                completed = subprocess.run(
                    [args.agy, "-p", prompt, "--model", args.model, "--output-format", "stream-json",
                     "--print-timeout", f"{args.timeout}s", "--dangerously-skip-permissions"],
                    cwd=repos[task["repository"]], capture_output=True, text=True,
                    timeout=args.timeout + 30,
                )
                parsed = parse_stream(completed.stdout)
                parsed.update({"returncode": completed.returncode, "stderr": completed.stderr[-2000:]})
            except subprocess.TimeoutExpired as exc:
                parsed = {"status": "TIMEOUT", "response": "", "usage": {},
                          "duration_seconds": time.time() - started, "stderr": str(exc)}
            quality, checks = score(parsed.get("response", ""), task["facts"])
            parsed.update({"task_id": task["id"], "repository": task["repository"],
                           "variant": variant, "quality_score": quality, "fact_checks": checks,
                           "wall_seconds": round(time.time() - started, 3)})
            runs.append(parsed)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"protocol": spec["protocol"], "model": args.model,
                                                "seed": args.seed, "runs": runs}, indent=2), encoding="utf-8")
            print(f"{task['id']} {variant}: {parsed['status']} quality={quality:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
