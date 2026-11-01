import importlib.util
from pathlib import Path

from graphtyn.core.change_analyst import query_intent
from graphtyn.core.ranking_weights import WEIGHTS, collect_features, weighted_score

_SPEC = importlib.util.spec_from_file_location(
    "learn_ranking_weights", Path(__file__).resolve().parents[1] / "tools" / "learn_ranking_weights.py")
learner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(learner)


def test_score_is_the_weighted_sum_of_named_features():
    assert weighted_score({"exact_hits": 2, "test_file": True, "degree": 0}) == round(
        2 * WEIGHTS["exact_hits"] + WEIGHTS["test_file"])


def test_collector_records_every_scored_candidate_only_inside_its_block():
    graph = {"nodes": [{"id": "a", "name": "performEvictions", "kind": "function", "file": "src/evict.c",
                        "line": 1}], "links": []}
    with collect_features() as collected:
        query_intent(graph, "Explica la evicción en performEvictions", "flow", 5)
    assert collected and collected[0][1]["id"] == "a"
    assert set(collected[0][0]) <= set(WEIGHTS)
    assert weighted_score({"degree": 1}, {"id": "x"}) == WEIGHTS["degree"]  # no collector active: nothing recorded


def test_fitting_accepts_only_steps_that_hurt_no_corpus():
    def task(corpus, good, bad):
        return {"id": corpus, "corpus": corpus, "total": 1, "candidates": [
            ({"exact_hits": good}, frozenset({"fact"}), "good"), ({"lexical_hits": bad}, frozenset(), "bad")]}
    tasks = [task("a", 1, 50), task("b", 1, 50)]
    weights = {name: 0.0 for name in WEIGHTS} | {"exact_hits": 10.0, "lexical_hits": 1.0}

    assert learner.objective(tasks, weights, top=1) == 0.0
    fitted = learner.fit(tasks, weights, top=1, rounds=2)
    assert learner.objective(tasks, fitted, top=1) == 1.0
