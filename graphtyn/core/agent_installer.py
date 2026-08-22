"""Project-scoped, reversible setup for popular coding agents."""

from __future__ import annotations

import json
from pathlib import Path

POLICY = """# Graphtyn\n\nBefore broad exploration, run `graphtyn query-intent \"<complete task>\" --path .`. Use `overview` for repository summaries. Before and after risky edits run `graphtyn impact --base HEAD --head HEAD --path .`; read `GRAPHTYN_CHANGE_REPORT.md` and execute its verification plan. Treat EXTRACTED as evidence, verify INFERRED in source, and never state AMBIGUOUS as fact. Use `graphtyn review --ambiguities --path .` for unresolved candidates and `graphtyn validate-answer --answer @response.md --path .` before publishing important claims. Generate `GRAPHTYN_REPORT.md` with `graphtyn report --path .` when a persistent architecture report is requested.\n"""

TARGETS = {
    "codex": Path("AGENTS.md"),
    "opencode": Path("AGENTS.md"),
    "claude": Path("CLAUDE.md"),
    "cursor": Path(".cursor/rules/graphtyn.mdc"),
    "gemini": Path("GEMINI.md"),
    "copilot": Path(".github/copilot-instructions.md"),
}


def install_agent(root: Path, platform: str) -> list[str]:
    selected = list(TARGETS) if platform == "all" else [platform]
    unknown = set(selected) - set(TARGETS)
    if unknown:
        raise ValueError(f"Plataforma desconocida: {', '.join(sorted(unknown))}")
    written = []
    for name in selected:
        target = root / TARGETS[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if "# Graphtyn" not in current:
            target.write_text(current + ("\n" if current and not current.endswith("\n") else "") + POLICY, encoding="utf-8")
        written.append(str(target))
    manifest = root / ".graphtyn" / "agent-install.json"
    manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps({"platforms": selected, "files": written}, indent=2), encoding="utf-8")
    return written


def install_ci(root: Path, platform: str, max_risk: str = "high") -> Path:
    if platform == "github":
        target = root / ".github" / "workflows" / "graphtyn.yml"
        content = f"""name: Graphtyn impact
on:
  pull_request:
permissions:
  contents: read
jobs:
  impact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install .
      - run: graphtyn ci-check --base origin/${{{{ github.base_ref }}}} --max-risk {max_risk} --output graphtyn-pr.md --path .
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: graphtyn-pr-impact
          path: graphtyn-pr.md
"""
    elif platform == "gitlab":
        target = root / ".gitlab" / "graphtyn-ci.yml"
        content = f"""graphtyn-impact:
  image: python:3.12
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  before_script:
    - pip install .
  script:
    - graphtyn ci-check --base origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME --max-risk {max_risk} --output graphtyn-pr.md --path .
  artifacts:
    when: always
    paths: [graphtyn-pr.md]
"""
    else:
        raise ValueError("CI soportado: github o gitlab")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
