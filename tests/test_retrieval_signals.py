import copy

from graphtyn.core import prompt_context
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.evidence_sufficiency import mark_thin_evidence, request_parts
from graphtyn.core.retrieval_signals import NameFrequency, cap_homonyms, flow_markers, with_call_chain
from graphtyn.core.vocabulary import translated_terms
from graphtyn.mcp_server import lean_payload


def _function(node_id, name, file="src/evict.c", **extra):
    return {"id": node_id, "name": name, "kind": "function", "file": file, "line": 1, **extra}


def test_spanish_programming_words_translate_to_identifier_fragments():
    terms = translated_terms("Explica cómo Redis libera memoria con la evicción y el búfer de salida")

    assert {"evict", "memory", "free", "buffer", "output"} <= set(terms)
    # Stems must not fire on unrelated words (`red` would match `Redis`).
    assert "network" not in terms


def test_name_frequency_separates_distinctive_from_pervasive_terms():
    nodes = [_function(f"f{index}", f"format_{index}") for index in range(200)]
    nodes += [_function("e1", "performEvictions"), _function("e2", "evictionPoolPopulate")]
    frequency = NameFrequency(nodes, ["evict", "format", "forma"], generic=set())

    assert frequency.distinctive == ["evict"]
    assert frequency.pervasive("format")
    assert "forma" not in frequency.counts  # a Spanish word spelled inside `format`
    assert frequency.hits("performEvictions") == 1
    assert frequency.hits("evict") == 0  # exact equality is scored elsewhere


def test_flow_markers_keep_only_operations_the_request_names():
    assert flow_markers(("save", "send", "publish"), "traza cómo se publish y se guarda") == ("publish",)


def test_homonym_cap_keeps_two_per_name_and_every_mandatory_candidate():
    ranked = [(10 - index, _function(f"n{index}", "format")) for index in range(4)]
    ranked.append((1, _function("w", "write_float")))

    capped = cap_homonyms(ranked, keep={"n3"})

    assert [node["id"] for _, node in capped] == ["n0", "n1", "n3", "w"]


def test_call_chain_places_distinctive_callees_after_the_seed_and_mandatory_items():
    graph = {
        "nodes": [_function("a", "format_to_n"), _function("b", "vformat_to_n"),
                  _function("log", "serverLog"), _function("m", "parse_args"), _function("z", "other")],
        "links": [{"source": "a", "target": "b", "label": "llama", "confidence": "EXTRACTED"},
                  {"source": "a", "target": "log", "label": "llama", "confidence": "EXTRACTED"}],
    }
    frequency = NameFrequency(graph["nodes"], ["format_to_n"], generic=set())
    ranked = [(30, graph["nodes"][0]), (20, graph["nodes"][3]), (10, graph["nodes"][4])]

    chained = with_call_chain(graph, ranked, frequency, keep_first={"m"})

    # The unrelated helper call is not a stage of the flow.
    assert [node["id"] for _, node in chained] == ["a", "m", "b", "z"]


def test_a_struct_field_named_in_a_flow_request_does_not_anchor_the_package():
    graph = {"nodes": [
        {"id": "field", "name": "lru", "kind": "field", "file": "src/object.h", "line": 3, "container": "robj"},
        {"id": "other", "name": "avg_ttl", "kind": "field", "file": "src/object.h", "line": 4},
        _function("perform", "performEvictions", operations=[{"name": "call", "text": "evictionPoolPopulate(db)", "line": 2}]),
        _function("pool", "evictionPoolPopulate"),
    ], "links": []}

    result = query_intent(graph, "Explica cómo Redis ejecuta la evicción con la política lru", "flow", 10)

    names = [node["name"] for node in result["nodes"]]
    assert names[0] == "performEvictions" and "evictionPoolPopulate" in names
    # The field's header is not reserved as an anchor file, so its siblings stay out.
    assert "avg_ttl" not in names


def _thin_package():
    return {"do_not_expand": True, "missing": [], "complete_for": ["flow"], "guidance": "Answer now.",
            "stopping": {"sufficient_evidence": True}, "files": {"F1": "src/a.c"},
            "entities": {"N1": {"name": "f", "kind": "function", "at": "F1:1"}}, "relations": []}


def test_request_parts_ignore_the_closing_citation_instruction():
    parts = request_parts("Explica X: desde dónde se invoca, cómo calcula el tamaño, qué ocurre si falla. "
                          "Cita archivo:línea.")

    assert parts == ["Explica X", "desde dónde se invoca", "cómo calcula el tamaño", "qué ocurre si falla."]


def test_thin_evidence_for_a_multi_part_request_withdraws_completeness():
    request = "Explica el flujo: la entrada, el cálculo del tamaño, la política, la elección, el borrado."
    result, mirror = _thin_package(), _thin_package()

    assert mark_thin_evidence(result, request, mirror=mirror)

    assert result["do_not_expand"] is False and result["complete_for"] == []
    assert result["missing"] == ["request_parts"]
    assert result["evidence_sufficiency"]["request_parts"] == 6
    assert "look up only the parts it does not address" in result["guidance"]
    assert mirror["do_not_expand"] is False and mirror["missing"] == ["request_parts"]


def test_thin_evidence_leaves_narrow_requests_and_open_packages_alone():
    narrow = _thin_package()
    assert not mark_thin_evidence(narrow, "Traza processCommand.")
    assert narrow["do_not_expand"] is True

    open_package = {**_thin_package(), "do_not_expand": False, "missing": ["x"]}
    before = copy.deepcopy(open_package)
    assert not mark_thin_evidence(open_package, "Uno, dos, tres partes, cuatro partes, cinco partes.")
    assert open_package == before


def test_hook_header_for_thin_evidence_asks_for_targeted_lookups_only():
    package = {**_thin_package(), "do_not_expand": False, "missing": ["request_parts"], "context_id": "c"}

    text = prompt_context.render_context(lean_payload(package))

    assert "thin for a request with several parts" in text
    assert "look up only the parts it does not address" in text
    assert "No further graph query is needed" not in text
