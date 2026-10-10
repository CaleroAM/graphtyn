"""Regression tests for findings H05 and H06 (Task G06).

Findings covered:
- H05: Risk calculation mixes documentation containment with functional contract risk
       (resolved in G06 by distinguishing containment from functional callers and capping doc impact).
- H06: Verification plan deduplicates by symbol name alone, dropping homonyms across files,
       and floods plan with internal sections of changed files
       (resolved in G06 by deduplicating by stable symbol/file ID and omitting internal doc sections).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.impact import analyze_impact
from graphtyn.core.verification import verification_plan


def test_h06_verification_plan_preserves_homonymous_consumers_across_files():
    """Verify that two distinct consumers sharing the same name in different files are preserved."""
    impact_data = {
        "changed_symbols": [],
        "impacted_nodes": [
            {
                "node": {"id": "symbol:a.py:validate", "name": "validate", "file": "a.py"},
                "hop": 1,
            },
            {
                "node": {"id": "symbol:b.py:validate", "name": "validate", "file": "b.py"},
                "hop": 1,
            },
        ],
    }

    plan = verification_plan(impact_data)

    # Previously: deduplicated by name alone, resulting in len(plan) == 1
    # Fixed: both distinct consumers are preserved
    assert len(plan) == 2, f"Expected 2 plan items, got {len(plan)}"
    symbols = [(item["symbol"], item["file"]) for item in plan]
    assert ("validate", "a.py") in symbols
    assert ("validate", "b.py") in symbols


def test_h06_large_plan_preserves_engine_actions_and_direct_consumers():
    impact_data = {
        "changed_files": ["src/change.py"],
        "changed_symbols": [
            {"id": f"symbol:src/change.py:f{i}", "name": f"f{i}", "file": "src/change.py"}
            for i in range(120)
        ],
        "verification_plan": [
            {"action": "run_adjacent_tests", "targets": ["tests/test_change.py"]},
            {"action": "review_ambiguous_relations", "targets": ["symbol:src/use.py:consumer"]},
        ],
        "impacted_nodes": [{
            "node": {"id": "symbol:src/use.py:consumer", "name": "consumer", "file": "src/use.py"},
            "hop": 1, "label": "llama",
        }],
    }

    plan = verification_plan(impact_data)
    actions = {item["action"] for item in plan}
    ids = {item["id"] for item in plan}
    assert len(plan) <= 100
    assert {"run_adjacent_tests", "review_ambiguous_relations"} <= actions
    assert "symbol:src/use.py:consumer" in ids


def test_h05_documentation_edit_does_not_saturate_risk_to_100(tmp_path):
    """Verify that changing a sentence in a 40-section README does not produce risk 100/100 or 41 plan items."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    readme = tmp_path / "README.md"
    content = "# Example\n\nIntro original.\n\n" + "".join(
        f"## Section {i:02}\n\nExplanatory text.\n\n" for i in range(40)
    )
    readme.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Audit", "-c", "user.email=audit@example.test", "commit", "-qm", "temporary baseline"],
        cwd=tmp_path, check=True
    )

    # Edit one sentence
    readme.write_text(content.replace("Intro original.", "Intro corregida."), encoding="utf-8")

    parsed = ASTParser().scan_directory(tmp_path, respect_git=True)
    impact = analyze_impact(tmp_path, parsed, base="HEAD")
    plan = verification_plan(impact)

    # Previously: risk 100/100 and plan had 41 entries
    # Fixed: risk is low (< 25) and plan does not repeat 40+ sections
    assert impact["risk"]["score"] < 25, f"Expected risk < 25 for editorial doc change, got {impact['risk']['score']}"
    assert impact["risk"]["level"] == "low"
    assert len(plan) < 10, f"Expected compact plan for doc change, got {len(plan)}"
