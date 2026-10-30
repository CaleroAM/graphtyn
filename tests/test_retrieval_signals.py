import copy

from graphtyn.core import prompt_context
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.change_analyst import classify_intent
from graphtyn.core.evidence_sufficiency import mark_insufficient_evidence, named_identifiers, request_parts
from graphtyn.core import retrieval_signals
from graphtyn.core.retrieval_signals import (NameFrequency, call_outline, cap_homonyms, command_handlers, flow_markers,
                                            with_call_chain)
from graphtyn.core.vocabulary import is_prose_word, translated_terms
from graphtyn.mcp_server import evidence_result, lean_payload


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
                  _function("log", "serverLog", file="src/server.c"), _function("m", "parse_args"),
                  _function("z", "other")],
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

    assert mark_insufficient_evidence(result, request, mirror=mirror)

    assert result["do_not_expand"] is False and result["complete_for"] == []
    assert result["missing"] == ["request_parts"]
    assert result["evidence_sufficiency"]["request_parts"] == 6
    assert "look up only what it does not address" in result["guidance"]
    assert mirror["do_not_expand"] is False and mirror["missing"] == ["request_parts"]


def test_thin_evidence_leaves_narrow_requests_and_open_packages_alone():
    narrow = _thin_package()
    assert not mark_insufficient_evidence(narrow, "Traza la función f.")
    assert narrow["do_not_expand"] is True

    open_package = {**_thin_package(), "do_not_expand": False, "missing": ["x"]}
    before = copy.deepcopy(open_package)
    assert not mark_insufficient_evidence(open_package, "Uno, dos, tres partes, cuatro partes, cinco partes.")
    assert open_package == before


def test_hook_header_for_thin_evidence_asks_for_targeted_lookups_only():
    package = {**_thin_package(), "do_not_expand": False, "missing": ["request_parts"], "context_id": "c"}

    text = prompt_context.render_context(lean_payload(package))

    assert "does not cover the whole request" in text
    assert "look up only what it does not address" in text
    assert "No further graph query is needed" not in text


def test_call_chain_follows_sibling_methods_of_the_entry_point_across_hops():
    def method(node_id, name, container="Persistence", file="lib/persistence.rb"):
        return {"id": node_id, "name": name, "kind": "method", "file": file, "container": container, "line": 1}
    nodes = [method("u", "update"), method("s", "save"), method("c", "create_or_update"),
             method("r", "_update_record"), method("t", "with_transaction", "Transactions", "lib/transactions.rb"),
             method("x", "unrelated")]
    calls = [("u", "s"), ("u", "t"), ("s", "c"), ("c", "r")]
    graph = {"nodes": nodes, "links": [{"source": a, "target": b, "label": "llama", "confidence": "EXTRACTED"}
                                       for a, b in calls]}
    frequency = NameFrequency(nodes, [], generic=set())

    chained = with_call_chain(graph, [(50, nodes[0]), (10, nodes[5])], frequency, keep_first=set())

    # The entry point's own class first, nearest stage first; a wrapper from
    # another owner is not a stage unless it spells a request term.
    assert [node["id"] for _, node in chained] == ["u", "s", "c", "r", "x"]


def test_registering_keys_or_names_is_not_a_bindings_request():
    assert classify_intent("Explica cómo WATCH registra claves y cómo EXEC aborta la transacción") == "flow"
    assert classify_intent("¿Dónde se registra el servicio de pagos en el contenedor de dependencias?") == "bindings"


def test_spanish_prose_words_are_not_matched_but_shared_english_stems_are():
    assert is_prose_word("transacción") and is_prose_word("registro")
    assert not is_prose_word("validates") and not is_prose_word("update")


def test_the_homonym_whose_signature_or_owner_the_request_describes_ranks_first():
    graph = {"nodes": [
        {"id": "rel", "name": "update", "kind": "method", "file": "lib/relation.rb", "container": "Relation",
         "signature": "def update(id = :all, attributes)", "line": 1,
         "operations": [{"name": "call", "text": "records.each { |r| r.update(attributes) }", "line": 2}]},
        {"id": "per", "name": "update", "kind": "method", "file": "lib/persistence.rb", "container": "Persistence",
         "signature": "def update(attributes)", "line": 1},
    ], "links": []}

    result = query_intent(graph, "Traza update(attributes) sobre un registro persistido", "flow", 10)

    assert result["nodes"][0]["id"] == "per"


def test_identifiers_named_by_the_request_must_appear_in_complete_evidence():
    request = "Explica cómo BLPOP bloquea al cliente y cómo LPUSH lo despierta."
    assert named_identifiers(request) == ["BLPOP", "LPUSH"]
    package = {**_thin_package(), "entities": {"N1": {"name": "lpushCommand", "kind": "function", "at": "F1:1"}}}

    assert mark_insufficient_evidence(package, request)

    assert package["missing"] == ["named_identifiers"]
    assert package["evidence_sufficiency"] == {"unmatched_identifiers": ["BLPOP"]}


def test_call_chain_follows_ruby_dispatch_across_module_files():
    def method(node_id, name, container, file):
        return {"id": node_id, "name": name, "kind": "method", "file": file, "container": container, "line": 1}
    nodes = [method("u", "update", "Persistence", "persistence.rb"), method("s", "save", "Validations", "validations.rb"),
             method("x", "unrelated", "Other", "other.rb")]
    graph = {"nodes": nodes, "links": [{"source": "u", "target": "s", "label": "llama", "confidence": "INFERRED",
                                        "resolution": {"strategy": "ruby-ancestors"}}]}

    chained = with_call_chain(graph, [(50, nodes[0]), (10, nodes[2])], NameFrequency(nodes, [], set()), set())

    assert [node["id"] for _, node in chained] == ["u", "s", "x"]


def test_selection_trace_records_every_stage_and_named_symbols_follow_the_request():
    from graphtyn.core.ranking_weights import trace_selection
    graph = {"nodes": [_function("s", "save"), _function("u", "update")], "links": []}

    with trace_selection() as trace:
        query_intent(graph, "Traza update y luego save", "flow", 10)

    assert {"scored", "homonyms", "anchors", "chain", "selected"} <= set(trace)
    # Named symbols lead in the order the request names them, not alphabetically.
    assert [node["id"] for node in trace["homonyms"][:2]] == ["u", "s"]


def _c_flow():
    """lua_pcallk → luaD_pcall → luaD_rawrunprotected → f_call, with a utility called from everywhere."""
    nodes = [_function("api", "lua_pcallk", "lapi.c"), _function("pcall", "luaD_pcall", "ldo.c"),
             _function("raw", "luaD_rawrunprotected", "ldo.c"), _function("fcall", "f_call", "lapi.c"),
             _function("err", "luaG_runerror", "ldebug.c"), _function("m1", "lua_settop", "lapi.c"),
             _function("m2", "lua_gettop", "lapi.c")]
    calls = [("api", "pcall"), ("api", "err"), ("pcall", "raw"), ("raw", "fcall")]
    calls += [(f"u{index}", "err") for index in range(retrieval_signals.UTILITY_FAN_IN + 1)]
    links = [{"source": a, "target": b, "label": "llama", "confidence": "EXTRACTED", "line": 1} for a, b in calls]
    return {"nodes": nodes, "links": links}


def test_a_reserved_chain_takes_unnamed_callees_ahead_of_overflowing_representatives(monkeypatch):
    monkeypatch.setattr(retrieval_signals, "CHAIN_SEEDS", 1)
    graph = _c_flow()
    nodes = {node["id"]: node for node in graph["nodes"]}
    frequency = NameFrequency(graph["nodes"], [], generic=set())
    ranked = [(50, nodes["api"]), (40, nodes["m1"]), (30, nodes["m2"])]

    legacy = with_call_chain(graph, ranked, frequency, keep_first={"m1", "m2"})
    reserved = with_call_chain(graph, ranked, frequency, keep_first={"m1", "m2"}, reserved=2, budget=3)

    # Without a reservation a callee needs a request term; with one, the
    # entry point's stages come before representatives beyond the budget, and
    # the utility called from everywhere is never a stage.
    assert [node["id"] for _, node in legacy] == ["api", "m1", "m2"]
    # Same-file stages first (C has no class), then the nearest.
    assert [node["id"] for _, node in reserved] == ["api", "fcall", "pcall", "m1", "m2"]


def test_call_outline_lists_deeper_stages_by_location_only():
    graph = _c_flow()
    frequency = NameFrequency(graph["nodes"], [], generic=set())
    selected = [graph["nodes"][0], graph["nodes"][1]]

    outline = call_outline(graph, selected, frequency, limit=5)

    assert [(item["caller"], item["callee"]) for item in outline] == [
        ("luaD_pcall", "luaD_rawrunprotected"), ("luaD_rawrunprotected", "f_call")]
    assert outline[0]["file"] == "ldo.c"


def test_call_outline_is_rendered_with_file_aliases_and_kept_by_the_lean_package():
    package = {"intent": "flow", "nodes": [_function("api", "lua_pcallk", "lapi.c")],
               "call_outline": [{"caller": "lua_pcallk", "callee": "luaD_pcall", "file": "ldo.c", "line": 1083,
                                 "confidence": "EXTRACTED"}]}

    lean = lean_payload(evidence_result(package))

    assert lean["call_outline"] == [["lua_pcallk", "luaD_pcall", "F2:1083", "E"]]
    assert lean["files"]["F2"] == "ldo.c"


def test_commands_written_in_capitals_name_their_handlers():
    nodes = [_function("b", "blpopCommand"), _function("t", "ttlCommand"), _function("g", "cmd_get"),
             _function("x", "lruCommandHelper")]

    handlers = command_handlers("Explica BLPOP y GET; la política LRU usa el TTL", nodes, set())

    assert handlers == {"blpopcommand", "ttlcommand", "cmd_get"}


def test_a_command_handler_joins_the_package_without_pinning_it_to_its_file(monkeypatch):
    monkeypatch.setattr(retrieval_signals, "COMMAND_NAMES", True)
    graph = {"nodes": [
        _function("ttl", "ttlCommand", "src/expire.c"),
        _function("evict", "performEvictions", "src/evict.c",
                  operations=[{"name": "call", "text": "evictionPoolPopulate(db)", "line": 2}]),
        _function("pool", "evictionPoolPopulate", "src/evict.c"),
    ], "links": []}

    result = query_intent(graph, "Explica cómo Redis ejecuta la evicción con LRU y TTL", "flow", 10)

    names = [node["name"] for node in result["nodes"]]
    assert "ttlCommand" in names and "performEvictions" in names
