#!/usr/bin/env python3
"""Semantic grading of agent answers against the task-bank rubrics.

The literal rubric counts a fact only when the answer writes one of its names,
which penalises short answers that describe a stage without naming it. This
judge asks a model, once per session, which rubric facts the answer states
either by name or by an unambiguous description of that code. Verdicts are
cached as judge.json next to each session, so a rerun only grades new answers.

usage: python judge_answers.py <split> <run-root> [<run-root> ...] [--model M] [--parallel N]

analyze_variants.py reads the cached verdicts and reports `mean_judged_quality`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPORA = ("redis", "fmt", "rails", "flask", "lua", "jq", "sinatra")
PROMPT = """You grade an answer about source code against a rubric. For every rubric fact, decide
whether the answer states it: either it names one of the listed identifiers, or it unambiguously
describes that same piece of code and its role (a vague mention of the topic does not count).
Answer with JSON only: {{"facts": {{"<fact id>": true|false, ...}}}}.

Task: {request}

Rubric facts (id: identifiers that denote it):
{facts}

Answer to grade:
<<<
{answer}
>>>"""


def judge(run_dir: Path, task: dict, model: str) -> dict | None:
    cached = run_dir / "judge.json"
    if cached.exists():
        return json.loads(cached.read_text())
    answer_path = run_dir / "answer.txt"
    answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
    facts = "\n".join(f"- {fact['id']}: {', '.join(fact['any'])}" for fact in task["rubric"])
    prompt = PROMPT.format(request=task["request"], facts=facts, answer=answer[:24000])
    # Outside any project, so no project instructions, hooks or MCP servers load.
    process = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--tools", "",
                              "--strict-mcp-config"], input=prompt, capture_output=True, text=True,
                             timeout=300, cwd=tempfile.gettempdir())
    try:
        text = json.loads(process.stdout)["result"]
        verdict = json.loads(re.search(r"\{.*\}", text, re.S).group(0))["facts"]
    except (ValueError, KeyError, AttributeError, TypeError):
        return None
    result = {"model": model, "facts": {fact["id"]: bool(verdict.get(fact["id"])) for fact in task["rubric"]}}
    cached.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("split")
    parser.add_argument("run_roots", type=Path, nargs="+")
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()
    specs = {task["id"]: task for corpus in CORPORA if (HERE / args.split / f"{corpus}_tasks.json").exists()
             for task in json.loads((HERE / args.split / f"{corpus}_tasks.json").read_text())["tasks"]}
    sessions = []
    for root in args.run_roots:
        for summary_path in sorted(root.glob("*/*/*/*/runs/*/summary.json")):
            summary = json.loads(summary_path.read_text())
            if summary.get("session_status") == "complete" and summary["task_id"] in specs:
                sessions.append((summary_path.parent, specs[summary["task_id"]]))
    with ThreadPoolExecutor(args.parallel) as pool:
        results = list(pool.map(lambda item: judge(item[0], item[1], args.model), sessions))
    print(f"judged {sum(result is not None for result in results)}/{len(sessions)} sessions")
    return 0 if all(result is not None for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
