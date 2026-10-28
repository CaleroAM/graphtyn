"""Candidate ranking for intent retrieval: named features and their weights.

`query_intent` describes every candidate with the features below and ranks
by their weighted sum. The weights started as hand-set constants. Their
current values come from ``tools/learn_ranking_weights.py`` on the 30-task dev
split of ``benchmarks/task_bank_2026-10-28`` (2026-10-28): it switched off
`concept_hits` and `described_owner`, lowered `exact_hits` and `qualified`, and
raised `written_signature`, `named_package`, `lexical_hits` and `callable_kind`.
With the full pipeline they match the hand-set values on dev (55.7 % vs 56.1 %)
and the held-out test2 split (60.8 % vs 59.7 %). Change them only by refitting
and measuring both splits.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

# feature -> weight. Counts are capped where they are computed.
WEIGHTS: dict[str, float] = {
    "operations": 25,            # operations matching intent markers or request terms (≤ 6)
    "operation_request_hits": 300,  # distinctive request terms inside operations (≤ 4)
    "lexical_hits": 20,          # request terms in name, container, file or signature
    "concept_hits": 0,          # intent markers and expansions in the same fields
    "exact_hits": 300,           # name or container equal to a request term
    "qualified": 450,            # matches a qualified symbol written in the request
    "distinctive_hits": 350,     # rare request terms spelled inside the name (≤ 2)
    "tests_intent_file": 100,    # a test file for a tests request
    "primary_path": 50,          # under src/, backend/ or app/
    "test_file": -700,           # a test file outside a tests request
    "benchmark_file": -400,
    "vendored_file": -400,
    "anchor_file": 90,           # declared in the file of a named component
    "named_container": 160,      # its container is a named component
    "described_owner": 0,      # homonym whose owner the request describes
    "written_signature": 1800,    # homonym whose signature the request writes out
    "named_package": 540,        # in a package the request names
    "entry_point": 1200,
    "route_capture": 700,
    "docker_file": 1200,
    "verifier": 700,
    "generator": 900,
    "lexical_route": 180,
    "callable_kind": 30,
    "degree": 1,                 # graph degree (≤ 10)
}

_COLLECTOR: ContextVar[list | None] = ContextVar("ranking_feature_collector", default=None)


def weighted_score(features: dict[str, float], node: dict[str, Any] | None = None) -> int:
    """Ranking score of a candidate; records its features while a collector is active."""
    collector = _COLLECTOR.get()
    if collector is not None and node is not None:
        collector.append((dict(features), node))
    return round(sum(WEIGHTS[name] * value for name, value in features.items() if value))


@contextmanager
def collect_features() -> Iterator[list]:
    """Collect (features, node) for every candidate scored inside the block (for fitting)."""
    collected: list = []
    token = _COLLECTOR.set(collected)
    try:
        yield collected
    finally:
        _COLLECTOR.reset(token)
