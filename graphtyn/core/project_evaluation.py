"""Small, reproducible evaluations against a real project memory store.

The scale benchmark measures retrieval in a controlled fixture.  This module
complements it with source-backed cases: every expected memory names real files
and graph nodes, while negative questions must return no evidence.  A failed
case is serialized with enough information to become a permanent regression.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ast_parser import ASTParser
from .shared_memory import SharedMemoryStore


def _node_id(graph: dict[str, Any], name: str) -> str | None:
    for node in graph.get("nodes", []):
        if str(node.get("name") or "") == name:
            return str(node.get("id"))
    return None


def default_project_cases(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return source-backed questions for Graphtyn's own production code."""
    cases = [
        {
            "id": "local-alias-resolution",
            "query": "¿Cómo se conserva el alcance local antes de resolver un alias importado?",
            "expected_key": "relation-resolution",
            "title": "Resolución de nombres locales y aliases",
            "content": "La resolución conserva primero las definiciones locales antes de recurrir a un alias importado.",
            "files": ["graphtyn/core/relation_resolution.py"],
            "node": "lexical_targets",
        },
        {
            "id": "structured-execution-evidence",
            "query": "¿Cómo se comprueban las métricas estructuradas de una ejecución local?",
            "expected_key": "execution-evidence",
            "title": "Evidencia estructurada de ejecuciones locales",
            "content": "El registro de ejecución enlaza resultados estructurados y conserva la procedencia del comando y sus dependencias.",
            "files": ["graphtyn/core/shared_memory.py"],
            "node": "run_local_execution",
        },
        {
            "id": "missing-orbital-protocol",
            "query": "teletransporte orbital protocolizado",
            "expected_key": None,
            "title": "Pregunta sin evidencia",
            "content": "Esta memoria no debe aparecer en una consulta sin respaldo.",
            "files": [],
            "node": None,
        },
    ]
    for case in cases:
        if case.get("node"):
            case["node_id"] = _node_id(graph, str(case["node"]))
    return cases


def evaluate_project(
    project: str | Path,
    *,
    cases: list[dict[str, Any]] | None = None,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate evidence recall, provenance and abstention in ``project``.

    The evaluator intentionally uses the same local ``SharedMemoryStore`` path
    as production.  It never treats a matching word as provenance: a positive
    case passes only when its expected memory is returned and every cited file
    and node can be resolved in the project at evaluation time.
    """
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project path is not a directory: {root}")
    graph = ASTParser().scan_directory(root, respect_git=True)
    selected_cases = cases if cases is not None else default_project_cases(graph)
    # Keep the evaluation store outside the project so it cannot become source
    # evidence or contaminate the project's own .graphtyn index.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="graphtyn-project-eval-") as temp:
        store = SharedMemoryStore(root, db_path=Path(temp) / "memory-v2.db")
        session = store.start_session("project-evaluator", "real project evidence evaluation",
                                      session_id="ses_project_evaluation")
        ids: dict[str, str] = {}
        for case in selected_cases:
            if case.get("expected_key") is None:
                continue
            node_id = case.get("node_id") or _node_id(graph, str(case.get("node") or ""))
            node_ids = [str(node_id)] if node_id else []
            memory = store.checkpoint(
                session["id"], "decision", str(case["title"]), str(case["content"]),
                files=[str(path) for path in case.get("files", [])], node_ids=node_ids,
                tests=["project_evaluation"], status="verified", confidence=1.0,
            )
            ids[str(case["expected_key"])] = str(memory["id"])

        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for case in selected_cases:
            expected_key = case.get("expected_key")
            context = store.context(str(case["query"]), requester_agent="project-evaluator",
                                    limit=5, token_budget=900, include_graph=False)
            returned = context.get("memories", [])
            expected_id = ids.get(str(expected_key)) if expected_key is not None else None
            hit = next((item for item in returned if item.get("id") == expected_id), None)
            provenance_errors: list[str] = []
            if hit:
                for relative in hit.get("files") or []:
                    candidate = (root / str(relative)).resolve()
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        provenance_errors.append(f"outside_project:{relative}")
                        continue
                    if not candidate.is_file():
                        provenance_errors.append(f"missing_file:{relative}")
                for node_id in hit.get("node_ids") or []:
                    if not any(str(node.get("id")) == str(node_id) for node in graph.get("nodes", [])):
                        provenance_errors.append(f"missing_node:{node_id}")
            if expected_key is None:
                passed = not returned
                reason = "abstained" if passed else "returned_unexpected_evidence"
            else:
                passed = bool(hit) and not provenance_errors
                reason = "evidence_and_provenance_resolved" if passed else (
                    "missing_expected_evidence" if not hit else "provenance_unresolved")
            row = {
                "id": case["id"], "query": case["query"], "expected_key": expected_key,
                "returned_keys": [key for key, value in ids.items()
                                  if any(item.get("id") == value for item in returned)],
                "hit": bool(hit), "provenance_ok": not provenance_errors,
                "provenance_errors": provenance_errors, "reason": reason,
                "context_id": context.get("context_id"),
                "claim_policies": [item.get("claim_policy") for item in returned],
            }
            rows.append(row)
            if not passed:
                errors.append({"case": case["id"], "reason": reason,
                               "query": case["query"], "returned_keys": row["returned_keys"],
                               "provenance_errors": provenance_errors})

    result = {
        "ok": not errors, "project": str(root), "graph": {"nodes": len(graph.get("nodes", [])),
                                                               "links": len(graph.get("links", []))},
        "cases": rows, "errors": errors,
        "contract": {
            "positive_requires": ["expected memory returned", "all files exist under project",
                                   "all node_ids resolve in current graph"],
            "negative_requires": ["no memories returned"],
            "provenance_source": "current project files and AST graph",
        },
    }
    if output:
        destination = Path(output).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        portable = {**result, "project": "<PROJECT>"}
        destination.write_text(json.dumps(portable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
