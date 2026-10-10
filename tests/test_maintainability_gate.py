import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.check_maintainability import collect_metrics, load_baseline, violations


def _write_baseline(path: Path, hotspots: list[dict] | None = None) -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "limits": {"module": 1200, "class": 800, "function": 120},
        "hotspots": hotspots or [],
    }), encoding="utf-8")


def test_maintainability_gate_rejects_a_new_oversized_function(tmp_path):
    package = tmp_path / "graphtyn"
    package.mkdir()
    (package / "oversized.py").write_text(
        "def oversized():\n" + "    value = 1\n" * 121,
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"
    _write_baseline(baseline_path)

    failures = violations(collect_metrics(tmp_path), load_baseline(baseline_path))

    assert any("nuevo function sobredimensionado" in failure for failure in failures)


def test_maintainability_gate_allows_legacy_hotspot_to_shrink(tmp_path):
    package = tmp_path / "graphtyn"
    package.mkdir()
    source = package / "legacy.py"
    source.write_text("def legacy():\n" + "    value = 1\n" * 121, encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    _write_baseline(baseline_path, [{
        "key": "graphtyn/legacy.py::legacy",
        "kind": "function",
        "max_lines": 130,
    }])

    assert violations(collect_metrics(tmp_path), load_baseline(baseline_path)) == []
