"""Where rubric facts are lost between the graph and the lean package.

For every task the script counts the rubric facts that some graph node spells
(name, signature or operations), the facts the first N candidates spell after
each selection stage of query_intent (N = the number of nodes finally selected),
the facts the selected nodes spell and the facts present in the lean package.

usage: GRAPHTYN_HOME=<home with indexes> PYTHONPATH=. \
       python selection_diagnosis.py dev|test|test2|test3 <dir with indexed corpora> [--jsonl out]
"""

import argparse
import json
import statistics
from pathlib import Path

from graphtyn.core.lean_package import lean_payload
from graphtyn.core.ranking_weights import trace_selection
from graphtyn.core.storage import data_home, project_store_dir
from graphtyn.mcp_server import build_intent_package

HERE = Path(__file__).resolve().parent
CORPORA = ("redis", "fmt", "rails", "flask", "lua")
STAGES = ("scored", "pre_mandatory", "homonyms", "anchors", "chain")


def node_text(node: dict) -> str:
    return " ".join([str(node.get("name") or ""), str(node.get("signature") or ""),
                     *(f"{op.get('name', '')} {op.get('text', '')}" for op in node.get("operations") or [])])


def facts_in(texts, rubric) -> set:
    joined = "\n".join(texts)
    return {fact["id"] for fact in rubric if any(term in joined for term in fact["any"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("split")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--jsonl", type=Path)
    args = parser.parse_args()
    patterns = json.loads((HERE / "split.json").read_text())[args.split]
    rows = []
    for corpus in CORPORA:
        files = [path for path in (HERE / pattern.format(corpus=corpus) for pattern in patterns) if path.exists()]
        if not files:
            continue
        root = args.workspace / corpus
        graph = json.loads((project_store_dir(data_home(), root) / "index.json").read_text())
        all_texts = [node_text(node) for node in graph["nodes"]]
        for path in files:
            for task in json.loads(path.read_text())["tasks"]:
                rubric = task["rubric"]
                with trace_selection() as trace:
                    _raw, result, _ = build_intent_package(root, graph, task["request"])
                selected = trace.get("selected", [])
                n = max(1, len(selected))
                row = {"task": task["id"], "total": len(rubric),
                       "graph": len(facts_in(all_texts, rubric))}
                for stage in STAGES:
                    row[stage] = len(facts_in([node_text(node) for node in trace.get(stage, [])[:n]], rubric))
                row["selected"] = len(facts_in([node_text(node) for node in selected], rubric))
                row["package"] = len(facts_in([json.dumps(lean_payload(result), ensure_ascii=False)], rubric))
                rows.append(row)
                print(" ".join(f"{key}={value}" for key, value in row.items()), flush=True)
    columns = ("graph", *STAGES, "selected", "package")
    print("mean share:", " ".join(
        f"{column}={statistics.fmean(row[column] / row['total'] for row in rows):.1%}" for column in columns))
    if args.jsonl:
        args.jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
