import re
from pathlib import Path

from graphtyn.core.agent_installer import MEMORY_POLICY_END, MEMORY_POLICY_START, _managed_memory_policy

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def _frontmatter(path: Path) -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert match, f"{path} has no frontmatter"
    return dict(line.split(": ", 1) for line in match.group(1).splitlines())


def test_published_skills_have_portable_frontmatter_and_distinct_scopes():
    code = _frontmatter(SKILLS / "graphtyn" / "SKILL.md")
    memory = _frontmatter(SKILLS / "graphtyn-memory" / "SKILL.md")

    assert (code["name"], memory["name"]) == ("graphtyn", "graphtyn-memory")
    for meta in (code, memory):
        assert len(meta["description"]) <= 1024 and re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"])
    # Each description routes the other job to the other skill.
    assert "use graphtyn-memory" in code["description"] and "brain" not in code["description"]
    assert "use graphtyn)" in memory["description"] and "blast radius" not in memory["description"]


def test_code_skill_stays_lean_and_links_its_reference():
    text = (SKILLS / "graphtyn" / "SKILL.md").read_text(encoding="utf-8")

    assert len(text.splitlines()) <= 120
    assert MEMORY_POLICY_START not in text and "OpenClaw" not in text
    assert "<graphtyn-context>" in text
    for link in re.findall(r"\]\((references/[^)]+)\)", text):
        assert (SKILLS / "graphtyn" / link).is_file()


def test_memory_skill_carries_the_current_managed_policy():
    text = (SKILLS / "graphtyn-memory" / "SKILL.md").read_text(encoding="utf-8")
    block = text[text.index(MEMORY_POLICY_START) + len(MEMORY_POLICY_START):text.index(MEMORY_POLICY_END)]

    assert block.strip() == _managed_memory_policy().strip()


def test_repository_skills_match_the_packaged_copies():
    from graphtyn.core.agent_installer import packaged_skill_files

    packaged = packaged_skill_files()
    published = {path.relative_to(SKILLS).as_posix(): path.read_text(encoding="utf-8")
                 for path in SKILLS.rglob("*") if path.is_file()}
    assert published == packaged


def _install(root, platform="claude"):
    import json
    from graphtyn.core.agent_installer import install_agent
    install_agent(root, platform)
    return json.loads((root / ".graphtyn" / "agent-install.json").read_text())


def test_agent_install_writes_both_skills_and_updates_only_untouched_files(tmp_path, monkeypatch):
    from graphtyn.core import agent_installer
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    skills = root / ".claude" / "skills"

    manifest = _install(root)
    packaged = agent_installer.packaged_skill_files()
    for relative, text in packaged.items():
        assert (skills / relative).read_text(encoding="utf-8") == text
    assert set(manifest["skill_hashes"]) == {f".claude/skills/{relative}" for relative in packaged}

    # A new Graphtyn release refreshes untouched files and keeps edited ones.
    edited = skills / "graphtyn" / "references" / "change-workflow.md"
    edited.write_text("my own workflow\n", encoding="utf-8")
    changed = {**packaged, "graphtyn/SKILL.md": packaged["graphtyn/SKILL.md"] + "\nNew rule.\n",
               "graphtyn/references/change-workflow.md": "new upstream text\n"}
    monkeypatch.setattr(agent_installer, "packaged_skill_files", lambda: changed)
    _install(root)
    assert (skills / "graphtyn" / "SKILL.md").read_text(encoding="utf-8").endswith("New rule.\n")
    assert edited.read_text(encoding="utf-8") == "my own workflow\n"


def test_agent_install_migrates_the_legacy_combined_skill_with_a_backup(tmp_path, monkeypatch):
    from graphtyn.core.agent_installer import LEGACY_SKILL_HEAD, MEMORY_POLICY_START, packaged_skill_files
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    legacy = root / ".agents" / "skills" / "graphtyn" / "SKILL.md"
    legacy.parent.mkdir(parents=True)
    old = LEGACY_SKILL_HEAD + "\n# Graphtyn\n\nold combined policy\n"
    legacy.write_text(old, encoding="utf-8")
    custom = root / ".claude" / "skills" / "graphtyn" / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("---\nname: graphtyn\ndescription: mine\n---\n\nhand written\n", encoding="utf-8")

    _install(root, ["antigravity", "claude"])

    assert legacy.read_text(encoding="utf-8") == packaged_skill_files()["graphtyn/SKILL.md"]
    assert (root / ".graphtyn/legacy-skills/.agents/skills/graphtyn/SKILL.md").read_text(encoding="utf-8") == old
    # A skill the user wrote is not Graphtyn's to replace.
    assert custom.read_text(encoding="utf-8").endswith("hand written\n")
    assert MEMORY_POLICY_START in (root / ".claude/skills/graphtyn-memory/SKILL.md").read_text(encoding="utf-8")


def test_removing_an_integration_deletes_only_unedited_skills(tmp_path, monkeypatch):
    import json
    from graphtyn.core.project_integrations import remove_project_integrations
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    _install(root, ["antigravity", "claude"])
    edited = root / ".claude/skills/graphtyn-memory/SKILL.md"
    edited.write_text(edited.read_text(encoding="utf-8") + "\nmy note\n", encoding="utf-8")

    result = remove_project_integrations(root, ["claude"])

    assert ".claude/skills/graphtyn/SKILL.md" in result["removed_skills"]
    assert result["preserved_skills"] == [".claude/skills/graphtyn-memory/SKILL.md"]
    assert not (root / ".claude/skills/graphtyn").exists() and edited.is_file()
    # The other client's skills and their records are untouched.
    assert (root / ".agents/skills/graphtyn/SKILL.md").is_file()
    hashes = json.loads((root / ".graphtyn/agent-install.json").read_text())["skill_hashes"]
    assert hashes and all(key.startswith(".agents/") for key in hashes)


def test_copilot_gets_a_workspace_mcp_server_that_round_trips(tmp_path, monkeypatch):
    import json
    from graphtyn.core.project_integrations import project_integration_status, remove_project_integrations
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    (root / ".vscode").mkdir()
    (root / ".vscode/mcp.json").write_text(json.dumps({"servers": {"mine": {"type": "stdio", "command": "x"}}}))

    _install(root, "copilot")

    config = json.loads((root / ".vscode/mcp.json").read_text())
    alias = next(name for name in config["servers"] if name != "mine")
    assert config["servers"][alias] == {"type": "stdio", "command": "graphtyn", "cwd": "${workspaceFolder}",
                                        "args": ["mcp", "--tool-profile", "intent", "--path", "."]}
    assert (root / ".github/copilot-instructions.md").is_file()
    client = next(c for c in project_integration_status(root)["clients"] if c["platform"] == "copilot")
    assert client["configuration_present"] is True

    assert remove_project_integrations(root, ["copilot"])["removed"] == ["copilot"]
    assert json.loads((root / ".vscode/mcp.json").read_text()) == {"servers": {"mine": {"type": "stdio", "command": "x"}}}
