"""Production consumers lead an impact package; tests are counted apart; textual leads are not proof."""
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.impact_context import _set_tests_apart
from graphtyn.core.source_evidence import attach_source_evidence

_TESTS = 50


def _project(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "lib" / "app.js").write_text(
        "class Application {\n"
        "  handleRequest (ctx, fnMiddleware) {\n"
        "    const onerror = (err) => ctx.onerror(err)\n"
        "    const handleResponse = () => respond(ctx)\n"
        "    return fnMiddleware(ctx).then(handleResponse).catch(onerror)\n"
        "  }\n"
        "}\n"
        "/**\n"
        "  ctx.onerror(err) is documented here\n"
        " */\n"
        "function respond (ctx) {\n"
        "  stream(ctx, err => { if (err) ctx.onerror(err) })\n"
        "}\n"
        "const HANDLERS = ['onerror', 'onload']\n", encoding="utf-8")
    (tmp_path / "lib" / "context.js").write_text(
        "module.exports = {\n  onerror (err) {\n    return err\n  }\n}\n", encoding="utf-8")
    (tmp_path / "tests" / "context.test.js").write_text(
        "".join(f"function case{n} () {{\n  ctx.onerror(new Error('e{n}'))\n}}\n" for n in range(_TESTS)), encoding="utf-8")
    nodes = [
        {"id": "app", "name": "Application", "kind": "class", "file": "lib/app.js", "line": 1, "end_line": 7},
        {"id": "hr", "name": "handleRequest", "kind": "method", "container": "Application", "file": "lib/app.js",
         "line": 2, "end_line": 6},
        {"id": "local", "name": "onerror", "kind": "function", "container": "Application", "file": "lib/app.js",
         "line": 3, "end_line": 3},
        {"id": "hres", "name": "handleResponse", "kind": "function", "container": "Application", "file": "lib/app.js",
         "line": 4, "end_line": 4},
        {"id": "respond", "name": "respond", "kind": "function", "file": "lib/app.js", "line": 11, "end_line": 13},
        {"id": "target", "name": "onerror", "kind": "method", "file": "lib/context.js", "line": 2, "end_line": 4},
        *({"id": f"t{n}", "name": f"case{n}", "kind": "function", "file": "tests/context.test.js",
           "line": 3 * n + 1, "end_line": 3 * n + 3} for n in range(_TESTS)),
    ]
    links = [{"source": "app", "target": "local", "label": "contiene", "file": "lib/app.js", "line": 3}]
    return {"nodes": nodes, "links": links}


def _package(tmp_path, request):
    graph = _project(tmp_path)
    return attach_source_evidence(tmp_path, query_intent(graph, request, "impact", 10), request, graph=graph)


def test_production_uses_lead_and_test_uses_are_counted_per_file(tmp_path):
    package = _package(tmp_path, "Si cambio ctx.onerror en lib/context.js, ¿qué se rompe?")
    consumers = package["direct_consumers"]

    # The innermost enclosing symbol owns a use: not the one-line arrow declared just above it.
    assert [row[:2] for row in consumers["text_references"]] == [
        ["handleRequest", "lib/app.js:3"], ["respond", "lib/app.js:12"]]
    listed = [row[1] for key in ("others", "text_references", "call_lines") for row in consumers.get(key) or []]
    assert not any(place.startswith("tests/") for place in listed)
    assert consumers["test_consumers"] == {"total": _TESTS, "by_file": {"tests/context.test.js": _TESTS}}
    assert package["answer_checks"][0].startswith("consumers: name each direct consumer (handleRequest, respond)")


def test_a_package_resting_on_textual_uses_is_not_complete(tmp_path):
    package = _package(tmp_path, "Si cambio ctx.onerror en lib/context.js, ¿qué se rompe?")

    assert "verify_text_references" in package["missing"]
    assert package["do_not_expand"] is False and package["complete_for"] == []


def test_a_request_about_tests_keeps_the_test_uses_listed(tmp_path):
    package = _package(tmp_path, "Si cambio ctx.onerror en lib/context.js, ¿qué tests se rompen?")
    consumers = package["direct_consumers"]

    assert "test_consumers" not in consumers
    assert any(row[1].startswith("tests/") for row in consumers["text_references"])


def test_package_paths_imports_and_comments_are_not_uses(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Element.java").write_text(
        "package org.example.select;\n"
        "class Element {\n"
        "  Elements select(String query) {\n"
        "    return null;\n"
        "  }\n"
        "}\n", encoding="utf-8")
    (tmp_path / "src" / "Util.java").write_text(
        "import org.example.select.Elements;\n"
        "class Util {\n"
        "  /**\n"
        "   <code>doc.select(\"p\")</code>\n"
        "  */\n"
        "  static final String[] TAGS = {\"select\", \"input\"};\n"
        "  Elements meta(Element doc) {\n"
        "    return doc.select(\"meta\");\n"
        "  }\n"
        "}\n", encoding="utf-8")
    graph = {"nodes": [
        {"id": "e", "name": "Element", "kind": "class", "file": "src/Element.java", "line": 2, "end_line": 6},
        {"id": "s", "name": "select", "kind": "method", "container": "Element", "file": "src/Element.java",
         "line": 3, "end_line": 5},
        {"id": "u", "name": "Util", "kind": "class", "file": "src/Util.java", "line": 2, "end_line": 10},
        {"id": "m", "name": "meta", "kind": "method", "container": "Util", "file": "src/Util.java", "line": 7, "end_line": 9},
    ], "links": []}
    request = "Si cambio Element.select, ¿qué se rompe?"

    package = attach_source_evidence(tmp_path, query_intent(graph, request, "impact", 10), request, graph=graph)

    assert [row[:2] for row in package["direct_consumers"]["text_references"]] == [["meta", "src/Util.java:8"]]


def test_a_document_mention_is_not_counted_as_a_test():
    consumers = {"others": [["README.md", ":"], ["case1", "tests/a.test.js:2"], ["run", "lib/a.js:4"]]}

    _set_tests_apart({}, consumers)

    assert consumers["others"] == [["README.md", ":"], ["run", "lib/a.js:4"]]
    assert consumers["test_consumers"] == {"total": 1, "by_file": {"tests/a.test.js": 1}}
