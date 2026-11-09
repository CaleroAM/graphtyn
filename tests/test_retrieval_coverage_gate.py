import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_retrieval_coverage", Path(__file__).resolve().parents[1] / "tools" / "check_retrieval_coverage.py")
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def _row(covered, total=8, complete=False):
    return {"covered": covered, "total": total, "do_not_expand": complete}


def test_gate_accepts_equal_or_better_coverage():
    baseline = {"A": _row(4), "B": _row(6, complete=True)}
    assert gate.compare({"A": _row(5), "B": _row(6, complete=True)}, baseline) == []


def test_gate_flags_a_task_losing_two_facts_and_a_mean_drop():
    failures = gate.compare({"A": _row(2), "B": _row(6)}, {"A": _row(4), "B": _row(6)})

    assert any(failure.startswith("mean coverage") for failure in failures)
    assert any(failure.startswith("A:") for failure in failures)


def test_gate_flags_a_new_false_completion_only():
    assert gate.compare({"A": _row(3, complete=True)}, {"A": _row(3, complete=True)}) == []
    failures = gate.compare({"A": _row(3, complete=True)}, {"A": _row(3)})
    assert failures == ["A: claims completeness with 3/8"]


def test_every_gated_corpus_has_tasks_in_the_bank():
    assert all(gate._tasks(corpus) for corpus in gate.CORPORA if corpus not in gate.GRAPH_ONLY)
    # Corpora kept only for their graph floor have no tasks.
    assert gate.GRAPH_ONLY <= set(gate.CORPORA) and not any(gate._tasks(corpus) for corpus in gate.GRAPH_ONLY)


def test_a_graph_that_loses_extracted_calls_fails_the_gate():
    baseline = {"gson": {"extracted_calls": 5758, "inheritance": 387, "typed_fields": 0}}
    assert gate.compare_graphs({"gson": {"extracted_calls": 5600, "inheritance": 387, "typed_fields": 0}}, baseline) == []
    assert gate.compare_graphs({"gson": {"extracted_calls": 350, "inheritance": 387, "typed_fields": 0}}, baseline) == [
        "gson: extracted_calls 350 (baseline 5758)"]


def test_checkout_refuses_a_non_git_directory(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    try:
        gate._checkout("https://example.invalid/repo", "0" * 40, tmp_path)
    except SystemExit as error:
        assert "not a git checkout" in str(error)
    else:
        raise AssertionError("expected a refusal")
    assert not (tmp_path / ".git").exists()
