"""Impact packages an agent can answer from without extra reading turns."""
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.source_evidence import attach_source_evidence


def _echo(tmp_path):
    (tmp_path / "context.go").write_text(
        "package echo\n\n"
        "type Context struct {\n\techo *Echo\n}\n\n"
        "func (c *Context) NoContent(code int) error {\n\treturn nil\n}\n\n"
        "func (c *Context) Echo() *Echo {\n\treturn c.echo\n}\n", encoding="utf-8")
    (tmp_path / "router.go").write_text(
        "package echo\n\n"
        "var optionsMethodHandler = func(c *Context) error {\n"
        "\treturn c.NoContent(204)\n"
        "}\n", encoding="utf-8")
    nodes = [
        {"id": "ctx", "name": "Context", "kind": "struct", "file": "context.go", "line": 3, "end_line": 5},
        {"id": "field", "name": "echo", "kind": "field", "container": "Context", "file": "context.go", "line": 4},
        {"id": "nc", "name": "NoContent", "kind": "method", "container": "Context", "file": "context.go",
         "line": 7, "end_line": 9},
        {"id": "echo", "name": "Echo", "kind": "method", "container": "Context", "file": "context.go",
         "line": 11, "end_line": 13},
        {"id": "file:router.go", "name": "router.go", "kind": "file"},
    ]
    links = [{"source": "file:router.go", "target": "nc", "label": "llama", "file": "router.go", "line": 4,
              "resolution": {"caller": ""}}]
    return {"nodes": nodes, "links": links}


def _package(tmp_path, request):
    graph = _echo(tmp_path)
    return attach_source_evidence(tmp_path, query_intent(graph, request, "impact", 10), request, graph=graph)


def test_a_qualified_target_is_the_only_anchor(tmp_path):
    package = _package(tmp_path, "Si cambio Context.NoContent en echo (context.go), ¿qué se rompe?")

    assert {node["name"] for node in package["matched"]} == {"NoContent"}


def test_a_call_given_to_a_file_is_named_after_the_function_value_that_makes_it(tmp_path):
    package = _package(tmp_path, "Si cambio Context.NoContent en echo (context.go), ¿qué se rompe?")
    consumers = package["direct_consumers"]

    rows = [*(consumers.get("others") or []), *(consumers.get("call_lines") or [])]
    assert [row[:2] for row in rows] == [["optionsMethodHandler", "router.go:4"]]
    assert package["answer_checks"][0].startswith("consumers: name each direct consumer (optionsMethodHandler)")


def test_a_document_mention_is_not_a_consumer_to_name(tmp_path):
    from graphtyn.core.impact_context import _answer_checks

    checks = _answer_checks([["README.md", ":"], ["httpAdapter", "lib/http.js:854"]], [], [], [], [])

    assert checks == ["consumers: name each direct consumer (httpAdapter) and what it does with the result, "
                      "from its call line"]
