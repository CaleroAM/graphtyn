"""Project-scoped, reversible setup for popular coding agents."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

MEMORY_POLICY_START = "<!-- BEGIN GRAPHTYN MANAGED MEMORY POLICY -->"
MEMORY_POLICY_END = "<!-- END GRAPHTYN MANAGED MEMORY POLICY -->"
MEMORY_POLICY_VERSION = 3

PRODUCT_IDENTITY = """Graphtyn is an independent product, not a Graphify backend or compatibility alias. Never install `graphifyy`, run `graphify-mcp`, register either command under the `graphtyn` MCP name, or treat `graphify-out/` as a Graphtyn index. If the `graphtyn` executable is unavailable, stop and request the official Graphtyn package/repository; do not substitute another product. Verify integrations with `graphtyn --version` and the client's MCP inspection command.\n\n"""

POLICY = """# Graphtyn\n\nBefore any repository listing, broad search, or source read, run `graphtyn query-intent \"<complete task>\" --path .`. Use `overview` for repository summaries. If the result says `do_not_expand=true` and its `source_evidence` covers the request, answer from that bounded evidence without reopening files. For a named missing obligation, read only the returned line range or extend the same `context_id`; never open an entire file merely to reconfirm supplied evidence. Before and after risky edits run `graphtyn impact --base HEAD --head HEAD --path .`; read `GRAPHTYN_CHANGE_REPORT.md` and execute its verification plan. Treat EXTRACTED as evidence, verify INFERRED in source, and never state AMBIGUOUS as fact. Use `graphtyn review --ambiguities --path .` for unresolved candidates and `graphtyn validate-answer --answer @response.md --path .` before publishing important claims. Generate `GRAPHTYN_REPORT.md` with `graphtyn report --path .` when a persistent architecture report is requested.\n\nWhen shared memory is opted in, call MCP `memory_ingest_turn` once near the end of every substantive turn. Reuse the native conversation id as `external_session_id`, identify the actual client in `agent_id`, set `consent=true` and `compact=true`, and include only the user message plus a concise assistant outcome. Never include system prompts, hidden reasoning, secrets, or bulk tool output. Use `memory_context` in future sessions and pass the real identity as `requester_agent`. Obey `claim_policy`: only `verified_measured`/`verified_fact` support factual language; qualify `historical_only`/`proposed_only`; never settle `contested`, `stale`, or `unsupported`. Before comparisons call `memory_ingest_evidence` and preserve benchmark limitations. For conversations created before installation, run `graphtyn memory bootstrap` as a preview and require explicit user consent before `--apply --consent`; imported claims remain historical until verified.\n"""

POLICY = POLICY.replace("# Graphtyn\n\n", "# Graphtyn\n\n" + PRODUCT_IDENTITY, 1)
_old_memory_start = POLICY.index("When shared memory is opted in")
_old_memory_end = POLICY.index("Before comparisons call `memory_ingest_evidence`", _old_memory_start)
POLICY = (POLICY[:_old_memory_start]
          + "For shared project memory, follow the managed memory policy below. "
          + POLICY[_old_memory_end:])


def _managed_memory_policy() -> str:
    return files("graphtyn").joinpath("agent_memory_policy.md").read_text(encoding="utf-8").strip()


def merge_managed_memory_policy(current: str) -> str:
    """Update Graphtyn's managed memory block while preserving user-authored text."""
    start_count = current.count(MEMORY_POLICY_START)
    end_count = current.count(MEMORY_POLICY_END)
    block = f"{MEMORY_POLICY_START}\n{_managed_memory_policy()}\n{MEMORY_POLICY_END}"
    if not start_count and not end_count:
        suffix = "\n\n" if current and not current.endswith("\n\n") else ("\n" if current else "")
        return current + suffix + block + "\n"
    if start_count != 1 or end_count != 1:
        raise ValueError("Marcadores de política Graphtyn incompletos o duplicados; no se modificó el archivo")
    start = current.index(MEMORY_POLICY_START)
    end = current.index(MEMORY_POLICY_END, start) + len(MEMORY_POLICY_END)
    return current[:start] + block + current[end:]

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

""" + POLICY + "\n\n" + f"{MEMORY_POLICY_START}\n{_managed_memory_policy()}\n{MEMORY_POLICY_END}\n"


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
        addition = ""
        if "# Graphtyn" not in current:
            addition = POLICY
        elif "not a Graphify backend" not in current:
            addition = "## Graphtyn product identity\n\n" + PRODUCT_IDENTITY
        if addition:
            current += ("\n" if current and not current.endswith("\n") else "") + addition
        updated = merge_managed_memory_policy(current)
        if updated != (target.read_text(encoding="utf-8") if target.exists() else ""):
            target.write_text(updated, encoding="utf-8")
        written.append(str(target))

    if "antigravity" in selected:
        skill = root / ".agents" / "skills" / "graphtyn" / "SKILL.md"
        plugin_dir = root / ".agents" / "plugins" / "graphtyn"
        plugin = plugin_dir / "plugin.json"
        mcp_config = plugin_dir / "mcp_config.json"
        skill.parent.mkdir(parents=True, exist_ok=True)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        current_skill = skill.read_text(encoding="utf-8") if skill.exists() else ""
        updated_skill = merge_managed_memory_policy(current_skill) if current_skill else ANTIGRAVITY_SKILL
        skill.write_text(updated_skill, encoding="utf-8")
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
                                    "memory_policy_version": MEMORY_POLICY_VERSION,
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
