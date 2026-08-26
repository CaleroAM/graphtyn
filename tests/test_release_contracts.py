import re
import tomllib
from pathlib import Path

import graphtyn
from graphtyn.api.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_public_versions_are_synchronized_and_stable():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert metadata["version"] == graphtyn.__version__ == app.version
    assert re.fullmatch(r"\d+\.\d+\.\d+", graphtyn.__version__)
    assert "Development Status :: 5 - Production/Stable" in metadata["classifiers"]


def test_release_documents_and_workflows_exist():
    required = ["LICENSE", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md",
                "docs/release-checklist.md", ".github/workflows/ci.yml",
                ".github/workflows/release.yml", "docs/release-validation-0.6.0.md"]
    assert all((ROOT / item).is_file() for item in required)


def test_readme_does_not_advertise_unpublished_or_legacy_install_sources():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "CaleroAM/openclaw" not in readme
    assert "pipx install graphtyn" not in readme
    assert "pip install graphtyn" not in readme
    assert "aún no está publicado en PyPI" in readme


def test_ci_has_required_release_gates():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for version in ('"3.10"', '"3.11"', '"3.12"', '"3.13"'):
        assert version in ci
    for gate in ("python -m pytest -q", "python -m build", "smoke_frontend.py",
                 "test_security_leaks.py", "pip_audit", "docker build"):
        assert gate in ci


def test_dashboard_assets_are_declared_as_package_data():
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for asset in ("web/*.html", "web/*.css", "web/*.js", "web/*.svg", "web/js/*.js"):
        assert asset in metadata


def test_architecture_is_canonical_and_readme_has_compact_map():
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for concept in ("FastAPI", "Starlette", "Uvicorn", "Dos grafos", "SQLite",
                    "Empaquetado, despliegue y entrega", "0.6.0"):
        assert concept in architecture
    assert architecture.count("```mermaid") >= 5
    assert "## Arquitectura en un minuto" in readme
    assert "[ARCHITECTURE.md](ARCHITECTURE.md)" in readme


def test_serve_defaults_to_loopback_and_announces_dashboard_url():
    cli = (ROOT / "graphtyn" / "cli.py").read_text(encoding="utf-8")
    assert 'serve_p.add_argument("--host", default="127.0.0.1"' in cli
    assert 'print(f"   Dashboard: {scheme}://{dashboard_host}:{args.port}")' in cli
