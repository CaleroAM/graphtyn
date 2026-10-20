from graphtyn.core.benchmark import syntactically_complete_answer
import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "run_opencode_mcp_comparison.py"
_SPEC = importlib.util.spec_from_file_location("run_opencode_mcp_comparison", _SCRIPT)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MODULE)


def test_completion_detector_flags_short_mid_section_answer():
    assert not syntactically_complete_answer("## Verificación\nLa firma usa TimestampSigner y después")
    assert syntactically_complete_answer("Respuesta breve pero completa.")
    assert syntactically_complete_answer("x" * 500)


def test_step_finish_usage_is_summed_when_events_are_per_step():
    events = [
        {"type": "step_finish", "part": {"tokens": {"input": 10, "output": 2, "reasoning": 1,
                                                         "total": 13, "cache": {"read": 4, "write": 0}},
                                           "cost": 0.01}},
        {"type": "step_finish", "part": {"tokens": {"input": 7, "output": 3, "reasoning": 2,
                                                         "total": 12, "cache": {"read": 1, "write": 2}},
                                           "cost": 0.02}},
    ]

    usage, raw = _MODULE.aggregate_step_usage(events, "per-step")

    assert len(raw) == 2
    assert usage == {"input_tokens": 17, "cached_input_tokens": 5,
                     "cache_write_input_tokens": 2, "output_tokens": 5,
                     "thinking_tokens": 3, "total_tokens": 25, "cost": 0.03}


def test_step_finish_usage_uses_last_event_when_declared_cumulative():
    events = [
        {"type": "step_finish", "part": {"tokens": {"input": 10, "total": 12}}},
        {"type": "step_finish", "part": {"tokens": {"input": 30, "total": 36}}},
    ]

    usage, _ = _MODULE.aggregate_step_usage(events, "cumulative")

    assert usage["input_tokens"] == 30
    assert usage["total_tokens"] == 36
