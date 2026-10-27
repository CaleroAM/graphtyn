"""Rubric facts present in the graph_query_intent package, without any agent.

usage: GRAPHTYN_HOME=<home with indexes> PYTHONPATH=<graphtyn tree> \
       python package_coverage.py old|new <dir with indexed redis/ fmt/ rails/ copies>
`old` uses the pre-lean pipeline (run it with PYTHONPATH at commit 2fde7ee).
"""
import json, sys
from pathlib import Path
mode = sys.argv[1]
W = Path(sys.argv[2])
B = Path(__file__).resolve().parents[1]
from graphtyn.mcp_server import query_intent, attach_source_evidence, evidence_result
from graphtyn.core.storage import data_home, project_store_dir
for corpus in ("redis", "fmt", "rails"):
    graph = json.loads((project_store_dir(data_home(), W / corpus) / "index.json").read_text())
    task_sets = [(f"heldout", B / f"heldout_tasks_2026-10-27/{corpus}_tasks.json"),
                 ("original", B / f"real_multi_client_hook_2026-10-27/{corpus}_tasks.json")]
    for label, path in task_sets:
        for task in json.loads(path.read_text())["tasks"]:
            if mode == "new":
                from graphtyn.mcp_server import build_intent_package, lean_payload
                _raw, result, _ = build_intent_package(W / corpus, graph, task["request"])
                result = lean_payload(result)
            else:
                raw = query_intent(graph, task["request"], "auto", 10)
                raw = attach_source_evidence(W / corpus, raw, task["request"], "auto")
                result = evidence_result(raw, max_nodes=10)
            text = json.dumps(result, ensure_ascii=False)
            hits = [r["id"] for r in task["rubric"] if any(a in text for a in r["any"])]
            print(json.dumps({"mode": mode, "set": label, "task": task["id"], "covered": len(hits),
                              "total": len(task["rubric"]), "missing": [r["id"] for r in task["rubric"] if r["id"] not in hits],
                              "tokens": result.get("payload_tokens") or result.get("estimated_tokens"),
                              "do_not_expand": result.get("do_not_expand")}))
