from pathlib import Path

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.overview_report import derive_architecture, render_report


def _project(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(
        "# Acme CRM\n\nAcme CRM manages customers, sales opportunities and invoicing for distributed commercial teams.\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"react":"latest","@inertiajs/react":"latest"},"devDependencies":{"typescript":"latest","vite":"latest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["fastapi","uvicorn"]\n', encoding="utf-8")
    (tmp_path / "main.py").write_text("def main():\n    return run()\ndef run():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_overview_verifies_purpose_frameworks_architecture_and_risks(tmp_path):
    root = _project(tmp_path)
    graph = ASTParser().scan_directory(root, respect_git=False)
    result = query_intent(graph, "Dime de qué trata este repositorio", "auto", 10)
    profile = result["project_profile"]
    assert result["intent"] == "overview"
    assert profile["purpose_source"] == "README.md"
    assert "manages customers" in profile["purpose"]
    assert {"React", "Inertia.js", "TypeScript", "Vite", "FastAPI", "Uvicorn"} <= set(profile["frameworks"])
    assert result["architecture"]["format"] == "mermaid"
    assert result["overview_quality"]["basis"].endswith("not semantic accuracy")
    assert isinstance(result["representative_flows"], list)
    assert isinstance(result["risk_signals"], list)


def test_report_is_compact_persistent_format_and_compares_graphify_tokens(tmp_path):
    root = _project(tmp_path)
    graphify = root / "GRAPH_REPORT.md"
    graphify.write_text("# Graphify\n" + ("large report text\n" * 500), encoding="utf-8")
    graph = ASTParser().scan_directory(root, respect_git=False)
    report, metrics = render_report(root, graph, graphify)
    assert report.startswith("# GRAPHTYN REPORT")
    assert "## Purpose" in report and "```mermaid" in report
    assert "## Representative flows" in report and "## Risk and technical-debt signals" in report
    assert metrics["estimated_tokens"] < metrics["graphify_report_tokens"]
    assert metrics["reduction_vs_selected_source"] <= 1  # tiny repos may honestly expand
    assert 0 <= metrics["graphify_observable_coverage"] <= 1
    assert metrics["quality_note"].startswith("Coverage compares observable")


def test_architecture_diagram_includes_extracted_cross_subsystem_dependencies():
    graph = {
        "nodes": [
            {"id": "controller", "file": "app/Http/Controllers/OrderController.php"},
            {"id": "model", "file": "app/Models/Order.php"},
        ],
        "links": [{"source": "controller", "target": "model", "confidence": "EXTRACTED"}],
    }
    architecture = derive_architecture(graph, {"subsystems": ["Controllers", "Models"]})
    assert architecture["dependencies"] == [{"source": "controllers", "target": "models", "relations": 1}]
    assert "S0 -->|1| S1" in architecture["diagram"]


def test_report_backfills_project_evidence_for_legacy_index(tmp_path):
    root = _project(tmp_path)
    legacy_graph = {"nodes": [{"id": "file:main.py", "name": "main.py", "kind": "file", "details": "main.py"}],
                    "links": [], "metadata": {"structural_parser": "tree-sitter"}}
    report, _metrics = render_report(root, legacy_graph)
    assert "Acme CRM manages customers" in report
    assert legacy_graph["metadata"]["project_evidence"]["purpose_source"] == "README.md"
