"""Honest differential verification without executing untrusted repository code."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30)


def _functions(source: str) -> dict[str, ast.AST]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = node
    return found


def verify_python_edits(root: Path, base: str = "HEAD") -> dict[str, Any]:
    """Prove only AST-identical functions; changed semantics explicitly abstain.

    This tier is deliberately conservative. AST identity is a sound equivalence
    result for the parsed function under the same runtime; any semantic edit is
    marked unsupported until a solver/property runner is available.
    """
    changed = _git(root, "diff", "--name-only", base, "--", "*.py")
    if changed.returncode != 0:
        return {"ok": False, "base": base, "error": changed.stderr.strip(), "verdicts": []}
    verdicts = []
    for relative in [line for line in changed.stdout.splitlines() if line]:
        current_path = root / relative
        old = _git(root, "show", f"{base}:{relative}")
        if old.returncode != 0 or not current_path.is_file():
            verdicts.append({"file": relative, "symbol": "*", "verdict": "unsupported", "reason": "added_or_deleted_file"})
            continue
        previous, current = _functions(old.stdout), _functions(current_path.read_text(encoding="utf-8", errors="replace"))
        for name in sorted(set(previous) | set(current)):
            if name not in previous or name not in current:
                verdict = {"verdict": "distinguished", "reason": "function_added_or_removed"}
            elif ast.dump(previous[name], include_attributes=False) == ast.dump(current[name], include_attributes=False):
                verdict = {"verdict": "equivalent", "reason": "canonical_ast_identical"}
            else:
                verdict = {"verdict": "unsupported", "reason": "semantic_edit_requires_solver_or_tests"}
            verdicts.append({"file": relative, "symbol": name, **verdict})
    counts = {key: sum(item["verdict"] == key for item in verdicts)
              for key in ("equivalent", "distinguished", "unsupported")}
    return {"ok": True, "base": base, "engine": "python-canonical-ast", "sound_scope": "AST-identical Python functions only",
            "verdicts": verdicts, "counts": counts}


def verification_plan(impact: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a deterministic callee/changed-first verification order."""
    plan = [{"symbol": item["name"], "file": item["file"], "order": index + 1, "reason": "changed"}
            for index, item in enumerate(impact.get("changed_symbols", []))]
    seen = {item["symbol"] for item in plan}
    for item in impact.get("impacted_nodes", []):
        node = item.get("node", {})
        name = node.get("name")
        if name and name not in seen:
            seen.add(name)
            plan.append({"symbol": name, "file": node.get("file"), "order": len(plan) + 1,
                         "reason": f"consumer_hop_{item.get('hop', 1)}"})
    return plan[:100]
