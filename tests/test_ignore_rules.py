from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.ignore_rules import IgnoreRules


def test_gitignore_subset_semantics():
    rules = IgnoreRules([
        "# generated code", "", "*.generated.py", "/fixtures/", "docs/**/draft_*.md",
        "legacy/", "!legacy/keep.py", "tmp?",
    ])

    assert rules.ignored("app/models/user.generated.py")
    assert rules.ignored("fixtures/data.py") and not rules.ignored("app/fixtures/data.py")
    assert rules.ignored("docs/a/b/draft_x.md") and not rules.ignored("docs/final.md")
    assert rules.ignored("src/legacy/old.py") and not rules.ignored("legacy/keep.py")
    assert rules.ignored("tmp1/x.py") and not rules.ignored("tmp12/x.py")
    assert not rules.ignored("legacy.py")
    assert not IgnoreRules()


def test_scan_skips_paths_listed_in_graphtynignore(tmp_path):
    (tmp_path / "app.py").write_text("def kept():\n    return 1\n", encoding="utf-8")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "client.py").write_text("def generated_fn():\n    return 2\n", encoding="utf-8")
    (tmp_path / ".graphtynignore").write_text("generated/\n", encoding="utf-8")

    names = {node.get("name") for node in ASTParser().scan_directory(tmp_path, respect_git=False)["nodes"]}

    assert "kept" in names
    assert "generated_fn" not in names
