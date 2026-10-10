"""Honest differential verification without executing untrusted repository code."""

from __future__ import annotations

import ast
import hashlib
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
    plan = []
    seen_ids = set()
    changed_files = set(impact.get("changed_files", []))

    def append(item: dict[str, Any]) -> None:
        if len(plan) >= 100:
            return
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen_ids:
            return
        seen_ids.add(item_id)
        item["order"] = len(plan) + 1
        plan.append(item)

    # Preserve the impact engine's category-level actions even when a large
    # working tree contains more than 100 changed symbols.
    for engine_item in impact.get("verification_plan", []):
        action = str(engine_item.get("action") or "manual_review")
        targets = [str(target) for target in engine_item.get("targets", []) if target][:20]
        if not targets:
            targets = sorted(changed_files)[:20]
        append({
            "id": "verification:" + action + ":" + hashlib.sha256("\0".join(targets).encode()).hexdigest()[:12],
            "symbol": None,
            "file": targets[0] if len(targets) == 1 and not targets[0].startswith(("symbol:", "file:")) else None,
            "reason": "impact_engine_action",
            "action": action,
            "targets": targets,
            "command": engine_item.get("command"),
            "conditions": engine_item.get("conditions") or ["run only in a trusted project environment"],
            "estimated_cost": engine_item.get("estimated_cost") or "unknown",
            "expected_result": engine_item.get("expected_result") or "no regressions in the affected contract",
            "verification_type": "command" if engine_item.get("command") else "manual",
        })

    changed_symbols = list(impact.get("changed_symbols", []))
    impacted_nodes = list(impact.get("impacted_nodes", []))
    changed_primary = changed_symbols[:48] if impacted_nodes else changed_symbols

    def append_changed(item: dict[str, Any]) -> None:
        node_id = str(item.get("id") or f"symbol:{item.get('file')}:{item.get('name')}")
        append({
            "id": node_id,
            "symbol": item.get("name"),
            "file": item.get("file"),
            "reason": "changed",
            "action": "verify_changed_symbol",
            "targets": [node_id],
            "command": None,
            "conditions": ["review current diff and public contract"],
            "estimated_cost": "manual-small",
            "expected_result": "changed behavior matches the intended contract",
        })

    for item in changed_primary:
        append_changed(item)

    for item in impacted_nodes:
        node = item.get("node", {})
        node_id = str(node.get("id") or f"symbol:{node.get('file')}:{node.get('name')}")
        name = node.get("name")
        file_path = node.get("file")
        label = item.get("label", "")

        # If this node is internal containment within an already-changed file (e.g. Markdown header sections),
        # do not flood the plan with dozens of section sub-items
        if label == "contiene" and file_path in changed_files:
            continue

        if node_id and node_id not in seen_ids:
            action = "run_adjacent_tests" if any(marker in str(file_path or "").lower()
                                                   for marker in ("/test", "_test.", "tests/")) else "review_consumer"
            append({
                "id": node_id,
                "symbol": name,
                "file": file_path,
                "reason": f"consumer_hop_{item.get('hop', 1)}",
                "action": action,
                "targets": [node_id],
                "command": None,
                "conditions": ["verify relation evidence before treating ambiguous links as consumers"],
                "estimated_cost": "manual-small",
                "expected_result": "consumer remains compatible with the changed symbol",
                "verification_type": "manual",
            })
    for item in changed_symbols[len(changed_primary):]:
        append_changed(item)
    return plan
