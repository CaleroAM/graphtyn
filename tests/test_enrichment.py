import json
import subprocess
from pathlib import Path

import pytest

from aether_graph.core.ast_parser import ASTParser
from aether_graph.api import main as api_main


def test_clean_answer_strips_prefixes_and_quotes():
    cases = {
        "La función bfs_path en aether_graph/cli.py realiza un recorrido": "Realiza un recorrido",
        '"Permite encontrar la ruta más corta"': "Permite encontrar la ruta más corta",
        "Este archivo Python define un parser": "Define un parser",
        "La clase HistoryTracker se encarga de gestionar el historial": "Se encarga de gestionar el historial",
    }
    for raw, expected in cases.items():
        assert api_main._clean_answer(raw) == expected


def test_role_hint_and_fix_detects_cli_and_fastapi():
    hints, fix = api_main._role_hint_and_fix("import argparse\nparser.add_parser('init')", "Resumen genérico")
    assert "CLI" in hints
    assert fix == "CLI que "
    hints2, fix2 = api_main._role_hint_and_fix("from fastapi import FastAPI\n@app.get('/')", "Resumen genérico")
    assert "FastAPI" in hints2
    assert fix2 == "API FastAPI que "
    hints3, fix3 = api_main._role_hint_and_fix("from fastapi import FastAPI", "Servidor web con FastAPI")
    assert fix3 == ""


def test_maybe_compact_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("AETHER_COMPACT", "1")
    long_ans = "Una descripcion exageradamente larga " * 10
    monkeypatch.setattr(api_main, "_llm_ask", lambda *a, **k: None)
    result = api_main._maybe_compact("host", "model", long_ans)
    assert len(result) <= 140
    short = "Descripcion corta"
    assert api_main._maybe_compact("host", "model", short) == short


def test_extract_symbol_source_csharp_method(tmp_path):
    cs = tmp_path / "Game.cs"
    cs.write_text(
        "public class Game\n{\n"
        "    public int RollDice(GameState state)\n    {\n"
        "        return state.Rng.Next(1, 7);\n    }\n}\n",
        encoding="utf-8",
    )
    snippet = api_main._extract_symbol_source(tmp_path, "Game.cs", "RollDice", kind="method")
    assert "RollDice" in snippet
    assert "return state.Rng.Next" in snippet


def test_extract_symbol_source_skips_keywords(tmp_path):
    cs = tmp_path / "Loop.cs"
    cs.write_text("public class Loop\n{\n    public void Run() { for (int i=0;i<3;i++) {} }\n}\n", encoding="utf-8")
    assert api_main._extract_symbol_source(tmp_path, "Loop.cs", "for", kind="method") == ""


def test_scan_directory_adds_confidence(tmp_path):
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import helper\n\nprint(helper())\n", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path)
    assert graph["links"], "esperaba links"
    for link in graph["links"]:
        assert "confidence" in link
        assert link["confidence"] in ("EXTRACTED", "INFERRED")
    labels = {l["label"] for l in graph["links"]}
    if "usa" in labels:
        assert any(l["confidence"] == "INFERRED" for l in graph["links"])


def test_scan_directory_drops_keyword_symbols(tmp_path):
    (tmp_path / "x.cs").write_text(
        "public class X { public void Run() { for (int i=0;i<3;i++) {} } }\n", encoding="utf-8"
    )
    graph = ASTParser().scan_directory(tmp_path)
    assert not any(n.get("name", "").lower() == "for" for n in graph["nodes"])


def test_detect_changed_files_in_git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    changed = api_main._detect_changed_files(tmp_path)
    assert changed == set()
    f.write_text("x = 2\n", encoding="utf-8")
    changed = api_main._detect_changed_files(tmp_path)
    assert "a.py" in changed
    new_file = tmp_path / "b.py"
    new_file.write_text("y = 1\n", encoding="utf-8")
    changed = api_main._detect_changed_files(tmp_path)
    assert "b.py" in changed


def _fake_index_data():
    return {
        "metadata": {"ai_summary": "Proyecto de prueba con dos subsistemas", "path": "/tmp/demo"},
        "nodes": [
            {"id": "file:src/core/engine.py", "name": "engine.py", "kind": "file", "degree": 5, "details": "Motor del sistema (src/core/engine.py)"},
            {"id": "file:src/core/utils.py", "name": "utils.py", "kind": "file", "degree": 2, "details": "Utilidades (src/core/utils.py)"},
            {"id": "file:docs/readme.md", "name": "readme.md", "kind": "file", "degree": 1, "details": "Docs (docs/readme.md)"},
            {"id": "symbol:src/core/engine.py:Engine", "name": "Engine", "kind": "class", "degree": 4, "details": "Clase Engine"},
        ],
        "links": [
            {"source": "file:src/core/engine.py", "target": "symbol:src/core/engine.py:Engine", "label": "contiene", "confidence": "EXTRACTED"},
            {"source": "file:src/core/utils.py", "target": "file:src/core/engine.py", "label": "usa", "confidence": "INFERRED"},
        ],
    }


def test_generate_semantic_graph_communities_and_god_nodes():
    graph = api_main.generate_semantic_graph(_fake_index_data())
    nodes = {n["id"]: n for n in graph["nodes"]}
    kinds = [n.get("kind") for n in graph["nodes"]]
    assert "community" in kinds
    assert "semantic_concept" in kinds
    assert not any(n.get("name", "").startswith("Concepto:") for n in graph["nodes"])
    comms = [n for n in graph["nodes"] if n.get("kind") == "community"]
    assert any("src/core" in c["name"] for c in comms)
    gods = [n["name"] for n in graph["nodes"] if n.get("god")]
    assert gods, "esperaba god nodes"
    labels = {l["label"] for l in graph["links"]}
    assert "pertenece" in labels and "agrupa" in labels


def test_scan_directory_respects_git_tracked(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("def noise():\n    return 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    graph_respect = ASTParser().scan_directory(tmp_path, respect_git=True)
    ids = {n["id"] for n in graph_respect["nodes"]}
    assert "file:tracked.py" in ids
    assert "file:ignored.py" not in ids

    graph_all = ASTParser().scan_directory(tmp_path, respect_git=False)
    ids_all = {n["id"] for n in graph_all["nodes"]}
    assert "file:ignored.py" in ids_all


def test_project_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / ".aether-store")
    assert api_main._load_project_config(tmp_path) == {}
    cfg = api_main._save_project_config(tmp_path, {"respect_git": False})
    assert cfg["respect_git"] is False
    assert api_main._load_project_config(tmp_path)["respect_git"] is False


def test_blast_radius_traversal():
    from aether_graph.mcp_server import blast_radius

    graph = {
        "nodes": [
            {"id": "symbol:a.py:Foo", "name": "Foo", "kind": "class"},
            {"id": "file:b.py", "name": "b.py", "kind": "file"},
            {"id": "symbol:b.py:Bar", "name": "Bar", "kind": "function"},
            {"id": "file:c.py", "name": "c.py", "kind": "file"},
        ],
        "links": [
            {"source": "file:b.py", "target": "symbol:a.py:Foo", "label": "usa", "confidence": "INFERRED"},
            {"source": "file:b.py", "target": "symbol:b.py:Bar", "label": "contiene", "confidence": "EXTRACTED"},
            {"source": "file:c.py", "target": "symbol:b.py:Bar", "label": "usa", "confidence": "INFERRED"},
        ],
    }
    result = blast_radius(graph, "Foo", depth=1)
    assert len(result["matched"]) == 1
    impacted = {i["node"]["id"]: i for i in result["impacted"]}
    assert "file:b.py" in impacted
    assert impacted["file:b.py"]["confidence"] == "INFERRED"
    assert impacted["file:b.py"]["hop"] == 1

    result2 = blast_radius(graph, "Foo", depth=2)
    ids2 = {i["node"]["id"] for i in result2["impacted"]}
    assert "symbol:b.py:Bar" in ids2
    assert "file:c.py" not in ids2  # está a hop 3

    result3 = blast_radius(graph, "Foo", depth=3)
    ids3 = {i["node"]["id"] for i in result3["impacted"]}
    assert "file:c.py" in ids3
