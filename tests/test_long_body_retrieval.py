from pathlib import Path

import pytest

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.source_evidence import _focused_excerpt, attach_source_evidence
from graphtyn.mcp_server import _drop_excerpt_middle


def _long_c_function(path: Path) -> Path:
    body = ["int processCommand(client *c) {", "    cmd = lookupCommand(c->argv, c->argc);"]
    body += [f"    filler_{index}(c);" for index in range(150)]
    body += ["    if (ACLCheckAllPerm(c, &err) != ACL_OK) return reject(c);"]
    body += [f"    other_{index}(c);" for index in range(150)]
    body += ["    if (c->flags & CLIENT_MULTI) queueMultiCommand(c);", "    call(c, CMD_CALL_FULL);", "}"]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def test_focused_excerpt_keeps_decisive_lines_of_a_long_body_with_real_numbers(tmp_path):
    source = _long_c_function(tmp_path / "server.c")

    text, start, end = _focused_excerpt(source, 1, 306, 100, ["acl", "multi", "call("], char_budget=2_000)

    assert (start, end) == (1, 306)
    assert "153: if (ACLCheckAllPerm(c, &err) != ACL_OK) return reject(c);" in text
    assert "305: call(c, CMD_CALL_FULL);" in text
    assert "lines omitted" in text
    assert "filler_100" not in text
    assert len(text) <= 2_200


def test_named_camel_case_entry_point_is_required_and_fully_focused(tmp_path):
    _long_c_function(tmp_path / "server.c")
    package = {
        "intent": "flow", "nodes": [], "complete_for": ["flow"], "missing": [], "do_not_expand": False,
        "matched": [{"id": "s:pc", "name": "processCommand", "kind": "function",
                     "file": "server.c", "line": 1, "end_line": 306}],
    }

    result = attach_source_evidence(
        tmp_path, package, "Traza processCommand: ACL, MULTI y dónde se ejecuta el comando", "precision")

    assert result["source_coverage"]["required_symbols"] == {"processcommand": True}
    text = result["source_evidence"][0]["text"]
    assert "ACLCheckAllPerm" in text and "queueMultiCommand" in text and "call(c, CMD_CALL_FULL)" in text


def test_framework_obligation_that_no_node_can_satisfy_is_not_applicable():
    graph = {"nodes": [{"id": "s:pc", "name": "processCommand", "kind": "function", "file": "src/server.c",
                        "line": 1, "end_line": 30, "signature": "int processCommand(client *c)",
                        "operations": [{"kind": "call", "name": "commandCheckArity", "line": 5,
                                        "text": "commandCheckArity(c->cmd, c->argc, &err)"}]}],
             "links": []}

    result = query_intent(graph, "Traza processCommand: validación de aridad y rechazo", "flow", 4)

    assert "validation_gate" in result["not_applicable_obligations"]
    assert "validation_gate" not in result["requested_obligations"]
    assert "validation_gate" not in result["missing"]


def test_flow_guidance_requires_real_file_line_citations():
    graph = {"nodes": [{"id": "s:f", "name": "save", "kind": "method", "file": "app/models/user.rb",
                        "line": 3, "operations": [{"kind": "call", "name": "insert", "line": 4, "text": "insert"}]}],
             "links": []}

    guidance = query_intent(graph, "Traza save", "flow", 4)["guidance"]

    assert "Cite real file:line" in guidance
    assert "Cite aliases" not in guidance


def test_payload_trim_keeps_entry_and_final_lines():
    text = "\n".join(f"{number}: line {number} " + "x" * 40 for number in range(1, 101))

    trimmed = _drop_excerpt_middle(text, 1_500)

    assert trimmed.startswith("1: line 1 ")
    assert trimmed.rstrip().endswith("100: line 100 " + "x" * 40)
    assert "lines omitted" in trimmed
    assert len(trimmed) < len(text) - 1_000


def test_csharp_receiver_type_only_uses_declarations_before_the_call(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "Run.cs").write_text(
        "class Runner {\n"
        "  void Early() { other.Ping(); }\n"
        "  void Late() { Second other = new Second();\n"
        "    other.Ping(); }\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "Second.cs").write_text("class Second { public void Ping() {} }", encoding="utf-8")
    (tmp_path / "Third.cs").write_text("class Third { public void Ping() {} }", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {nodes[link["source"]]["name"]: link for link in graph["links"]
             if link.get("label") == "llama" and nodes.get(link["source"], {}).get("name") in {"Early", "Late"}}
    assert calls["Late"]["resolution"]["receiver_type"] == "Second"
    assert "Early" not in calls or calls["Early"]["resolution"]["receiver_type"] != "Second"


def test_ready_citations_use_real_paths_and_never_displace_evidence(tmp_path):
    from graphtyn.mcp_server import evidence_result
    _long_c_function(tmp_path / "server.c")
    graph = {"nodes": [{"id": "s:pc", "name": "processCommand", "kind": "function", "file": "server.c",
                        "line": 1, "end_line": 306, "signature": "int processCommand(client *c)",
                        "operations": [{"kind": "call", "name": "call", "line": 305, "text": "call(c, CMD_CALL_FULL)"}]}],
             "links": []}
    request = "Traza processCommand: ACL, MULTI y dónde se ejecuta"
    package = attach_source_evidence(tmp_path, query_intent(graph, request, "flow", 4), request, "precision")

    compact = evidence_result(package, max_nodes=4, token_budget=1_200)

    assert compact["citations"][0] == "server.c:1-306 processCommand"
    assert any(item.startswith("server.c:305 processCommand → call") for item in compact["citations"])
    assert compact["payload_tokens"] <= 1_200
    assert not any(alias in " ".join(compact["citations"]) for alias in compact["files"])


def test_query_vocabulary_is_generic():
    from graphtyn.core.change_analyst import _QUERY_EXPANSIONS
    fragments = {fragment for values in _QUERY_EXPANSIONS.values() for fragment in values}
    # Product- or library-specific identifiers overfit benchmark corpora.
    assert not fragments & {"salesinvoice", "salesproposal", "converttoinvoice", "isauctionactive",
                            "timestampsigner", "badsignature", "mark_accessed", "id_poligono"}


def test_rejection_branches_outrank_rare_words_in_comments(tmp_path):
    body = ["int handle(client *c) {"]
    body += [f"    /* note {index}: DELs and trims happen elsewhere */" for index in range(40)]
    body += [f"    step_{index}(c);" for index in range(80)]
    body += ["    if (disk_error()) rejectCommand(c, shared.diskerr);",
             "    if (!replicas_ok()) rejectCommand(c, shared.noreplicaserr);", "}"]
    source = tmp_path / "server.c"
    source.write_text("\n".join(body) + "\n", encoding="utf-8")

    text, _start, _end = _focused_excerpt(source, 1, len(body), 20, ["del", "reject", "err"], char_budget=600)

    assert "shared.diskerr" in text and "shared.noreplicaserr" in text


def test_type_named_in_request_is_required_with_its_full_brace_extent(tmp_path):
    lines = ["template <typename... T> struct fstring {", "  string_view str;"]
    lines += ["  FMT_CONSTEVAL fstring(const char (&s)[N]) : str(s) {", "    check(s);", "  }"]
    lines += [f"  int member_{index};" for index in range(10)]
    lines += ["  fstring(runtime_format_string<> fmt) : str(fmt.str) {}", "};"]
    (tmp_path / "core.h").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "color.h").write_text("void format_to(int) {\n  styled();\n}\n", encoding="utf-8")
    package = {
        "intent": "flow", "complete_for": ["flow"], "missing": [], "do_not_expand": False, "matched": [],
        # The parser closed the struct at its first constructor body (line 5).
        "nodes": [{"id": "s:fs", "name": "fstring", "kind": "struct", "file": "core.h", "line": 1, "end_line": 5},
                  {"id": "s:a", "name": "format_to", "kind": "function", "file": "core.h", "line": 3, "end_line": 5},
                  {"id": "s:b", "name": "format_to", "kind": "function", "file": "color.h", "line": 1, "end_line": 3}],
    }

    result = attach_source_evidence(
        tmp_path, package, "Explica cómo format_string/fstring valida y cómo funciona format_to", "precision")

    assert result["source_coverage"]["required_symbols"] == {"format_to": True, "fstring": True}
    fstring = next(item for item in result["source_evidence"] if item["symbol"] == "fstring")
    assert fstring["end_line"] == len(lines) and "runtime_format_string" in fstring["text"]
    # A homonym in another file is no longer required merely by sharing the name.
    assert sum(item["symbol"] == "format_to" for item in result["source_evidence"]) == 1
