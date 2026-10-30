"""Rubric facts present in the graph_query_intent package, without agents.

usage: GRAPHTYN_HOME=<home with indexes> PYTHONPATH=<graphtyn tree> \
       python coverage.py dev|test|test2|test3 <dir with indexed redis/ fmt/ rails/ copies> [--jsonl out]

A package is a false completion when it sets do_not_expand=true while covering
less than half of the rubric.
"""
import argparse
import json
import statistics
from pathlib import Path

from graphtyn.core.lean_package import lean_payload
from graphtyn.core.storage import data_home, project_store_dir
from graphtyn.mcp_server import build_intent_package

HERE = Path(__file__).resolve().parent
CORPORA = ("redis", "fmt", "rails", "flask", "lua")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=("dev", "test", "test2", "test3"))
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--jsonl", type=Path)
    args = parser.parse_args()
    patterns = json.loads((HERE / "split.json").read_text())[args.split]
    rows = []
    for corpus in CORPORA:
        task_files = [HERE / pattern.format(corpus=corpus) for pattern in patterns]
        task_files = [path for path in task_files if path.exists()]
        if not task_files:
            continue
        root = args.workspace / corpus
        graph = json.loads((project_store_dir(data_home(), root) / "index.json").read_text())
        for path in task_files:
            for task in json.loads(path.read_text())["tasks"]:
                _raw, result, _ = build_intent_package(root, graph, task["request"])
                result = lean_payload(result)
                text = json.dumps(result, ensure_ascii=False)
                hits = [r["id"] for r in task["rubric"] if any(a in text for a in r["any"])]
                rows.append({"split": args.split, "task": task["id"], "covered": len(hits),
                             "total": len(task["rubric"]),
                             "missing": [r["id"] for r in task["rubric"] if r["id"] not in hits],
                             "intent": result.get("intent"), "tokens": result.get("payload_tokens"),
                             "do_not_expand": result.get("do_not_expand")})
    for row in rows:
        print(f"{row['task']:30} {row['covered']}/{row['total']} intent={row['intent']} "
              f"dne={row['do_not_expand']} tokens={row['tokens']} missing={row['missing']}")
    ratio = statistics.fmean(r["covered"] / r["total"] for r in rows)
    false_complete = [r["task"] for r in rows if r["do_not_expand"] and r["covered"] / r["total"] < 0.5]
    print(f"{args.split}: tasks={len(rows)} mean_coverage={ratio:.1%} false_complete={len(false_complete)} {false_complete}")
    if args.jsonl:
        args.jsonl.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
