"""Measurement tools: citation resolution for judges, paired statistics, resumable runs."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_citation_is_resolved_to_the_symbol_around_it(tmp_path):
    judge = _module("judge_grades")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "class Flask:\n    def handle_user_exception(self, e):\n        handler = self._find(e)\n        return handler\n",
        encoding="utf-8")
    answer = ("Error handlers use it ([src/app.py:3](/runs/x/workspaces/codex_T_r1/src/app.py:3)) "
              "and src/missing.py:9 does not exist.")

    resolved = judge.resolve_citations(answer, tmp_path)

    assert resolved == ["- src/app.py:3 → Flask.handle_user_exception: handler = self._find(e)"]
    prompt = judge._prompt({"request": "q", "rubric": [{"id": "handlers", "any": ["handle_user_exception"]}]},
                           answer, resolved)
    assert "resolved by the harness" in prompt and "handle_user_exception: handler" in prompt
    assert "resolved by the harness" not in judge._prompt({"request": "q", "rubric": []}, answer, [])


def test_paired_statistics_resample_tasks_and_pair_by_repetition():
    stats = _module("paired_stats")

    def row(variant, task, repetition, hits, tokens):
        verdict = {f"f{index}": index < hits for index in range(4)}
        return {"variant": variant, "task": task, "repetition": repetition, "tokens": tokens,
                "consensus": verdict, "gemini": verdict, "gpt": verdict, "literal": verdict}

    rows = [row("main", "A", 1, 2, 100), row("fix", "A", 1, 3, 50),
            row("main", "B", 1, 4, 100), row("fix", "B", 1, 4, 100),
            row("main", "C", 1, 1, 100)]  # C has no pair and is left out

    tasks = stats.per_task(rows, "main", "fix", "consensus")
    summary = stats.summarize(tasks)

    assert [task["task"] for task in tasks] == ["A", "B"]
    assert summary["fact_share_difference"] == 0.125 and summary["tasks_better"] == 1 and summary["tasks_worse"] == 0
    assert summary["fact_share_difference_95ci"] == [0.0, 0.25]
    assert summary["token_ratio"] == 0.707


def test_a_finished_run_is_recognised_for_resuming(tmp_path):
    runner = _module("run_three_client_mcp_comparison")
    (tmp_path / "done").mkdir()
    (tmp_path / "done" / "summary.json").write_text(json.dumps({"session_status": "complete"}), encoding="utf-8")
    (tmp_path / "failed").mkdir()
    (tmp_path / "failed" / "summary.json").write_text(json.dumps({"session_status": "error"}), encoding="utf-8")

    assert runner._complete_run(tmp_path / "done")
    assert not runner._complete_run(tmp_path / "failed") and not runner._complete_run(tmp_path / "absent")
