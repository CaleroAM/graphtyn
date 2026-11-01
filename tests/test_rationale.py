from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.change_analyst import query_intent
from graphtyn.core.rationale import attach_rationale, extract_rationale
from graphtyn.mcp_server import evidence_result


SOURCE = """import time

# WHY: the upstream API rate-limits bursts, so retries back off
# exponentially instead of failing the whole batch.
def fetch_with_retry(client, url):
    for attempt in range(5):
        try:
            return client.get(url)
        except TimeoutError:
            # NOTE: jitter avoids synchronized retries
            time.sleep(2 ** attempt)

def parse(raw):
    return raw  # implements RFC 7231 date parsing
"""


def test_extracts_marked_comments_with_continuations_and_citations():
    entries = extract_rationale(SOURCE)
    assert [(item["line"], item["marker"]) for item in entries] == [(3, "WHY"), (10, "NOTE"), (14, "RFC-7231")]
    assert entries[0]["text"] == ("the upstream API rate-limits bursts, so retries back off "
                                  "exponentially instead of failing the whole batch.")
    assert extract_rationale("// HACK: work around the vendor bug\nint x;")[0]["marker"] == "HACK"
    assert extract_rationale("x = 1  # not a marker WHY: here\n") == []


def test_rationale_attaches_to_documented_symbol_and_skips_prose(tmp_path):
    (tmp_path / "svc.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "README.md").write_text("# NOTE: a heading, not a comment\n", encoding="utf-8")

    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    by_name = {node.get("name"): node for node in graph["nodes"]}
    assert [item["marker"] for item in by_name["fetch_with_retry"]["rationale"]] == ["WHY", "NOTE"]
    assert by_name["parse"]["rationale"][0]["marker"] == "RFC-7231"
    assert "rationale" not in by_name["README.md"]
    assert graph["metadata"]["rationale_comments"] == 3


def test_file_level_rationale_without_owner_symbol():
    nodes = [{"id": "file:config.yml", "name": "config.yml", "kind": "file"}]
    assert attach_rationale(nodes, {"config.yml": "# DECISION: keep two replicas for failover\nreplicas: 2\n"}) == 1
    assert nodes[0]["rationale"][0]["text"] == "keep two replicas for failover"


def test_compact_package_exposes_why(tmp_path):
    (tmp_path / "svc.py").write_text(SOURCE, encoding="utf-8")
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)

    package = evidence_result(query_intent(graph, "por qué fetch_with_retry reintenta", "flow", 4), max_nodes=4)

    why = [entity["why"] for entity in package["entities"].values() if entity.get("name") == "fetch_with_retry"]
    assert why and why[0][0][1] == "WHY"
