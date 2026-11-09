#!/usr/bin/env python3
"""Grade answers with two model judges besides the literal rubric, and measure their agreement.

The literal rubric looks for identifiers (`ACTIVE_EXPIRE_CYCLE_FAST`), so a correct answer
written in prose scores zero and guidance that asks to name identifiers can inflate it.
Two judges from different vendors (Gemini through the Antigravity CLI and GPT through the
Codex CLI), without tools or access to the code, decide for each fact whether the answer
states it by name or by an unambiguous description. Cohen's kappa between the judges says
whether that decision is reproducible; the consensus counts a fact only when both agree.

Usage: judge_grades.py --tasks-root <benchmark folder> --run-root <runs> --variant <name> [--variant ...]
The tasks root holds the `*_tasks.json` files with each task's rubric. Results go to
<tasks root>/judge_grades.json; judge calls are cached in <tasks root>/judge_cache.json.
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

MAX_ANSWER = 24_000
JUDGES = {
    "gemini": lambda prompt, cwd: ["agy", "-p", prompt, "--model", "gemini-3.8-flash-high", "--output-format", "text",
                                   "--print-timeout", "150s", "--disable-slash-commands"],
    "gpt": lambda prompt, cwd: ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                                "--color", "never", "-m", "gpt-5.6-luna", "-s", "read-only", "-C", cwd, prompt],
}


def _specs(root: Path) -> dict[str, dict]:
    return {task["id"]: {**task, "corpus": path.name.removesuffix("_tasks.json")} for path in root.glob("**/*_tasks.json")
            for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]}


_CITATION = re.compile(r"([\w./-]+\.[A-Za-z0-9]+):(\d+)")
_CITED = 40


def resolve_citations(answer: str, root: Path | None) -> list[str]:
    """The answer's own `file:line` citations, mapped to the symbol around each line and its code.

    A judge without the code cannot tell that `app.py:890` is `handle_user_exception`, so an answer
    that cites a consumer by its line lost the fact. The mapping is read from the pinned corpus.
    """
    if root is None:
        return []
    from graphtyn.core.tree_sitter_backend import parse_file

    symbols: dict[str, list[dict]] = {}
    resolved, seen = [], set()
    for raw, number in _CITATION.findall(answer):
        path = raw.split("/workspaces/", 1)[-1].split("/", 1)[-1] if "/workspaces/" in raw else raw.lstrip("./")
        source = root / path
        if (path, number) in seen or not source.is_file():
            continue
        seen.add((path, number))
        if path not in symbols:
            facts = parse_file(source, path) or {}
            symbols[path] = [item for item in facts.get("symbols") or [] if item.get("line") and item.get("end_line")]
        line = int(number)
        around = [item for item in symbols[path] if item["line"] <= line <= item["end_line"]]
        owner = min(around, key=lambda item: item["end_line"] - item["line"], default=None)
        name = f"{owner.get('container') + '.' if owner and owner.get('container') else ''}{owner['name']}" if owner else ""
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
        code = " ".join(lines[line - 1].split())[:160] if 0 < line <= len(lines) else ""
        resolved.append(f"- {path}:{line} → {name or '(file level)'}: {code}")
        if len(resolved) >= _CITED:
            break
    return resolved


def _prompt(task: dict, answer: str, citations: list[str] | None = None) -> str:
    facts = "\n".join(f"- {fact['id']}: {', '.join(fact['any'])}" for fact in task["rubric"])
    keys = ", ".join(f'"{fact["id"]}": true|false' for fact in task["rubric"])
    appendix = ("\n\nThe answer's own file:line citations, resolved by the harness from the source "
                "(symbol around the line: code at the line):\n" + "\n".join(citations)) if citations else ""
    cited_rule = (" A fact the answer points to only by a citation counts when the resolved citation shows that "
                  "the cited code is the fact's symbol or behaviour and the answer says what it is.") if citations else ""
    return ("You are grading an answer about source code. Do NOT use tools or read files. Reply with JSON only.\n"
            f"Question: {task['request']}\n\nAnswer:\n{answer[:MAX_ANSWER]}{appendix}\n\n"
            "Facts (id: identifiers or files that evidence it):\n"
            f"{facts}\n\n"
            "For each fact, answer true only if the answer states that fact explicitly, by name or by an unambiguous "
            f"description of the same code or behaviour; a vague or generic statement is false.{cited_rule} Ignore the "
            f"language of the answer.\nReturn {{{keys}}}.")


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
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--variant", action="append", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", default="judge_grades.json", help="file name inside the tasks root")
    parser.add_argument("--cache", default="judge_cache.json", help="file name inside the tasks root")
    parser.add_argument("--repos", type=Path, action="append", default=[],
                        help="directory holding the pinned corpora by name; resolves the answers' citations")
    args = parser.parse_args()
    corpus_root = lambda corpus: next((base / corpus for base in args.repos if (base / corpus).is_dir()), None)  # noqa: E731
    specs = _specs(args.tasks_root)
    cache_path, output_path = args.tasks_root / args.cache, args.tasks_root / args.output
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    runs = []
    for variant in args.variant:
        for summary_path in sorted((args.run_root / variant).glob("*/runs/*/summary.json")):
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            answer_path = summary_path.parent / "answer.txt"
            answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
            task = specs[summary["task_id"]]
            literal = {fact["id"]: any(term.casefold() in answer.casefold() for term in fact["any"]) for fact in task["rubric"]}
            runs.append({"variant": variant, "arm": summary.get("arm", ""), "task": task["id"],
                         "repetition": summary["repetition"],
                         "tokens": summary["usage"].get("total_tokens"), "literal": literal,
                         "prompt": _prompt(task, answer, resolve_citations(answer, corpus_root(task["corpus"]))),
                         "facts": [fact["id"] for fact in task["rubric"]]})
    jobs = [(run, judge) for run in runs for judge in JUDGES
            if hashlib.sha256(f"{judge}\n{run['prompt']}".encode()).hexdigest() not in cache]
    with tempfile.TemporaryDirectory(prefix="graphtyn-judge-") as cwd, ThreadPoolExecutor(args.workers) as pool:
        for (run, judge), verdict in zip(jobs, pool.map(lambda job: _ask(job[1], job[0]["prompt"], cwd), jobs)):
            if verdict is not None:
                cache[hashlib.sha256(f"{judge}\n{run['prompt']}".encode()).hexdigest()] = verdict
    cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")
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
        rows.append({key: run[key] for key in ("variant", "arm", "task", "repetition", "tokens", "literal")}
                    | {"gemini": judged["gemini"], "gpt": judged["gpt"], "consensus": consensus})
    summary = {}
    # One group per variant, split by arm when a variant runs several (baseline, graphtyn, graphify).
    for key in dict.fromkeys((row["variant"], row["arm"]) for row in rows):
        group = [row for row in rows if (row["variant"], row["arm"]) == key]
        label = key[0] if len({row["arm"] for row in rows if row["variant"] == key[0]}) == 1 else "/".join(key)
        summary[label] = {"runs": len(group), "facts": sum(len(row["literal"]) for row in group),
                          "tokens": sum(int(row["tokens"] or 0) for row in group),
                          **{name: sum(sum(row[name].values()) for row in group)
                             for name in ("literal", "gemini", "gpt", "consensus")}}
    agreement = {name: _kappa(*values) for name, values in pairs.items()}
    output_path.write_text(json.dumps({"summary": summary, "kappa": agreement, "runs": rows},
                                                        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "kappa": agreement}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
