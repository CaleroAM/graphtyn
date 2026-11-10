"""Named identifiers: prose acronyms are not gaps, text-only names get locations, real gaps stay."""
from graphtyn.core.evidence_sufficiency import _verdict, mark_insufficient_evidence, requested_identifiers


def _graph():
    return {"nodes": [{"id": "file:app/config.py", "name": "config.py", "kind": "file"},
                      {"id": "s:get", "name": "getCommand", "kind": "function", "file": "app/config.py"},
                      {"id": "s:unl", "name": "unlinkCommand", "kind": "function", "file": "app/config.py"}],
            "links": []}


def test_a_prose_acronym_is_not_a_requested_identifier():
    graph = _graph()
    assert requested_identifiers("How does the API handle GET with a JWT?", graph) == ["GET"]
    assert requested_identifiers("How does the API handle GET?") == ["API", "GET"]


def test_text_only_identifiers_get_locations_and_absent_ones_are_reported(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "config.py").write_text("MAX_RETRY_COUNT = 3\ndef getCommand():\n    return MAX_RETRY_COUNT\n",
                                                encoding="utf-8")
    package = {"do_not_expand": True, "entities": {"N1": {"name": "getCommand"}}, "missing": [], "complete_for": ["flow"]}
    request = "Where is MAX_RETRY_COUNT read, and what does UNLINK do with missing_config_flag?"

    claimed_gap = mark_insufficient_evidence(package, request, graph=_graph(), root=tmp_path)

    lookup = package["identifier_lookup"]
    assert lookup["identifier_hits"]["MAX_RETRY_COUNT"][0] == ["app/config.py:1", "MAX_RETRY_COUNT = 3"]
    assert lookup["absent_identifiers"] == ["missing_config_flag"]
    # UNLINK names unlinkCommand, a symbol the package did not select: that stays a real gap.
    assert claimed_gap and package["evidence_sufficiency"]["unmatched_identifiers"] == ["UNLINK"]
    assert package["do_not_expand"] is False


def test_without_a_graph_the_check_is_unchanged():
    verdict = _verdict({"entities": {}}, "What does BLPOP do?")
    assert verdict["unmatched_identifiers"] == ["BLPOP"]
