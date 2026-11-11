"""JavaScript methods assigned to an object (`res.send = function send()`) and TypeScript `#private` calls."""
from graphtyn.core.ast_parser import ASTParser


def _graph(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    graph = ASTParser().scan_directory(root, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = {(nodes[link["source"]].get("name"), nodes[link["target"]].get("container"), nodes[link["target"]].get("name"),
              link.get("confidence")) for link in graph["links"] if link.get("label") == "llama"}
    return nodes, calls


def test_assigned_methods_are_symbols_of_their_object_and_calls_reach_them(tmp_path):
    nodes, calls = _graph(tmp_path, {
        "lib/response.js": "var res = Object.create(http.ServerResponse.prototype);\n"
                           "res.status = function status(code) { this.statusCode = code; return this; };\n"
                           "res.send = function send(body) { return this.status(200); };\n"
                           "function helper() {\n  const response = {};\n  response.json = () => 1;\n}\n"
                           "Math.random = () => 4;\nmodule.exports = res;\n",
        "test/res.send.js": "res.send('ok');\nconst response = {};\nresponse.text = async () => '';\n"})
    methods = {(node.get("container"), node.get("name")) for node in nodes.values() if node.get("kind") == "method"}

    assert methods == {("res", "status"), ("res", "send")}  # not a local patch, a global or a test stub
    assert ("send", "res", "status", "EXTRACTED") in calls
    # Another file reaches it only because its variable is also named `res`.
    assert any(call[1:] == ("res", "send", "INFERRED") for call in calls)


def test_private_members_are_called_by_their_hash_name(tmp_path):
    _nodes, calls = _graph(tmp_path, {"ky.ts": "export class Ky {\n  #delay(): number { return 1; }\n"
                                               "  retry(): number { return 0; }\n  run() { return this.#delay(); }\n}\n"})
    assert ("run", "Ky", "#delay", "EXTRACTED") in calls and not any(call[2] == "retry" for call in calls)


def test_every_name_of_an_alias_chain_is_the_method(tmp_path):
    # Express: `res.set = res.header = function header()`; its own methods call `this.set(...)`.
    nodes, calls = _graph(tmp_path, {"lib/response.js": "var res = Object.create(http.ServerResponse.prototype);\n"
                                     "res.set =\nres.header = function header(field, val) { return this; };\n"
                                     "res.type = function type(t) { return this.set('Content-Type', t); };\n"})
    methods = {(node.get("container"), node.get("name")) for node in nodes.values() if node.get("kind") == "method"}
    assert methods == {("res", "set"), ("res", "header"), ("res", "type")}
    assert ("type", "res", "set", "EXTRACTED") in calls


def test_a_recursive_self_call_does_not_fall_back_to_a_homonym(tmp_path):
    _nodes, calls = _graph(tmp_path, {
        "lib/application.js": "var app = exports = module.exports = {};\n"
                              "app.set = function set(setting, val) { if (val) { this.set('x', 1); } return this; };\n",
        "lib/response.js": "var res = Object.create(http.ServerResponse.prototype);\n"
                           "res.set = function header(field, val) { return this; };\n"})
    assert not any(call[0] == "set" and call[1] == "res" for call in calls)
