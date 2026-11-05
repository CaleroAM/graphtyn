#!/usr/bin/env python3
"""Grade answers with two model judges besides the literal rubric, and measure their agreement.

The literal rubric looks for identifiers (`ACTIVE_EXPIRE_CYCLE_FAST`), so a correct answer
written in prose scores zero and guidance that asks to name identifiers can inflate it.
Two judges from different vendors (Gemini through the Antigravity CLI and GPT through the
Codex CLI), without tools or access to the code, decide for each fact whether the answer
states it by name or by an unambiguous description. Cohen's kappa between the judges says
whether that decision is reproducible; the consensus counts a fact only when both agree.

Usage: judge_grades.py --run-root <runs> --variant <name> [--variant ...]
Results go to judge_grades.json; calls are cached in judge_cache.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "judge_cache.json"
MAX_ANSWER = 24_000
JUDGES = {
    "gemini": lambda prompt, cwd: ["agy", "-p", prompt, "--model", "gemini-3.8-flash-high", "--output-format", "text",
                                   "--print-timeout", "150s", "--disable-slash-commands"],
    "gpt": lambda prompt, cwd: ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                                "--color", "never", "-m", "gpt-5.6-luna", "-s", "read-only", "-C", cwd, prompt],
}


def _specs() -> dict[str, dict]:
    return {task["id"]: task for path in HERE.glob("**/*_tasks.json")
            for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]}


def _prompt(task: dict, answer: str) -> str:
    facts = "\n".join(f"- {fact['id']}: {', '.join(fact['any'])}" for fact in task["rubric"])
    keys = ", ".join(f'"{fact["id"]}": true|false' for fact in task["rubric"])
    return ("You are grading an answer about source code. Do NOT use tools or read files. Reply with JSON only.\n"
            f"Question: {task['request']}\n\nAnswer:\n{answer[:MAX_ANSWER]}\n\n"
            "Facts (id: identifiers or files that evidence it):\n"
            f"{facts}\n\n"
            "For each fact, answer true only if the answer states that fact explicitly, by name or by an unambiguous "
            "description of the same code or behaviour; a vague or generic statement is false. Ignore the language "
            f"of the answer.\nReturn {{{keys}}}.")


def _ask(judge: str, prompt: str, cwd: str) -> dict[str, bool] | None:
    for _attempt in range(2):
        try:
            output = subprocess.run(JUDGES[judge](prompt, cwd), capture_output=True, text=True, timeout=240,
                                    stdin=subprocess.DEVNULL, cwd=cwd).stdout
            match = re.search(r"\{[^{}]*\}", output, re.S)
            if match:
                return {key: bool(value) for key, value in json.loads(match.group(0)).items()}
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            continue
    return None


def _kappa(left: list[bool], right: list[bool]) -> float | None:
    if not left:
        return None
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    p_left, p_right = sum(left) / len(left), sum(right) / len(right)
    expected = p_left * p_right + (1 - p_left) * (1 - p_right)
    return round((observed - expected) / (1 - expected), 3) if expected < 1 else 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--variant", action="append", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    specs = _specs()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    runs = []
    for variant in args.variant:
        for summary_path in sorted((args.run_root / variant).glob("*/runs/*/summary.json")):
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            answer_path = summary_path.parent / "answer.txt"
            answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
            task = specs[summary["task_id"]]
            literal = {fact["id"]: any(term.casefold() in answer.casefold() for term in fact["any"]) for fact in task["rubric"]}
            runs.append({"variant": variant, "task": task["id"], "repetition": summary["repetition"],
                         "tokens": summary["usage"].get("total_tokens"), "literal": literal,
                         "prompt": _prompt(task, answer), "facts": [fact["id"] for fact in task["rubric"]]})
    jobs = [(run, judge) for run in runs for judge in JUDGES
            if hashlib.sha256(f"{judge}\n{run['prompt']}".encode()).hexdigest() not in cache]
    with tempfile.TemporaryDirectory(prefix="graphtyn-judge-") as cwd, ThreadPoolExecutor(args.workers) as pool:
        for (run, judge), verdict in zip(jobs, pool.map(lambda job: _ask(job[1], job[0]["prompt"], cwd), jobs)):
            if verdict is not None:
                cache[hashlib.sha256(f"{judge}\n{run['prompt']}".encode()).hexdigest()] = verdict
    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    rows, pairs = [], {"judges": ([], []), "literal_consensus": ([], [])}
    for run in runs:
        verdicts = {judge: cache.get(hashlib.sha256(f"{judge}\n{run['prompt']}".encode()).hexdigest()) for judge in JUDGES}
        if any(verdict is None for verdict in verdicts.values()):
            continue
        judged = {judge: {fact: bool(verdict.get(fact)) for fact in run["facts"]} for judge, verdict in verdicts.items()}
        consensus = {fact: judged["gemini"][fact] and judged["gpt"][fact] for fact in run["facts"]}
        for fact in run["facts"]:
            pairs["judges"][0].append(judged["gemini"][fact])
            pairs["judges"][1].append(judged["gpt"][fact])
            pairs["literal_consensus"][0].append(run["literal"][fact])
            pairs["literal_consensus"][1].append(consensus[fact])
        rows.append({key: run[key] for key in ("variant", "task", "repetition", "tokens", "literal")}
                    | {"gemini": judged["gemini"], "gpt": judged["gpt"], "consensus": consensus})
    summary = {}
    for variant in args.variant:
        group = [row for row in rows if row["variant"] == variant]
        summary[variant] = {"runs": len(group), "facts": sum(len(row["literal"]) for row in group),
                            **{key: sum(sum(row[key].values()) for row in group)
                               for key in ("literal", "gemini", "gpt", "consensus")}}
    agreement = {name: _kappa(*values) for name, values in pairs.items()}
    (HERE / "judge_grades.json").write_text(json.dumps({"summary": summary, "kappa": agreement, "runs": rows},
                                                        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "kappa": agreement}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
