import json
import re
import shutil
import subprocess

import pytest

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.html_export import graph_payload, render_html


def _repo(tmp_path):
    (tmp_path / "svc.py").write_text(
        "# WHY: keep </script> safe in embedded data\n"
        "def core():\n    return 1\n\n"
        "def a():\n    return core()\n\n"
        "def b():\n    return core() + a()\n", encoding="utf-8")
    return ASTParser().scan_directory(tmp_path, respect_git=False)


def test_html_is_offline_and_escapes_embedded_data(tmp_path):
    page = render_html(_repo(tmp_path), "demo <repo>")

    assert not re.search(r"""(?:src|href)=["']https?://""", page)
    assert "demo &lt;repo&gt;" in page
    data = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1)
    assert "</script>" not in data
    payload = json.loads(data)
    names = {node["n"]: node for node in payload["nodes"]}
    assert {"core", "a", "b"} <= set(names)
    assert names["core"]["w"] == ["keep </script> safe in embedded data"]


def test_node_limit_reports_omitted_symbols(tmp_path):
    payload = graph_payload(_repo(tmp_path), node_limit=1)
    assert len(payload["nodes"]) == 1 and payload["omitted_symbols"] == payload["total_symbols"] - 1
    assert payload["nodes"][0]["n"] == "core"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_embedded_script_is_valid_javascript(tmp_path):
    page = render_html(_repo(tmp_path), "demo")
    script = re.findall(r"<script>(.*?)</script>", page, re.S)[0]
    source = tmp_path / "page.js"
    source.write_text(script, encoding="utf-8")
    assert subprocess.run(["node", "--check", str(source)], capture_output=True).returncode == 0
