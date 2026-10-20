from graphtyn.core.memory_retrieval_benchmark import run_source_message_benchmark


def test_source_message_benchmark_is_isolated_deterministic_and_bounded():
    result = run_source_message_benchmark(repetitions=2)

    assert result["ok"] is True
    assert result["isolated"] is True
    assert result["external_models"] is False
    assert result["live_store_modified"] is False
    assert result["recall_at_6"] == 1.0
    assert result["evaluation_leak_rate"] == 0.0
    assert result["consumption_guardrail"]["passed"] is True
