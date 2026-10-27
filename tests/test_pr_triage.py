import subprocess

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.pr_triage import render_markdown, triage


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                   capture_output=True)


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "pricing.py").write_text(
        "def tax(amount):\n    return amount * 0.16\n\n\n"
        "def total(amount):\n    return amount + tax(amount)\n", encoding="utf-8")
    (root / "notes.py").write_text("def banner():\n    return 'v1'\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    for branch, path, old, new in (
        ("rate", "pricing.py", "amount * 0.16", "amount * 0.18"),
        ("caller", "pricing.py", "amount + tax(amount)", "round(amount + tax(amount), 2)"),
        ("banner-a", "notes.py", "'v1'", "'v2-a'"),
        ("banner-b", "notes.py", "'v1'", "'v2-b'"),
    ):
        _git(root, "checkout", "-q", "-b", branch, "main")
        text = (root / path).read_text(encoding="utf-8").replace(old, new)
        (root / path).write_text(text, encoding="utf-8")
        _git(root, "commit", "-qam", branch)
    _git(root, "checkout", "-q", "main")
    return root


def test_triage_finds_conflicts_coupling_and_orders_providers_first(tmp_path):
    root = _repo(tmp_path)
    graph = ASTParser().scan_directory(root)

    result = triage(root, graph, "main", ["caller", "rate", "banner-a", "banner-b"])

    pairs = {tuple(sorted(pair["branches"])): pair for pair in result["pairs"]}
    banners = pairs[("banner-a", "banner-b")]
    assert banners["risk"] == "high" and banners["textual_conflicts"] == ["notes.py"]
    coupling = pairs[("caller", "rate")]["semantic_coupling"]
    assert coupling == [{"changed_by": "rate", "symbol": "tax",
                         "callers_changed_by": "caller", "callers": ["total"]}]
    assert result["merge_order"].index("rate") < result["merge_order"].index("caller")
    assert subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True,
                          text=True).stdout == ""
    assert "Orden de merge sugerido" in render_markdown(result)
