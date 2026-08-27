"""Project-scoped, reversible setup for popular coding agents."""

from __future__ import annotations

import json
from pathlib import Path

POLICY = """# Graphtyn\n\nBefore any repository listing, broad search, or source read, run `graphtyn query-intent \"<complete task>\" --path .`. Use `overview` for repository summaries. If the result says `do_not_expand=true` and its `source_evidence` covers the request, answer from that bounded evidence without reopening files. For a named missing obligation, read only the returned line range or extend the same `context_id`; never open an entire file merely to reconfirm supplied evidence. Before and after risky edits run `graphtyn impact --base HEAD --head HEAD --path .`; read `GRAPHTYN_CHANGE_REPORT.md` and execute its verification plan. Treat EXTRACTED as evidence, verify INFERRED in source, and never state AMBIGUOUS as fact. Use `graphtyn review --ambiguities --path .` for unresolved candidates and `graphtyn validate-answer --answer @response.md --path .` before publishing important claims. Generate `GRAPHTYN_REPORT.md` with `graphtyn report --path .` when a persistent architecture report is requested.\n\nWhen shared memory is opted in, call MCP `memory_ingest_turn` once near the end of every substantive turn. Reuse the native conversation id as `external_session_id`, identify the actual client in `agent_id`, set `consent=true` and `compact=true`, and include only the user message plus a concise assistant outcome. Never include system prompts, hidden reasoning, secrets, or bulk tool output. Use `memory_context` in future sessions and pass the real identity as `requester_agent`. Obey `claim_policy`: only `verified_measured`/`verified_fact` support factual language; qualify `historical_only`/`proposed_only`; never settle `contested`, `stale`, or `unsupported`. Before comparisons call `memory_ingest_evidence` and preserve benchmark limitations. For conversations created before installation, run `graphtyn memory bootstrap` as a preview and require explicit user consent before `--apply --consent`; imported claims remain historical until verified.\n"""

TARGETS = {
    "codex": Path("AGENTS.md"),
    "opencode": Path("AGENTS.md"),
    # Runtime placement (host, container or VPS) is configured separately.
    "openclaw": Path("AGENTS.md"),
    "hermes": Path("AGENTS.md"),
    "claude": Path("CLAUDE.md"),
    "cursor": Path(".cursor/rules/graphtyn.mdc"),
    "gemini": Path("GEMINI.md"),
    # Antigravity consumes GEMINI.md at project scope. The explicit name keeps
    # that client discoverable without exposing this implementation detail.
    "antigravity": Path("GEMINI.md"),
    "copilot": Path(".github/copilot-instructions.md"),
}

ANTIGRAVITY_SKILL = """---
name: graphtyn
description: Use Graphtyn before broad repository exploration to obtain compact, evidence-backed context, impact and shared project memory.
---

""" + POLICY


def install_agent(root: Path, platform: str | list[str], tool_profile: str = "intent") -> list[str]:
    if tool_profile not in {"intent", "memory", "full"}:
        raise ValueError("tool_profile debe ser intent, memory o full")
    requested = [platform] if isinstance(platform, str) else list(platform)
    selected = list(TARGETS) if requested == ["all"] else list(dict.fromkeys(requested))
    unknown = set(selected) - set(TARGETS)
    if unknown:
        raise ValueError(f"Plataforma desconocida: {', '.join(sorted(unknown))}")
    written: list[str] = []
    for relative in dict.fromkeys(TARGETS[name] for name in selected):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if "# Graphtyn" not in current:
            target.write_text(current + ("\n" if current and not current.endswith("\n") else "") + POLICY, encoding="utf-8")
        written.append(str(target))

    if "antigravity" in selected:
        skill = root / ".agents" / "skills" / "graphtyn" / "SKILL.md"
        plugin_dir = root / ".agents" / "plugins" / "graphtyn"
        plugin = plugin_dir / "plugin.json"
        mcp_config = plugin_dir / "mcp_config.json"
        skill.parent.mkdir(parents=True, exist_ok=True)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        skill.write_text(ANTIGRAVITY_SKILL, encoding="utf-8")
        plugin.write_text(json.dumps({
            "name": "graphtyn",
            "description": "Graphtyn code graph, impact analysis and MCP server",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        mcp_config.write_text(json.dumps({"mcpServers": {"graphtyn": {
            "command": "graphtyn", "args": ["mcp", "--tool-profile", tool_profile]
        }}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.extend(map(str, (skill, plugin, mcp_config)))

    written = list(dict.fromkeys(written))
    manifest = root / ".graphtyn" / "agent-install.json"
    manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps({"platforms": selected, "tool_profile": tool_profile,
                                    "files": written}, indent=2), encoding="utf-8")
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
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
      - run: pip install .
      - run: graphtyn ci-check --base origin/${{{{ github.base_ref }}}} --max-risk {max_risk} --output graphtyn-pr.md --path .
      - uses: actions/upload-artifact@v7
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
