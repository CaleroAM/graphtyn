from graphtyn.core.ast_parser import ASTParser


def test_sql_schema_entities_are_first_class_nodes(tmp_path):
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE customers (id bigint);\nCREATE VIEW active_customers AS SELECT * FROM customers;\n",
        encoding="utf-8",
    )
    graph = ASTParser().scan_directory(tmp_path, respect_git=False)
    found = {(node["name"], node["kind"]) for node in graph["nodes"]}
    assert ("customers", "table") in found
    assert ("active_customers", "view") in found
