import json
import subprocess

import pytest

from graphtyn.api import main as api_main
from graphtyn.core.benchmark import run_benchmark
from graphtyn.core.impact import analyze_impact
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.tree_sitter_backend import parse_file
from graphtyn.core.external_benchmark import score_graphify
from graphtyn.core.change_analyst import classify_intent, query_intent


def test_overview_intent_builds_diverse_repository_profile():
    graph = {
        "nodes": [
            {"id": "file:README.md", "name": "README.md", "kind": "file", "details": "README.md", "degree": 2},
            {"id": "file:package.json", "name": "package.json", "kind": "file", "details": "package.json", "degree": 1},
            {"id": "file:src/main.ts", "name": "main.ts", "kind": "file", "details": "src/main.ts", "degree": 2},
            {"id": "dir:src", "name": "src", "kind": "module", "details": "Carpeta: src", "degree": 4},
            {"id": "symbol:src/App.ts:App", "name": "App", "kind": "class", "file": "src/App.ts", "degree": 8},
            {"id": "symbol:tests/App.test.ts:test", "name": "test", "kind": "method", "file": "tests/App.test.ts", "degree": 20},
        ],
        "links": [],
    }
    request = "Utiliza Graphtyn y dime de qué trata el proyecto/repositorio"
    assert classify_intent(request) == "overview"
    result = query_intent(graph, request, "auto", 10)
    assert result["planner"] == "overview-v1"
    assert result["complete_for"] == ["overview"]
    assert result["do_not_expand"] is True
    assert result["project_profile"]["technologies"] == ["TypeScript"]
    assert result["project_profile"]["entry_points"] == ["src/main.ts"]
    assert "package.json" in result["project_profile"]["manifests"]
    assert result["project_profile"]["read_first"][:2] == ["README.md", "package.json"]
    assert "tests" not in result["project_profile"]["subsystems"]
    assert not any("tests/" in str(node.get("file") or "") for node in result["nodes"])


@pytest.mark.parametrize("module,filename,source,expected", [
    ("tree_sitter_python", "sample.py", "class Service:\n    def run(self):\n        helper()\n", {"Service", "run"}),
    ("tree_sitter_java", "Service.java", "class Service { void run() { helper(); } }", {"Service", "run"}),
    ("tree_sitter_go", "service.go", "package demo\nfunc Run() { helper() }\n", {"Run"}),
    ("tree_sitter_rust", "service.rs", "struct Service;\nfn run() { helper(); }\n", {"Service", "run"}),
])
def test_extended_tree_sitter_languages(tmp_path, module, filename, source, expected):
    pytest.importorskip("tree_sitter")
    pytest.importorskip(module)
    path = tmp_path / filename
    path.write_text(source, encoding="utf-8")
    result = parse_file(path, filename)
    assert result and expected <= {symbol["name"] for symbol in result["symbols"]}


def test_csharp_members_are_typed_graph_entities(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    source = tmp_path / "AuctionService.cs"
    source.write_text("""
public class AuctionService {
    private int _currentBid;
    public string Winner { get; private set; }
    public event System.Action<int> BidChanged;
}
""", encoding="utf-8")
    parsed = parse_file(source, source.name)
    by_name = {member["name"]: member for member in parsed["members"]}
    assert by_name["_currentBid"]["kind"] == "field"
    assert by_name["Winner"]["kind"] == "property"
    assert by_name["BidChanged"]["kind"] == "event"
    graph = ASTParser().scan_directory(tmp_path)
    graph_members = {node["name"]: node for node in graph["nodes"] if node.get("kind") in {"field", "property", "event"}}
    assert graph_members["_currentBid"]["member_type"] == "int"
    assert graph_members["BidChanged"]["container"] == "AuctionService"
    assert any(link["label"] == "declara" and link["target"] == graph_members["Winner"]["id"] for link in graph["links"])


def test_change_analyst_returns_grounded_targets_state_and_contracts(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "AuctionService.cs").write_text("""
public class AuctionService {
    private int _currentBid;
    public int CurrentBid { get; private set; }
    public event System.Action<int> BidChanged;
    public void PlaceBid(int amount) { CurrentBid = amount; BidChanged?.Invoke(amount); }
}
""", encoding="utf-8")
    from graphtyn.core.change_analyst import analyze_change
    graph = ASTParser().scan_directory(tmp_path)
    result = analyze_change(graph, "Cambiar AuctionService CurrentBid y el evento BidChanged")
    assert result["plan"]["confidence"] == "high"
    assert result["plan"]["target_ids"]
    assert result["plan"]["state"]
    assert result["plan"]["contracts"]
    place_bid = next(node for node in result["nodes"] if node.get("name") == "PlaceBid")
    assert {op["kind"] for op in place_bid["operations"]} >= {"assign", "call"}
    assert result["plan"]["risks"]


def test_csharp_method_operations_preserve_external_calls_and_returns(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "Bindings.cs").write_text("""
public static class Bindings {
  public static object Register(IServiceCollection services) {
    services.AddScoped<IRepository, EfRepository>()
            .AddScoped<IQuery, SqlQuery>();
    return services;
  }
}
""", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path)
    register = next(node for node in graph["nodes"] if node.get("name") == "Register")
    operation_text = " ".join(op["text"] for op in register["operations"])
    assert "AddScoped<IRepository, EfRepository>" in operation_text
    assert "AddScoped<IQuery, SqlQuery>" in operation_text
    assert any(op["kind"] == "return" and op["line"] == 6 for op in register["operations"])


def test_query_intent_filters_bindings_into_one_shot_package(tmp_path):
    pytest.importorskip("tree_sitter_c_sharp")
    (tmp_path / "Bindings.cs").write_text("""
public static class Bindings {
  public static void AddInfrastructureServices(IServiceCollection services) {
    services.AddScoped<IRepository, EfRepository>();
    services.AddScoped<IQuery, SqlQuery>();
  }
}
""", encoding="utf-8")
    from graphtyn.core.change_analyst import query_intent
    result = query_intent(ASTParser().scan_directory(tmp_path), "Audita bindings AddScoped", "auto", 6)
    assert result["intent"] == "bindings"
    assert result["complete_for"] == ["bindings"]
    assert result["do_not_expand"] is True
    text = json.dumps(result["nodes"])
    assert "IRepository" in text and "IQuery" in text
    assert len(result["nodes"]) <= 6


def test_query_intent_keeps_exact_python_component_without_flow_markers(tmp_path):
    pytest.importorskip("tree_sitter_python")
    (tmp_path / "sessions.py").write_text("""
class SessionMiddleware:
    async def __call__(self, scope, receive, send):
        data = self.signer.unsign(scope["cookie"])
        await self.app(scope, receive, send)
""", encoding="utf-8")
    from graphtyn.core.change_analyst import query_intent
    result = query_intent(
        ASTParser().scan_directory(tmp_path),
        "Audita el ciclo completo de SessionMiddleware y su firma",
        "flow",
        6,
    )
    assert any(node.get("container") == "SessionMiddleware" for node in result["nodes"])


def test_tree_sitter_python_empty_file_does_not_crash(tmp_path):
    pytest.importorskip("tree_sitter_python")
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path)
    assert graph["metadata"]["structural_parser"]


def test_laravel_routes_connect_tsx_controller_request_model_and_event(tmp_path):
    pytest.importorskip("tree_sitter_php")
    (tmp_path / "routes").mkdir()
    (tmp_path / "app" / "Http" / "Controllers").mkdir(parents=True)
    (tmp_path / "app" / "Http" / "Requests").mkdir(parents=True)
    (tmp_path / "app" / "Models").mkdir(parents=True)
    (tmp_path / "app" / "Events").mkdir(parents=True)
    (tmp_path / "resources" / "js" / "pages").mkdir(parents=True)
    (tmp_path / "routes" / "web.php").write_text("""<?php
Route::post('proposals', [ProposalController::class, 'store'])->name('proposals.store');
""", encoding="utf-8")
    (tmp_path / "app" / "Http" / "Controllers" / "ProposalController.php").write_text("""<?php
class ProposalController {
 public function store(StoreProposalRequest $request) {
  $proposal = new Proposal();
  $proposal->save();
  ProposalCreated::dispatch($proposal);
 }
}
""", encoding="utf-8")
    (tmp_path / "app" / "Http" / "Requests" / "StoreProposalRequest.php").write_text("<?php class StoreProposalRequest {}", encoding="utf-8")
    (tmp_path / "app" / "Models" / "Proposal.php").write_text("<?php class Proposal {}", encoding="utf-8")
    (tmp_path / "app" / "Events" / "ProposalCreated.php").write_text("<?php class ProposalCreated {}", encoding="utf-8")
    (tmp_path / "resources" / "js" / "pages" / "Create.tsx").write_text("router.post(route('proposals.store'));", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path)
    labels = {link["label"] for link in graph["links"]}
    assert {"despacha", "invoca ruta", "valida con", "crea", "despacha evento"} <= labels
    store = next(node for node in graph["nodes"] if node.get("container") == "ProposalController" and node.get("name") == "store")
    assert store["parser"] == "tree-sitter"
    assert {op["kind"] for op in store["operations"]} >= {"new", "call"}


def test_benchmark_ground_truth(tmp_path):
    (tmp_path / "service.py").write_text("class Service:\n    def run(self):\n        pass\n", encoding="utf-8")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"expected_symbols": [
        {"file": "service.py", "name": "Service", "kind": "class"},
        {"file": "service.py", "name": "run", "kind": "method"},
    ]}), encoding="utf-8")
    result = run_benchmark(tmp_path, truth, tmp_path / "cache.json")
    assert result["ground_truth"]["symbol_recall"] == 1
    assert result["quality"]["dangling_edges"] == 0


def test_benchmark_scores_positive_and_forbidden_edges(tmp_path):
    (tmp_path / "a.py").write_text("def helper():\n    return 1\ndef run():\n    return helper()\n", encoding="utf-8")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({
        "expected_edges": [{"target": "symbol:a.py:helper", "label": "llama"}],
        "forbidden_edges": [{"target": "symbol:a.py:missing", "label": "llama"}],
    }), encoding="utf-8")
    result = run_benchmark(tmp_path, truth, tmp_path / "cache.json")
    assert result["ground_truth"]["edges"]["precision"] == 1
    assert result["ground_truth"]["edges"]["recall"] == 1


def test_pr_impact_reports_risk_and_changed_file(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "service.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    source.write_text("def run():\n    return 2\n", encoding="utf-8")
    report = analyze_impact(tmp_path, ASTParser().scan_directory(tmp_path), None)
    assert report["changed_files"] == ["service.py"]
    assert report["risk"]["score"] > 0
    assert "conflict_detection" in report


def test_symbol_level_diff_impacts_callers_not_every_symbol(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import helper\ndef run():\n    return helper()\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py", "b.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=True)
    report = analyze_impact(tmp_path, graph)
    assert {symbol["name"] for symbol in report["changed_symbols"]} == {"helper"}
    impacted_names = {item["node"].get("name") for item in report["impacted_nodes"]}
    assert "run" in impacted_names


def test_http_mcp_requires_token_and_serves_tools(monkeypatch):
    monkeypatch.delenv("GRAPHTYN_MCP_TOKEN", raising=False)
    disabled = api_main.mcp_http({"id": 1, "method": "tools/list"}, authorization=None)
    assert disabled.status_code == 503
    monkeypatch.setenv("GRAPHTYN_MCP_TOKEN", "secret")
    denied = api_main.mcp_http({"id": 1, "method": "tools/list"}, authorization="Bearer wrong")
    assert denied.status_code == 401
    allowed = api_main.mcp_http({"id": 1, "method": "tools/list"}, authorization="Bearer secret")
    body = json.loads(allowed.body)
    assert allowed.status_code == 200
    assert "graph_pr_impact" in {tool["name"] for tool in body["result"]["tools"]}
    assert "graph_context_bundle" in {tool["name"] for tool in body["result"]["tools"]}
    assert "graph_analyze_change" in {tool["name"] for tool in body["result"]["tools"]}


def test_semantic_media_edges_include_auditable_evidence():
    nodes = [
        {"id": "file:a.png", "name": "mapa.png", "kind": "image", "details": "Mapa interactivo del museo con rutas de visitantes"},
        {"id": "file:b.pdf", "name": "rutas.pdf", "kind": "doc", "details": "Documento del museo con mapa de rutas para visitantes"},
    ]
    graph = api_main.generate_semantic_graph({"nodes": nodes, "links": [], "metadata": {"path": "/tmp/demo"}})
    inferred = [link for link in graph["links"] if link.get("confidence") == "INFERRED"]
    assert inferred and inferred[0]["evidence"]["shared_terms"]
    assert inferred[0]["explanation"]


def test_graphify_adapter_scores_same_edge_truth(tmp_path):
    graph = tmp_path / "graph.json"
    truth = tmp_path / "truth.json"
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "a_run", "label": ".run()", "source_file": "a.py"},
            {"id": "b_help", "label": ".help()", "source_file": "b.py"},
        ],
        "edges": [{"source": "a_run", "target": "b_help", "relation": "calls", "source_location": "L4"}],
    }))
    truth.write_text(json.dumps({
        "expected_edges": [{"source": "symbol:a.py:run", "target": "symbol:b.py:help", "line": 4}],
        "forbidden_edges": [{"source": "symbol:b.py:help", "target": "symbol:a.py:run", "line": 4}],
    }))
    result = score_graphify(graph, truth)
    assert result["ground_truth"]["f1"] == 1


def test_intent_prioritizes_named_component_file_and_security_operations():
    graph = {
        "nodes": [
            {"id": "class:session", "name": "SessionMiddleware", "kind": "class", "file": "middleware/sessions.py", "degree": 3},
            {"id": "method:call", "name": "__call__", "container": "SessionMiddleware", "kind": "method",
             "file": "middleware/sessions.py", "line": 39, "degree": 2, "operations": [
                 {"kind": "call", "name": "unsign", "line": 50, "text": "self.signer.unsign(data, max_age=self.max_age)"},
                 {"kind": "catch", "name": "BadSignature", "line": 53, "text": "except BadSignature"},
             ]},
            {"id": "method:send", "name": "send_wrapper", "container": "SessionMiddleware", "kind": "method",
             "file": "middleware/sessions.py", "line": 58, "degree": 2, "operations": [
                 {"kind": "call", "name": "append", "line": 75, "text": "headers.append('Set-Cookie', header_value)"},
             ]},
            {"id": "method:delete", "name": "delete", "kind": "method", "file": "testclient.py", "line": 600,
             "degree": 30, "operations": [{"kind": "call", "name": "request", "line": 601, "text": "request('DELETE')"}]},
        ],
        "links": [],
    }
    result = query_intent(graph, "Audita SessionMiddleware: verificación de firma inválida y borrado de cookie", "flow", 3)
    selected = [node["id"] for node in result["nodes"]]
    assert "method:call" in selected and "method:send" in selected
    assert "method:delete" not in selected
