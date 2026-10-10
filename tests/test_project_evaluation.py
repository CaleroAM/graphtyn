from graphtyn.core.project_evaluation import evaluate_project


def test_real_project_evaluation_requires_evidence_provenance_and_abstention(tmp_path):
    (tmp_path / "service.py").write_text(
        "def collect():\n    return 1\n", encoding="utf-8"
    )
    result = evaluate_project(tmp_path, cases=[
        {"id": "positive", "query": "collect local evidence", "expected_key": "collect",
         "title": "Collect evidence", "content": "collect local evidence", "files": ["service.py"],
         "node": "collect", "node_id": "symbol:service.py:collect"},
        {"id": "negative", "query": "orbital quantum protocol", "expected_key": None,
         "title": "No evidence", "content": "never returned", "files": []},
    ])

    assert result["ok"] is True
    positive, negative = result["cases"]
    assert positive["hit"] is True
    assert positive["provenance_ok"] is True
    assert negative["reason"] == "abstained"
    assert result["errors"] == []


def test_real_project_evaluation_registers_missing_provenance_as_regression(tmp_path):
    (tmp_path / "service.py").write_text("def collect():\n    return 1\n", encoding="utf-8")
    result = evaluate_project(tmp_path, cases=[
        {"id": "stale-source", "query": "collect local evidence", "expected_key": "collect",
         "title": "Collect evidence", "content": "collect local evidence",
         "files": ["deleted_after_capture.py"], "node": None},
    ])

    assert result["ok"] is False
    assert result["errors"] == [{
        "case": "stale-source", "reason": "provenance_unresolved",
        "query": "collect local evidence", "returned_keys": ["collect"],
        "provenance_errors": ["missing_file:deleted_after_capture.py"],
    }]
